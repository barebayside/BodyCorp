"""
Sign-in by a 6-digit code sent by email. No passwords.

    /auth/start   ->  a code is emailed (only its salted hash is stored), 10 minutes, 5 tries
    /auth/verify  ->  right code: a session token (only its hash is stored), 30 days
    every call    ->  X-Session: <token>  ->  `user_for`

/auth/start says the same thing whether or not the email is known, and anyone may
start: a new person signs in first and claims their units after. One live code per
email (a new start kills the old one), and at most 5 starts per email per hour.

ENVIRONMENT
    AUTH_SALT   mixed into every code hash, so a copy of the table can't be brute-forced offline
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import timedelta

import mailer
import store

logger = logging.getLogger("bodycorp_api.auth")

EMAIL = re.compile(r"^[^@\s'\"<>]+@[^@\s'\"<>]+\.[A-Za-z]{2,}$")
CODE_LIFE = timedelta(minutes=10)
SESSION_LIFE = timedelta(days=30)
MAX_TRIES = 5
DEAD = 99               # Attempts value for a used or replaced code
STARTS_PER_HOUR = 5


def clean_email(email):
    """Lower-cased and trimmed, or "" if it isn't an email address."""
    email = str(email or "").strip().lower()
    return email if len(email) <= 254 and EMAIL.match(email) else ""


def _code_hash(email, code):
    salt = os.environ.get("AUTH_SALT", "")
    return hashlib.sha256("{}:{}:{}".format(salt, email, code).encode("utf-8")).hexdigest()


def _token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _now(now):
    return now or store.utc_now()


def start(db, email, building, now=None):
    """Email a fresh code. Returns nothing, and says nothing, about whether the email is known."""
    email, now = clean_email(email), _now(now)
    if not email:
        return
    rows = db.find(store.LOGIN_CODES, {"Email": email})
    # Expires_At is creation + 10 minutes, so a code made in the last hour expires after now - 50 minutes.
    recent = [r for r in rows if (store.parse_dt(r.get("Expires_At")) or now) > now - timedelta(minutes=50)]
    if len(recent) >= STARTS_PER_HOUR:
        logger.warning("sign-in code limit reached for one email")
        return
    for row in rows:
        if row not in recent:
            db.delete(store.LOGIN_CODES, row["ROWID"])       # old rows only make the table grow
        elif int(row.get("Attempts") or 0) < DEAD:
            db.update(store.LOGIN_CODES, {"ROWID": row["ROWID"], "Attempts": DEAD})
    code = "{:06d}".format(secrets.randbelow(10 ** 6))
    db.insert(store.LOGIN_CODES, {"Email": email, "Code_Hash": _code_hash(email, code),
                                  "Expires_At": store.fmt_dt(now + CODE_LIFE), "Attempts": 0})
    name = (building or {}).get("name") or "BodyCorp"
    body = mailer.page(building, "Your sign-in code", [
        "Your code is: {}".format(code),
        "It works once, for 10 minutes. If you didn't ask for it, ignore this email."])
    mailer.send(db, email, "Your sign-in code for {}: {}".format(name, code), body, building=building, secret=True)


def _live_code(db, email, now):
    rows = [r for r in db.find(store.LOGIN_CODES, {"Email": email})
            if int(r.get("Attempts") or 0) < MAX_TRIES and (store.parse_dt(r.get("Expires_At")) or now) > now]
    return max(rows, key=lambda r: int(r["ROWID"])) if rows else None


def find_or_make_user(db, email):
    rows = db.find(store.USERS, {"Email": email})
    return rows[0] if rows else db.insert(store.USERS, {"Email": email, "Name": ""})


def public_user(row):
    return {"id": str(row["ROWID"]), "email": row.get("Email") or "", "name": row.get("Name") or ""}


def verify(db, email, code, now=None):
    """(token, user) for the right code, else None. A wrong guess uses up one of the 5 tries."""
    email, now = clean_email(email), _now(now)
    code = re.sub(r"\D", "", str(code or ""))
    if not email or len(code) != 6:
        return None
    row = _live_code(db, email, now)
    if not row:
        return None
    if not hmac.compare_digest(str(row.get("Code_Hash") or ""), _code_hash(email, code)):
        db.update(store.LOGIN_CODES, {"ROWID": row["ROWID"], "Attempts": int(row.get("Attempts") or 0) + 1})
        return None
    db.update(store.LOGIN_CODES, {"ROWID": row["ROWID"], "Attempts": DEAD})
    user = find_or_make_user(db, email)
    token = secrets.token_urlsafe(32)
    db.insert(store.SESSIONS, {"Token_Hash": _token_hash(token), "User_Id": int(user["ROWID"]),
                               "Expires_At": store.fmt_dt(now + SESSION_LIFE)})
    return token, public_user(user)


def _bare(bearer):
    value = str(bearer or "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else value


def user_for(db, bearer, now=None):
    """The signed-in user {id, email, name} for an X-Session header, or None."""
    token, now = _bare(bearer), _now(now)
    if not token:
        return None
    for row in db.find(store.SESSIONS, {"Token_Hash": _token_hash(token)}):
        if (store.parse_dt(row.get("Expires_At")) or now) > now:
            user = db.get(store.USERS, row.get("User_Id"))
            return public_user(user) if user else None
    return None


def logout(db, bearer):
    token = _bare(bearer)
    if token:
        for row in db.find(store.SESSIONS, {"Token_Hash": _token_hash(token)}):
            db.delete(store.SESSIONS, row["ROWID"])
