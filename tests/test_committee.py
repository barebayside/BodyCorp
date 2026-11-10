"""Committee working view, phase B: votes outside a meeting, meetings, minutes and tasks (law file §4-5)."""

import json
from datetime import datetime, timedelta

import buildings
import cases
import deadlines
import meetings
import store
import votes
from conftest import ADMIN, NOW

PET = {"animal": "Cat", "how_many": "1", "where_kept": "Inside"}
FIVE = ("chair", "secretary", "treasurer", "member", "member2")


def _committee(world, names=FIVE):
    for name in names:
        world.role("{}@example.com".format(name), "member" if name.startswith("member") else name)
    world.member("jo@example.com", "4")
    world.member("owner5@example.com", "5")


def _id(world, email):
    return world.user(email)["id"]


def _open(world, words="That the pool fence be repaired for $800.", case_id=None, now=NOW, email="secretary@example.com"):
    body, status = world.call("POST", "/votes", {"words": words, "case_id": case_id}, email=email, now=now)
    assert status == 200, body
    return body["vote"]


def _ballot(world, vote_id, email, vote="yes", conflict=False, note="", now=NOW):
    return world.call("POST", "/vote/ballot", {"id": vote_id, "vote": vote, "conflict": conflict, "note": note},
                      email=email, now=now)


def _pet(world, now=NOW):
    return cases.create(world.db, world.building, world.user("jo@example.com"), world.ctx("jo@example.com"),
                        world.units["4"], "pet", dict(PET), [], now)["case"]


# ---------- votes outside a meeting (SM s 68-70) ----------

def test_vocm_needs_a_majority_of_all_entitled_not_of_those_who_voted(world):
    _committee(world)
    world.db.outbox.clear()
    vote = _open(world)
    assert vote["tally"]["entitled"] == 5 and vote["tally"]["needed_yes"] == 3 and vote["closes_text"] == "1 Dec 2026"
    notice = world.db.mail_to("treasurer@example.com")[0]["html"]
    assert notice.index("IF NOBODY DECIDES") < notice.index("The motion:") and "NOT AGREED" in notice
    assert world.db.mail_to("owner5@example.com"), "owners are advised at the same time (SM s 68(3))"
    _ballot(world, vote["id"], "chair@example.com")
    body, _ = _ballot(world, vote["id"], "secretary@example.com")
    assert body["vote"]["status"] == "open"                                  # 2 of 5: not a majority of all
    body, _ = _ballot(world, vote["id"], "treasurer@example.com")
    assert body["vote"]["status"] == "passed" and body["vote"]["tally"]["yes"] == 3
    assert any("result of a committee vote" in m["subject"] for m in world.db.mail_to("owner5@example.com"))


def test_vocm_defeated_when_half_or_more_say_no(world):
    _committee(world, ("chair", "secretary", "treasurer", "member"))
    vote = _open(world)
    _ballot(world, vote["id"], "chair@example.com", "no")
    body, _ = _ballot(world, vote["id"], "member@example.com", "no")
    assert body["vote"]["status"] == "defeated"


def test_conflict_and_unfinancial_reduce_who_is_entitled(world):
    _committee(world, ("chair", "secretary", "treasurer", "member"))
    world.call("POST", "/committee/settings", {"unfinancial": [_id(world, "member@example.com")]}, email=ADMIN)
    vote = _open(world)
    assert vote["tally"]["entitled"] == 3
    assert _ballot(world, vote["id"], "member@example.com")[1] == 403        # owes a debt: no vote (SM s 64)
    assert _ballot(world, vote["id"], "chair@example.com", conflict=True)[1] == 400   # say what the conflict is
    body, _ = _ballot(world, vote["id"], "chair@example.com", conflict=True, note="My unit")
    assert body["vote"]["tally"]["entitled"] == 2
    body, _ = _ballot(world, vote["id"], "secretary@example.com")
    assert body["vote"]["status"] == "open"                                  # 1 of 2 is not more than half
    body, _ = _ballot(world, vote["id"], "treasurer@example.com")
    assert body["vote"]["status"] == "passed"


