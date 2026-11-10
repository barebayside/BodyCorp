"""The failure check: the mail queue and its retries, the daily self-check, crashes logged, who sees failures."""

from datetime import timedelta

import flask
import pytest

import cases
import content
import deadlines
import failures
import main
import mailer
import store
from conftest import ADMIN, NOW

SUPPORT = "support@example.com"
CRON = {"X-Cron-Key": "cron-key"}


def at(world, utc):
    """Make the fake store stamp CREATEDTIME as if it were `utc` (Catalyst stamps Brisbane time)."""
    world.db.clock = utc + timedelta(hours=10)


def kinds(world):
    return [r["Kind"] for r in world.db.find(store.FAILURES)]


def other_building(world, admin_email):
    row = world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other Tower"})
    user = world.user(admin_email)
    world.db.insert(store.ROLES, {"User_Id": int(user["id"]), "Building_Id": int(row["ROWID"]), "Role": "admin"})
    return str(row["ROWID"])


def stale_case(world):
    """An open 7-day request lodged 10 days ago, untouched since."""
    world.member("jo@example.com", "4")
    at(world, NOW - timedelta(days=10))
    answers = {"which": "Minutes", "how": "Email copies"}
    return cases.create(world.db, world.building, world.user("jo@example.com"), world.ctx("jo@example.com"),
                        world.units["4"], "records", answers, [], NOW - timedelta(days=10))["case"]


# ---------- the queue ----------

def test_failed_email_is_queued_and_logged(world):
    world.db.mail_error = "MailError: sender not verified"
    assert mailer.send(world.db, "jo@example.com", "Altai: hello", "<p>x</p>", bcc=["b@example.com"],
                       building=world.building) is False
    row = world.db.find(store.MAIL_QUEUE)[0]
    assert {k: row[k] for k in ("To_Email", "Bcc", "Subject", "Html", "Status", "Attempts", "Last_Error")} == {
        "To_Email": "jo@example.com", "Bcc": "b@example.com", "Subject": "Altai: hello", "Html": "<p>x</p>",
        "Status": "queued", "Attempts": 1, "Last_Error": "MailError: sender not verified"}
    assert row["Building_Id"] == world.building["id"]
    wait = store.parse_dt(row["Next_Try"]) - store.utc_now()
    assert timedelta(minutes=4) < wait <= timedelta(minutes=5)
    failure = world.db.find(store.FAILURES)[0]
    assert failure["Kind"] == "mail" and failure["Resolved"] is False
    assert failure["Building_Id"] == world.building["id"] and "@" not in failure["Detail"]


def test_no_sender_queues_without_trying(world, monkeypatch):
    monkeypatch.setenv("MAIL_FROM", "")
    world.role("c@example.com", "committee")
    world.member("jo@example.com", "4")
    world.db.outbox.clear()
    content.post_notice(world.db, world.building, world.ctx("c@example.com"), "Pool", "Closed", "all")
    assert world.db.outbox == []
    queued = world.db.find(store.MAIL_QUEUE)
    assert queued and all(r["Last_Error"] == "MAIL_FROM is not set" for r in queued)
    assert "mail" in kinds(world)


def test_sign_in_code_is_never_queued(world):
    world.db.mail_error = "MailError: down"
    world.call("POST", "/auth/start", {"email": "sam@example.com"})
    assert world.db.find(store.MAIL_QUEUE) == []
    failure = world.db.find(store.FAILURES)[0]
    assert failure["Kind"] == "mail" and "sign-in" in failure["Detail"]
    assert "Your sign-in code" not in failure["Detail"]           # the subject carries the code; never recorded


