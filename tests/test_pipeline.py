"""Committee working view, phase A: positions, stages and buttons, the board, and what silence means."""

import json
from datetime import datetime, timedelta

import pytest

import admin
import buildings
import cases
import pipeline
import store
import topics
from conftest import ADMIN, NOW
from errors import ApiError

PET = {"animal": "Cat", "how_many": "1", "where_kept": "Inside"}
RENO = {"work": "New timber floor", "affects_common": "No"}


def _committee(world, sizes=("chair", "secretary", "treasurer")):
    for position in sizes:
        world.role("{}@example.com".format(position), position)


def _case(world, topic="pet", answers=None, now=NOW, email="jo@example.com", unit="4"):
    if not world.db.find(store.MEMBERSHIPS, {"User_Id": int(world.user(email)["id"])}):
        world.member(email, unit)
    return cases.create(world.db, world.building, world.user(email), world.ctx(email), world.units[unit], topic,
                        dict(answers or (PET if topic == "pet" else RENO)), [], now)["case"]


def _act(world, case_id, action, email="secretary@example.com", note="", now=NOW):
    return world.call("POST", "/case/action", {"id": case_id, "action": action, "note": note}, email=email, now=now)


# ---------- positions ----------

def test_positions_vote_and_handle_committee_cases_committee_role_does_not_vote(world):
    _committee(world)
    world.role("bcm@example.com", "committee")
    case = _case(world)
    for email in ("chair@example.com", "treasurer@example.com", "bcm@example.com"):
        body, status = world.call("GET", "/case", {"id": case["id"]}, email=email)
        assert status == 200 and body["case"]["can_handle"] is True
    assert world.ctx("treasurer@example.com")["cmt"]["voting"] is True
    assert world.ctx("bcm@example.com")["cmt"]["voting"] is False
    body, _ = world.call("GET", "/me", email="secretary@example.com")
    assert body["committee"]["positions"] == ["secretary"] and body["can"]["handle"] is True


# ---------- what silence means, from the topic's data ----------

def test_if_missed_wording_dates_and_citation_from_topic_data(world):
    _committee(world)
    pet = _case(world)
    body, _ = world.call("GET", "/case", {"id": pet["id"]}, email="secretary@example.com")
    missed = body["case"]["missed"]
    assert missed["outcome"] == "deemed_approved" and missed["date_text"] == "1 Dec 2026"
    assert "treated as APPROVED" in missed["banner"] and "1 Dec 2026" in missed["banner"]
    assert missed["card"] == "auto-approves after 1 Dec" and "SM s 58A" in missed["citation"]
    reno = _case(world, "renovation")
    body, _ = world.call("GET", "/case", {"id": reno["id"]}, email="secretary@example.com")
    missed = body["case"]["missed"]
    assert missed["outcome"] == "not_agreed" and missed["card"] == "treated as not agreed after 22 Dec"
    assert "NOT AGREED" in missed["banner"] and "SM s 58" in missed["citation"] and missed["extendable"]


def test_urgent_only_in_the_last_three_days(world):
    _committee(world)
    case = _case(world)                                                  # due 1 Dec: 3 days left on 28 Nov
    world.token("secretary@example.com")
    body = world.call("GET", "/case", {"id": case["id"]}, email="secretary@example.com", now=NOW + timedelta(days=18))[0]
    assert body["case"]["missed"]["days_left"] == 3 and body["case"]["missed"]["urgent"] is True
    body = world.call("GET", "/case", {"id": case["id"]}, email="secretary@example.com", now=NOW + timedelta(days=17))[0]
    assert body["case"]["missed"]["days_left"] == 4 and body["case"]["missed"]["urgent"] is False


def test_residents_never_get_the_stage_or_missed_panel(world):
    _committee(world)
    case = _case(world)
    body, _ = world.call("GET", "/case", {"id": case["id"]}, email="jo@example.com")
    assert "stage" not in body["case"] and "missed" not in body["case"] and "votes" not in body


def test_new_request_email_to_approvers_starts_with_if_missed(world):
    _committee(world)
    world.db.outbox.clear()
    _case(world)
    mail = world.db.mail_to("secretary@example.com")[0]["html"]
    assert mail.index("IF NOBODY DECIDES") < mail.index("Keep a pet for")
    assert "#/case/" in mail
    assert "IF NOBODY DECIDES" not in "".join(m["html"] for m in world.db.mail_to("jo@example.com"))


# ---------- buttons ----------

