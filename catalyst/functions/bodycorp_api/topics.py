"""
Topics: what a resident can ask for, as JSON data per building.

A topic says who may use it (owner/tenant), who handles it (committee/manager),
which fields the form asks, the steps to work through and any legal clock:

    {"label": "Keep a pet", "audience": ["owner", "tenant"], "handler": "committee", "draft": true,
     "intro": "...", "fields": [{"key": "animal", "label": "What animal?", "type": "text", "required": true}],
     "deadline": {"days": 21, "if_missed": "..."}, "steps": [{"title": "...", "rule": "..."}]}

A new building, or a new business on the same kit, changes these rows, not code.

THE COMMITTEE PIPELINE (2026-11-10, all optional, so older topics still load)
    "deadline": {"days": 21, "business_day": true, "outcome": "deemed_approved" | "not_agreed" | "none",
                 "card": "auto-approves after {short_date}", "banner": "If ... by {date}, ... APPROVED.",
                 "citation": "SM s 58A(2), s 69(3)(b)", "extend_to_days": 84, "if_missed": "..."}
    "vote": {"animal": true, "if_passed": "approved", "if_defeated": null, "if_no_result": "deemed_approved"}
    "after_decision": "decided"          the stage a case moves to once decided
    "stages": [{"key", "label", "owner" (a duty or role), "status", "instructions", "rule",
                "buttons": [{"key", "label", "next", "note": "" | "optional" | "required", "note_label",
                             "needs_decision", "opens_vote", "motion", "extends",
                             "email": {"to": "resident" | "committee" | "voting" | "manager",
                                       "subject", "body"}}]}]
    Email placeholders: {name} {ref} {title} {unit} {building} {link} {date} {if_missed} {note} {decision} {sender}.
    An email to anyone but the resident starts with the "if nobody decides" line (stages.missed_line).
"""

import json
import re

import store
from errors import bad

FIELD_TYPES = ("text", "textarea", "date", "select", "checkbox", "file")
CASE_STATUSES = ("new", "in_progress", "waiting_on_resident", "with_committee", "decided", "closed")
DEEMED = ("deemed_approved", "not_agreed", "none")
DECISIONS = ("approved", "approved_with_conditions", "refused", "deemed_approved", "not_agreed")
RECIPIENTS = ("resident", "committee", "voting", "manager")
NOTE_KINDS = ("", "optional", "required")
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
            "stages": d.get("stages") or [], "vote": d.get("vote") or {}, "after_decision": d.get("after_decision") or "",
            "active": _active(row), "sort": int(row.get("Sort") or 0), "id": str(row["ROWID"])}


def _rows(db, building):
    return db.find(store.TOPICS, {"Building_Id": int(building["id"])})


def all_topics(db, building):
    return sorted((from_row(r) for r in _rows(db, building)), key=lambda t: (t["sort"], t["label"]))


def public(topic):
    return {k: topic[k] for k in ("key", "label", "intro", "fields", "draft", "deadline")}


def for_member(db, building, ctx, now=None):
    """Active topics (as in force now) this person may use. Handlers see every topic, to know what residents see."""
    relations = ctx["relations"]
    out = []
    for topic in current(db, building, now or store.utc_now()):
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
        if not _days(days):
            raise bad("A deadline needs a number of days between 1 and 366.")
        if (deadline.get("outcome") or "none") not in DEEMED:
            raise bad("A deadline's outcome is deemed_approved, not_agreed or none.")
        extend = deadline.get("extend_to_days")
        if extend is not None and not (_days(extend) and extend > days):
            raise bad("extend_to_days must be more days than the deadline.")
    _check_stages(definition)
    vote = definition.get("vote")
    if vote is not None:
        if not isinstance(vote, dict):
            raise bad("vote must be an object.")
        for key in ("if_passed", "if_defeated", "if_no_result"):
            if vote.get(key) not in (None,) + DECISIONS:
                raise bad("vote.{} must be a decision or null.".format(key))