def test_retry_backs_off_then_gives_up(world):
    world.db.mail_error = "MailError: down"
    mailer.send(world.db, "jo@example.com", "Altai: hello", "<p>x</p>", building=world.building)
    row = lambda: world.db.find(store.MAIL_QUEUE)[0]          # noqa: E731
    due = store.parse_dt(row()["Next_Try"])
    # Not due yet: untouched.
    assert mailer.retry_queue(world.db, due - timedelta(seconds=1)) == {"sent": 0, "failed": 0, "waiting": 1}
    assert row()["Attempts"] == 1
    for tries, wait in ((2, timedelta(minutes=30)), (3, timedelta(hours=2)), (4, timedelta(hours=6))):
        now = store.parse_dt(row()["Next_Try"])
        assert mailer.retry_queue(world.db, now)["waiting"] == 1
        assert row()["Attempts"] == tries and store.parse_dt(row()["Next_Try"]) == now + wait
    assert "mail_gave_up" not in kinds(world)
    assert mailer.retry_queue(world.db, store.parse_dt(row()["Next_Try"])) == {"sent": 0, "failed": 1, "waiting": 0}
    assert row()["Status"] == "failed" and row()["Attempts"] == 5
    gave_up = [r for r in world.db.find(store.FAILURES) if r["Kind"] == "mail_gave_up"]
    assert len(gave_up) == 1 and gave_up[0]["Building_Id"] == world.building["id"]
    assert mailer.retry_queue(world.db, NOW + timedelta(days=30)) == {"sent": 0, "failed": 0, "waiting": 0}


def test_retry_sends_when_mail_works_again(world):
    world.db.mail_error = "MailError: down"
    mailer.send(world.db, "a@example.com", "Altai: hello", "<p>x</p>", bcc=["b@example.com", "c@example.com"])
    world.db.mail_error = None
    assert mailer.retry_queue(world.db, NOW + timedelta(days=1))["sent"] == 1
    assert world.db.find(store.MAIL_QUEUE)[0]["Status"] == "sent"
    assert world.db.outbox[-1] == {"to": ["a@example.com"], "subject": "Altai: hello", "html": "<p>x</p>",
                                   "bcc": ["b@example.com", "c@example.com"]}


def test_reminders_route_retries_the_queue_first(world):
    world.db.mail_error = "MailError: down"
    mailer.send(world.db, "a@example.com", "Altai: hello", "<p>x</p>")
    world.db.mail_error = None
    due = store.parse_dt(world.db.find(store.MAIL_QUEUE)[0]["Next_Try"])
    body, _ = world.call("POST", "/cron/reminders", headers=CRON, now=due)
    assert body["queue"]["sent"] == 1 and world.db.mail_to("a@example.com")


# ---------- size ----------

def test_too_long_html_is_sent_whole_and_logged(world):
    big = "<p>" + "x" * store.TEXT_MAX + "</p>"
    assert mailer.send(world.db, "jo@example.com", "Altai: big", big, building=world.building) is True
    assert world.db.outbox[-1]["html"] == big                       # sent in full, not cut
    assert kinds(world) == ["mail_too_long"]
    world.db.mail_error = "MailError: down"
    assert mailer.send(world.db, "jo@example.com", "Altai: big", big) is False
    assert world.db.find(store.MAIL_QUEUE) == []                   # can't be kept, so it says so
    assert kinds(world) == ["mail_too_long", "mail_too_long"]


def test_normal_emails_fit_a_queued_copy(world):
    # The longest real ones: a 5,000-character notice full of escapable text, and a 40-case reminder digest.
    notice = ("It's the pool & gym, \"closed\" <for> cleaning.\n" * 200)[:content.MAX_BODY]
    assert len(mailer.page(world.building, "x" * 255, [notice], "Open the portal")) < store.TEXT_MAX
    lines = ["ALT-{:04d} · {} · Unit 120 · OVERDUE by 12 day(s)".format(i, "y" * 60) for i in range(40)]
    assert len(mailer.page(world.building, "Requests due soon", lines, "Open the inbox")) < store.TEXT_MAX


# ---------- the daily check ----------

def test_healthy_check_sends_nothing(world):
    at(world, NOW)
    world.call("POST", "/cron/reminders", headers=CRON)
    world.db.outbox.clear()
    body, status = world.call("POST", "/cron/check", headers=CRON, now=NOW + timedelta(hours=1))
    assert status == 200 and body["ok"] is True and body["problems"] == [] and body["digests"] == 0
    assert world.db.outbox == []


def test_check_needs_key(world):
    assert world.call("POST", "/cron/check")[1] == 403
    assert world.call("POST", "/cron/check", headers={"X-Cron-Key": "nope"})[1] == 403


