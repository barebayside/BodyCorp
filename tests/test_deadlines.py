"""Task 5: legal clocks in Brisbane time, and the daily reminder."""

from datetime import datetime, timedelta

import cases
import deadlines
import store
from conftest import NOW


def test_due_at_brisbane_end_of_day():
    # 15:30 UTC on the 10th is 01:30 on the 11th in Brisbane: the clock starts on the 11th.
    assert deadlines.due_at(datetime(2026, 11, 10, 15, 30), 21) == datetime(2026, 12, 2, 13, 59, 59)
    # 13:00 UTC on the 10th is 23:00 on the 10th in Brisbane.
    assert deadlines.due_at(datetime(2026, 11, 10, 13, 0), 21) == datetime(2026, 12, 1, 13, 59, 59)


def test_days_left_crosses_midnight():
    due = datetime(2026, 12, 1, 13, 59, 59)                                  # end of 1 Dec, Brisbane
    assert deadlines.days_left(due, datetime(2026, 11, 30, 13, 59)) == 1     # 23:59 on 30 Nov
    assert deadlines.days_left(due, datetime(2026, 11, 30, 14, 1)) == 0      # 00:01 on 1 Dec
    assert deadlines.days_left(due, datetime(2026, 12, 1, 14, 0)) == -1      # 00:00 on 2 Dec


def _case(world, email, unit, topic, now):
    answers = {"animal": "Cat", "how_many": "1", "where_kept": "Inside", "which": "Minutes", "how": "Email copies"}
    return cases.create(world.db, world.building, world.user(email), world.ctx(email), world.units[unit], topic,
                        answers, [], now)["case"]


def test_remind_sends_one_digest_per_handler(world):
    world.member("jo@example.com", "4")
    world.role("c1@example.com", "committee")
    world.role("c2@example.com", "committee")
    world.role("m@example.com", "manager")
    _case(world, "jo@example.com", "4", "pet", NOW)                            # due in 21 days: not yet
    _case(world, "jo@example.com", "4", "records", NOW)                        # due in 7 days
    _case(world, "jo@example.com", "4", "records", NOW - timedelta(days=10))   # overdue
    world.db.outbox.clear()
    assert deadlines.remind(world.db, NOW) == 2
    for email in ("c1@example.com", "c2@example.com"):
        mails = world.db.mail_to(email)
        assert len(mails) == 1 and "2 request(s)" in mails[0]["subject"]
        assert "OVERDUE" in mails[0]["html"]
    assert world.db.mail_to("m@example.com") == []


def test_closed_cases_not_reminded(world):
    world.member("jo@example.com", "4")
    world.role("c1@example.com", "committee")
    case = _case(world, "jo@example.com", "4", "records", NOW)
    for status in ("closed", "decided"):
        world.db.update(store.CASES, {"ROWID": case["id"], "Status": status})
        world.db.outbox.clear()
        assert deadlines.remind(world.db, NOW) == 0


def test_due_stored_utc_and_shown_brisbane(world):
    world.member("jo@example.com", "4")
    case = _case(world, "jo@example.com", "4", "pet", datetime(2026, 11, 10, 15, 30))
    assert world.db.get(store.CASES, case["id"])["Due_At"] == "2026-12-02 13:59:59"
    assert case["due_at"] == "2026-12-02T13:59:59Z" and case["due_date"] == "2026-12-02"


def test_cron_route_needs_key(world):
    assert world.call("POST", "/cron/reminders")[1] == 403
    assert world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "wrong"})[1] == 403
    body, status = world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"})
    assert status == 200 and body == {"ok": True, "sent": 0, "queue": {"sent": 0, "failed": 0, "waiting": 0}}