def test_action_emails_with_link_moves_stage_and_logs(world):
    _committee(world)
    case = _case(world)
    world.db.outbox.clear()
    body, status = _act(world, case["id"], "acknowledge")
    assert status == 200
    assert body["case"]["stage"]["key"] == "checking" and body["case"]["status"] == "in_progress"
    mail = world.db.mail_to("jo@example.com")[0]
    assert "we have your request" in mail["subject"] and "#/request/{}".format(case["id"]) in mail["html"]
    kinds = [(e["kind"], e["internal"]) for e in body["events"]]
    assert ("action", True) in kinds and ("message", False) in kinds
    resident = world.call("GET", "/case", {"id": case["id"]}, email="jo@example.com")[0]
    assert [e["kind"] for e in resident["events"]] == ["created", "message"]


def test_action_owner_position_from_duty_map(world):
    _committee(world)
    case = _case(world)
    assert _act(world, case["id"], "acknowledge", "treasurer@example.com")[1] == 403
    assert _act(world, case["id"], "acknowledge", "jo@example.com")[1] == 403
    # The building gives acknowledgements to the treasurer instead.
    world.call("POST", "/committee/settings", {"duties": {"acknowledge": "treasurer"}}, email=ADMIN)
    assert _act(world, case["id"], "acknowledge", "treasurer@example.com")[1] == 200


def test_nobody_holds_the_position_any_voting_member_may_act(world):
    world.role("chair@example.com", "chair")
    case = _case(world)
    assert _act(world, case["id"], "acknowledge", "chair@example.com")[1] == 200


def test_required_note_and_unknown_button(world):
    _committee(world)
    case = _case(world)
    body, status = _act(world, case["id"], "ask")
    assert status == 400 and "What's missing?" in body["error"]
    assert _act(world, case["id"], "close")[1] == 400
    body, _ = _act(world, case["id"], "ask", note="Please send a photo.")
    assert body["case"]["status"] == "waiting_on_resident" and body["case"]["stage"]["key"] == "received"


def test_failed_email_is_queued_and_the_step_still_moves(world):
    _committee(world)
    case = _case(world)
    world.token("secretary@example.com")                                 # signed in before email broke
    world.db.mail_error = "sender not verified"
    body, status = _act(world, case["id"], "acknowledge")
    assert status == 200 and body["case"]["stage"]["key"] == "checking"
    assert world.db.find(store.MAIL_QUEUE, {"Status": "queued"})
    assert "queued" in [e for e in body["events"] if e["kind"] == "action"][0]["body"]


def test_extension_once_before_deadline_to_twelve_weeks(world):
    _committee(world)
    case = _case(world, "renovation")
    _act(world, case["id"], "acknowledge")
    assert _act(world, case["id"], "extend")[1] == 400                       # needs the written reason
    body, status = _act(world, case["id"], "extend", note="Waiting on the engineer's report.")
    assert status == 200 and body["case"]["due_date"] == "2027-02-02"         # 12 weeks after 10 Nov
    assert body["case"]["missed"]["extendable"] is False
    assert "2 Feb 2027" in world.db.mail_to("jo@example.com")[-1]["html"]
    assert _act(world, case["id"], "extend", note="again")[1] == 400


def test_action_on_other_building_case_404(world):
    _committee(world)
    case = _case(world)
    other = buildings.from_row(world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other",
                                                                 "Brand": "{}", "Settings": "{}"}))
    world.db.insert(store.ROLES, {"User_Id": int(world.user("boss@example.com")["id"]),
                                  "Building_Id": int(other["id"]), "Role": "secretary"})
    body, status = world.call("POST", "/case/action", {"b": "other", "id": case["id"], "action": "acknowledge"},
                              email="boss@example.com")
    assert status == 404


# ---------- the board ----------

def test_board_columns_cards_and_who_sees_it(world):
    _committee(world)
    world.role("m@example.com", "manager")
    pet = _case(world)
    _case(world, "maintenance", {"where": "Lift", "problem": "Stuck", "urgent": "No"})
    body, status = world.call("GET", "/board", email="secretary@example.com")
    assert status == 200
    keys = [c["key"] for c in body["columns"]]
    assert keys[:4] == ["received", "checking", "deciding", "decided"] and "working" not in keys
    card = body["columns"][0]["cards"][0]
    assert card["id"] == pet["id"] and card["missed_label"] == "auto-approves after 1 Dec"
    assert card["owner_label"] == "Secretary" and card["days_left"] == 21
    body, _ = world.call("GET", "/board", email="m@example.com")
    assert [c["title"] for col in body["columns"] for c in col["cards"]] == ["Maintenance or repair"]
    assert world.call("GET", "/board", email="jo@example.com")[1] == 403


def test_module_note_only_for_admins_until_recorded(world):
    _committee(world)
    body, _ = world.call("GET", "/board", email=ADMIN)
    assert body["module_note"] == "Module not recorded — committee rules are guidance only."
    assert world.call("GET", "/board", email="secretary@example.com")[0]["module_note"] is None
    world.call("POST", "/committee/settings", {"module": "standard", "evidence": "CMS 7001234"}, email=ADMIN)
    assert world.call("GET", "/board", email=ADMIN)[0]["module_note"] is None
    assert world.call("POST", "/committee/settings", {"module": "standard"}, email="secretary@example.com")[1] == 403


