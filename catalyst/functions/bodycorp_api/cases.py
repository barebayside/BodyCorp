"""
Cases: a resident's tracked request, from lodging to decision.

    create  ->  Ref ALT-0042, handler and steps from the topic, legal clock started, handlers emailed
    handle  ->  tick steps, change status, message (to the resident, or an internal note), decide

WHO SEES A CASE
    A handler: anyone with the case's handler role (committee or manager), or an admin.
    A resident: the person who lodged it, or an approved OWNER of its unit, and only
    while their own membership of that unit is still approved. Everyone else gets 404,
    the same answer as a case that doesn't exist, so ids can't be probed.

Every change is also written to Events, which is the permanent record.
"""

import json
import logging
import re

import buildings
import deadlines
import mailer
import store
import topics
import uploads
from errors import bad, forbidden, not_found

logger = logging.getLogger("bodycorp_api.cases")

STATUSES = ("new", "in_progress", "waiting_on_resident", "with_committee", "decided", "closed")
STATUS_LABELS = {"new": "New", "in_progress": "In progress", "waiting_on_resident": "Waiting on you",
                 "with_committee": "With the committee", "decided": "Decided", "closed": "Closed"}
OUTCOMES = ("approved", "approved_with_conditions", "refused")
MAX_ANSWER = 4000
MAX_MESSAGE = 5000


# ---------- lodging ----------

def _clean_value(field, value):
    kind = field.get("type")
    if kind == "checkbox":
        return value in (True, "true", "on", "yes", 1)
    text = str(value if value is not None else "").strip()
    if len(text) > MAX_ANSWER:
        raise bad("{} is too long.".format(field.get("label")))
    if kind == "date" and text and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise bad("{} needs a date.".format(field.get("label")))
    if kind == "select" and text and text not in [str(o) for o in field.get("options") or []]:
        raise bad("Choose one of the options for {}.".format(field.get("label")))
    return text


def clean_answers(topic, answers, files):
    """
    Answers for the topic's own fields only (anything else is dropped), with required
    fields enforced. A file may name its field; otherwise it belongs to the first file field.
    """
    answers = answers if isinstance(answers, dict) else {}
    files = files if isinstance(files, list) else []
    file_fields = [f["key"] for f in topic["fields"] if f.get("type") == "file"]
    if files and not file_fields:
        raise bad("This form doesn't take files.")
    if len(files) > uploads.MAX_FILES:
        raise bad("Attach at most {} files.".format(uploads.MAX_FILES))
    placed = []
    for item in files:
        field = (item or {}).get("field") if isinstance(item, dict) else None
        placed.append((field if field in file_fields else (file_fields[0] if file_fields else ""), item))
    out = {}
    for field in topic["fields"]:
        if field.get("type") == "file":
            if field.get("required") and not any(f == field["key"] for f, _ in placed):
                raise bad("Please attach: {}".format(field.get("label")))
            continue
        value = _clean_value(field, answers.get(field["key"]))
        if field.get("required") and value in ("", False):
            raise bad("Please fill in: {}".format(field.get("label")))
        out[field["key"]] = value
    return out, placed


def _next_number(db, building):
    biggest = 0
    for row in db.find(store.CASES, {"Building_Id": int(building["id"])}):
        tail = re.search(r"(\d+)$", str(row.get("Ref") or ""))
        biggest = max(biggest, int(tail.group(1)) if tail else 0)
    return biggest + 1


def _insert_with_ref(db, building, row):
    """Insert with the next free Ref; two lodged at once both get one."""
    prefix = str(building["settings"].get("ref_prefix") or "BC").upper()
    number = _next_number(db, building)
    for _ in range(5):
        ref = "{}-{:04d}".format(prefix, number)
        try:
            return db.insert(store.CASES, dict(row, Ref=ref))
        except Exception:  # noqa: BLE001 — a duplicate Ref raises; anything else is re-raised below
            if not db.find(store.CASES, {"Ref": ref}):
                raise
            number += 1
    raise bad("Couldn't number the request. Please send it again.")


def _save_files(db, building, case_row, decoded):
    saved, failed = [], 0
    for index, (field, data, kind, name) in enumerate(decoded):
        key = "cases/{}/{}/{}-{}".format(building["id"], case_row["ROWID"], index, name)
        try:
            db.put_file(key, data, kind)
        except Exception:  # noqa: BLE001 — the case is kept; the handler sees the gap in the record
            logger.exception("file upload failed for case %s", case_row["ROWID"])
            failed += 1
            continue
        saved.append({"name": name, "type": kind, "size": len(data), "key": key, "field": field})
    return saved, failed