def test_no_result_by_day_21_is_not_agreed(world):
    _committee(world)
    vote = _open(world)
    _ballot(world, vote["id"], "chair@example.com")
    votes.settle_all(world.db, datetime(2026, 12, 1, 13, 59))
    assert world.db.get(store.MOTIONS, vote["id"])["Status"] == "open"
    votes.settle_all(world.db, datetime(2026, 12, 1, 14, 0, 1))
    assert world.db.get(store.MOTIONS, vote["id"])["Status"] == "not_agreed"
    assert _ballot(world, vote["id"], "secretary@example.com", now=NOW + timedelta(days=22))[1] == 400


def test_pet_vote_runs_21_days_from_the_request_and_is_deemed_approved(world):
    _committee(world)
    case = _pet(world, NOW - timedelta(days=10))                           # asked on 31 Oct
    world.call("POST", "/case/action", {"id": case["id"], "action": "acknowledge"}, email="secretary@example.com")
    body, status = world.call("POST", "/case/action", {"id": case["id"], "action": "vote", "note": "Kept inside."},
                              email="secretary@example.com")
    assert status == 200 and body["case"]["stage"]["key"] == "deciding"
    vote = body["votes"][0]
    assert vote["animal"] and vote["closes_at"] == case["due_at"] != deadlines.iso_utc(deadlines.due_at(NOW, 21))
    assert "treated as APPROVED" in vote["missed"] and "Kept inside." in vote["words"]
    votes.settle_all(world.db, store.parse_dt(case["due_at"].replace("T", " ").rstrip("Z")) + timedelta(seconds=2))
    row = world.db.get(store.CASES, case["id"])
    assert json.loads(row["Decision"])["outcome"] == "deemed_approved" and row["Stage"] == "decided"
    assert world.db.get(store.MOTIONS, vote["id"])["Status"] == "deemed_approved"


def test_vote_passed_decides_the_case_from_the_topic_data(world):
    _committee(world)
    case = _pet(world)
    vote = _open(world, "That request ALT-0001 be approved.", case["id"])
    for email in ("chair@example.com", "secretary@example.com", "member@example.com"):
        _ballot(world, vote["id"], email)
    body, _ = world.call("GET", "/case", {"id": case["id"]}, email="secretary@example.com")
    assert body["case"]["decision"]["outcome"] == "approved" and body["case"]["stage"]["key"] == "decided"
    assert body["votes"][0]["act_note"].startswith("Can be acted on")          # animal approvals: at once (SM s 73(1)(e))
    assert any("decided" in m["subject"] for m in world.db.mail_to("jo@example.com"))


def test_passed_motion_waits_seven_days_under_the_standard_module(world):
    _committee(world)
    world.call("POST", "/committee/settings", {"module": "standard"}, email=ADMIN)
    vote = _open(world)
    for email in ("chair@example.com", "secretary@example.com", "member@example.com"):
        body, _ = _ballot(world, vote["id"], email)
    assert body["vote"]["act_note"] == "Can be acted on from 17 Nov 2026."


def test_only_voting_members_vote_and_only_the_committee_sees_votes(world):
    _committee(world)
    world.role("bcm@example.com", "committee")
    vote = _open(world)
    assert _ballot(world, vote["id"], "bcm@example.com")[1] == 403
    assert world.call("GET", "/vote", {"id": vote["id"]}, email="bcm@example.com")[1] == 200
    world.role("m@example.com", "manager")
    for email in ("jo@example.com", "m@example.com"):
        assert world.call("GET", "/votes", email=email)[1] == 403
        assert world.call("GET", "/vote", {"id": vote["id"]}, email=email)[1] == 403
        assert _ballot(world, vote["id"], email)[1] == 403
    assert world.call("POST", "/votes", {"words": "x"}, email="treasurer@example.com")[1] == 403   # secretary sends


