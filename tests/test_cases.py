"""Task 4: topics and tracked cases, and who may see them."""

import base64
import json

import pytest

import buildings
import cases
import people
import store
import topics
from conftest import ADMIN, NOW
from errors import ApiError

PET = {"animal": "Cat", "how_many": "1", "where_kept": "Inside", "junk": "dropped"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _pet(world, email="jo@example.com", unit="4", answers=None, files=None):
    return cases.create(world.db, world.building, world.user(email), world.ctx(email), world.units[unit], "pet",
                        dict(answers or PET), files or [], NOW)


def _expect(status, fn, *args):
    with pytest.raises(ApiError) as err:
        fn(*args)
    assert err.value.status == status
    return err.value


def test_create_sets_ref_handler_steps_and_due(world):
    world.member("jo@example.com", "4")
    out = _pet(world)
    case = out["case"]
    assert case["ref"] == "ALT-0001" and case["handler"] == "committee" and case["status"] == "new"
    assert case["answers"] == {"animal": "Cat", "breed_size": "", "how_many": "1", "where_kept": "Inside",
                               "registered": False}
    assert out["steps"][0] == {"title": "Check the request against the animals by-law",
                               "rule": "By-law (animals) — DRAFT", "done": False}
    assert case["days_left"] == 21 and out["topic"]["draft"] is True
    assert _pet(world)["case"]["ref"] == "ALT-0002"
    assert [e["kind"] for e in out["events"]] == ["created"]


def test_missing_required_field_refused(world):
    world.member("jo@example.com", "4")
    err = _expect(400, _pet, world, "jo@example.com", "4", {"animal": "", "how_many": "1", "where_kept": "x"})
    assert "What animal?" in err.message
    _expect(400, _pet, world, "jo@example.com", "4", dict(PET, how_many="lots"))
    assert world.db.find(store.CASES) == []


def test_resident_cannot_see_other_units_case(world):
    world.member("jo@example.com", "4")
    world.member("sam@example.com", "5")
    case_id = _pet(world)["case"]["id"]
    _expect(404, cases.detail, world.db, world.building, world.ctx("sam@example.com"), case_id, NOW)
    _expect(404, cases.file, world.db, world.building, world.ctx("sam@example.com"), case_id, 0)
    _expect(404, cases.message, world.db, world.building, world.ctx("sam@example.com"), case_id, "hi", False, NOW)
    assert cases.list_mine(world.db, world.building, world.ctx("sam@example.com"), NOW) == []
    body, status = world.call("GET", "/case", {"id": case_id}, email="sam@example.com")
    assert status == 404 and body["ok"] is False and "case" not in body


def test_tenant_sees_own_case_owner_sees_tenants_case(world):
    world.member("owner@example.com", "4", "owner")
    world.member("tenant@example.com", "4", "tenant")
    world.member("tenant2@example.com", "4", "tenant")
    case_id = _pet(world, "tenant@example.com")["case"]["id"]
    assert cases.detail(world.db, world.building, world.ctx("owner@example.com"), case_id, NOW)
    _expect(404, cases.detail, world.db, world.building, world.ctx("tenant2@example.com"), case_id, NOW)


def test_other_building_case_404(world):
    world.member("jo@example.com", "4")
    case_id = _pet(world)["case"]["id"]
    other = buildings.from_row(world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other",
                                                                 "Brand": "{}", "Settings": "{}"}))
    boss = world.user("boss@example.com")
    world.db.insert(store.ROLES, {"User_Id": int(boss["id"]), "Building_Id": int(other["id"]), "Role": "admin"})
    _expect(404, cases.detail, world.db, other, people.context(world.db, boss, other), case_id, NOW)
    # The same person asking through Altai has no role there: still 404.
    _expect(404, cases.detail, world.db, world.building, world.ctx("boss@example.com"), case_id, NOW)


