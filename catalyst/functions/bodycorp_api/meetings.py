"""
Committee meetings and their minutes. Law file §4 (SM s 54-71) and §8 rules 9-11, 15-17, 20-22.

    call      the secretary (duty "notices") sets a time at least 7 CLEAR days ahead (2, only when
              every voting member agreed: the agreement is recorded) (SM s 55(2); AIA s 38(1)(a)).
              The agenda always starts with confirming the last minutes and each vote outside a
              meeting since (SM s 57(3)). Notice to every committee member, advice to owners at the
              same time, with when, where and the agenda (SM s 55(1), (3)-(4)).
    attend    who came and how: in person, electronically, by proxy (held by a voting member who
              is there; one each, SM s 122(1)-(2)), or absent. Quorum = half the voting members,
              rounded up; a proxy holder counts 2; unfinancial members count; the committee (no
              vote) members don't (SM s 60).
    vote      the chair records each motion's votes. No quorum, no decision (SM s 65(3)). Passes on
              more yes than no among those voting; a tie is lost (SM s 65(2)). Conflicted and
              unfinancial members don't vote (SM s 64, s 66).
    close     the minutes are drafted from the meeting (every SM s 71(6) item) and are due 21 days
              after the meeting (SM s 71(2)-(4)).
    issue     blocked until the secretary's name and contact address exist (SM s 71(6)). Goes to
              committee members and owners, and into Documents (owners). Passed motions can then be
              acted on after the 7-day opposition window if the building is under the Standard Module
              (SM s 72-73).
"""

import json
from datetime import datetime, timedelta, timezone

import cases
import committee
import content
import deadlines
import mailer
import stages
import store
import topics
import votes
from errors import bad, forbidden, not_found

HOW = ("present", "electronic", "proxy", "absent")
HOW_LABELS = {"present": "in person", "electronic": "by phone or video", "proxy": "by proxy", "absent": "absent"}
MAX_ITEMS = 30
CLEAR_DAYS, SHORT_DAYS = 7, 2
MINUTES_DAYS = 21


# ---------- time ----------