def test_residents_never_see_votes_internal_notes_or_tasks(world):
    _committee(world)
    case = _pet(world)
    cases.message(world.db, world.building, world.ctx("secretary@example.com"), case["id"], "SECRET note", False, NOW)
    _open(world, "Approve it.", case["id"])
    world.call("POST", "/tasks", {"title": "Check the cat", "case_id": case["id"]}, email="secretary@example.com")
    body, _ = world.call("GET", "/case", {"id": case["id"]}, email="jo@example.com")
    assert "votes" not in body and "tasks" not in body and "SECRET" not in json.dumps(body)
    assert all(not e["internal"] for e in body["events"])
    for path in ("/tasks", "/meetings", "/committee"):
        assert world.call("GET", path, email="jo@example.com")[1] == 403


def test_other_buildings_get_404(world):
    _committee(world)
    vote = _open(world)
    other = buildings.from_row(world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other",
                                                                 "Brand": "{}", "Settings": "{}"}))
    world.db.insert(store.ROLES, {"User_Id": int(_id(world, "boss@example.com")), "Building_Id": int(other["id"]),
                                  "Role": "secretary"})
    assert world.call("GET", "/vote", {"b": "other", "id": vote["id"]}, email="boss@example.com")[1] == 404
    assert world.call("POST", "/vote/ballot", {"b": "other", "id": vote["id"], "vote": "yes"},
                      email="boss@example.com")[1] == 404


# ---------- meetings (SM s 54-66) ----------

def _meeting(world, starts="2026-11-18T18:00", short="", items=None, now=NOW):
    return world.call("POST", "/meetings", {"title": "November committee meeting", "starts_at": starts,
                                            "place": "Level 1 meeting room", "items": items or [],
                                            "short_notice": short}, email="secretary@example.com", now=now)


def test_meeting_needs_seven_clear_days_or_two_with_agreement(world):
    _committee(world)
    body, status = _meeting(world, "2026-11-17T18:00")                     # 6 clear days (11th-16th)
    assert status == 400 and "18 Nov 2026" in body["error"]
    world.db.outbox.clear()
    body, status = _meeting(world)                                          # 18th: 7 clear days
    assert status == 200 and body["meeting"]["notice_text"].endswith("7 clear days before.")
    assert world.db.mail_to("member@example.com") and world.db.mail_to("owner5@example.com")
    assert _meeting(world, "2026-11-12T18:00", short="All 5 agreed by email on 9 Nov")[1] == 400   # 1 clear day
    assert _meeting(world, "2026-11-13T18:00", short="All 5 agreed by email on 9 Nov")[1] == 200
    assert world.call("POST", "/meetings", {"starts_at": "2026-12-20T18:00"}, email="chair@example.com")[1] == 403


def _attend(world, meeting_id, people):
    rows = [dict({"user_id": _id(world, "{}@example.com".format(name)), "how": how},
                 **({"proxy_holder": _id(world, "{}@example.com".format(holder))} if holder else {}))
            for name, how, holder in people]
    return world.call("POST", "/meeting/attendance", {"id": meeting_id, "people": rows}, email="chair@example.com")


def test_quorum_counts_proxy_holders_twice_and_blocks_votes_without_it(world):
    _committee(world)
    meeting = _meeting(world, items=[{"text": "Pool fence", "motion": "That the pool fence be repaired."}])[0]["meeting"]
    motion_id = meeting["agenda"][0]["motion_id"]
    body, _ = _attend(world, meeting["id"], [("chair", "present", None), ("secretary", "electronic", None)])
    assert body["meeting"]["quorum"] == dict(body["meeting"]["quorum"], voting=5, needed=3, present=2, ok=False)
    body, status = world.call("POST", "/meeting/vote", {"motion_id": motion_id, "votes": {
        _id(world, "chair@example.com"): "yes"}}, email="chair@example.com")
    assert status == 400 and "No quorum" in body["error"]
    body, _ = _attend(world, meeting["id"], [("chair", "present", None), ("secretary", "electronic", None),
                                             ("treasurer", "proxy", "chair")])
    assert body["meeting"]["quorum"]["present"] == 3 and body["meeting"]["quorum"]["ok"]
    assert _attend(world, meeting["id"], [("chair", "present", None), ("treasurer", "proxy", "chair"),
                                          ("member", "proxy", "chair")])[1] == 400      # one proxy each


