"""
Phone notifications by Web Push: the home-screen app's "you have something to look at".

Email stays the record and the fallback. A push is a nudge: it may not arrive (phone
off, permission withdrawn, iPhone app not on the Home Screen), so nothing depends on it
and `send` never raises.

HOW A PUSH TRAVELS
    The phone's browser gives the page a subscription: an `endpoint` URL at Apple,
    Google or Mozilla, plus two keys (p256dh, auth). The page POSTs it to us and we
    keep it in Push_Subs, one row per device per person per building. To notify, we
    encrypt the message for that device (RFC 8291, aes128gcm) and POST it to the
    endpoint, signed with our VAPID key (RFC 8292) so the push service knows it's us.

WHY NO pywebpush
    Catalyst's deploy installs requirements with `--only-binary=:all:` for Linux, and
    pywebpush depends on http-ece, which ships no wheel, so the deploy fails. This
    module does the same two steps with `cryptography` alone (needs
    `cryptography==43.0.3` in requirements.txt: the newest with a manylinux2014 wheel
    for Python 3.9). Checked against RFC 8291's own worked example in the tests.

KEYS (env vars, never in git)
    VAPID_PUBLIC_KEY   base64url, 65-byte uncompressed P-256 point. The page needs it too
                       (GET /push/key) as the subscription's applicationServerKey.
    VAPID_PRIVATE_KEY  base64url, the 32-byte private number.
    VAPID_SUBJECT      mailto: address push services can write to (Apple insists on one).

TABLE Push_Subs
    User_Id bigint · Building_Id bigint · Endpoint text · Sub_Keys text (JSON
    {"p256dh", "auth"}) · User_Agent varchar(255). "Keys" is a reserved word in the
    Data Store, hence Sub_Keys. Every read is filtered by building.

FAILURES
    An endpoint answering 404 or 410 means the person uninstalled, cleared or turned
    off notifications: the row is deleted quietly, that's normal. Anything else that
    stops a push is one `failures.log(db, "push", ...)` row per send, naming only the
    push service's host and the status, never an address or the message.
"""

import base64
import json
import logging
import os
import struct
import time
from urllib.parse import urlparse

import failures
import store
from errors import bad

logger = logging.getLogger("bodycorp_api.push")

PUSH_SUBS = getattr(store, "PUSH_SUBS", "Push_Subs")
GONE = (404, 410)
OK = (200, 201, 202)
TTL = 24 * 60 * 60            # a day: after that the news is stale, email has it anyway
RECORD_SIZE = 4096
PAYLOAD_MAX = 3000            # bytes of JSON; push services take ~4 KB after encryption
TITLE_MAX, BODY_MAX = 80, 240
TIMEOUT = 8
MAX_SUBS_PER_USER = 10        # a person's phones and computers in one building
DEFAULT_ICON = "icons/product-192.png"
DEFAULT_BADGE = "icons/product-badge-96.png"


# ---------- base64url ----------

