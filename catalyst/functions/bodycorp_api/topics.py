"""
Topics: what a resident can ask for, as JSON data per building.

A topic says who may use it (owner/tenant), who handles it (committee/manager),
which fields the form asks, the steps to work through and any legal clock:

    {"label": "Keep a pet", "audience": ["owner", "tenant"], "handler": "committee", "draft": true,
     "intro": "...", "fields": [{"key": "animal", "label": "What animal?", "type": "text", "required": true}],
     "deadline": {"days": 21, "if_missed": "..."}, "steps": [{"title": "...", "rule": "..."}]}

A new building, or a new business on the same kit, changes these rows, not code.
"""

import json
import re

import store
from errors import bad

FIELD_TYPES = ("text", "textarea", "date", "select", "checkbox", "file")
HANDLERS = ("committee", "manager")
KEY = re.compile(r"^[a-z0-9_-]{1,60}$")


def _definition(row):
    try:
        value = json.loads(row.get("Definition") or "{}")
    except (TypeError, ValueError):
        value = {}
    return value if isinstance(value, dict) else {}


def _active(row):
    return row.get("Active") not in (False, "false", 0, "0")


def from_row(row):
    d = _definition(row)
    return {"key": row.get("Topic_Key"), "label": d.get("label") or row.get("Topic_Key"),
            "intro": d.get("intro") or "", "fields": d.get("fields") or [], "draft": bool(d.get("draft")),
            "deadline": d.get("deadline") or None, "audience": d.get("audience") or [],
            "handler": d.get("handler") or "manager", "steps": d.get("steps") or [],
            "active": _active(row), "sort": int(row.get("Sort") or 0), "id": str(row["ROWID"])}


def _rows(db, building):
    return db.find(store.TOPICS, {"Building_Id": int(building["id"])})


def all_topics(db, building):
    return sorted((from_row(r) for r in _rows(db, building)), key=lambda t: (t["sort"], t["label"]))


def public(topic):
    return {k: topic[k] for k in ("key", "label", "intro", "fields", "draft", "deadline")}


def for_member(db, building, ctx):
    """Active topics this person may use. Handlers see every topic, to know what residents see."""
    relations = ctx["relations"]
    out = []
    for topic in all_topics(db, building):
        if topic["active"] and (ctx["can"]["handle"] or relations & set(topic["audience"])):
            out.append(public(topic))
    return out


def get(db, building, key):
    """One topic by key (active or not, so old cases still show their topic), or None."""
    for row in _rows(db, building):
        if row.get("Topic_Key") == key:
            return from_row(row)
    return None


def _check_field(field, seen):
    if not isinstance(field, dict) or not KEY.match(str(field.get("key") or "")):
        raise bad("Each field needs a key (lower-case letters, numbers, - or _).")
    if field["key"] in seen:
        raise bad("Field keys must be different: {}".format(field["key"]))
    if field.get("type") not in FIELD_TYPES:
        raise bad("Field {} has an unknown type.".format(field["key"]))
    if not str(field.get("label") or "").strip():
        raise bad("Field {} needs a label.".format(field["key"]))
    if field["type"] == "select" and not (isinstance(field.get("options"), list) and field["options"]):
        raise bad("Field {} needs options.".format(field["key"]))
    seen.add(field["key"])


def check_definition(definition):
    """Refuse a definition the forms or cases couldn't use."""
    if not isinstance(definition, dict) or not str(definition.get("label") or "").strip():
        raise bad("A topic needs a label.")
    if definition.get("handler") not in HANDLERS:
        raise bad("Handler must be committee or manager.")
    audience = definition.get("audience")
    if not isinstance(audience, list) or not audience or not set(audience) <= {"owner", "tenant"}:
        raise bad("Audience must list owner and/or tenant.")
    seen = set()
    for field in definition.get("fields") or []:
        _check_field(field, seen)
    for step in definition.get("steps") or []:
        if not isinstance(step, dict) or not str(step.get("title") or "").strip():
            raise bad("Each step needs a title.")
    deadline = definition.get("deadline")
    if deadline is not None:
        days = deadline.get("days") if isinstance(deadline, dict) else None
        if not isinstance(days, int) or isinstance(days, bool) or not 0 < days <= 366:
            raise bad("A deadline needs a number of days between 1 and 366.")


def save(db, building, key, definition, active=True, sort=0):
    """Add or replace one topic by key."""
    key = str(key or "").strip().lower()
    if not KEY.match(key):
        raise bad("A topic key is lower-case letters, numbers, - or _.")
    check_definition(definition)
    row = {"Building_Id": int(building["id"]), "Topic_Key": key, "Definition": json.dumps(definition),
           "Active": active is not False, "Sort": int(sort or 0)}
    existing = [r for r in _rows(db, building) if r.get("Topic_Key") == key]
    if existing:
        db.update(store.TOPICS, dict(row, ROWID=existing[0]["ROWID"]))
    else:
        db.insert(store.TOPICS, row)
