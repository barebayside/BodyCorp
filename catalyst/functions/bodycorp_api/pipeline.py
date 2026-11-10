"""
The committee's working view: the board, the stage buttons, and the clock running out.

    board   GET /board        every open request the person handles, in columns by stage;
                              each card says who acts next and what happens if nobody decides
    action  POST /case/action press one of the current stage's buttons:
                              check the presser holds the stage's position  ->  extend / open a vote
                              ->  send the button's email (queued if it fails)  ->  move the stage
                              ->  log it (and show the resident what they were sent)
    deemed  daily (cron)      a case past its deadline whose topic says deemed_approved or
                              not_agreed is decided by the law: recorded and the resident told
                              (SM s 58(7), s 69(3)-(4); law file §5-6, §8 rules 28, 31, 33)

Which buttons exist, their wording and where they lead are the topic's data (stages.py).
"""

import re

import buildings
import cases
import committee
import mailer
import people
import stages
import store
import topics
from errors import bad, forbidden

OPEN = ("new", "in_progress", "waiting_on_resident", "with_committee", "decided")
MAX_NOTE = 5000


# ---------- the board ----------

def _columns(topic_list):
    """
    Every stage of these topics, merged in order. A stage new to the list goes just before the next
    stage of its own topic that is already there (so a records "preparing" lands before "done").
    """
    order, labels = [], {}
    for topic in topic_list:
        keys = [s.get("key") for s in stages.of(topic)]
        for i, stage in enumerate(stages.of(topic)):
            key = keys[i]
            labels.setdefault(key, stage.get("label") or key)
            if key in order:
                continue
            later = next((k for k in keys[i + 1:] if k in order), None)
            order.insert(order.index(later) if later else len(order), key)
    return order, labels


def card(db, building, row, topic, labels, now, votes_by_case):
    stage = stages.current(topic, row)
    missed = stages.missed(topic, row, now)
    summary = cases.summary(row, labels, now)
    summary.update(stage=stage.get("key"), stage_label=stage.get("label"), topic_label=topic.get("label"),
                   owner_label=committee.owner_label(building, stage.get("owner")),
                   missed_label=missed["card"] if missed else "", missed=missed,
                   urgent=bool(missed and missed["urgent"]), vote=votes_by_case.get(str(row["ROWID"])))
    return summary


def board(db, building, ctx, now=None, open_votes=None):
    """Columns of open cases for the stages of the topics this person handles. Closed cases leave the board."""
    if not ctx["can"]["handle"]:
        raise forbidden("Only the committee or building manager has a board.")
    now = now or store.utc_now()
    every = {t["key"]: t for t in topics.all_topics(db, building)}
    pinned = topics.case_lookup(db, building)
    rows = [r for r in db.find(store.CASES, {"Building_Id": int(building["id"])})
            if cases.handles(ctx, r) and r.get("Status") != "closed"]
    mine = [t for t in every.values() if t["active"] and cases.handles(ctx, {"Handler": t["handler"]})]
    mine += [every[k] for k in {r.get("Topic_Key") for r in rows} if k in every and every[k] not in mine]
    order, names = _columns(sorted(mine, key=lambda t: (t["sort"], t["label"])))
    labels = buildings.unit_labels(db, building)
    columns = {key: [] for key in order}
    for row in rows:
        topic = pinned(row) or {"label": row.get("Title"), "handler": row.get("Handler")}
        item = card(db, building, row, topic, labels, now, open_votes or {})
        columns.setdefault(item["stage"], []).append(item)
        if item["stage"] not in order:
            order.append(item["stage"])
            names[item["stage"]] = item["stage_label"]

    def urgency(item):
        left = item["days_left"]
        return (0 if item["urgent"] else 1, left if left is not None else 10 ** 6, -int(item["id"]))

    closed = sum(1 for r in db.find(store.CASES, {"Building_Id": int(building["id"])})
                 if cases.handles(ctx, r) and r.get("Status") == "closed")
    return {"columns": [{"key": k, "label": names.get(k, k), "cards": sorted(columns[k], key=urgency)}
                        for k in order if not (k == "done" and not columns[k])],
            "closed": closed, "module_note": committee.module_note(building, ctx)}


# ---------- pressing a button ----------

def _values(db, building, row, topic, note, sender, staff_link, decision=None):
    lodger = db.get(store.USERS, row.get("User_Id")) or {}
    missed = stages.missed(topic, row, store.utc_now())
    due = store.parse_dt(row.get("Due_At"))
    return {"name": (lodger.get("Name") or "").split(" ")[0] or "there", "ref": row.get("Ref") or "",
            "title": row.get("Title") or "", "unit": buildings.unit_labels(db, building).get(str(row.get("Unit_Id")), ""),
            "building": building["name"], "link": cases.case_link(building, row, staff_link),
            "date": stages.long_date(due) if due else "", "if_missed": missed["banner"] if missed else "",
            "note": note, "note_line": "\n" + note if note else "", "sender": sender,
            "decision": "\n".join(cases.decision_lines(decision)) if decision else ""}


def recipients(db, building, row, to):
    if to == "resident":
        return [cases._resident_email(db, row)]
    if to == "voting":
        return committee.emails_of(db, committee.voting_ids(db, building))
    if to == "committee":
        return committee.emails_of(db, committee.committee_ids(db, building))
    if to == "manager":
        return people.emails_with_roles(db, building, ("manager",))
    return []


