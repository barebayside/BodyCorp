"""
Legal clocks and the daily reminder.

A deadline of N days runs to the END of the Brisbane calendar day N days after
lodging: a pet request lodged at 9 pm on the 1st with 21 days is due by 11:59:59 pm
on the 22nd, Brisbane time. It is stored in UTC like every other datetime.

Queensland has no daylight saving, so a fixed +10 hours is correct and stays correct.
"""

from datetime import datetime, time, timedelta, timezone

import buildings
import mailer
import people
import store

BRISBANE = timezone(timedelta(hours=10))
OPEN = ("new", "in_progress", "waiting_on_resident", "with_committee")
SOON_DAYS = 7


def _utc(value):
    """A naive value is UTC; an aware one is converted."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def due_at(created_utc, days, business_day=False):
    """
    End of the Brisbane day `days` after `created_utc`, as a naive UTC datetime.
    `business_day`: a last day on a Saturday or Sunday moves to the Monday (AIA s 38(2), law file §8
    "Counting days"). Public holidays are not known to the portal, so they are not skipped.
    """
    day = _utc(created_utc).astimezone(BRISBANE).date() + timedelta(days=int(days))
    while business_day and day.weekday() >= 5:
        day += timedelta(days=1)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=BRISBANE)
    return end.astimezone(timezone.utc).replace(tzinfo=None)


def days_left(due_utc, now_utc):
    """Brisbane calendar days from today to the due day. 0 = due today, negative = overdue."""
    due_day = _utc(due_utc).astimezone(BRISBANE).date()
    today = _utc(now_utc).astimezone(BRISBANE).date()
    return (due_day - today).days


def brisbane_date(due_utc):
    return _utc(due_utc).astimezone(BRISBANE).strftime("%Y-%m-%d")


def iso_utc(value):
    """For the page: an ISO time with Z, which every browser reads the same way."""
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def handler_emails(db, building, handler):
    """Whoever holds the case's handler role; the building's admins if nobody does yet, so nothing is lost."""
    return people.emails_with_roles(db, building, (handler,)) or people.emails_with_roles(db, building, ("admin",))


def _due_soon(db, building, now_utc):
    out = []
    for row in db.find(store.CASES, {"Building_Id": int(building["id"])}):
        due = store.parse_dt(row.get("Due_At"))
        if row.get("Status") in OPEN and due and days_left(due, now_utc) <= SOON_DAYS:
            out.append((days_left(due, now_utc), row))
    return sorted(out, key=lambda pair: pair[0])


def _line(left, row, labels, topic=None, now=None):
    """One case in a digest, with what happens if nobody decides (the topic's own words)."""
    import stages  # here, not at the top: stages reads this module's clock helpers
    when = "OVERDUE by {} day(s)".format(-left) if left < 0 else ("due TODAY" if left == 0 else
                                                                   "due in {} day(s)".format(left))
    missed = stages.missed(topic, row, now) if topic and now else None
    return "{} · {} · {} · {}{}".format(row.get("Ref"), row.get("Title"), labels.get(str(row.get("Unit_Id")), ""),
                                        when, " · " + missed["card"] if missed and missed["card"] else "")


def remind(db, now_utc, extra=None):
    """
    One digest per handler per building of open cases due within 7 days or overdue. Returns emails sent.
    `extra(building)` may add {email: [lines]} (tasks and minutes due, from main) to the same digests.
    """
    sent = 0
    for building in (buildings.from_row(r) for r in db.find(store.BUILDINGS)):
        labels, digests = None, {}
        every = None
        for left, row in _due_soon(db, building, now_utc):
            labels = labels if labels is not None else buildings.unit_labels(db, building)
            if every is None:
                import topics
                every = {t["key"]: t for t in topics.all_topics(db, building)}
            for email in handler_emails(db, building, row.get("Handler")):
                digests.setdefault(email, []).append(_line(left, row, labels, every.get(row.get("Topic_Key")),
                                                           now_utc))
        for email, lines in ((extra(building) if extra else None) or {}).items():
            digests.setdefault(email, []).extend(lines)
        for email, lines in sorted(digests.items()):
            body = mailer.page(building, "Requests due soon", lines, "Open the inbox")
            subject = "{}: {} item(s) due soon or overdue".format(building["name"], len(lines)) if any(
                line.startswith(("Task:", "Minutes:")) for line in lines) else                 "{}: {} request(s) due soon or overdue".format(building["name"], len(lines))
            sent += 1 if mailer.send(db, email, subject, body, building=building) else 0
    return sent