def parse_local(text):
    """'YYYY-MM-DDTHH:MM' in Brisbane -> naive UTC, or None."""
    try:
        local = datetime.strptime(str(text or "").strip()[:16].replace(" ", "T"), "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return local.replace(tzinfo=deadlines.BRISBANE).astimezone(timezone.utc).replace(tzinfo=None)


def local_text(utc):
    """'Tue 1 Dec 2026, 6:00 pm' in Brisbane."""
    when = utc.replace(tzinfo=timezone.utc).astimezone(deadlines.BRISBANE)
    hour = when.strftime("%I").lstrip("0") or "12"
    return "{} {} {} {}, {}:{} {}".format(when.strftime("%a"), when.day, when.strftime("%b"), when.year, hour,
                                         when.strftime("%M"), when.strftime("%p").lower())


def clear_days(now, starts):
    """Whole days between the notice day and the meeting day, both left out (AIA s 38(1)(a))."""
    give = now.replace(tzinfo=timezone.utc).astimezone(deadlines.BRISBANE).date()
    meet = starts.replace(tzinfo=timezone.utc).astimezone(deadlines.BRISBANE).date()
    return (meet - give).days - 1


# ---------- loading ----------

def load(db, building, ctx, meeting_id):
    committee.require_committee(ctx)
    row = db.get(store.MEETINGS, meeting_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That meeting wasn't found.")
    return row


def _may_run(db, building, ctx):
    return any(committee.may_act(db, building, ctx, duty) for duty in ("chair_meetings", "notices", "minutes"))


def _require_run(db, building, ctx):
    if not _may_run(db, building, ctx):
        raise forbidden("Only the chair, secretary or minute-taker can do that.")


def _agenda(row):
    return cases._json(row.get("Agenda"), [])


def _attendance(row):
    return cases._json(row.get("Attendance"), {})


def _names(db, ids):
    return {i: (db.get(store.USERS, i) or {}) for i in set(ids)}


# ---------- quorum ----------

def quorum(db, building, attendance):
    """SM s 60: half the voting members, rounded up. Proxy holders count 2; non-voting members don't."""
    voting = set(committee.voting_ids(db, building))
    rows = attendance.get("people") or []
    present = {r["user_id"] for r in rows if r.get("how") in ("present", "electronic") and r["user_id"] in voting}
    proxies = {r["user_id"]: r.get("proxy_holder") for r in rows
               if r.get("how") == "proxy" and r.get("proxy_holder") in present and r["user_id"] in voting}
    needed = (len(voting) + 1) // 2
    count = len(present) + len(proxies)
    return {"voting": len(voting), "needed": needed, "present": count, "ok": bool(voting) and count >= needed,
            "present_ids": sorted(present), "proxies": proxies}


# ---------- calling a meeting ----------

def _previous(db, building, before):
    rows = [r for r in db.find(store.MEETINGS, {"Building_Id": int(building["id"])})
            if r.get("Status") == "closed" and store.parse_dt(r.get("Starts_At")) < before]
    return max(rows, key=lambda r: store.parse_dt(r.get("Starts_At"))) if rows else None


def _on_other_agenda(db, building):
    """VOCM ids already listed on a meeting that hasn't happened yet."""
    ids = set()
    for row in db.find(store.MEETINGS, {"Building_Id": int(building["id"])}):
        if row.get("Status") != "closed":
            ids |= {i.get("vocm_id") for i in _agenda(row) if i.get("vocm_id")}
    return ids


def _motion(db, building, meeting_id, words, case_id=None, exempt=""):
    row = {"Building_Id": int(building["id"]), "Meeting_Id": int(meeting_id), "Kind": "meeting",
           "Words": words[:votes.MAX_WORDS], "Status": "pending", "Exempt": exempt, "Animal": False}
    if case_id:
        row["Case_Id"] = int(case_id)
        topic = topics.for_case(db, building, db.get(store.CASES, case_id) or {}) or {}
        if (topic.get("vote") or {}).get("animal"):
            row.update(Animal=True, Exempt="animal")
    return db.insert(store.MOTIONS, row)


def _case_in(db, building, ctx, case_id):
    if not case_id:
        return None
    row = cases.load(db, building, ctx, case_id)
    cases._handler_only(ctx, row)
    return row


def create(db, building, ctx, title, starts_at, place, items, short_notice, now=None):
    now = now or store.utc_now()
    committee.require_committee(ctx)
    if not committee.may_act(db, building, ctx, "notices"):
        raise forbidden("Committee meetings are called by the {} (SM s 54(1)).".format(
            committee.owner_label(building, "notices").lower()))
    starts = parse_local(starts_at)
    if not starts:
        raise bad("Pick the date and time of the meeting.")
    short_notice = str(short_notice or "").strip()[:255]
    need = SHORT_DAYS if short_notice else CLEAR_DAYS
    if clear_days(now, starts) < need:
        earliest = (now.replace(tzinfo=timezone.utc).astimezone(deadlines.BRISBANE).date()
                    + timedelta(days=need + 1))
        raise bad("A committee meeting needs at least {} clear days' notice (SM s 55(2)). The earliest date is {} {} {}."
                  .format(need, earliest.day, earliest.strftime("%b"), earliest.year) +
                  ("" if short_notice else " Only 2 days if every voting member agreed in writing."))
    title = str(title or "").strip()[:255] or "Committee meeting"
    place = str(place or "").strip()[:255]
    items = items if isinstance(items, list) else []
    if len(items) > MAX_ITEMS:
        raise bad("At most {} agenda items.".format(MAX_ITEMS))
    clean = []
    for item in items:
        item = item if isinstance(item, dict) else {"text": item}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if len(text) > 500:
            raise bad("Keep each agenda item under 500 characters; put the detail in the motion.")
        clean.append({"text": text, "motion": str(item.get("motion") or "").strip(),
                      "case": _case_in(db, building, ctx, item.get("case_id"))})
    row = db.insert(store.MEETINGS, {"Building_Id": int(building["id"]), "Title": title,
                                     "Starts_At": store.fmt_dt(starts), "Place": place, "Status": "scheduled",
                                     "Short_Notice": short_notice, "Agenda": "[]", "Attendance": "{}",
                                     "Minutes_Status": "none", "Created_By": int(ctx["user_id"])})
    agenda = []
    previous = _previous(db, building, starts)
    if previous and previous.get("Minutes_Status") != "confirmed":
        when = stages.long_date(store.parse_dt(previous["Starts_At"]))
        m = _motion(db, building, row["ROWID"], "That the minutes of the committee meeting of {} be confirmed as a "
                                               "true record.".format(when))
        agenda.append({"kind": "confirm_minutes", "text": "Confirm the minutes of the meeting of {}".format(when),
                       "motion_id": str(m["ROWID"]), "meeting_id": str(previous["ROWID"])})
    listed = _on_other_agenda(db, building)
    for vocm in sorted(db.find(store.MOTIONS, {"Building_Id": int(building["id"]), "Kind": "vocm"}),
                       key=lambda r: int(r["ROWID"])):
        if vocm.get("Status") in ("open", "pending") or vocm.get("Confirmed_Meeting_Id") or str(vocm["ROWID"]) in listed:
            continue
        when = stages.long_date(store.parse_dt(vocm.get("Decided_At")) or now)
        words = "That the result of the vote outside a meeting decided {} ({}) on the motion “{}” be " \
                "confirmed.".format(when, votes.STATUS_LABELS.get(vocm.get("Status"), "").lower(), vocm.get("Words"))
        m = _motion(db, building, row["ROWID"], words)
        agenda.append({"kind": "confirm_vocm", "text": "Confirm the vote outside a meeting of {}".format(when),
                       "motion_id": str(m["ROWID"]), "vocm_id": str(vocm["ROWID"])})
    for item in clean:
        entry = {"kind": "item", "text": item["text"]}
        if item["case"]:
            entry["case_id"] = str(item["case"]["ROWID"])
        if item["motion"]:
            entry["motion_id"] = str(_motion(db, building, row["ROWID"], item["motion"],
                                             entry.get("case_id"))["ROWID"])
        agenda.append(entry)
    text = json.dumps(agenda)
    if len(text) > store.TEXT_MAX:
        raise bad("The agenda is too long.")
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Agenda": text, "Notice_Sent_At": store.fmt_dt(now)})
    row = db.get(store.MEETINGS, row["ROWID"])
    _send_notice(db, building, row, agenda)
    return detail(db, building, ctx, row["ROWID"], now)


def _meeting_link(building, row):
    base = mailer.portal_link(building)
    return "{}#/meeting/{}".format(base, row["ROWID"]) if base else ""


def _send_notice(db, building, row, agenda):
    when = local_text(store.parse_dt(row["Starts_At"]))
    lines = ["When: {}".format(when), "Where: {}".format(row.get("Place") or "to be confirmed"), "Agenda:"]
    lines += ["{}. {}".format(i + 1, item["text"]) for i, item in enumerate(agenda)] or ["(no items yet)"]
    if row.get("Short_Notice"):
        lines.append("Short notice: every voting member agreed ({}).".format(row["Short_Notice"]))
    html = mailer.page(building, row.get("Title") or "Committee meeting", lines, "Open the meeting",
                       link=_meeting_link(building, row))
    for email in committee.emails_of(db, committee.committee_ids(db, building)):
        mailer.send(db, email, "{}: committee meeting {}".format(building["name"], when), html, building=building)
    owners = lines + ["Owners may attend and observe if they tell the secretary in writing at least 24 hours "
                      "before (SM s 63)."]
    mailer.send_many(db, content.audience_emails(db, building, "owners"),
                     "{}: committee meeting {} (advice to owners)".format(building["name"], when),
                     mailer.page(building, row.get("Title") or "Committee meeting", owners, "Open the portal"),
                     building=building)


# ---------- reading ----------

def summary(row, now):
    starts = store.parse_dt(row.get("Starts_At"))
    due = store.parse_dt(row.get("Minutes_Due_At"))
    return {"id": str(row["ROWID"]), "title": row.get("Title"), "starts_at": deadlines.iso_utc(starts),
            "when": local_text(starts) if starts else "", "place": row.get("Place") or "",
            "status": row.get("Status"), "minutes_status": row.get("Minutes_Status") or "none",
            "minutes_due": stages.long_date(due) if due else "",
            "minutes_days_left": deadlines.days_left(due, now) if due and row.get("Minutes_Status") == "draft" else None}


def listing(db, building, ctx, now=None):
    committee.require_committee(ctx)
    now = now or store.utc_now()
    rows = sorted(db.find(store.MEETINGS, {"Building_Id": int(building["id"])}),
                  key=lambda r: store.parse_dt(r.get("Starts_At")), reverse=True)
    return {"meetings": [summary(r, now) for r in rows],
            "can_call": committee.may_act(db, building, ctx, "notices"),
            "module_note": committee.module_note(building, ctx)}


def detail(db, building, ctx, meeting_id, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, meeting_id)
    attendance = _attendance(row)
    team = committee.members(db, building)
    q = quorum(db, building, attendance)
    agenda = []
    for item in _agenda(row):
        entry = dict(item)
        if item.get("motion_id"):
            motion = db.get(store.MOTIONS, item["motion_id"])
            entry["motion"] = votes.out(db, building, ctx, motion, now) if motion else None
        if item.get("case_id"):
            case_row = db.get(store.CASES, item["case_id"])
            entry["case_ref"] = (case_row or {}).get("Ref")
        agenda.append(entry)
    out = summary(row, now)
    starts = store.parse_dt(row.get("Starts_At"))
    sent = store.parse_dt(row.get("Notice_Sent_At"))
    out.update(agenda=agenda, attendance=attendance.get("people") or [], others=attendance.get("others") or "",
               quorum=q, members=team, minutes=row.get("Minutes") or "",
               short_notice=row.get("Short_Notice") or "",
               notice_text="Notice sent {}, {} clear days before.".format(
                   stages.long_date(sent), clear_days(sent, starts)) if sent and starts else "",
               can_run=_may_run(db, building, ctx), can_minute=committee.may_act(db, building, ctx, "minutes"),
               secretary_ready=bool(_secretary(db, building)[1]), doc_id=str(row.get("Doc_Id") or "") or None,
               module_note=committee.module_note(building, ctx))
    return {"meeting": out}


# ---------- at the meeting ----------

def record_attendance(db, building, ctx, meeting_id, people_rows, others, now=None):
    row = load(db, building, ctx, meeting_id)
    _require_run(db, building, ctx)
    if row.get("Status") == "closed":
        raise bad("This meeting is closed.")
    members = {m["user_id"] for m in committee.members(db, building)}
    voting = set(committee.voting_ids(db, building))
    clean, holders = [], set()
    for item in people_rows if isinstance(people_rows, list) else []:
        uid = str(store.as_id((item or {}).get("user_id")) or "")
        how = (item or {}).get("how")
        if uid not in members or how not in HOW:
            raise bad("Each person needs one of: in person, by phone or video, by proxy, absent.")
        entry = {"user_id": uid, "how": how}
        if how == "proxy":
            holder = str(store.as_id(item.get("proxy_holder")) or "")
            if uid not in voting:
                raise bad("Only a voting member can appoint a proxy.")
            if holder not in voting or holder == uid:
                raise bad("A proxy must be another voting member (SM s 122(1)).")
            if holder in holders:
                raise bad("A voting member can hold only one proxy at a meeting (SM s 122(2)(b)).")
            holders.add(holder)
            entry["proxy_holder"] = holder
        clean.append(entry)
    for entry in clean:
        if entry.get("proxy_holder") and not any(e["user_id"] == entry["proxy_holder"]
                                                 and e["how"] in ("present", "electronic") for e in clean):
            raise bad("A proxy holder has to be at the meeting.")
    text = json.dumps({"people": clean, "others": str(others or "").strip()[:2000]})
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Attendance": text, "Status": "open"})
    return detail(db, building, ctx, row["ROWID"], now)


def add_motion(db, building, ctx, meeting_id, words, case_id, exempt, now=None):
    row = load(db, building, ctx, meeting_id)
    _require_run(db, building, ctx)
    if row.get("Status") == "closed":
        raise bad("This meeting is closed.")
    words = str(words or "").strip()
    if not words:
        raise bad("Write the motion: the exact words voted on.")
    if exempt not in votes.EXEMPT:
        raise bad("Unknown exemption.")
    case_row = _case_in(db, building, ctx, case_id)
    motion = _motion(db, building, row["ROWID"], words, case_row["ROWID"] if case_row else None, exempt)
    agenda = _agenda(row) + [{"kind": "item", "text": words[:200], "motion_id": str(motion["ROWID"]),
                              "case_id": str(case_row["ROWID"]) if case_row else None, "added": True}]
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Agenda": json.dumps(agenda)})
    return detail(db, building, ctx, row["ROWID"], now)


def record_votes(db, building, ctx, motion_id, given, now=None):
    """The chair records each member's vote on one motion. Quorum first; a tie is lost."""
    now = now or store.utc_now()
    motion = votes.load(db, building, ctx, motion_id)
    if motion.get("Kind") != "meeting":
        raise bad("That isn't a meeting motion.")
    meeting = load(db, building, ctx, motion.get("Meeting_Id"))
    _require_run(db, building, ctx)
    if meeting.get("Status") != "open":
        raise bad("Record who attended first." if meeting.get("Status") == "scheduled" else "This meeting is closed.")
    if motion.get("Status") != "pending":
        raise bad("The votes on this motion are already recorded.")
    q = quorum(db, building, _attendance(meeting))
    if not q["ok"]:
        raise bad("No quorum: {} counted, {} needed. The committee can't decide anything (SM s 60, s 65(3))."
                  .format(q["present"], q["needed"]))
    debt = committee.unfinancial(building)
    may = (set(q["present_ids"]) | set(q["proxies"])) - debt
    given = given if isinstance(given, dict) else {}
    ballots = []
    for uid, vote in given.items():
        uid = str(store.as_id(uid) or "")
        if vote in (None, "", "none"):
            continue
        if uid not in may:
            raise bad("Only voting members at the meeting (or represented by proxy) who are entitled can vote "
                      "(SM s 64, s 65).")
        if vote not in votes.VOTES + ("conflict",):
            raise bad("Each vote is yes, no, abstain or conflict.")
        ballots.append(db.insert(store.BALLOTS, {"Motion_Id": int(motion["ROWID"]), "Building_Id": int(building["id"]),
                                                 "User_Id": int(uid), "Vote": vote, "Conflict": vote == "conflict",
                                                 "Note": ""}))
    if not ballots:
        raise bad("Record at least one vote.")
    counts = votes.tally(sorted(may), ballots)
    result = votes.meeting_result(counts)
    db.update(store.MOTIONS, {"ROWID": motion["ROWID"], "Eligible": json.dumps(sorted(may)),
                              "Opened_At": store.fmt_dt(now)})
    votes.finish(db, building, db.get(store.MOTIONS, motion["ROWID"]), result, counts, ballots, now)
    if result == "passed":
        _confirmations(db, building, meeting, motion)
    return detail(db, building, ctx, meeting["ROWID"], now)


def _confirmations(db, building, meeting, motion):
    for item in _agenda(meeting):
        if item.get("motion_id") != str(motion["ROWID"]):
            continue
        if item.get("kind") == "confirm_vocm":
            db.update(store.MOTIONS, {"ROWID": item["vocm_id"], "Confirmed_Meeting_Id": int(meeting["ROWID"])})
        if item.get("kind") == "confirm_minutes":
            db.update(store.MEETINGS, {"ROWID": item["meeting_id"], "Minutes_Status": "confirmed"})


def close(db, building, ctx, meeting_id, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, meeting_id)
    _require_run(db, building, ctx)
    if row.get("Status") != "open":
        raise bad("Record who attended first." if row.get("Status") == "scheduled" else "Already closed.")
    starts = store.parse_dt(row["Starts_At"])
    change = {"ROWID": row["ROWID"], "Status": "closed", "Closed_At": store.fmt_dt(now), "Minutes_Status": "draft",
              "Minutes_Due_At": store.fmt_dt(deadlines.due_at(starts, MINUTES_DAYS))}
    db.update(store.MEETINGS, change)
    row = dict(row, **change)
    text = draft_minutes(db, building, row, now)
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Minutes": text[:store.TEXT_MAX]})
    return detail(db, building, ctx, row["ROWID"], now)


# ---------- minutes ----------

def _secretary(db, building):
    """(names, contact address) for the minutes (SM s 71(6)(j))."""
    ids = committee.holders(db, building, "secretary")
    names = [(db.get(store.USERS, i) or {}).get("Name") or (db.get(store.USERS, i) or {}).get("Email") for i in ids]
    contact = ((building.get("settings") or {}).get("secretary_contact") or "").strip()
    return ", ".join(n for n in names if n), contact if names else ""


def _answers_line(db, building, case_row):
    topic = topics.for_case(db, building, case_row) or {}
    answers = cases._json(case_row.get("Answers"), {})
    parts = []
    for field in topic.get("fields") or []:
        value = answers.get(field["key"])
        if field.get("type") == "file" or value in (None, "", False):
            continue
        parts.append("{}: {}".format(field.get("label"), "Yes" if value is True else value))
    return "; ".join(parts)


def draft_minutes(db, building, row, now):
    """Every SM s 71(6) item, from what the meeting recorded. The minute-taker edits before issuing."""
    starts = store.parse_dt(row["Starts_At"])
    attendance = _attendance(row)
    team = {m["user_id"]: m for m in committee.members(db, building)}
    q = quorum(db, building, attendance)

    def who(uid):
        member = team.get(uid) or {}
        return "{}, {}".format(member.get("name") or member.get("email") or "?", member.get("label") or "")

    present = [who(p["user_id"]) + " — " + HOW_LABELS[p["how"]] for p in attendance.get("people") or []
               if p["how"] in ("present", "electronic")]
    absent = [who(p["user_id"]) for p in attendance.get("people") or [] if p["how"] == "absent"]
    proxies = ["{} held a proxy for {}".format(who(p["proxy_holder"]), who(p["user_id"]))
               for p in attendance.get("people") or [] if p["how"] == "proxy"]
    lines = ["MINUTES — {}, {}".format(row.get("Title"), building["name"]),
             "DRAFT — check every item before issuing. Guidance, checked by your advisors.", "",
             "1. Date, time and place: {}, {}".format(local_text(starts), row.get("Place") or "(place)"),
             "2. Present: " + ("; ".join(present) or "(nobody recorded)")]
    if absent:
        lines.append("   Absent: " + "; ".join(absent))
    if attendance.get("others"):
        lines.append("   Also attending: " + attendance["others"])
    lines.append("3. Proxies tabled: " + ("; ".join(proxies) or "none"))
    lines.append("   Quorum: {} counted, {} needed — {}.".format(q["present"], q["needed"],
                                                               "quorum present" if q["ok"] else "NO QUORUM"))
    owner_motions, animals, motions = [], [], []
    for n, item in enumerate(i for i in _agenda(row) if i.get("motion_id")):
        motion = db.get(store.MOTIONS, item["motion_id"]) or {}
        counts = cases._json(motion.get("Tally"), {})
        if motion.get("Status") in ("passed", "lost"):
            result = "CARRIED" if motion["Status"] == "passed" else (
                "LOST (tied: no casting vote)" if counts.get("yes") == counts.get("no") else "LOST")
            motions.append("   Motion {}: “{}” — For {}, Against {}, Abstained {}{}. {}".format(
                n + 1, motion.get("Words"), counts.get("yes", 0), counts.get("no", 0), counts.get("abstain", 0),
                ", conflicts declared {}".format(counts["conflicts"]) if counts.get("conflicts") else "", result))
        else:
            motions.append("   Motion {}: “{}” — not dealt with.".format(n + 1, motion.get("Words")))
        case_row = db.get(store.CASES, motion.get("Case_Id")) if motion.get("Case_Id") else None
        if case_row:
            lodger = db.get(store.USERS, case_row.get("User_Id")) or {}
            lodged = stages.long_date(store.created_utc(case_row)) if store.created_utc(case_row) else ""
            decision = cases._json(case_row.get("Decision"), {})
            if motion.get("Animal") in (True, "true"):
                animals.append("   {} — requested {}; {}{}".format(
                    case_row.get("Ref"), lodged, _answers_line(db, building, case_row),
                    "; conditions: " + decision["conditions"] if decision.get("conditions") else ""))
            else:
                owner_motions.append("   {} ({}) — submitted {} by {}{}".format(
                    case_row.get("Ref"), case_row.get("Title"), lodged, lodger.get("Name") or lodger.get("Email") or "",
                    "; decision period extended" if stages.is_extended(
                        topics.for_case(db, building, case_row) or {}, case_row) else ""))
    lines.append("4. Owner motions: " + ("" if owner_motions else "none"))
    lines += owner_motions
    lines.append("5. Animal requests: " + ("" if animals else "none"))
    lines += animals
    lines.append("6. Motions and votes:" + ("" if motions else " none"))
    lines += motions
    lines.append("7. Correspondence, reports and documents tabled: (add here)")
    closed = store.parse_dt(row.get("Closed_At"))
    lines.append("8. Meeting closed at: {}".format(local_text(closed) if closed else "(time)"))
    later = [r for r in db.find(store.MEETINGS, {"Building_Id": int(building["id"])})
             if store.parse_dt(r.get("Starts_At")) > starts and r.get("Status") != "closed"]
    lines.append("9. Next meeting: {}".format(
        local_text(store.parse_dt(min(later, key=lambda r: r["Starts_At"])["Starts_At"])) if later else "not yet set"))
    names, contact = _secretary(db, building)
    lines.append("10. Secretary: {}, {}".format(names or "(secretary's name)", contact or "(contact address)"))
    return "\n".join(lines)


def save_minutes(db, building, ctx, meeting_id, text, now=None):
    row = load(db, building, ctx, meeting_id)
    if not committee.may_act(db, building, ctx, "minutes"):
        raise forbidden("Only the minute-taker can edit the minutes.")
    if row.get("Minutes_Status") != "draft":
        raise bad("Only draft minutes can be edited.")
    text = str(text or "").strip()
    if not text:
        raise bad("The minutes are empty.")
    if len(text) > store.TEXT_MAX:
        raise bad("The minutes are too long ({:,} characters at most).".format(store.TEXT_MAX))
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Minutes": text})
    return detail(db, building, ctx, row["ROWID"], now)


def issue_minutes(db, building, ctx, meeting_id, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, meeting_id)
    if not committee.may_act(db, building, ctx, "minutes"):
        raise forbidden("Only the minute-taker can issue the minutes.")
    if row.get("Minutes_Status") != "draft":
        raise bad("These minutes aren't a draft.")
    names, contact = _secretary(db, building)
    if not names or not contact:
        raise bad("Minutes must give the secretary's name and contact address (SM s 71(6)). Give someone the "
                  "secretary position and add the contact address in Committee settings.")
    text = row.get("Minutes") or ""
    if "(secretary's name)" in text or "(contact address)" in text:
        raise bad("Fill in item 10: the secretary's name and contact address.")
    starts = store.parse_dt(row["Starts_At"])
    day = deadlines.brisbane_date(starts)
    key = "docs/{}/minutes-{}-{}.txt".format(building["id"], day, row["ROWID"])
    db.put_file(key, text.replace("DRAFT — check every item before issuing. ", "").encode("utf-8"),
                "text/plain; charset=utf-8")
    doc = db.insert(store.DOCS, {"Building_Id": int(building["id"]), "User_Id": int(ctx["user_id"]),
                                 "Title": "Committee meeting minutes, {}".format(stages.long_date(starts)),
                                 "Category": "Minutes", "Audience": "owners", "File_Key": key,
                                 "File_Name": "minutes-{}.txt".format(day)})
    db.update(store.MEETINGS, {"ROWID": row["ROWID"], "Minutes_Status": "issued",
                               "Minutes_Issued_At": store.fmt_dt(now), "Doc_Id": int(doc["ROWID"])})
    for item in _agenda(row):
        motion = db.get(store.MOTIONS, item["motion_id"]) if item.get("motion_id") else None
        if motion and motion.get("Status") == "passed":
            act = votes._act_from(building, motion, now)
            if act:
                db.update(store.MOTIONS, dict(act, ROWID=motion["ROWID"]))
    lines = ["The minutes of the committee meeting of {} are in Documents.".format(stages.long_date(starts))]
    if committee.module(building) == "standard":
        lines.append("Owners of at least half the lots may oppose a committee resolution by notice to the secretary "
                     "within 7 days (SM s 72).")
    html = mailer.page(building, "Committee meeting minutes", lines, "Open Documents")
    emails = set(committee.emails_of(db, committee.committee_ids(db, building)))
    emails |= set(content.audience_emails(db, building, "owners"))
    mailer.send_many(db, sorted(emails), "{}: committee meeting minutes".format(building["name"]), html,
                     building=building)
    return detail(db, building, ctx, row["ROWID"], now)


def minutes_due(db, building, now):
    """[(days left, meeting row)] for draft minutes due within 7 days or overdue, for the daily reminders."""
    out = []
    for row in db.find(store.MEETINGS, {"Building_Id": int(building["id"])}):
        due = store.parse_dt(row.get("Minutes_Due_At"))
        if row.get("Minutes_Status") == "draft" and due and deadlines.days_left(due, now) <= deadlines.SOON_DAYS:
            out.append((deadlines.days_left(due, now), row))
    return out
