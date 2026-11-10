"""Task 2: sign-in by email code."""

from datetime import timedelta

import auth
import store
from conftest import NOW


def _start(world, email="sam@example.com", now=NOW):
    auth.start(world.db, email, world.building, now)
    return world.last_code(email)


def test_code_works_once(world):
    code = _start(world)
    token, user = auth.verify(world.db, " Sam@Example.com ", code, NOW)
    assert token and user["email"] == "sam@example.com"
    assert auth.user_for(world.db, "Bearer " + token, NOW)["id"] == user["id"]
    assert auth.verify(world.db, "sam@example.com", code, NOW) is None


def test_sixth_attempt_fails(world):
    code = _start(world)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert auth.verify(world.db, "sam@example.com", wrong, NOW) is None
    assert auth.verify(world.db, "sam@example.com", code, NOW) is None


def test_expired_code_fails(world):
    code = _start(world)
    assert auth.verify(world.db, "sam@example.com", code, NOW + timedelta(minutes=10, seconds=1)) is None


def test_code_stored_hashed(world):
    code = _start(world)
    for rows in world.db.tables.values():
        for row in rows:
            assert all(code not in str(v) for v in row.values())
    token, _ = auth.verify(world.db, "sam@example.com", code, NOW)
    assert all(token not in str(v) for r in world.db.tables[store.SESSIONS] for v in r.values())


def test_start_sends_branded_email(world):
    _start(world)
    mail = world.db.mail_to("sam@example.com")[-1]
    assert "Altai on the Park" in mail["subject"]
    assert "#1f4d3a" in mail["html"] and "var(" not in mail["html"]


def test_logout_kills_session(world):
    token, _ = auth.verify(world.db, "sam@example.com", _start(world), NOW)
    auth.logout(world.db, "Bearer " + token)
    assert auth.user_for(world.db, "Bearer " + token, NOW) is None


def test_new_code_replaces_old(world):
    first = _start(world)
    second = _start(world, now=NOW + timedelta(seconds=30))
    if first != second:
        assert auth.verify(world.db, "sam@example.com", first, NOW + timedelta(seconds=31)) is None
    assert auth.verify(world.db, "sam@example.com", second, NOW + timedelta(seconds=31))


def test_start_rate_limited_and_silent(world):
    for minute in range(5):
        _start(world, now=NOW + timedelta(minutes=minute))
    sent = len(world.db.outbox)
    body, status = world.call("POST", "/auth/start", {"email": "sam@example.com"}, now=NOW + timedelta(minutes=6))
    assert status == 200 and body == {"ok": True}
    assert len(world.db.outbox) == sent
    _start(world, now=NOW + timedelta(minutes=61))
    assert len(world.db.outbox) == sent + 1


def test_start_same_answer_known_unknown_or_invalid(world):
    world.user("known@example.com")
    for email in ("known@example.com", "new@example.com", "not-an-email"):
        assert world.call("POST", "/auth/start", {"email": email}) == ({"ok": True}, 200)


def test_session_expires(world):
    token, _ = auth.verify(world.db, "sam@example.com", _start(world), NOW)
    assert auth.user_for(world.db, token, NOW + timedelta(days=31)) is None


def test_wrong_code_route_is_400(world):
    _start(world)
    body, status = world.call("POST", "/auth/verify", {"email": "sam@example.com", "code": "12345"})
    assert status == 400 and body["ok"] is False