def test_committee_checks_warn_on_make_up(world):
    world.role("chair@example.com", "chair")
    body, _ = world.call("GET", "/committee", email="chair@example.com")
    assert any("at least 3" in c for c in body["checks"]) and any("secretary" in c for c in body["checks"])
    assert world.call("GET", "/committee", email="jo@example.com")[1] == 403


# ---------- the clock running out ----------

def test_pet_deemed_approved_only_after_the_last_day_ends(world):
    _committee(world)
    case = _case(world)                                                       # due end of 1 Dec, Brisbane
    assert pipeline.apply_deemed(world.db, datetime(2026, 12, 1, 13, 59)) == 0
    world.db.outbox.clear()
    assert pipeline.apply_deemed(world.db, datetime(2026, 12, 1, 14, 0, 1)) == 1
    row = world.db.get(store.CASES, case["id"])
    decision = json.loads(row["Decision"])
    assert row["Status"] == "decided" and decision["outcome"] == "deemed_approved" and decision["deemed"]
    assert row["Stage"] == "decided"
    assert any("decided" in m["subject"] for m in world.db.mail_to("jo@example.com"))   # SM s 69(4)
    assert pipeline.apply_deemed(world.db, datetime(2026, 12, 3)) == 0


def test_deadline_on_a_weekend_moves_to_monday(world):
    _committee(world)
    case = _case(world, now=datetime(2026, 11, 14, 2, 0))                     # Sat 14 Nov + 21 = Sat 5 Dec
    assert case["due_date"] == "2026-12-07"


def test_owner_motion_not_agreed_and_records_deadline_has_no_deemed_outcome(world):
    _committee(world)
    reno = _case(world, "renovation")
    records = _case(world, "records", {"which": "Minutes", "how": "Email copies"})
    assert pipeline.apply_deemed(world.db, NOW + timedelta(days=60)) == 1
    assert json.loads(world.db.get(store.CASES, reno["id"])["Decision"])["outcome"] == "not_agreed"
    assert world.db.get(store.CASES, records["id"])["Status"] == "new"


def test_cron_applies_deemed_and_keeps_its_answer_shape(world):
    _committee(world)
    case = _case(world)
    body, status = world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"},
                              now=NOW + timedelta(days=30))
    assert status == 200 and set(body) == {"ok", "sent", "queue"}
    assert world.db.get(store.CASES, case["id"])["Status"] == "decided"


# ---------- topics as data ----------

def test_topic_stages_are_checked(world):
    good = topics.get(world.db, world.building, "pet")
    definition = {k: good[k] for k in ("label", "audience", "handler", "fields", "steps", "deadline", "stages")}
    definition["stages"] = json.loads(json.dumps(definition["stages"]))
    definition["stages"][0]["buttons"][0]["next"] = "nowhere"
    body, status = world.call("POST", "/admin/topics", {"key": "pet", "definition": definition}, email=ADMIN)
    assert status == 400 and "next" in body["error"]
    definition["stages"][0]["buttons"][0]["next"] = "checking"
    definition["deadline"] = dict(definition["deadline"], outcome="maybe")
    assert world.call("POST", "/admin/topics", {"key": "pet", "definition": definition}, email=ADMIN)[1] == 400


def test_old_topic_gets_a_plain_pipeline_and_upgrades_from_seed(world):
    row = [r for r in world.db.find(store.TOPICS) if r["Topic_Key"] == "pet"][0]
    old = json.loads(row["Definition"])
    for key in ("stages", "vote", "after_decision"):
        old.pop(key)
    old["deadline"] = {"days": 21, "if_missed": "old words"}
    old["label"] = "Pets (edited)"
    world.db.update(store.TOPICS, {"ROWID": row["ROWID"], "Definition": json.dumps(old)})
    _committee(world)
    case = _case(world)
    body, _ = world.call("GET", "/case", {"id": case["id"]}, email="secretary@example.com")
    assert [s["key"] for s in body["case"]["stage"]["path"]] == ["received", "working", "done"]
    assert body["case"]["missed"]["banner"] == "old words"
    body, status = world.call("POST", "/admin/topics", {"from_seed": "altai"}, email=ADMIN)
    assert status == 200 and body["counts"]["updated"] == 8
    pet = topics.get(world.db, world.building, "pet")
    assert pet["label"] == "Pets (edited)" and pet["stages"][1]["key"] == "checking"
    assert world.call("POST", "/admin/topics", {"from_seed": "altai"}, email="secretary@example.com")[1] == 403