def test_pending_member_cannot_submit(world):
    world.member("pending@example.com", "4", status="pending")
    world.member("removed@example.com", "5", status="removed")
    _expect(403, _pet, world, "pending@example.com", "4")
    _expect(403, _pet, world, "removed@example.com", "5")
    body, status = world.call("GET", "/topics", email="pending@example.com")
    assert status == 403 and body["ok"] is False


def test_removed_member_loses_their_case(world):
    world.member("jo@example.com", "4")
    case_id = _pet(world)["case"]["id"]
    membership = world.db.find(store.MEMBERSHIPS, {"Status": "approved"})[0]
    people.remove(world.db, world.ctx(ADMIN), world.building, membership["ROWID"])
    _expect(404, cases.detail, world.db, world.building, world.ctx("jo@example.com"), case_id, NOW)


def test_internal_note_hidden_from_resident(world):
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    case_id = _pet(world)["case"]["id"]
    handler = world.ctx("c@example.com")
    cases.message(world.db, world.building, handler, case_id, "SECRET note", False, NOW)
    cases.message(world.db, world.building, handler, case_id, "Please send a photo", True, NOW)
    cases.set_step(world.db, world.building, handler, case_id, 0, True, NOW)
    seen = cases.detail(world.db, world.building, world.ctx("jo@example.com"), case_id, NOW)
    bodies = " ".join(e["body"] for e in seen["events"])
    assert "SECRET" not in bodies and "Please send a photo" in bodies and "Done:" not in bodies
    assert seen["steps"][0]["done"] is True
    assert any("SECRET" in e["body"] for e in cases.detail(world.db, world.building, handler, case_id, NOW)["events"])
    assert not any("SECRET" in m["html"] for m in world.db.mail_to("jo@example.com"))
    # A resident's message is never internal, whatever the page sends.
    event = cases.message(world.db, world.building, world.ctx("jo@example.com"), case_id, "Here", False, NOW)
    assert event["internal"] is False and event["from_resident"] is True


def test_refusal_needs_reasons(world):
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    case_id = _pet(world)["case"]["id"]
    handler = world.ctx("c@example.com")
    _expect(400, cases.decide, world.db, world.building, handler, case_id, "refused", "", "", NOW)
    _expect(400, cases.decide, world.db, world.building, handler, case_id, "approved_with_conditions", "", "", NOW)
    _expect(403, cases.decide, world.db, world.building, world.ctx("jo@example.com"), case_id, "approved", "", "", NOW)
    out = cases.decide(world.db, world.building, handler, case_id, "refused", "Too many pets", "", NOW)
    assert out["case"]["status"] == "decided" and out["case"]["decision"]["outcome"] == "refused"
    assert any("decided" in m["subject"] for m in world.db.mail_to("jo@example.com"))


def test_handler_inbox_only_own_handler_type(world):
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    world.role("m@example.com", "manager")
    _pet(world)
    cases.create(world.db, world.building, world.user("jo@example.com"), world.ctx("jo@example.com"),
                 world.units["4"], "maintenance", {"where": "Lift", "problem": "Stuck", "urgent": "Yes"}, [], NOW)
    assert [c["handler"] for c in cases.list_inbox(world.db, world.building, world.ctx("c@example.com"))] == ["committee"]
    assert [c["handler"] for c in cases.list_inbox(world.db, world.building, world.ctx("m@example.com"))] == ["manager"]
    assert len(cases.list_inbox(world.db, world.building, world.ctx(ADMIN))) == 2
    _expect(403, cases.list_inbox, world.db, world.building, world.ctx("jo@example.com"))
    pet_id = [c["id"] for c in cases.list_mine(world.db, world.building, world.ctx("jo@example.com")) if c["handler"] == "committee"][0]
    # A manager can't even see a committee case, so acting on it is 404 like any unseen case.
    _expect(404, cases.set_status, world.db, world.building, world.ctx("m@example.com"), pet_id, "in_progress", "", NOW)


def test_new_case_emails_handlers(world):
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    world.role("m@example.com", "manager")
    _pet(world)
    assert any("ALT-0001" in m["subject"] for m in world.db.mail_to("c@example.com"))
    assert world.db.mail_to("m@example.com") == []