def _event(db, building, case_id, user_id, kind, body, internal=False):
    return db.insert(store.EVENTS, {"Case_Id": int(case_id), "Building_Id": int(building["id"]),
                                    "User_Id": int(user_id), "Kind": kind, "Body": body, "Internal": internal})


def create(db, building, user, ctx, unit_id, topic_key, answers, files, now=None):
    now = now or store.utc_now()
    unit_id = str(store.as_id(unit_id) or "")
    if unit_id not in ctx["unit_ids"]:
        raise forbidden("You can't send requests for that unit yet.")
    topic = topics.get(db, building, str(topic_key or ""))
    relations = {m.get("Relation") for m in ctx["memberships"]
                 if m.get("Status") == "approved" and str(m.get("Unit_Id")) == unit_id}
    if not topic or not topic["active"] or not relations & set(topic["audience"]):
        raise not_found("That form wasn't found.")
    clean, placed = clean_answers(topic, answers, files)
    # Every file is read and checked before anything is saved.
    decoded = [(field,) + uploads.decode(item) for field, item in placed]
    row = {"Building_Id": int(building["id"]), "Unit_Id": int(unit_id), "User_Id": int(user["id"]),
           "Topic_Key": topic["key"], "Title": topic["label"][:255], "Status": "new", "Handler": topic["handler"],
           "Answers": json.dumps(clean), "Decision": "", "Files": "[]",
           "Steps": json.dumps([{"title": s.get("title"), "rule": s.get("rule") or "", "done": False}
                                for s in topic["steps"]])}
    if len(row["Answers"]) > store.TEXT_MAX:
        raise bad("Your answers are too long. Shorten them and send again.")
    days = (topic.get("deadline") or {}).get("days")
    if days:
        row["Due_At"] = store.fmt_dt(deadlines.due_at(now, days))
    case_row = _insert_with_ref(db, building, row)
    saved, failed = _save_files(db, building, case_row, decoded)
    if saved:
        db.update(store.CASES, {"ROWID": case_row["ROWID"], "Files": json.dumps(saved)})
        case_row = dict(case_row, Files=json.dumps(saved))
    _event(db, building, case_row["ROWID"], user["id"], "created", "Request lodged.")
    if failed:
        _event(db, building, case_row["ROWID"], user["id"], "note",
               "{} file(s) couldn't be saved. Ask the resident to send them again.".format(failed), True)
    _email_handlers(db, building, case_row, "New request {}".format(case_row["Ref"]),
                    ["{} for {}.".format(topic["label"], buildings.unit_labels(db, building).get(unit_id, ""))])
    out = detail(db, building, ctx, case_row["ROWID"], now)
    if failed:
        out["warning"] = "{} file(s) couldn't be saved. Please send them in a message.".format(failed)
    return out


# ---------- who may see and act ----------

def handles(ctx, row):
    return "admin" in ctx["roles"] or row.get("Handler") in ctx["roles"]


def resident_sees(ctx, row):
    unit = str(row.get("Unit_Id"))
    return unit in ctx["unit_ids"] and (str(row.get("User_Id")) == ctx["user_id"] or unit in ctx["owner_unit_ids"])


