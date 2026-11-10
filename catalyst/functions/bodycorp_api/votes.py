"""
Motions and votes: outside a meeting (VOCM, "flying minute") and at a committee meeting.
Law file §4 "How decisions are made" and §5 (SM s 65-70), §8 rules 15-17 and 26-29.

OUTSIDE A MEETING (Kind "vocm")
    open    the secretary (duty "vocm", SM s 68(4)) sends the words to every committee member,
            and advice to owners at the same time (SM s 68(1), (3)). Closes 21 days after the
            notice, or 21 days after the REQUEST for an animal request (SM s 69(1)(b)).
    ballot  a voting member entitled to vote says yes, no or abstain, or declares a conflict
            and so has no vote (SM s 66, s 70). Unfinancial members can't vote (SM s 64, s 67).
    settle  E = entitled members at the start - declared conflicts.
            yes > E/2 -> passed;  no >= E/2 -> defeated  (both can happen before day 21)
            day 21 with neither -> not agreed, or deemed APPROVED for an animal request (SM s 69(3))
    after   the result goes onto the case (the topic's "vote" data says what each result means),
            the record of motions goes to committee members and owners (SM s 71(2)-(4), (6)),
            and it waits to be confirmed at the next meeting (SM s 68(5), s 57(3)(b)).

AT A MEETING (Kind "meeting") -- meetings.py records the votes
    Passes on a majority of the votes of those present and entitled who vote (SM s 65(2)).
    A tie is LOST: there is no casting vote. Needs a quorum (SM s 65(3)).

ACTING ON IT (Standard Module only, SM s 72-73)
    A passed motion can be acted on 7 days after its record or minutes go to owners, unless it is
    an animal approval, routine admin of $240 or less, or an emergency (Exempt). Under the
    Accommodation Module there is no such window. If the module isn't recorded, we say so.
"""

import json
from datetime import timedelta

import cases
import committee
import content
import deadlines
import mailer
import stages
import store
import topics
from errors import bad, forbidden, not_found

VOTES = ("yes", "no", "abstain")
EXEMPT = ("", "animal", "routine", "emergency")
OPEN_DAYS = 21
STATUS_LABELS = {"open": "Voting open", "passed": "Passed", "defeated": "Defeated", "not_agreed": "Not agreed (no result in time)",
                 "deemed_approved": "Deemed approved (no result in time)", "pending": "Not voted yet", "lost": "Lost"}
MAX_WORDS = 5000


def _json(text, default):
    return cases._json(text, default)