def test_meeting_tie_is_lost_and_majority_of_those_voting_passes(world):
    _committee(world, ("chair", "secretary", "treasurer", "member"))
    meeting = _meeting(world, items=[{"text": "A", "motion": "Motion A."}, {"text": "B", "motion": "Motion B."}])[0]
    agenda = meeting["meeting"]["agenda"]
    _attend(world, meeting["meeting"]["id"], [(n, "present", None) for n in ("chair", "secretary", "treasurer", "member")])
    ids = {n: _id(world, "{}@example.com".format(n)) for n in ("chair", "secretary", "treasurer", "member")}
    body, _ = world.call("POST", "/meeting/vote", {"motion_id": agenda[0]["motion_id"], "votes": {
        ids["chair"]: "yes", ids["secretary"]: "yes", ids["treasurer"]: "no", ids["member"]: "no"}},
        email="chair@example.com")
    assert body["meeting"]["agenda"][0]["motion"]["status"] == "lost"
    body, _ = world.call("POST", "/meeting/vote", {"motion_id": agenda[1]["motion_id"], "votes": {
        ids["chair"]: "yes", ids["secretary"]: "abstain", ids["treasurer"]: "abstain", ids["member"]: "conflict"}},
        email="chair@example.com")
    assert body["meeting"]["agenda"][1]["motion"]["status"] == "passed"       # 1 yes, 0 no among those voting
    assert world.call("POST", "/meeting/vote", {"motion_id": agenda[1]["motion_id"], "votes": {ids["chair"]: "no"}},
                      email="chair@example.com")[1] == 400                    # already recorded


def test_agenda_confirms_last_minutes_and_each_vote_outside_a_meeting(world):
    _committee(world)
    vote = _open(world)
    for email in ("chair@example.com", "secretary@example.com", "member@example.com"):
        _ballot(world, vote["id"], email)
    meeting = _meeting(world)[0]["meeting"]
    item = meeting["agenda"][0]
    assert item["kind"] == "confirm_vocm" and item["vocm_id"] == vote["id"]
    _attend(world, meeting["id"], [(n, "present", None) for n in ("chair", "secretary", "treasurer")])
    world.call("POST", "/meeting/vote", {"motion_id": item["motion_id"], "votes": {
        _id(world, "chair@example.com"): "yes", _id(world, "secretary@example.com"): "yes"}}, email="chair@example.com")
    assert str(world.db.get(store.MOTIONS, vote["id"])["Confirmed_Meeting_Id"]) == meeting["id"]
    world.call("POST", "/meeting/close", {"id": meeting["id"]}, email="chair@example.com")
    nxt = _meeting(world, "2026-12-10T18:00")[0]["meeting"]
    assert nxt["agenda"][0]["kind"] == "confirm_minutes" and len(nxt["agenda"]) == 1