def load(db, building, ctx, case_id):
    """The case if this person may see it. Otherwise 404, never the case."""
    row = db.get(store.CASES, case_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That request wasn't found.")
    if not (handles(ctx, row) or resident_sees(ctx, row)):
        raise not_found("That request wasn't found.")
    return row


def _handler_only(ctx, row):
    if not handles(ctx, row):
        raise forbidden("Only the committee or building manager handling this can do that.")


# ---------- reading ----------

def _json(text, default):
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def summary(row, labels, now):
    due = store.parse_dt(row.get("Due_At"))
    return {"id": str(row["ROWID"]), "ref": row.get("Ref"), "title": row.get("Title"), "status": row.get("Status"),
            "status_label": STATUS_LABELS.get(row.get("Status"), row.get("Status")),
            "unit_id": str(row.get("Unit_Id")), "unit_label": labels.get(str(row.get("Unit_Id")), ""),
            "due_at": deadlines.iso_utc(due), "due_date": deadlines.brisbane_date(due) if due else None,
            "days_left": deadlines.days_left(due, now) if due else None, "handler": row.get("Handler"),
            "topic_key": row.get("Topic_Key"), "created": row.get("CREATEDTIME") or ""}


def _sorted(rows, labels, now):
    return [summary(r, labels, now) for r in sorted(rows, key=lambda r: -int(r["ROWID"]))]


def list_mine(db, building, ctx, now=None):
    now = now or store.utc_now()
    rows = []
    for unit in sorted(ctx["unit_ids"]):
        rows += [r for r in db.find(store.CASES, {"Building_Id": int(building["id"]), "Unit_Id": int(unit)})
                 if resident_sees(ctx, r)]
    return _sorted(rows, buildings.unit_labels(db, building), now)


def list_inbox(db, building, ctx, now=None):
    if not ctx["can"]["handle"]:
        raise forbidden("Only the committee or building manager has an inbox.")
    now = now or store.utc_now()
    rows = [r for r in db.find(store.CASES, {"Building_Id": int(building["id"])}) if handles(ctx, r)]
    return _sorted(rows, buildings.unit_labels(db, building), now)


def _events(db, row, ctx, is_handler, names):
    out = []
    for e in sorted(db.find(store.EVENTS, {"Case_Id": int(row["ROWID"])}), key=lambda e: int(e["ROWID"])):
        internal = e.get("Internal") in (True, "true", 1, "1")
        if internal and not is_handler:
            continue
        author = names.get(str(e.get("User_Id"))) or {}
        out.append({"id": str(e["ROWID"]), "kind": e.get("Kind"), "body": e.get("Body") or "",
                    "internal": internal, "at": e.get("CREATEDTIME") or "",
                    "author": author.get("Name") or author.get("Email") or "",
                    "from_resident": e.get("Kind") in ("created", "reply")})
    return out


def detail(db, building, ctx, case_id, now=None):
    """The case, its steps, its record (internal notes only for handlers) and its topic."""
    now = now or store.utc_now()
    row = load(db, building, ctx, case_id)
    is_handler = handles(ctx, row)
    topic = topics.get(db, building, row.get("Topic_Key")) or {"label": row.get("Title"), "fields": []}
    events_rows = db.find(store.EVENTS, {"Case_Id": int(row["ROWID"])})
    ids = {str(e.get("User_Id")) for e in events_rows} | {str(row.get("User_Id"))}
    names = {i: db.get(store.USERS, i) or {} for i in sorted(ids)}
    answers = _json(row.get("Answers"), {})
    steps = _json(row.get("Steps"), [])
    files = [{"n": i, "name": f.get("name"), "type": f.get("type"), "size": f.get("size"), "field": f.get("field")}
             for i, f in enumerate(_json(row.get("Files"), []))]
    lodger = names.get(str(row.get("User_Id"))) or {}
    case = dict(summary(row, buildings.unit_labels(db, building), now),
                answers=answers, files=files, steps=steps, decision=_json(row.get("Decision"), {}) or None,
                answers_list=[{"key": f["key"], "label": f.get("label"), "value": answers.get(f["key"])}
                              for f in topic.get("fields", []) if f["key"] in answers],
                lodged_by=lodger.get("Name") or lodger.get("Email") or "",
                lodged_by_email=lodger.get("Email") if is_handler else None,
                can_handle=is_handler, if_missed=(topic.get("deadline") or {}).get("if_missed"))
    return {"case": case, "steps": steps, "events": _events(db, row, ctx, is_handler, names),
            "topic": {k: topic.get(k) for k in ("key", "label", "intro", "fields", "draft", "deadline")}}


def file(db, building, ctx, case_id, n):
    """(bytes, type, name) of one attachment, under the same rule as seeing the case."""
    row = load(db, building, ctx, case_id)
    saved = _json(row.get("Files"), [])
    if not str(n).isdigit() or int(n) >= len(saved):
        raise not_found("That file wasn't found.")
    item = saved[int(n)]
    data = db.get_file(item.get("key"))
    if data is None:
        raise not_found("That file wasn't found.")
    return data, item.get("type") or "application/octet-stream", item.get("name") or "file"


# ---------- handling ----------

def _resident_email(db, row):
    return (db.get(store.USERS, row.get("User_Id")) or {}).get("Email") or ""


def _email_resident(db, building, row, heading, lines):
    subject = "{}: {} {}".format(building["name"], row.get("Ref"), heading)
    mailer.send(db, _resident_email(db, row), subject, mailer.page(building, heading, lines, "See your request"))


def _email_handlers(db, building, row, heading, lines):
    body = mailer.page(building, heading, lines, "Open the inbox")
    for email in deadlines.handler_emails(db, building, row.get("Handler")):
        mailer.send(db, email, "{}: {}".format(building["name"], heading), body)


def set_step(db, building, ctx, case_id, index, done, now=None):
    row = load(db, building, ctx, case_id)
    _handler_only(ctx, row)
    steps = _json(row.get("Steps"), [])
    position = int(index) if str(index).lstrip("-").isdigit() else -1
    if not 0 <= position < len(steps):
        raise bad("That step wasn't found.")
    steps[position]["done"] = done in (True, "true", 1, "1")
    db.update(store.CASES, {"ROWID": row["ROWID"], "Steps": json.dumps(steps)})
    _event(db, building, row["ROWID"], ctx["user_id"], "step",
           "{}: {}".format("Done" if steps[position]["done"] else "Not done", steps[position].get("title")), True)
    return detail(db, building, ctx, row["ROWID"], now)


def set_status(db, building, ctx, case_id, status, note, now=None):
    row = load(db, building, ctx, case_id)
    _handler_only(ctx, row)
    if status not in STATUSES:
        raise bad("Unknown status.")
    if status == "decided":
        raise bad("Record the decision to mark it decided.")
    note = str(note or "").strip()
    if len(note) > MAX_MESSAGE:
        raise bad("That note is too long.")
    db.update(store.CASES, {"ROWID": row["ROWID"], "Status": status})
    label = STATUS_LABELS[status]
    _event(db, building, row["ROWID"], ctx["user_id"], "status", "Status: {}{}".format(
        label, "\n" + note if note else ""))
    _email_resident(db, building, row, "is now: {}".format(label), [note])
    return detail(db, building, ctx, row["ROWID"], now)


def message(db, building, ctx, case_id, body, to_resident, now=None):
    """A handler's message (to the resident, or an internal note) or a resident's reply (never internal)."""
    row = load(db, building, ctx, case_id)
    body = str(body or "").strip()
    if not body:
        raise bad("Write a message first.")
    if len(body) > MAX_MESSAGE:
        raise bad("That message is too long.")
    if handles(ctx, row):
        to_resident = to_resident in (True, "true", 1, "1")
        event = _event(db, building, row["ROWID"], ctx["user_id"], "message", body, not to_resident)
        if to_resident:
            _email_resident(db, building, row, "has a new message", [body])
    else:
        event = _event(db, building, row["ROWID"], ctx["user_id"], "reply", body, False)
        _email_handlers(db, building, row, "Reply on {}".format(row.get("Ref")), [body])
    who = ctx["user"].get("name") or ctx["user"].get("email")
    return {"id": str(event["ROWID"]), "kind": event.get("Kind"), "body": body,
            "internal": event.get("Internal") is True, "at": event.get("CREATEDTIME") or "", "author": who,
            "from_resident": event.get("Kind") == "reply"}


def decide(db, building, ctx, case_id, outcome, reasons, conditions, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, case_id)
    _handler_only(ctx, row)
    reasons, conditions = str(reasons or "").strip(), str(conditions or "").strip()
    if outcome not in OUTCOMES:
        raise bad("Choose approved, approved with conditions, or refused.")
    if outcome == "refused" and not reasons:
        raise bad("A refusal needs reasons.")
    if outcome == "approved_with_conditions" and not conditions:
        raise bad("Write the conditions.")
    if len(reasons) > MAX_MESSAGE or len(conditions) > MAX_MESSAGE:
        raise bad("That's too long.")
    decision = {"outcome": outcome, "reasons": reasons, "conditions": conditions,
                "by": ctx["user_id"], "at": store.fmt_dt(now)}
    db.update(store.CASES, {"ROWID": row["ROWID"], "Status": "decided", "Decision": json.dumps(decision)})
    words = outcome.replace("_", " ").capitalize()
    lines = ["Decision: {}".format(words)]
    lines += ["Conditions: " + conditions] if conditions else []
    lines += ["Reasons: " + reasons] if reasons else []
    _event(db, building, row["ROWID"], ctx["user_id"], "decision", "\n".join(lines))
    _email_resident(db, building, row, "has been decided", lines)
    return detail(db, building, ctx, row["ROWID"], now)