def test_files_saved_and_downloadable_by_case_viewers(world):
    world.member("jo@example.com", "4")
    photo = {"name": "cat pic.jpg", "type": "image/jpeg", "data": base64.b64encode(JPEG).decode()}
    out = _pet(world, files=[photo])
    assert out["case"]["files"][0]["name"] == "cat-pic.jpg"
    data, kind, _ = cases.file(world.db, world.building, world.ctx("jo@example.com"), out["case"]["id"], 0)
    assert data == JPEG and kind == "image/jpeg"


def test_bad_or_big_file_refused_before_saving(world):
    world.member("jo@example.com", "4")
    fake = {"name": "x.jpg", "data": base64.b64encode(b"MZ not a photo").decode()}
    _expect(400, _pet, world, "jo@example.com", "4", None, [fake])
    big = {"name": "big.jpg", "data": base64.b64encode(JPEG + b"\x00" * (5 * 1024 * 1024)).decode()}
    _expect(400, _pet, world, "jo@example.com", "4", None, [big])
    assert world.db.find(store.CASES) == [] and world.db.files == {}


def test_too_long_answers_refused(world):
    world.member("jo@example.com", "4")
    _expect(400, _pet, world, "jo@example.com", "4", dict(PET, where_kept="x" * 4001))


def test_tenant_cannot_use_owner_only_topic(world):
    world.member("tenant@example.com", "4", "tenant")
    _expect(404, cases.create, world.db, world.building, world.user("tenant@example.com"),
            world.ctx("tenant@example.com"), world.units["4"], "renovation", {"work": "x", "affects_common": "No"},
            [], NOW)
    keys = [t["key"] for t in topics.for_member(world.db, world.building, world.ctx("tenant@example.com"))]
    assert "renovation" not in keys and "records" not in keys and "pet" in keys


def test_ref_retries_on_duplicate(world):
    world.member("jo@example.com", "4")
    first = _pet(world)["case"]
    # Someone else's insert took the next number between our count and our insert.
    original = cases._next_number
    cases._next_number = lambda db, building: 1
    try:
        assert _pet(world)["case"]["ref"] == "ALT-0002"
    finally:
        cases._next_number = original
    assert first["ref"] == "ALT-0001"


def test_case_routes_shape(world):
    world.member("jo@example.com", "4")
    world.role("c@example.com", "committee")
    body, status = world.call("POST", "/cases", {"unit_id": world.units["4"], "topic_key": "pet", "answers": PET},
                              email="jo@example.com")
    assert status == 200 and body["ok"] and set(body) >= {"case", "steps", "events", "topic"}
    case_id = body["case"]["id"]
    body, _ = world.call("GET", "/cases", {"scope": "inbox"}, email="c@example.com")
    row = body["cases"][0]
    assert set(row) >= {"id", "ref", "title", "status", "unit_label", "due_at", "days_left", "handler"}
    body, status = world.call("POST", "/case/step", {"id": case_id, "index": 0, "done": True}, email="c@example.com")
    assert status == 200 and body["steps"][0]["done"] is True
    body, status = world.call("POST", "/case/status", {"id": case_id, "status": "in_progress", "note": "On it"},
                              email="c@example.com")
    assert status == 200 and body["case"]["status"] == "in_progress"
    body, status = world.call("POST", "/case/message", {"id": case_id, "body": "Thanks", "to_resident": True},
                              email="c@example.com")
    assert status == 200 and body["event"]["internal"] is False
    body, status = world.call("POST", "/case/decide", {"id": case_id, "outcome": "approved_with_conditions",
                                                       "conditions": "Keep it inside"}, email="c@example.com")
    assert status == 200 and body["case"]["decision"]["conditions"] == "Keep it inside"
    body, _ = world.call("GET", "/case", {"id": case_id}, email="jo@example.com")
    assert body["case"]["status"] == "decided" and json.dumps(body)