def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(text):
    text = str(text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------- keys ----------

def public_key():
    """The VAPID public key for the page (GET /push/key), or '' when push isn't set up."""
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def configured():
    return bool(public_key() and os.environ.get("VAPID_PRIVATE_KEY", "").strip())


def _private_key(raw_b64u):
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.derive_private_key(int.from_bytes(unb64u(raw_b64u), "big"), ec.SECP256R1())


def _point(public):
    from cryptography.hazmat.primitives import serialization
    return public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def make_vapid_keys():
    """A new (public, private) pair, both base64url. Run once per product, keep in env vars."""
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    return b64u(_point(key.public_key())), b64u(key.private_numbers().private_value.to_bytes(32, "big"))


# ---------- RFC 8291: encrypt one message for one device ----------

def _hkdf(salt, ikm, info, length):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(plaintext, p256dh, auth, _server_key=None, _salt=None):
    """
    The aes128gcm body for one device: salt | record size | key id | ciphertext.
    `_server_key` and `_salt` are for the RFC's worked example only; normally fresh each time.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ua_public = unb64u(p256dh)
    auth_secret = unb64u(auth)
    server_key = _server_key or ec.generate_private_key(ec.SECP256R1())
    salt = _salt or os.urandom(16)
    as_public = _point(server_key.public_key())

    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = server_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)   # \x02 = last (only) record
    header = salt + struct.pack("!I", RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


# ---------- RFC 8292: VAPID signature ----------

def vapid_header(endpoint, now=None):
    """The Authorization header value for a push to `endpoint`, valid 12 hours."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    parts = urlparse(endpoint)
    claims = {"aud": "{}://{}".format(parts.scheme, parts.netloc),
              "exp": int(now if now is not None else time.time()) + 12 * 60 * 60,
              "sub": os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:support@barebaysidelabs.com"}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = "{}.{}".format(head, body).encode("ascii")
    der = _private_key(os.environ["VAPID_PRIVATE_KEY"]).sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    token = "{}.{}".format(signing_input.decode("ascii"), b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big")))
    return "vapid t={}, k={}".format(token, public_key())


# ---------- sending ----------

def post(endpoint, headers, data):
    """POST one encrypted push. Returns the HTTP status. Tests replace this (or pass sender=)."""
    import requests
    return requests.post(endpoint, headers=headers, data=data, timeout=TIMEOUT).status_code


def _keys(row):
    try:
        keys = json.loads(row.get("Sub_Keys") or "{}")
    except (TypeError, ValueError):
        return None
    return keys if isinstance(keys, dict) and keys.get("p256dh") and keys.get("auth") else None


def message(building, title, body, url):
    """The JSON the service worker shows. Short: the lock screen cuts the rest off anyway."""
    brand = (building or {}).get("brand") or {}
    data = {"title": str(title or "")[:TITLE_MAX], "body": " ".join(str(body or "").split())[:BODY_MAX],
            "url": str(url or "portal.html?b={}".format((building or {}).get("slug") or "")),
            "icon": brand.get("app_icon") or DEFAULT_ICON, "badge": brand.get("app_badge") or DEFAULT_BADGE,
            "tag": (building or {}).get("slug") or "portal"}
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    while len(raw) > PAYLOAD_MAX and data["body"]:
        data["body"] = data["body"][:-40]
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return raw


def subscriptions(db, building, user_ids):
    """Every device of these people in this building, one per endpoint."""
    seen, rows = set(), []
    for uid in {store.as_id(u) for u in (user_ids or [])} - {None}:
        for row in db.find(PUSH_SUBS, {"Building_Id": int(building["id"]), "User_Id": uid}):
            if row.get("Endpoint") and row["Endpoint"] not in seen:
                seen.add(row["Endpoint"])
                rows.append(row)
    return rows


def send(db, building, user_ids, title, body, url, sender=None):
    """
    Notify these people's devices in this building. Returns {"sent", "removed", "failed"}.
    Never raises: a push that doesn't go must never break the action that caused it.
    """
    result = {"sent": 0, "removed": 0, "failed": 0}
    try:
        rows = subscriptions(db, building, user_ids)
        if not rows:
            return result
        if not configured():
            failures.log(db, "push", "Phone notifications aren't set up (VAPID keys missing); "
                                     "{} device(s) not told.".format(len(rows)), building["id"])
            result["failed"] = len(rows)
            return result
        payload = message(building, title, body, url)
        deliver = sender or post
        problems = []
        for row in rows:
            endpoint = row["Endpoint"]
            host = urlparse(endpoint).netloc or "?"
            keys = _keys(row)
            if not keys:
                db.delete(PUSH_SUBS, row["ROWID"])
                result["removed"] += 1
                continue
            try:
                headers = {"TTL": str(TTL), "Urgency": "normal", "Content-Encoding": "aes128gcm",
                           "Content-Type": "application/octet-stream",
                           "Authorization": vapid_header(endpoint)}
                status = deliver(endpoint, headers, encrypt(payload, keys["p256dh"], keys["auth"]))
            except Exception as exc:  # noqa: BLE001 — network, bad keys: count it, carry on
                problems.append("{} {}".format(host, type(exc).__name__))
                result["failed"] += 1
                continue
            if status in OK:
                result["sent"] += 1
            elif status in GONE:
                db.delete(PUSH_SUBS, row["ROWID"])
                result["removed"] += 1
            else:
                problems.append("{} {}".format(host, status))
                result["failed"] += 1
        if problems:
            failures.log(db, "push", "Phone notification not delivered ({} of {}): {}".format(
                len(problems), len(rows), "; ".join(problems)[:500]), building["id"])
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.exception("push send failed")
        failures.log(db, "push", "Phone notifications crashed: {}".format(type(exc).__name__),
                     (building or {}).get("id"))
    return result


def user_ids_for(db, emails):
    """The user ids behind these addresses (the app picks recipients by email). Unknown ones are skipped."""
    ids = []
    for email in {str(e or "").strip().lower() for e in (emails or [])} - {""}:
        for row in db.find(store.USERS, {"Email": email}):
            ids.append(str(row["ROWID"]))
    return ids


def send_to_emails(db, building, emails, title, body, url, sender=None):
    """`send` for code that already has the email recipients: put it beside the mailer.send call."""
    try:
        ids = user_ids_for(db, emails)
    except Exception:  # noqa: BLE001 — never break the caller
        logger.exception("push recipients lookup failed")
        return {"sent": 0, "removed": 0, "failed": 0}
    return send(db, building, ids, title, body, url, sender=sender)


# ---------- the page's subscription (for POST/DELETE /push/subscribe) ----------

def _clean(body):
    sub = body.get("subscription") if isinstance(body.get("subscription"), dict) else body
    endpoint = str(sub.get("endpoint") or "").strip()
    keys = sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
    if not endpoint.startswith("https://") or len(endpoint) > 2000:
        raise bad("That notification address isn't valid.")
    try:
        p256dh, auth = unb64u(keys.get("p256dh")), unb64u(keys.get("auth"))
    except (TypeError, ValueError):
        raise bad("That notification key isn't valid.")
    if len(p256dh) != 65 or p256dh[:1] != b"\x04" or len(auth) != 16:
        raise bad("That notification key isn't valid.")
    return endpoint, {"p256dh": b64u(p256dh), "auth": b64u(auth)}


def subscribe(db, building, user, body, user_agent=""):
    """
    Keep (or refresh) this device for this person in this building. Same endpoint again =
    the same row, updated. A device that changed hands (another person signs in on it)
    moves to the new person, so the old one stops getting their pushes.
    """
    endpoint, keys = _clean(body or {})
    bid, uid = int(building["id"]), int(user["id"])
    row = {"User_Id": uid, "Building_Id": bid, "Endpoint": endpoint,
           "Sub_Keys": json.dumps(keys, separators=(",", ":")), "User_Agent": str(user_agent or "")[:255]}
    same = [r for r in db.find(PUSH_SUBS, {"Building_Id": bid}) if r.get("Endpoint") == endpoint]
    for extra in same[1:]:
        db.delete(PUSH_SUBS, extra["ROWID"])
    if same:
        db.update(PUSH_SUBS, dict(row, ROWID=same[0]["ROWID"]))
    else:
        mine = sorted(db.find(PUSH_SUBS, {"Building_Id": bid, "User_Id": uid}), key=lambda r: int(r["ROWID"]))
        for old in mine[:max(0, len(mine) - MAX_SUBS_PER_USER + 1)]:
            db.delete(PUSH_SUBS, old["ROWID"])
        db.insert(PUSH_SUBS, row)
    return {"subscribed": True}


def unsubscribe(db, building, user, body):
    """Forget this device for this person (sign-out, or notifications turned off in the app)."""
    body = body or {}
    sub = body.get("subscription") if isinstance(body.get("subscription"), dict) else body
    endpoint = str(sub.get("endpoint") or "").strip()
    if not endpoint:
        raise bad("Which device? (endpoint is missing)")
    gone = 0
    for row in db.find(PUSH_SUBS, {"Building_Id": int(building["id"]), "User_Id": int(user["id"])}):
        if row.get("Endpoint") == endpoint:
            db.delete(PUSH_SUBS, row["ROWID"])
            gone += 1
    return {"subscribed": False, "removed": gone}