def _days(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 366


def _check_stages(definition):
    stages = definition.get("stages")
    if stages is None:
        return
    if not isinstance(stages, list) or not stages:
        raise bad("stages must be a list with at least one stage.")
    keys = [s.get("key") if isinstance(s, dict) else None for s in stages]
    if any(not KEY.match(str(k or "")) for k in keys) or len(set(keys)) != len(keys):
        raise bad("Each stage needs its own key (lower-case letters, numbers, - or _).")
    for stage in stages:
        if not str(stage.get("label") or "").strip():
            raise bad("Stage {} needs a label.".format(stage["key"]))
        if stage.get("status") is not None and stage["status"] not in CASE_STATUSES:
            raise bad("Stage {} has an unknown status.".format(stage["key"]))
        buttons = stage.get("buttons") or []
        if not isinstance(buttons, list) or len({b.get("key") for b in buttons if isinstance(b, dict)}) != len(buttons):
            raise bad("Stage {}: each button needs its own key.".format(stage["key"]))
        for button in buttons:
            where = "Stage {}, button {}".format(stage["key"], button.get("key"))
            if not KEY.match(str(button.get("key") or "")) or not str(button.get("label") or "").strip():
                raise bad(where + " needs a key and a label.")
            if button.get("next") not in keys:
                raise bad(where + ": next must be one of the stages.")
            if (button.get("note") or "") not in NOTE_KINDS:
                raise bad(where + ": note is optional or required.")
            email = button.get("email")
            if email is not None and (not isinstance(email, dict) or email.get("to") not in RECIPIENTS
                                      or not str(email.get("subject") or "").strip()):
                raise bad(where + ": an email needs to (resident, committee, voting or manager) and a subject.")
    after = definition.get("after_decision")
    if after and after not in keys:
        raise bad("after_decision must be one of the stages.")


# ---------- versions: a request is pinned to the rules in force when it was lodged ----------
#
# Topic_Versions holds every version of a request type (made by the AI helper's Apply, an undo, or an admin
# edit once a type has history). Cases.Topic_Version is the version in force when a case was lodged; a case
# without one (lodged before any history) uses the "baseline" version, the lowest. A type with no versions
# at all is simply its Topics row, as before.

def _stamp(now):
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _live_version(row):
    return row.get("Active") not in (False, "false", 0, "0")


def versions_of(db, building, key=None):
    where = {"Building_Id": int(building["id"])}
    if key:
        where["Topic_Key"] = key
    return db.find(store.TOPIC_VERSIONS, where)


def in_force(versions, key, stamp):
    """The version row of `key` in force at `stamp` (UTC text), or None: latest Effective_From <= stamp."""
    live = [v for v in versions if v.get("Topic_Key") == key and _live_version(v)
            and str(v.get("Effective_From"))[:19] <= stamp]
    return max(live, key=lambda v: (str(v["Effective_From"])[:19], int(v["Version"]))) if live else None


def as_topic(live, version_row, key):
    """A topic (the from_row shape) carrying a version's settings, with the live row's id and sort."""
    fake = {"Topic_Key": key, "Definition": version_row.get("Definition"),
            "Active": version_row.get("Topic_Active") not in (False, "false", 0, "0"),
            "Sort": (live or {}).get("sort") or 0, "ROWID": (live or {}).get("id") or version_row.get("ROWID")}
    topic = from_row(fake)
    topic["version"] = int(version_row["Version"])
    return topic


def pinned(live, versions, row):
    """The topic as it was for this case (see above). `live` is get()'s answer, `versions` that type's rows."""
    key = row.get("Topic_Key")
    mine = [v for v in versions if v.get("Topic_Key") == key]
    if not mine:
        return live
    want = store.as_id(row.get("Topic_Version"))
    if want:
        match = [v for v in mine if int(v["Version"]) == want]
        if match:
            return as_topic(live, match[0], key)
    first = min(mine, key=lambda v: int(v["Version"]))
    return as_topic(live, first, key)


def for_case(db, building, row):
    """The topic a case runs under (its pinned version), or None."""
    key = row.get("Topic_Key")
    return pinned(get(db, building, key), versions_of(db, building, key), row)


def case_lookup(db, building):
    """A function row -> pinned topic, reading the building's topics and versions once (for boards and jobs)."""
    every = {t["key"]: t for t in all_topics(db, building)}
    versions = versions_of(db, building)
    return lambda row: pinned(every.get(row.get("Topic_Key")), versions, row)


def for_new_case(db, building, key, now):
    """(topic in force now, its version number or None) for a request being lodged."""
    live = get(db, building, key)
    version = in_force(versions_of(db, building, key), key, _stamp(now))
    if version is None:
        return live, None
    return as_topic(live, version, key), int(version["Version"])


def current(db, building, now):
    """Every topic as in force now: the Topics row, or the version in force if the daily job hasn't copied it yet."""
    versions = versions_of(db, building)
    out = []
    for topic in all_topics(db, building):
        version = in_force(versions, topic["key"], _stamp(now))
        out.append(as_topic(topic, version, topic["key"]) if version else topic)
    have = {t["key"] for t in out}
    for key in sorted({v.get("Topic_Key") for v in versions} - have):
        version = in_force(versions, key, _stamp(now))
        if version:
            out.append(as_topic(None, version, key))
    return sorted(out, key=lambda t: (t["sort"], t["label"]))


def note_version(db, building, key, definition, active, source, user_id, now, note=""):
    """
    Once a type has versions, an edit made outside the AI helper (an admin, a seed upgrade) is recorded as a
    new version in force now, so the daily job never copies an older version back over it.
    """
    versions = versions_of(db, building, key)
    if not versions:
        return None
    row = {"Building_Id": int(building["id"]), "Topic_Key": key,
           "Version": max(int(v["Version"]) for v in versions) + 1, "Definition": json.dumps(definition),
           "Effective_From": _stamp(now), "Source": source, "Topic_Active": active is not False, "Active": True,
           "Note": str(note or "")[:255]}
    if store.as_id(user_id):
        row["Created_By"] = int(user_id)
    return db.insert(store.TOPIC_VERSIONS, row)


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
