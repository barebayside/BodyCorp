"""
A request type's pipeline and its "if nobody decides in time", read from the topic's data.

Nothing here knows about pets or owner motions: it reads the topic Definition JSON
(see topics.py). The wording, the dates' meaning and the legal source all come from there.

    stages      [{key, label, owner, status, instructions, rule, buttons: [...]}]
                owner is a duty (committee.DUTIES) or a role; the building's duty map decides who.
    deadline    {days, outcome, card, banner, citation, extend_to_days, business_day}
                outcome: deemed_approved | not_agreed | none

A topic with no stages (made before 2026-11-10) gets one plain pipeline from `fallback`.
"""

import re
from datetime import datetime, timedelta

import committee
import deadlines
import store

OUTCOME_WORDS = {"deemed_approved": "treated as APPROVED", "not_agreed": "treated as NOT AGREED", "none": ""}
FINISHED = ("decided", "closed")
URGENT_DAYS = 3


def fallback(topic):
    """The pipeline for a topic saved before stages existed: received -> being worked on -> done."""
    owner = "acknowledge" if topic.get("handler") == "committee" else "manager"
    hello = {"to": "resident", "subject": "{ref}: we have your request",
             "body": "Hi {name},\n\nWe have your request {ref} ({title}) and are looking at it.\n\n{link}"}
    answer = {"to": "resident", "subject": "{ref}: an update", "body": "Hi {name},\n\n{note}\n\n{link}"}
    return [
        {"key": "received", "label": "New", "owner": owner, "status": "new",
         "instructions": "Check the request is complete, then let the resident know it's in hand.",
         "buttons": [{"key": "acknowledge", "label": "Acknowledge", "next": "working", "email": hello}]},
        {"key": "working", "label": "Being worked on", "owner": owner, "status": "in_progress",
         "instructions": "Do the steps, then tell the resident the outcome.",
         "buttons": [{"key": "update", "label": "Send an update", "next": "working", "note": "required",
                      "email": answer},
                     {"key": "finish", "label": "Tell the resident it's done", "next": "done", "note": "required",
                      "email": answer}]},
        {"key": "done", "label": "Done", "owner": owner, "status": "closed", "buttons": []},
    ]


def of(topic):
    stages = (topic or {}).get("stages")
    return stages if isinstance(stages, list) and stages else fallback(topic or {})


def current(topic, row):
    """The case's stage, or the first one (an old case with no Stage starts at the beginning)."""
    stages = of(topic)
    key = row.get("Stage") or ""
    for stage in stages:
        if stage.get("key") == key:
            return stage
    return stages[0]


def find(topic, key):
    return next((s for s in of(topic) if s.get("key") == key), None)


# ---------- dates and words ----------

def long_date(due_utc):
    """'1 Dec 2026', in Brisbane."""
    day = datetime.strptime(deadlines.brisbane_date(due_utc), "%Y-%m-%d")
    return "{} {} {}".format(day.day, day.strftime("%b"), day.year)


def short_date(due_utc):
    day = datetime.strptime(deadlines.brisbane_date(due_utc), "%Y-%m-%d")
    return "{} {}".format(day.day, day.strftime("%b"))


def render(text, values):
    """Fill {placeholders} from values; an unknown one is left as written, so a typo shows rather than vanishes."""
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
                  str(text or ""))


def deadline_of(topic):
    deadline = (topic or {}).get("deadline")
    return deadline if isinstance(deadline, dict) and deadline.get("days") else None


def missed(topic, row, now):
    """
    What happens if nobody decides in time, for an open case, or None (no clock, or already decided).
    `banner` is the sentence shown first to approvers; `card` the short label on the board.
    """
    deadline = deadline_of(topic)
    due = store.parse_dt(row.get("Due_At"))
    if not deadline or not due or row.get("Status") in FINISHED:
        return None
    outcome = deadline.get("outcome") or "none"
    left = deadlines.days_left(due, now)
    values = {"date": long_date(due), "short_date": short_date(due)}
    banner = render(deadline.get("banner") or deadline.get("if_missed") or "", values)
    card = render(deadline.get("card") or ("due {short_date}"), values)
    if left < 0 and outcome in ("deemed_approved", "not_agreed"):
        banner = "No decision by {}: now {} ({}).".format(values["date"], OUTCOME_WORDS[outcome],
                                                       deadline.get("citation") or "")
    return {"outcome": outcome, "due_at": deadlines.iso_utc(due), "date_text": values["date"], "days_left": left,
            "urgent": left <= URGENT_DAYS, "banner": banner, "card": card, "citation": deadline.get("citation") or "",
            "extendable": bool(deadline.get("extend_to_days")) and not is_extended(topic, row) and left >= 0,
            "extended": is_extended(topic, row)}


def is_extended(topic, row):
    """Extended once already: the clock runs later than the topic's normal days from lodging."""
    created, due = store.created_utc(row), store.parse_dt(row.get("Due_At"))
    first = due_for(topic, created) if created else None
    return bool(first and due and due > first)


def missed_line(topic, row, now):
    """The first line of an email to approvers, or None."""
    info = missed(topic, row, now)
    if not info or not info["banner"]:
        return None
    return "IF NOBODY DECIDES: {}{}".format(info["banner"], " ({})".format(info["citation"]) if info["citation"]
                                           else "")


def due_for(topic, created_utc):
    """When a new case's clock runs out, or None."""
    deadline = deadline_of(topic)
    if not deadline:
        return None
    return deadlines.due_at(created_utc, deadline["days"], bool(deadline.get("business_day")))


def extended_due(topic, created_utc):
    deadline = deadline_of(topic) or {}
    days = deadline.get("extend_to_days")
    return deadlines.due_at(created_utc, days, bool(deadline.get("business_day"))) if days else None


# ---------- what a handler sees ----------

def button_out(button):
    email = button.get("email") or {}
    return {"key": button.get("key"), "label": button.get("label"), "next": button.get("next"),
            "to": email.get("to") or "", "note": button.get("note") or "",
            "note_label": button.get("note_label") or "", "needs_decision": bool(button.get("needs_decision")),
            "opens_vote": bool(button.get("opens_vote")), "extends": bool(button.get("extends"))}


def view(db, building, ctx, topic, row):
    """The current stage for the case page: what to do, who does it, and the buttons this person may press."""
    stage = current(topic, row)
    allowed = committee.may_act(db, building, ctx, stage.get("owner"))
    stages = of(topic)
    return {"key": stage.get("key"), "label": stage.get("label"), "owner": committee.resolve(building, stage.get("owner")),
            "owner_label": committee.owner_label(building, stage.get("owner")),
            "instructions": stage.get("instructions") or "", "rule": stage.get("rule") or "",
            "allowed": allowed, "buttons": [button_out(b) for b in stage.get("buttons") or []],
            "path": [{"key": s.get("key"), "label": s.get("label")} for s in stages],
            "index": stages.index(stage)}


def plus_days(when, days):
    return when + timedelta(days=days)