def load(db, building, ctx, motion_id):
    committee.require_committee(ctx)
    row = db.get(store.MOTIONS, motion_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That vote wasn't found.")
    return row


def _names(db, ids):
    return {i: (db.get(store.USERS, i) or {}) for i in sorted(set(ids))}


def _name(user):
    return user.get("Name") or user.get("Email") or "?"


# ---------- counting ----------

def tally(eligible, ballots):
    """Counts among the entitled. E = entitled - conflicted (SM s 69(2), s 70)."""
    eligible = {str(i) for i in eligible}
    counted = [b for b in ballots if str(b.get("User_Id")) in eligible]
    conflicts = sum(1 for b in counted if b.get("Conflict") in (True, "true"))
    votes = [b.get("Vote") for b in counted if b.get("Conflict") not in (True, "true")]
    entitled = len(eligible) - conflicts
    return {"yes": votes.count("yes"), "no": votes.count("no"), "abstain": votes.count("abstain"),
            "conflicts": conflicts, "entitled": entitled, "voted": len(counted), "needed_yes": entitled // 2 + 1}


def vocm_result(counts, closed, animal):
    """'passed', 'defeated', 'not_agreed', 'deemed_approved' or 'open'. Law file §5 decision logic."""
    entitled = counts["entitled"]
    if entitled > 0 and counts["yes"] * 2 > entitled:
        return "passed"
    if entitled > 0 and counts["no"] * 2 >= entitled:
        return "defeated"
    if closed:
        return "deemed_approved" if animal else "not_agreed"
    return "open"


def meeting_result(counts):
    """Majority of those who vote; a tie is lost (SM s 65(2); no casting vote)."""
    return "passed" if counts["yes"] > counts["no"] else "lost"


# ---------- reading ----------

def missed_text(row, with_citation=True):
    """What happens if the vote runs out of time (SM s 69(3)), in plain words; "" once decided."""
    closes = store.parse_dt(row.get("Closes_At"))
    if not closes or row.get("Status") != "open":
        return ""
    date = stages.long_date(closes)
    animal = row.get("Animal") in (True, "true")
    text = ("If the committee hasn't decided by the end of {}, this pet request is treated as APPROVED."
            if animal else "If not enough members vote yes by the end of {}, this motion is treated as NOT AGREED."
            ).format(date)
    return "{} ({})".format(text[:-1], missed_citation(row)) + "." if with_citation else text


def missed_citation(row):
    return "SM s 69(1)(b)(ii), s 69(3)(b)" if row.get("Animal") in (True, "true") else "SM s 69(3)(a)"


def act_note(building, row):
    if row.get("Status") != "passed":
        return ""
    act = store.parse_dt(row.get("Act_From"))
    if act:
        return "Can be acted on from {}.".format(stages.long_date(act))
    if row.get("Kind") == "meeting" and not row.get("Exempt"):
        return "The 7-day window for owners to oppose it starts when the minutes are issued (SM s 72-73)."
    if not committee.module(building):
        return "Module not recorded: check whether owners have 7 days to oppose it before acting (SM s 72-73)."
    return ""


def out(db, building, ctx, row, now, with_ballots=True):
    eligible = _json(row.get("Eligible"), [])
    ballots = db.find(store.BALLOTS, {"Motion_Id": int(row["ROWID"])})
    counts = tally(eligible, ballots) if row.get("Kind") == "vocm" else (_json(row.get("Tally"), {}) or
                                                                          tally(eligible, ballots))
    closes = store.parse_dt(row.get("Closes_At"))
    case = db.get(store.CASES, row.get("Case_Id")) if row.get("Case_Id") else None
    mine = next((b for b in ballots if str(b.get("User_Id")) == ctx["user_id"]), None)
    names = _names(db, [str(b.get("User_Id")) for b in ballots])
    item = {"id": str(row["ROWID"]), "kind": row.get("Kind"), "words": row.get("Words") or "",
            "status": row.get("Status"), "status_label": STATUS_LABELS.get(row.get("Status"), row.get("Status")),
            "animal": row.get("Animal") in (True, "true"), "exempt": row.get("Exempt") or "",
            "case_id": str(row.get("Case_Id") or "") or None, "case_ref": (case or {}).get("Ref"),
            "case_title": (case or {}).get("Title"), "meeting_id": str(row.get("Meeting_Id") or "") or None,
            "opened_at": deadlines.iso_utc(store.parse_dt(row.get("Opened_At"))),
            "closes_at": deadlines.iso_utc(closes), "closes_text": stages.long_date(closes) if closes else "",
            "days_left": deadlines.days_left(closes, now) if closes else None,
            "decided_at": deadlines.iso_utc(store.parse_dt(row.get("Decided_At"))),
            "missed": missed_text(row, False), "missed_citation": missed_citation(row) if row.get("Status") == "open" else "",
            "tally": counts, "act_note": act_note(building, row),
            "confirmed": bool(row.get("Confirmed_Meeting_Id")),
            "my_vote": ("conflict" if mine.get("Conflict") in (True, "true") else mine.get("Vote")) if mine else None,
            "can_vote": (row.get("Kind") == "vocm" and row.get("Status") == "open" and ctx["cmt"]["vote"]
                         and ctx["user_id"] in {str(i) for i in eligible})}
    item["urgent"] = item["days_left"] is not None and item["days_left"] <= stages.URGENT_DAYS and item["status"] == "open"
    if with_ballots:
        item["ballots"] = [{"name": _name(names.get(str(b.get("User_Id"))) or {}),
                            "vote": "conflict" if b.get("Conflict") in (True, "true") else b.get("Vote"),
                            "note": b.get("Note") or ""} for b in ballots]
    return item


def listing(db, building, ctx, now=None):
    committee.require_committee(ctx)
    now = now or store.utc_now()
    settle_building(db, building, now)
    rows = [r for r in db.find(store.MOTIONS, {"Building_Id": int(building["id"])}) if r.get("Kind") == "vocm"]
    rows.sort(key=lambda r: -int(r["ROWID"]))
    return {"votes": [out(db, building, ctx, r, now, False) for r in rows],
            "can_open": committee.may_act(db, building, ctx, "vocm"),
            "module_note": committee.module_note(building, ctx)}


def detail(db, building, ctx, motion_id, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, motion_id)
    row = settle(db, building, row, now) or row
    return {"vote": out(db, building, ctx, row, now)}


def open_for_case(db, building, case_id):
    """Open motions on a case, for the board and the case page."""
    return [r for r in db.find(store.MOTIONS, {"Building_Id": int(building["id"]), "Case_Id": int(case_id)})]


# ---------- opening a vote outside a meeting ----------

def open_vocm(db, building, ctx, words, case_id=None, exempt="", now=None):
    now = now or store.utc_now()
    committee.require_committee(ctx)
    if not committee.may_act(db, building, ctx, "vocm"):
        raise forbidden("Votes outside a meeting are sent by the {} (SM s 68(4)).".format(
            committee.owner_label(building, "vocm").lower()))
    words = str(words or "").strip()
    if not words:
        raise bad("Write the motion: the exact words the committee votes on.")
    if len(words) > MAX_WORDS:
        raise bad("That motion is too long.")
    if exempt not in EXEMPT:
        raise bad("Unknown exemption.")
    eligible = sorted(set(committee.voting_ids(db, building)) - committee.unfinancial(building))
    if not eligible:
        raise bad("There are no voting members entitled to vote yet. Give people committee positions first.")
    row = {"Building_Id": int(building["id"]), "Kind": "vocm", "Words": words, "Status": "open",
           "Opened_At": store.fmt_dt(now), "Eligible": json.dumps(eligible), "Created_By": int(ctx["user_id"]),
           "Exempt": exempt, "Animal": False}
    case_row, topic = None, None
    if case_id:
        case_row = cases.load(db, building, ctx, case_id)
        cases._handler_only(ctx, case_row)
        if case_row.get("Status") in ("decided", "closed"):
            raise bad("This request is already decided.")
        if any(m.get("Status") == "open" for m in open_for_case(db, building, case_row["ROWID"])):
            raise bad("There's already a vote open on this request.")
        topic = topics.get(db, building, case_row.get("Topic_Key")) or {}
        animal = bool((topic.get("vote") or {}).get("animal"))
        row.update(Case_Id=int(case_row["ROWID"]), Animal=animal, Exempt="animal" if animal else exempt)
    closes = store.parse_dt(case_row.get("Due_At")) if row["Animal"] and case_row else None
    row["Closes_At"] = store.fmt_dt(closes or deadlines.due_at(now, OPEN_DAYS))
    motion = db.insert(store.MOTIONS, row)
    _send_notice(db, building, motion, case_row)
    if case_row:
        cases._event(db, building, case_row["ROWID"], ctx["user_id"], "vote",
                     "Vote outside a meeting opened; closes {}.\n{}".format(
                         stages.long_date(store.parse_dt(motion["Closes_At"])), words), True)
    return motion


def _vote_link(building, motion):
    base = mailer.portal_link(building)
    return "{}#/vote/{}".format(base, motion["ROWID"]) if base else ""


def _send_notice(db, building, motion, case_row):
    """Written notice to every committee member, and the owners' advice at the same time (SM s 68(1), (3))."""
    closes = stages.long_date(store.parse_dt(motion["Closes_At"]))
    first = "IF NOBODY DECIDES: " + missed_text(motion)
    lines = [first, "The motion:", motion["Words"],
             "Vote in the portal by the end of {}. It passes when more than half of the members entitled to vote "
             "say yes. If you have a conflict of interest, declare it there instead of voting.".format(closes)]
    if case_row:
        lines.insert(1, "It is about request {} ({}).".format(case_row.get("Ref"), case_row.get("Title")))
    html = mailer.page(building, "A committee vote outside a meeting", lines, "Vote now",
                       link=_vote_link(building, motion))
    for email in committee.emails_of(db, committee.committee_ids(db, building)):
        mailer.send(db, email, "{}: committee vote — closes {}".format(building["name"], closes), html,
                    building=building)
    advice = mailer.page(building, "The committee is voting on a motion",
                         ["The committee is voting outside a meeting on this motion:", motion["Words"],
                          "Voting closes at the end of {}. The result will be sent to owners.".format(closes)],
                         "Open the portal")
    mailer.send_many(db, content.audience_emails(db, building, "owners"),
                     "{}: committee vote (advice to owners)".format(building["name"]), advice, building=building)


# ---------- voting ----------

def ballot(db, building, ctx, motion_id, vote, conflict, note, now=None):
    now = now or store.utc_now()
    row = load(db, building, ctx, motion_id)
    row = settle(db, building, row, now) or row
    if row.get("Kind") != "vocm":
        raise bad("Meeting votes are recorded by the chair at the meeting.")
    if row.get("Status") != "open":
        raise bad("This vote has closed.")
    if not ctx["cmt"]["vote"] or ctx["user_id"] not in {str(i) for i in _json(row.get("Eligible"), [])}:
        raise forbidden("Only voting members entitled to vote on this motion can vote (SM s 64, s 67).")
    conflict = conflict in (True, "true", 1, "1")
    if not conflict and vote not in VOTES:
        raise bad("Choose yes, no or abstain.")
    note = str(note or "").strip()[:255]
    if conflict and not note:
        raise bad("Say briefly what the conflict is (SM s 66).")
    fields = {"Vote": "conflict" if conflict else vote, "Conflict": conflict, "Note": note}
    existing = [b for b in db.find(store.BALLOTS, {"Motion_Id": int(row["ROWID"])})
                if str(b.get("User_Id")) == ctx["user_id"]]
    if existing:
        db.update(store.BALLOTS, dict(fields, ROWID=existing[0]["ROWID"]))
    else:
        db.insert(store.BALLOTS, dict(fields, Motion_Id=int(row["ROWID"]), Building_Id=int(building["id"]),
                                      User_Id=int(ctx["user_id"])))
    settle(db, building, db.get(store.MOTIONS, row["ROWID"]), now)
    return detail(db, building, ctx, row["ROWID"], now)


# ---------- deciding ----------

def settle(db, building, row, now):
    """Decide an open VOCM if it has a result or its time is up. Returns the updated row, or None if unchanged."""
    if row.get("Kind") != "vocm" or row.get("Status") != "open":
        return None
    closes = store.parse_dt(row.get("Closes_At"))
    ballots = db.find(store.BALLOTS, {"Motion_Id": int(row["ROWID"])})
    counts = tally(_json(row.get("Eligible"), []), ballots)
    result = vocm_result(counts, bool(closes and now > closes), row.get("Animal") in (True, "true"))
    if result == "open":
        return None
    return finish(db, building, row, result, counts, ballots, now)


def finish(db, building, row, result, counts, ballots, now):
    """Record a result, put it on the case, and (for a VOCM) send the record of motions."""
    names = _names(db, [str(b.get("User_Id")) for b in ballots] + _json(row.get("Eligible"), []))
    record = dict(counts, voters=[_name(names[str(b.get("User_Id"))]) for b in ballots
                                  if b.get("Conflict") not in (True, "true")],
                  given_to=[_name(names[i]) for i in _json(row.get("Eligible"), [])])
    change = {"ROWID": row["ROWID"], "Status": result, "Decided_At": store.fmt_dt(now), "Tally": json.dumps(record)}
    if result == "passed" and row.get("Kind") == "vocm":
        change.update(_act_from(building, row, now))
    db.update(store.MOTIONS, change)
    row = dict(row, **change)
    apply_to_case(db, building, row, result, counts, now)
    if row.get("Kind") == "vocm":
        _send_record(db, building, row, record)
    return row


def _act_from(building, row, now):
    """When a passed motion can be acted on (SM s 72-73). The record goes out now, so the window starts now."""
    if row.get("Exempt") or committee.module(building) == "accommodation":
        return {"Act_From": store.fmt_dt(now)}
    if committee.module(building) == "standard":
        return {"Act_From": store.fmt_dt(deadlines.due_at(now, 7))}
    return {}


def apply_to_case(db, building, row, result, counts, now):
    """What the result means for the request comes from the topic's "vote" data."""
    if not row.get("Case_Id"):
        return
    case_row = db.get(store.CASES, row["Case_Id"])
    if not case_row or case_row.get("Status") in ("decided", "closed"):
        return
    rule = (topics.get(db, building, case_row.get("Topic_Key")) or {}).get("vote") or {}
    outcome = {"passed": rule.get("if_passed", "approved"), "defeated": rule.get("if_defeated"),
               "lost": rule.get("if_defeated"), "not_agreed": rule.get("if_no_result", "not_agreed"),
               "deemed_approved": "deemed_approved"}.get(result)
    how = "Committee vote {}: {} for, {} against, {} abstained.".format(
        "outside a meeting" if row.get("Kind") == "vocm" else "at a meeting", counts["yes"], counts["no"],
        counts["abstain"])
    if not outcome:
        cases._event(db, building, case_row["ROWID"], None, "vote",
                     "{} The motion was {}. The committee still needs to decide this request.".format(
                         how, STATUS_LABELS.get(result, result).lower()), True)
        return
    reasons = "{} Motion: {}".format(how, row.get("Words"))
    if result in ("deemed_approved", "not_agreed"):
        reasons = "{} {}".format(STATUS_LABELS[result], "(SM s 69(3)).")
    cases.apply_decision(db, building, case_row, outcome, reasons, "", "", now, {"motion_id": str(row["ROWID"])})


def _send_record(db, building, row, record):
    """The record of motions to committee members and owners (SM s 71(2)-(4), (6))."""
    opened = store.parse_dt(row.get("Opened_At"))
    lines = ["Motion: " + (row.get("Words") or ""),
             "Result: {}.".format(STATUS_LABELS.get(row.get("Status"), row.get("Status"))),
             "For: {} · Against: {} · Abstained: {} · Conflicts declared: {}".format(
                 record["yes"], record["no"], record["abstain"], record["conflicts"]),
             "Notice given {} to: {}".format(stages.long_date(opened) if opened else "", ", ".join(record["given_to"])),
             "Voted: {}".format(", ".join(record["voters"]) or "nobody"),
             act_note(building, row),
             "It will be confirmed at the next committee meeting."]
    html = mailer.page(building, "Record of a committee vote", lines, "Open the portal")
    emails = set(committee.emails_of(db, committee.committee_ids(db, building)))
    emails |= set(content.audience_emails(db, building, "owners"))
    mailer.send_many(db, sorted(emails), "{}: result of a committee vote".format(building["name"]), html,
                     building=building)


def settle_building(db, building, now):
    for row in db.find(store.MOTIONS, {"Building_Id": int(building["id"]), "Status": "open"}):
        settle(db, building, row, now)


def settle_all(db, now=None):
    """Every building's open votes whose time is up (the daily reminders run this first)."""
    import buildings
    now = now or store.utc_now()
    for building in (buildings.from_row(r) for r in db.find(store.BUILDINGS)):
        settle_building(db, building, now)


def case_votes(db, building, ctx, case_id, now):
    """For the case page: the votes on this case (committee only)."""
    return [out(db, building, ctx, r, now) for r in sorted(open_for_case(db, building, case_id),
                                                           key=lambda r: -int(r["ROWID"]))]


def open_by_case(db, building, now):
    """{case id: short vote state} for board cards."""
    found = {}
    for row in db.find(store.MOTIONS, {"Building_Id": int(building["id"]), "Status": "open"}):
        if row.get("Case_Id"):
            counts = tally(_json(row.get("Eligible"), []), db.find(store.BALLOTS, {"Motion_Id": int(row["ROWID"])}))
            found[str(row["Case_Id"])] = {"id": str(row["ROWID"]), "yes": counts["yes"], "no": counts["no"],
                                          "needed": counts["needed_yes"], "entitled": counts["entitled"]}
    return found


def plus(when, days):
    return when + timedelta(days=days)