def test_check_sends_one_digest_with_the_problems(world):
    case = stale_case(world)
    world.role("c@example.com", "committee")
    at(world, NOW - timedelta(days=2))
    world.db.mail_error = "MailError: down"
    mailer.send(world.db, "a@example.com", "Altai: hello", "<p>x</p>", building=world.building)
    world.db.mail_error = None
    failures.log(world.db, "error", "GET /me: KeyError: x")                 # product-wide
    world.db.outbox.clear()
    world.db.mail_error = "MailError: still down"            # the retry fails, so the email stays stuck
    body, status = world.call("POST", "/cron/check", headers=CRON)
    world.db.mail_error = None
    assert status == 200 and body["ok"] is False
    found = {(p["building"], p["kind"]) for p in body["problems"]}
    assert found >= {(None, "reminders_late"), ("altai", "mail_stuck"), ("altai", "case_stale"),
                     ("altai", "failures"), (None, "failures")}
    assert any(case["ref"] in p["text"] for p in body["problems"])
    # The digests themselves failed (mail is down), so they were queued: one for support, one for Altai's admin.
    digests = world.db.find(store.MAIL_QUEUE, {"Status": "queued"})[-2:]
    assert [d["To_Email"] for d in digests] == [SUPPORT, ADMIN]
    assert "Whole product" in digests[0]["Html"] and case["ref"] in digests[1]["Html"]
    assert "Whole product" not in digests[1]["Html"]                     # admins see their building only


def test_check_digest_goes_once_to_each(world):
    stale_case(world)
    world.db.outbox.clear()
    body, _ = world.call("POST", "/cron/check", headers=CRON)
    assert body["digests"] == 2
    assert len(world.db.mail_to(SUPPORT)) == 1 and len(world.db.mail_to(ADMIN)) == 1
    assert len(world.db.outbox) == 2
    assert world.db.mail_to("jo@example.com") == []                      # residents are never told


def test_check_reports_reminders_late(world):
    at(world, NOW)
    world.call("POST", "/cron/reminders", headers=CRON)
    body, _ = world.call("POST", "/cron/check", headers=CRON, now=NOW + timedelta(hours=27, minutes=30))
    assert [p["kind"] for p in body["problems"]] == ["reminders_late"]
    assert "27 hours" in body["problems"][0]["text"]
    assert [r["Kind"] for r in world.db.find(store.FAILURES)].count(failures.HEARTBEAT_REMINDERS) == 1


def test_status_is_public_and_says_when_checked(world):
    body, status = world.call("GET", "/status", {"b": ""})
    assert status == 200 and body == {"ok": True, "status": "alive", "checked_at": None}
    at(world, NOW)
    world.call("POST", "/cron/check", headers=CRON)
    body, _ = world.call("GET", "/status")
    assert set(body) == {"ok", "status", "checked_at"} and body["checked_at"].startswith("2026-11-10T02:00")


# ---------- crashes ----------

def _boom(c):
    raise ValueError("could not save 'PRIVATE ANSWER' for jo@example.com")


def _handle(path, json):
    app = flask.Flask("test")
    with app.test_request_context("/server/bodycorp_api" + path, method="POST", json=json):
        response = main.handler(flask.request)
    return response.status_code, response.get_json(force=True)


def test_crash_is_logged_without_the_body(world, monkeypatch):
    monkeypatch.setattr(store, "Db", lambda: world.db)
    monkeypatch.setitem(main.ROUTES, ("POST", "/boom"), _boom)
    status, body = _handle("/boom", {"b": "altai", "answers": {"note": "SECRET NOTE"}})
    assert status == 500 and body == {"ok": False, "error": "Something went wrong (ValueError)."}
    row = world.db.find(store.FAILURES)[0]
    assert row["Kind"] == "error" and row["Building_Id"] == world.building["id"]
    assert row["Detail"].startswith("POST /boom: ValueError: could not save")
    for secret in ("PRIVATE", "SECRET", "jo@example.com", "answers"):
        assert secret not in row["Detail"]


