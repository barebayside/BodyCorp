"""
The daily self-check: POST /cron/check, so a problem reaches a person instead of sitting in a log.

    retry the mail queue  ->  look for trouble  ->  any?  ->  ONE digest to SUPPORT_EMAIL (everything)
                                                          ->  ONE digest to each affected building's admins
                                                              (their building only)
                          ->  stamp heartbeat_check  ->  {ok, problems, queue, checked_at}

WHAT COUNTS AS TROUBLE
    reminders_late   the daily reminders haven't stamped heartbeat_reminders in 26 hours
    mail_stuck       queued email older than 24 hours
    case_stale       an open case past its legal deadline with nothing on its record for 3+ days
    failures         unresolved Failures rows (grouped by building and kind)

The answer is also for an outside monitor: `ok` is false whenever there are
problems, though the call itself worked (HTTP 200). Problems are re-sent every
day until fixed: a failure stops counting once an admin resolves it.

ENVIRONMENT
    SUPPORT_EMAIL   the product's support address; gets every digest
"""

import os
from datetime import timedelta

import buildings
import deadlines
import failures
import mailer
import people
import store

REMINDERS_LATE = timedelta(hours=26)
MAIL_STUCK = timedelta(hours=24)
QUIET = timedelta(days=3)
MAX_LINES = 25


def _problem(building, kind, text):
    return {"building": building["slug"] if building else None, "kind": kind, "text": text}


def _hours(delta):
    return int(delta.total_seconds() // 3600)


def _reminders(db, now):
    last = failures.last_run(db, failures.HEARTBEAT_REMINDERS)
    if not last:
        return [_problem(None, "reminders_late", "The daily reminders have never run.")]
    if now - last > REMINDERS_LATE:
        return [_problem(None, "reminders_late",
                         "The daily reminders last ran {} hours ago.".format(_hours(now - last)))]
    return []


def _stuck_mail(db, now, by_id):
    counts = {}
    for row in db.find(store.MAIL_QUEUE, {"Status": "queued"}):
        made = store.created_utc(row)
        if made and now - made > MAIL_STUCK:
            key = str(row.get("Building_Id") or "")
            counts[key] = counts.get(key, 0) + 1
    return [_problem(by_id.get(key), "mail_stuck",
                     "{} email(s) still waiting to send after more than a day.".format(n))
            for key, n in sorted(counts.items())]


def _stale_cases(db, building, now):
    last = {}
    for event in db.find(store.EVENTS, {"Building_Id": int(building["id"])}):
        when = store.created_utc(event)
        key = str(event.get("Case_Id"))
        if when and (key not in last or when > last[key]):
            last[key] = when
    out = []
    for row in sorted(db.find(store.CASES, {"Building_Id": int(building["id"])}), key=lambda r: int(r["ROWID"])):
        due = store.parse_dt(row.get("Due_At"))
        if row.get("Status") not in deadlines.OPEN or not due or due >= now:
            continue
        active = last.get(str(row["ROWID"])) or store.created_utc(row) or now
        if now - active >= QUIET:
            out.append(_problem(building, "case_stale", "{} ({}) is {} day(s) overdue and nothing has happened "
                                "on it for {} days.".format(row.get("Ref"), row.get("Title"),
                                                            -deadlines.days_left(due, now), (now - active).days)))
    return out


def _open_failures(db, by_id):
    counts = {}
    for row in failures.unresolved(db):
        key = (str(row.get("Building_Id") or ""), row.get("Kind"))
        counts[key] = counts.get(key, 0) + 1
    return [_problem(by_id.get(b), "failures", "{} unresolved failure(s) of kind \"{}\". See the Needs attention "
                     "list in the portal.".format(n, kind)) for (b, kind), n in sorted(counts.items())]


def _lines(problems, with_building, names):
    lines = []
    for p in problems[:MAX_LINES]:
        where = names.get(p["building"], "Whole product") if with_building else ""
        lines.append("{}{}".format(where + ": " if where else "", p["text"]))
    if len(problems) > MAX_LINES:
        lines.append("…and {} more.".format(len(problems) - MAX_LINES))
    return lines


def _send_digests(db, problems, by_slug):
    """One email to support with everything, one to each affected building's admins with theirs."""
    names = {slug: b["name"] for slug, b in by_slug.items()}
    support = os.environ.get("SUPPORT_EMAIL", "").strip().lower()
    sent = 0
    if support:
        body = mailer.page(None, "Needs attention", _lines(problems, True, names), "Open the portal")
        sent += int(mailer.send(db, support, "BodyCorp check: {} problem(s)".format(len(problems)), body))
    for slug in sorted({p["building"] for p in problems if p["building"]}):
        building = by_slug[slug]
        mine = [p for p in problems if p["building"] == slug]
        admins = [e for e in people.emails_with_roles(db, building, ("admin",)) if e != support]
        if admins:
            body = mailer.page(building, "Needs attention", _lines(mine, False, names), "Open the portal")
            subject = "{}: {} thing(s) need attention".format(building["name"], len(mine))
            sent += int(mailer.send(db, admins, subject, body, building=building))
    return sent


def check(db, now=None):
    """Run the whole self-check. Returns {ok, problems, queue, digests, checked_at}."""
    now = now or store.utc_now()
    queue = mailer.retry_queue(db, now)
    every = [buildings.from_row(r) for r in db.find(store.BUILDINGS)]
    by_id = {b["id"]: b for b in every}
    problems = _reminders(db, now) + _stuck_mail(db, now, by_id)
    for building in every:
        problems += _stale_cases(db, building, now)
    problems += _open_failures(db, by_id)
    if not os.environ.get("SUPPORT_EMAIL", "").strip():
        problems.insert(0, _problem(None, "config", "SUPPORT_EMAIL is not set, so only building admins hear "
                                                    "about problems."))
    digests = _send_digests(db, problems, {b["slug"]: b for b in every}) if problems else 0
    failures.heartbeat(db, failures.HEARTBEAT_CHECK, "{} problem(s), {} digest(s).".format(len(problems), digests))
    return {"ok": not problems, "problems": problems, "queue": queue, "digests": digests,
            "checked_at": deadlines.iso_utc(now)}
