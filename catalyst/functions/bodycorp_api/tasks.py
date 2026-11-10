"""
Tasks: what a resolution asks someone to do, with a due date.

    create   a committee member makes one, usually from a passed motion: assigned to a person on the
             committee or to a position (whoever holds it), due on a date
    mine     open tasks assigned to me or to a position I hold ("My tasks")
    done     ticked off by the assignee, a position holder, or the person who made it
    remind   the daily reminders list tasks due within 7 days or overdue for each assignee

Committee business: residents and the building manager never see tasks (403).
"""

from datetime import datetime

import committee
import deadlines
import store
from errors import bad, forbidden, not_found

MAX_DETAIL = 2000


def _row(db, building, task_id):
    row = db.get(store.TASKS, task_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That task wasn't found.")
    return row


def _done(row):
    return row.get("Done") in (True, "true", 1, "1")


def assigned_to_me(ctx, row):
    if str(row.get("Assignee_User_Id") or "") == ctx["user_id"]:
        return True
    position = row.get("Assignee_Position") or ""
    return bool(position) and (position in ctx["roles"] or (position == "voting" and ctx["cmt"]["voting"]))


def out(db, building, ctx, row, now):
    due = store.parse_dt(row.get("Due_At"))
    user = db.get(store.USERS, row.get("Assignee_User_Id")) if row.get("Assignee_User_Id") else None
    who = ((user or {}).get("Name") or (user or {}).get("Email")) if user else committee.POSITION_LABELS.get(
        row.get("Assignee_Position") or "", row.get("Assignee_Position") or "")
    left = deadlines.days_left(due, now) if due else None
    return {"id": str(row["ROWID"]), "title": row.get("Title"), "detail": row.get("Detail") or "",
            "assignee": who or "", "position": row.get("Assignee_Position") or "",
            "due_at": deadlines.iso_utc(due), "due_date": deadlines.brisbane_date(due) if due else None,
            "days_left": left, "urgent": left is not None and left <= 3 and not _done(row), "done": _done(row),
            "mine": assigned_to_me(ctx, row), "motion_id": str(row.get("Motion_Id") or "") or None,
            "case_id": str(row.get("Case_Id") or "") or None, "meeting_id": str(row.get("Meeting_Id") or "") or None}


def listing(db, building, ctx, scope="mine", now=None):
    committee.require_committee(ctx)
    now = now or store.utc_now()
    rows = db.find(store.TASKS, {"Building_Id": int(building["id"])})
    if scope != "all":
        rows = [r for r in rows if assigned_to_me(ctx, r)]
    items = [out(db, building, ctx, r, now) for r in rows]
    items.sort(key=lambda t: (t["done"], t["days_left"] if t["days_left"] is not None else 10 ** 6, t["title"]))
    return {"tasks": items, "people": [{"user_id": m["user_id"], "name": m["name"] or m["email"]}
                                       for m in committee.members(db, building)],
            "positions": [{"key": k, "label": committee.POSITION_LABELS[k]}
                          for k in committee.POSITIONS + ("committee",)]}


def _link(db, building, table, value):
    number = store.as_id(value)
    if not value:
        return None
    row = db.get(table, number) if number else None
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That link wasn't found.")
    return number


def create(db, building, ctx, title, detail, due_date, assignee_user_id, assignee_position, motion_id=None,
           case_id=None, meeting_id=None, now=None):
    committee.require_committee(ctx)
    now = now or store.utc_now()
    title = str(title or "").strip()
    if not title or len(title) > 255:
        raise bad("Give the task a short title (255 characters at most).")
    detail = str(detail or "").strip()
    if len(detail) > MAX_DETAIL:
        raise bad("That detail is too long.")
    row = {"Building_Id": int(building["id"]), "Title": title, "Detail": detail, "Done": False,
           "Created_By": int(ctx["user_id"])}
    uid = str(store.as_id(assignee_user_id) or "")
    if uid:
        if uid not in {m["user_id"] for m in committee.members(db, building)}:
            raise bad("Assign it to someone on the committee, or to a position.")
        row["Assignee_User_Id"] = int(uid)
    else:
        position = assignee_position or committee.resolve(building, "tasks")
        if position not in committee.POSITIONS + ("committee", "voting"):
            raise bad("Unknown position.")
        row["Assignee_Position"] = position
    if due_date:
        try:
            day = datetime.strptime(str(due_date), "%Y-%m-%d")
        except ValueError:
            raise bad("The due date looks wrong.")
        row["Due_At"] = store.fmt_dt(deadlines.due_at(day.replace(hour=2), 0))   # end of that Brisbane day
    for column, table, value in (("Motion_Id", store.MOTIONS, motion_id), ("Case_Id", store.CASES, case_id),
                                 ("Meeting_Id", store.MEETINGS, meeting_id)):
        linked = _link(db, building, table, value)
        if linked:
            row[column] = linked
    made = db.insert(store.TASKS, row)
    return {"task": out(db, building, ctx, made, now)}


def set_done(db, building, ctx, task_id, done, now=None):
    committee.require_committee(ctx)
    now = now or store.utc_now()
    row = _row(db, building, task_id)
    if not (assigned_to_me(ctx, row) or str(row.get("Created_By")) == ctx["user_id"] or "admin" in ctx["roles"]):
        raise forbidden("Only the person it's assigned to can tick it off.")
    done = done in (True, "true", 1, "1")
    change = {"ROWID": row["ROWID"], "Done": done}
    if done:
        change["Done_At"] = store.fmt_dt(now)
    db.update(store.TASKS, change)
    return {"task": out(db, building, ctx, dict(row, **change), now)}


def due_lines(db, building, now):
    """{email: [line]} for open tasks due within 7 days or overdue, for the daily digest."""
    lines = {}
    for row in db.find(store.TASKS, {"Building_Id": int(building["id"])}):
        due = store.parse_dt(row.get("Due_At"))
        if _done(row) or not due or deadlines.days_left(due, now) > deadlines.SOON_DAYS:
            continue
        left = deadlines.days_left(due, now)
        when = "OVERDUE by {} day(s)".format(-left) if left < 0 else ("due TODAY" if left == 0 else
                                                                       "due in {} day(s)".format(left))
        ids = [str(row["Assignee_User_Id"])] if row.get("Assignee_User_Id") else committee.holders(
            db, building, row.get("Assignee_Position") or "secretary")
        for email in committee.emails_of(db, ids):
            lines.setdefault(email, []).append("Task: {} · {}".format(row.get("Title"), when))
    return lines