def test_minutes_drafted_tracked_and_issued_to_owners_and_documents(world):
    _committee(world)
    world.call("POST", "/committee/settings", {"module": "standard"}, email=ADMIN)
    case = _pet(world)
    meeting = _meeting(world, items=[{"text": "Pet request", "motion": "That the cat be approved.",
                                      "case_id": case["id"]}])[0]["meeting"]
    _attend(world, meeting["id"], [("chair", "present", None), ("secretary", "present", None),
                                   ("treasurer", "proxy", "chair"), ("member", "absent", None)])
    ids = {n: _id(world, "{}@example.com".format(n)) for n in ("chair", "secretary", "treasurer")}
    world.call("POST", "/meeting/vote", {"motion_id": meeting["agenda"][0]["motion_id"], "votes": {
        ids["chair"]: "yes", ids["secretary"]: "yes", ids["treasurer"]: "yes"}}, email="chair@example.com")
    assert json.loads(world.db.get(store.CASES, case["id"])["Decision"])["outcome"] == "approved"
    body, _ = world.call("POST", "/meeting/close", {"id": meeting["id"]}, email="chair@example.com")
    minutes = body["meeting"]["minutes"]
    for part in ("1. Date, time and place: Wed 18 Nov 2026, 6:00 pm", "held a proxy for", "Quorum: 3 counted, 3 needed",
                 "5. Animal requests:", "What animal?: Cat", "“That the cat be approved.” — For 3, Against 0",
                 "CARRIED", "10. Secretary:"):
        assert part in minutes, part
    assert body["meeting"]["minutes_status"] == "draft" and body["meeting"]["minutes_due"] == "9 Dec 2026"
    body, status = world.call("POST", "/meeting/minutes/issue", {"id": meeting["id"]}, email="secretary@example.com")
    assert status == 400 and "contact address" in body["error"]
    world.call("POST", "/committee/settings", {"secretary_contact": "PO Box 1, Spring Hill QLD 4000"}, email=ADMIN)
    body, _ = world.call("POST", "/meeting/close", {"id": meeting["id"]}, email="chair@example.com")   # already closed
    text = minutes.replace("(contact address)", "PO Box 1, Spring Hill QLD 4000")
    assert world.call("POST", "/meeting/minutes", {"id": meeting["id"], "text": text}, email="chair@example.com")[1] == 403
    world.call("POST", "/meeting/minutes", {"id": meeting["id"], "text": text}, email="secretary@example.com")
    world.db.outbox.clear()
    body, status = world.call("POST", "/meeting/minutes/issue", {"id": meeting["id"]}, email="secretary@example.com")
    assert status == 200 and body["meeting"]["minutes_status"] == "issued"
    doc = world.db.find(store.DOCS)[0]
    assert doc["Category"] == "Minutes" and doc["Audience"] == "owners"
    assert world.db.mail_to("owner5@example.com")
    body, _ = world.call("GET", "/docs", email="owner5@example.com")
    assert body["docs"][0]["title"].startswith("Committee meeting minutes")
    motion = world.db.get(store.MOTIONS, meeting["agenda"][0]["motion_id"])
    assert motion["Act_From"]                                                  # animal approval: no window


def test_minutes_due_reminder_goes_to_the_minute_taker(world):
    _committee(world)
    meeting = _meeting(world)[0]["meeting"]
    _attend(world, meeting["id"], [(n, "present", None) for n in ("chair", "secretary", "treasurer")])
    world.call("POST", "/meeting/close", {"id": meeting["id"]}, email="chair@example.com")
    world.db.outbox.clear()
    world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"}, now=NOW + timedelta(days=26))
    assert any("Minutes:" in m["html"] for m in world.db.mail_to("secretary@example.com"))
    assert not world.db.mail_to("chair@example.com")


# ---------- tasks ----------

def test_tasks_assigned_to_a_position_listed_reminded_and_done(world):
    _committee(world)
    body, status = world.call("POST", "/tasks", {"title": "Get two quotes for the fence", "due_date": "2026-11-12",
                                                 "assignee_position": "treasurer"}, email="secretary@example.com")
    assert status == 200 and body["task"]["assignee"] == "Treasurer"
    task_id = body["task"]["id"]
    assert [t["id"] for t in world.call("GET", "/tasks", email="treasurer@example.com")[0]["tasks"]] == [task_id]
    assert world.call("GET", "/tasks", email="chair@example.com")[0]["tasks"] == []
    assert len(world.call("GET", "/tasks", {"scope": "all"}, email="chair@example.com")[0]["tasks"]) == 1
    world.db.outbox.clear()
    world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"})
    assert any("Get two quotes" in m["html"] for m in world.db.mail_to("treasurer@example.com"))
    assert world.call("POST", "/task/done", {"id": task_id, "done": True}, email="member@example.com")[1] == 403
    body, _ = world.call("POST", "/task/done", {"id": task_id, "done": True}, email="treasurer@example.com")
    assert body["task"]["done"] is True
    assert world.call("POST", "/tasks", {"title": "x", "assignee_user_id": _id(world, "jo@example.com")},
                      email="secretary@example.com")[1] == 400