def test_failure_logging_never_breaks_the_answer(world, monkeypatch):
    monkeypatch.setitem(main.ROUTES, ("POST", "/boom"), _boom)

    def broken_insert(table, row):
        raise RuntimeError("database down")
    monkeypatch.setattr(world.db, "insert", broken_insert)
    monkeypatch.setattr(store, "Db", lambda: world.db)
    assert _handle("/boom", {"b": "altai"})[0] == 500

    def no_db():
        raise RuntimeError("no SDK")
    monkeypatch.setattr(store, "Db", no_db)
    assert _handle("/boom", {"b": "altai"})[0] == 500


# ---------- who sees failures ----------

@pytest.fixture
def logged(world):
    other_id = other_building(world, "other-admin@example.com")
    failures.log(world.db, "mail", "altai one", world.building["id"])
    failures.log(world.db, "mail", "other one", other_id)
    failures.log(world.db, "error", "product one")
    failures.heartbeat(world.db, failures.HEARTBEAT_CHECK, "ran")
    return other_id


def details(body):
    return sorted(f["detail"] for f in body["failures"])


def test_building_admin_sees_only_their_building(world, logged):
    body, status = world.call("GET", "/failures", email=ADMIN)
    assert status == 200 and details(body) == ["altai one"] and body["product_admin"] is False
    assert body["failures"][0]["building"] == "altai" and body["total"] == 1
    body, _ = world.call("GET", "/failures", {"b": "other"}, email="other-admin@example.com")
    assert details(body) == ["other one"]
    assert world.call("GET", "/failures", {"b": "other"}, email=ADMIN)[1] == 403
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    for email in ("jo@example.com", "c@example.com"):
        assert world.call("GET", "/failures", email=email)[1] == 403
    assert world.call("GET", "/failures")[1] == 401


def test_only_the_product_admin_sees_all(world, logged):
    assert world.call("GET", "/failures", {"all": "1"}, email=ADMIN)[1] == 403
    assert world.call("GET", "/failures", {"all": "1"}, email=SUPPORT)[1] == 403       # not an admin anywhere
    world.role(SUPPORT, "admin")
    body, status = world.call("GET", "/failures", {"all": "1"}, email=SUPPORT)
    assert status == 200 and body["product_admin"] is True
    assert details(body) == ["altai one", "other one", "product one"]                   # never heartbeats


def test_resolve_own_building_only(world, logged):
    mine = world.call("GET", "/failures", email=ADMIN)[0]["failures"][0]["id"]
    other = world.db.find(store.FAILURES, {"Detail": "other one"})[0]["ROWID"]
    product = world.db.find(store.FAILURES, {"Detail": "product one"})[0]["ROWID"]
    for rowid in (other, product):
        assert world.call("POST", "/failures/resolve", {"id": rowid}, email=ADMIN)[1] == 404
    body, status = world.call("POST", "/failures/resolve", {"id": mine}, email=ADMIN)
    assert status == 200 and body["failure"]["resolved"] is True
    assert world.db.get(store.FAILURES, mine)["Resolved_By"] == int(world.user(ADMIN)["id"])
    assert world.call("GET", "/failures", email=ADMIN)[0]["failures"] == []
    world.role(SUPPORT, "admin")
    assert world.call("POST", "/failures/resolve", {"id": product}, email=SUPPORT)[1] == 200
    assert [f["detail"] for f in world.call("GET", "/failures", {"all": "1"}, email=SUPPORT)[0]["failures"]] == [
        "other one"]


def test_resolved_failures_stop_the_digest(world):
    at(world, NOW)
    world.call("POST", "/cron/reminders", headers=CRON)
    row = failures.log(world.db, "error", "GET /me: KeyError: x", world.building["id"])
    assert world.call("POST", "/cron/check", headers=CRON)[0]["ok"] is False
    world.call("POST", "/failures/resolve", {"id": row["ROWID"]}, email=ADMIN)
    assert world.call("POST", "/cron/check", headers=CRON)[0]["ok"] is True


def test_due_soon_reminder_still_works_through_the_queue(world):
    # The existing reminder path, with mail down: nothing sent, but the digest is kept for retry.
    stale_case(world)
    world.role("c1@example.com", "committee")
    world.db.mail_error = "MailError: down"
    assert deadlines.remind(world.db, NOW) == 0
    assert [r["To_Email"] for r in world.db.find(store.MAIL_QUEUE)] == ["c1@example.com"]