def send_button_email(db, building, row, topic, email, note, sender, now, decision=None):
    """The button's email, from the topic's template. Anyone but the resident reads the deadline line first."""
    to = email.get("to")
    values = _values(db, building, row, topic, note, sender, to != "resident", decision)
    subject = stages.render(email.get("subject"), values)[:200]
    body = stages.render(email.get("body") or "", values)
    lines = [part.strip() for part in body.split("\n\n")]
    first = stages.missed_line(topic, row, now) if to != "resident" else None
    html = mailer.page(building, subject, ([first] if first else []) + lines,
                       "See your request" if to == "resident" else "Open the request", link=values["link"])
    sent = 0
    addresses = recipients(db, building, row, to)
    for address in addresses:
        sent += 1 if mailer.send(db, address, "{}: {}".format(building["name"], subject), html,
                                 building=building) else 0
    # The same people's phones, one line each (the subject already starts with the ref). Never raises.
    if to == "resident":
        cases.push_resident(db, building, row, subject)
    else:
        cases.push_handlers(db, building, row, addresses, subject)
    # The copy kept on the request leaves out the link: the reader is already looking at it.
    record = re.sub(r"\n{3,}", "\n\n", stages.render(email.get("body") or "", dict(values, link=""))).strip()
    return record, sent


def action(db, building, ctx, case_id, key, note, now=None, open_vote=None):
    """
    Press a button on the case's current stage. `open_vote(row, words)` opens a vote outside a
    meeting (votes.py, passed in to keep the modules one-way).
    """
    now = now or store.utc_now()
    row = cases.load(db, building, ctx, case_id)
    cases._handler_only(ctx, row)
    topic = topics.for_case(db, building, row) or {}
    stage = stages.current(topic, row)
    button = next((b for b in stage.get("buttons") or [] if b.get("key") == key), None)
    if not button:
        raise bad("That button isn't on this step any more. Reload the page.")
    if not committee.may_act(db, building, ctx, stage.get("owner")):
        raise forbidden("This step is for the {}.".format(committee.owner_label(building, stage.get("owner")).lower()))
    note = str(note or "").strip()
    if button.get("note") == "required" and not note:
        raise bad("Please fill in: {}".format(button.get("note_label") or "the note"))
    if len(note) > MAX_NOTE:
        raise bad("That note is too long.")
    decision = cases._json(row.get("Decision"), {}) or None
    if button.get("needs_decision") and not decision:
        raise bad("Record the decision first.")
    sender = ctx["user"].get("name") or ctx["user"].get("email")
    done = []
    if button.get("extends"):
        done.append(_extend(db, building, row, topic, now))
        row = db.get(store.CASES, row["ROWID"])
    if button.get("opens_vote"):
        if row.get("Status") in ("decided", "closed"):
            raise bad("This request is already decided.")
        if open_vote is None:
            raise bad("Votes aren't available here.")
        words = stages.render(button.get("motion") or "That the committee approve request {ref}.{note_line}",
                              _values(db, building, row, topic, note, sender, True))
        open_vote(row, words)
        done.append("opened a vote outside a meeting")
    if button.get("email"):
        body, sent = send_button_email(db, building, row, topic, button["email"], note, sender, now, decision)
        who = {"resident": "the resident", "voting": "the voting members", "committee": "the committee",
               "manager": "the building manager"}[button["email"]["to"]]
        done.append("emailed {}".format(who) if sent else "email to {} queued (it will be retried)".format(who))
        if button["email"]["to"] == "resident":
            cases._event(db, building, row["ROWID"], ctx["user_id"], "message", body, False)
    move = stages.find(topic, button.get("next")) or stage
    change = {"ROWID": row["ROWID"], "Stage": move.get("key")}
    status = button.get("status") or (move.get("status") if move is not stage else None)
    if status and not (row.get("Status") == "decided" and status not in ("decided", "closed")):
        change["Status"] = status
    db.update(store.CASES, change)
    moved = "moved to {}".format(move.get("label")) if move is not stage else "stayed at {}".format(stage.get("label"))
    cases._event(db, building, row["ROWID"], ctx["user_id"], "action",
                 "{}: {}; {}.".format(button.get("label"), "; ".join(done) or "no email", moved), True)
    return cases.detail(db, building, ctx, row["ROWID"], now)


def _extend(db, building, row, topic, now):
    """An owner motion's decision period, extended once by written notice before it ends (SM s 58(3))."""
    new_due = stages.extended_due(topic, store.created_utc(row))
    due = store.parse_dt(row.get("Due_At"))
    if not new_due or not due:
        raise bad("This request's deadline can't be extended.")
    if stages.is_extended(topic, row):
        raise bad("The deadline has already been extended once.")
    if now > due:
        raise bad("The deadline has passed; it can only be extended before it ends (SM s 58(3)).")
    db.update(store.CASES, {"ROWID": row["ROWID"], "Due_At": store.fmt_dt(new_due)})
    return "deadline extended to {}".format(stages.long_date(new_due))


# ---------- the clock running out ----------

def apply_deemed(db, now=None):
    """Decide every open case whose deadline has passed and whose topic says what silence means. Returns how many."""
    now = now or store.utc_now()
    count = 0
    for building in (buildings.from_row(r) for r in db.find(store.BUILDINGS)):
        pinned = topics.case_lookup(db, building)
        for row in db.find(store.CASES, {"Building_Id": int(building["id"])}):
            topic = pinned(row)
            due = store.parse_dt(row.get("Due_At"))
            deadline = stages.deadline_of(topic) or {}
            outcome = deadline.get("outcome")
            if (not topic or not due or due > now or outcome not in ("deemed_approved", "not_agreed")
                    or row.get("Status") in ("decided", "closed")):
                continue
            reason = "No decision by {} ({}).".format(stages.long_date(due), deadline.get("citation") or "")
            cases.apply_decision(db, building, row, outcome, reason, "", "", now, {"deemed": True})
            count += 1
    return count
