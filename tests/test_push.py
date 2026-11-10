"""Phone notifications: the encryption (against RFC 8291's worked example), the VAPID signature,
who gets a push, expired devices removed, failures logged without personal data, subscribe/unsubscribe."""

import json
import struct

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

import push  # noqa: E402
import store  # noqa: E402
from errors import ApiError  # noqa: E402

APPLE = "https://web.push.apple.com/QGuQyavXutnMH-ABC"
GOOGLE = "https://fcm.googleapis.com/fcm/send/abc:def"


# ---------- helpers ----------

def device():
    """A pretend phone: its private key, and the subscription keys it would hand the page."""
    key = ec.generate_private_key(ec.SECP256R1())
    import os
    auth = os.urandom(16)
    return key, {"p256dh": push.b64u(push._point(key.public_key())), "auth": push.b64u(auth)}


def decrypt(body, ua_key, auth_b64):
    """What the phone does with a push (RFC 8291 read backwards)."""
    salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    assert rs == push.RECORD_SIZE
    ua_public = push._point(ua_key.public_key())
    shared = ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = push._hkdf(push.unb64u(auth_b64), shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = push._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = push._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


class Sender:
    """Stands in for the push services: answers each endpoint with a set status, records what was sent."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.sent = []

    def __call__(self, endpoint, headers, data):
        self.sent.append({"endpoint": endpoint, "headers": headers, "data": data})
        answer = self.answers.get(endpoint, 201)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def keys(monkeypatch):
    public, private = push.make_vapid_keys()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:support@example.com")
    return public


@pytest.fixture
def db(world):
    world.db.tables.setdefault(push.PUSH_SUBS, [])
    return world.db


def add_sub(world, email, endpoint, building=None):
    key, sub_keys = device()
    building = building or world.building
    push.subscribe(world.db, building, world.user(email), {"endpoint": endpoint, "keys": sub_keys}, "iPhone")
    return key, sub_keys


def push_failures(world):
    return [r for r in world.db.find(store.FAILURES) if r["Kind"] == "push"]


# ---------- the encryption and the signature ----------

def test_encryption_matches_rfc_8291_worked_example():
    """RFC 8291 Appendix A: fixed keys and salt must give exactly the published message."""
    server = push._private_key("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw")
    body = push.encrypt(b"When I grow up, I want to be a watermelon",
                        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                        "BTBZMqHH6r4Tts7J_aSIgg", _server_key=server, _salt=push.unb64u("DGv6ra1nlYgDCS1FRnbzlw"))
    assert push.b64u(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK"
        "6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_a_phone_can_read_what_we_send():
    key, sub = device()
    message = json.dumps({"title": "Altai", "body": "Your request was approved"}).encode()
    assert decrypt(push.encrypt(message, sub["p256dh"], sub["auth"]), key, sub["auth"]) == message


def test_vapid_header_is_a_valid_es256_token_for_the_push_service(keys):
    value = push.vapid_header(APPLE + "?x=1", now=1000)
    assert value.startswith("vapid t=") and value.endswith(", k=" + keys)
    token = value[len("vapid t="):value.index(", k=")]
    head, body, sig = token.split(".")
    assert json.loads(push.unb64u(head)) == {"typ": "JWT", "alg": "ES256"}
    claims = json.loads(push.unb64u(body))
    assert claims == {"aud": "https://web.push.apple.com", "exp": 1000 + 12 * 3600, "sub": "mailto:support@example.com"}
    raw = push.unb64u(sig)
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.unb64u(keys))
    public.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                  "{}.{}".format(head, body).encode(), ec.ECDSA(hashes.SHA256()))


def test_made_keys_fit_what_browsers_expect():
    public, private = push.make_vapid_keys()
    assert len(push.unb64u(public)) == 65 and push.unb64u(public)[:1] == b"\x04"
    assert len(push.unb64u(private)) == 32
    assert push._point(push._private_key(private).public_key()) == push.unb64u(public)


# ---------- who gets a push ----------

def test_send_reaches_each_device_of_the_named_people_only(world, db, keys):
    jo_phone, jo_keys = add_sub(world, "jo@example.com", APPLE)
    add_sub(world, "jo@example.com", GOOGLE)
    add_sub(world, "sam@example.com", "https://updates.push.services.mozilla.com/wpush/v2/sam")
    sender = Sender()
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "Altai on the Park",
                       "Your request ALT-0001 was approved", "portal.html?b=altai#/case/1", sender=sender)
    assert result == {"sent": 2, "removed": 0, "failed": 0}
    assert sorted(s["endpoint"] for s in sender.sent) == sorted([APPLE, GOOGLE])
    to_apple = [s for s in sender.sent if s["endpoint"] == APPLE][0]
    assert to_apple["headers"]["Content-Encoding"] == "aes128gcm" and to_apple["headers"]["TTL"] == "86400"
    assert to_apple["headers"]["Authorization"].startswith("vapid t=")
    shown = json.loads(decrypt(to_apple["data"], jo_phone, jo_keys["auth"]))
    assert shown == {"title": "Altai on the Park", "body": "Your request ALT-0001 was approved",
                     "url": "portal.html?b=altai#/case/1", "icon": push.DEFAULT_ICON, "badge": push.DEFAULT_BADGE,
                     "tag": "altai"}


def test_send_never_crosses_buildings(world, db, keys):
    other = world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other Tower"})
    other_building = {"id": str(other["ROWID"]), "slug": "other", "brand": {}}
    add_sub(world, "jo@example.com", GOOGLE, building=other_building)
    sender = Sender()
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "t", "b", "u", sender=sender)
    assert result == {"sent": 0, "removed": 0, "failed": 0} and sender.sent == []


def test_send_to_emails_finds_the_people_behind_the_addresses(world, db, keys):
    add_sub(world, "jo@example.com", APPLE)
    sender = Sender()
    result = push.send_to_emails(db, world.building, ["Jo@Example.com", "nobody@example.com", ""], "t", "b", "u",
                                 sender=sender)
    assert result["sent"] == 1 and [s["endpoint"] for s in sender.sent] == [APPLE]


def test_building_icon_comes_from_its_brand(world, db, keys):
    key, sub = add_sub(world, "jo@example.com", APPLE)
    building = dict(world.building, brand=dict(world.building["brand"], app_icon="icons/altai-192.png",
                                               app_badge="icons/altai-badge-96.png"))
    sender = Sender()
    push.send(db, building, [world.user("jo@example.com")["id"]], "t", "b", "u", sender=sender)
    shown = json.loads(decrypt(sender.sent[0]["data"], key, sub["auth"]))
    assert shown["icon"] == "icons/altai-192.png" and shown["badge"] == "icons/altai-badge-96.png"


def test_a_long_body_is_cut_to_fit_a_lock_screen(world):
    raw = push.message(world.building, "T" * 500, "word " * 2000, "u")
    data = json.loads(raw)
    assert len(data["title"]) == push.TITLE_MAX and len(data["body"]) <= push.BODY_MAX
    assert len(raw) <= push.PAYLOAD_MAX


# ---------- devices that went away, and failures ----------

def test_expired_devices_are_removed_quietly(world, db, keys):
    add_sub(world, "jo@example.com", APPLE)
    add_sub(world, "jo@example.com", GOOGLE)
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "t", "b", "u",
                       sender=Sender({APPLE: 410, GOOGLE: 404}))
    assert result == {"sent": 0, "removed": 2, "failed": 0}
    assert db.find(push.PUSH_SUBS) == [] and push_failures(world) == []


def test_other_refusals_are_one_failure_naming_only_the_service(world, db, keys):
    add_sub(world, "jo@example.com", APPLE)
    add_sub(world, "jo@example.com", GOOGLE)
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "t", "Secret words", "u",
                       sender=Sender({APPLE: 403, GOOGLE: ConnectionError("fcm down jo@example.com")}))
    assert result == {"sent": 0, "removed": 0, "failed": 2}
    logged = push_failures(world)
    assert len(logged) == 1 and logged[0]["Building_Id"] == world.building["id"]
    detail = logged[0]["Detail"]
    assert "web.push.apple.com 403" in detail and "fcm.googleapis.com ConnectionError" in detail
    assert "jo@" not in detail and "Secret" not in detail and "QGuQ" not in detail
    assert len(db.find(push.PUSH_SUBS)) == 2          # kept: it may work next time


def test_no_devices_means_no_work_and_no_failure_even_without_keys(world, db):
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "t", "b", "u", sender=Sender())
    assert result == {"sent": 0, "removed": 0, "failed": 0} and push_failures(world) == []


def test_missing_keys_with_devices_waiting_is_a_failure(world, db, monkeypatch):
    add_sub(world, "jo@example.com", APPLE)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    sender = Sender()
    result = push.send(db, world.building, [world.user("jo@example.com")["id"]], "t", "b", "u", sender=sender)
    assert result["failed"] == 1 and sender.sent == []
    assert "VAPID" in push_failures(world)[0]["Detail"]


def test_send_never_raises(world, db, keys):
    class Broken:
        def find(self, *a, **k):
            raise RuntimeError("store down")

        def insert(self, *a, **k):
            raise RuntimeError("store down")

    assert push.send(Broken(), world.building, ["1"], "t", "b", "u") == {"sent": 0, "removed": 0, "failed": 0}


# ---------- the page's subscription ----------

def test_subscribe_keeps_one_row_per_device_and_refreshes_it(world, db):
    jo = world.user("jo@example.com")
    _, first = device()
    _, second = device()
    push.subscribe(db, world.building, jo, {"subscription": {"endpoint": APPLE, "keys": first}}, "iPhone")
    push.subscribe(db, world.building, jo, {"endpoint": APPLE, "keys": second}, "iPhone")
    rows = db.find(push.PUSH_SUBS)
    assert len(rows) == 1 and json.loads(rows[0]["Sub_Keys"]) == second
    assert str(rows[0]["User_Id"]) == jo["id"] and str(rows[0]["Building_Id"]) == world.building["id"]


def test_a_device_that_changes_hands_moves_to_the_new_person(world, db):
    add_sub(world, "jo@example.com", APPLE)
    add_sub(world, "sam@example.com", APPLE)
    rows = db.find(push.PUSH_SUBS)
    assert len(rows) == 1 and str(rows[0]["User_Id"]) == world.user("sam@example.com")["id"]


def test_subscribe_refuses_what_isnt_a_real_subscription(world, db):
    jo = world.user("jo@example.com")
    _, good = device()
    for body in ({"endpoint": "http://insecure.example/x", "keys": good},
                 {"endpoint": APPLE, "keys": {"p256dh": "short", "auth": good["auth"]}},
                 {"endpoint": APPLE, "keys": {"p256dh": good["p256dh"], "auth": "AAAA"}},
                 {"endpoint": APPLE}):
        with pytest.raises(ApiError) as caught:
            push.subscribe(db, world.building, jo, body)
        assert caught.value.status == 400
    assert db.find(push.PUSH_SUBS) == []


def test_unsubscribe_forgets_only_that_device(world, db):
    add_sub(world, "jo@example.com", APPLE)
    add_sub(world, "jo@example.com", GOOGLE)
    assert push.unsubscribe(db, world.building, world.user("jo@example.com"), {"endpoint": APPLE})["removed"] == 1
    assert [r["Endpoint"] for r in db.find(push.PUSH_SUBS)] == [GOOGLE]
    with pytest.raises(ApiError):
        push.unsubscribe(db, world.building, world.user("jo@example.com"), {})


def test_public_key_is_what_the_page_subscribes_with(keys):
    assert push.public_key() == keys and push.configured()
