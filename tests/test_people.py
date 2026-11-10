"""Task 3: unit claims, approvals and roles."""

import json

import pytest

import buildings
import people
import store
from conftest import ADMIN
from errors import ApiError


def _claim(world, email, unit_no, relation="owner"):
    return people.claim(world.db, world.user(email), world.building,
                        [{"unit_id": world.units[unit_no], "relation": relation}])


def _pending_id(world, email):
    return [p for p in people.pending(world.db, world.building) if p["user_email"] == email][0]["id"]


def _other_building(world):
    row = world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other", "Brand": "{}",
                                            "Settings": json.dumps({"ref_prefix": "OTH"})})
    return buildings.from_row(row)


def test_claim_creates_pending_and_emails_approvers(world):
    world.role("approver@example.com", "approver")
    memberships = _claim(world, "jo@example.com", "4")
    assert [(m["unit_label"], m["status"]) for m in memberships] == [("Unit 4", "pending")]
    for email in ("approver@example.com", ADMIN):
        assert any("approve" in m["subject"] for m in world.db.mail_to(email))
    assert world.ctx("jo@example.com")["unit_ids"] == set()


def test_approve_gives_unit_access(world):
    _claim(world, "jo@example.com", "4")
    out = people.decide(world.db, world.ctx(ADMIN), world.building, _pending_id(world, "jo@example.com"),
                        "approve", "On the roll")
    assert out["status"] == "approved"
    ctx = world.ctx("jo@example.com")
    assert ctx["unit_ids"] == {world.units["4"]} and ctx["can"]["submit"] and ctx["can"]["owner"]
    assert any("You're in" in m["subject"] for m in world.db.mail_to("jo@example.com"))


def test_reject_gives_no_access(world):
    _claim(world, "jo@example.com", "4")
    people.decide(world.db, world.ctx(ADMIN), world.building, _pending_id(world, "jo@example.com"), "reject", "")
    ctx = world.ctx("jo@example.com")
    assert ctx["unit_ids"] == set() and not ctx["can"]["submit"]


def test_remove_stops_access(world):
    world.member("jo@example.com", "4")
    membership = world.db.find(store.MEMBERSHIPS, {"Status": "approved"})[0]
    people.remove(world.db, world.ctx(ADMIN), world.building, membership["ROWID"])
    assert world.ctx("jo@example.com")["unit_ids"] == set()


def test_one_login_two_units(world):
    people.claim(world.db, world.user("jo@example.com"), world.building,
                 [{"unit_id": world.units["4"], "relation": "owner"},
                  {"unit_id": world.units["7"], "relation": "tenant"}])
    for item in people.pending(world.db, world.building):
        people.decide(world.db, world.ctx(ADMIN), world.building, item["id"], "approve", "")
    ctx = world.ctx("jo@example.com")
    assert ctx["unit_ids"] == {world.units["4"], world.units["7"]}
    assert ctx["owner_unit_ids"] == {world.units["4"]}


def test_non_approver_cannot_decide(world):
    _claim(world, "jo@example.com", "4")
    world.member("other@example.com", "5")
    world.role("committee@example.com", "committee")
    for email in ("other@example.com", "committee@example.com", "jo@example.com"):
        with pytest.raises(ApiError) as err:
            people.decide(world.db, world.ctx(email), world.building, _pending_id(world, "jo@example.com"),
                          "approve", "")
        assert err.value.status == 403


def test_claim_for_unit_of_other_building_refused(world):
    other = _other_building(world)
    unit = world.db.insert(store.UNITS, {"Building_Id": int(other["id"]), "Unit_No": "1"})
    with pytest.raises(ApiError) as err:
        people.claim(world.db, world.user("jo@example.com"), world.building,
                     [{"unit_id": unit["ROWID"], "relation": "owner"}])
    assert err.value.status == 400
    assert world.db.find(store.MEMBERSHIPS) == []


def test_approver_of_other_building_cannot_decide(world):
    _claim(world, "jo@example.com", "4")
    other = _other_building(world)
    user = world.user("boss@example.com")
    world.db.insert(store.ROLES, {"User_Id": int(user["id"]), "Building_Id": int(other["id"]), "Role": "admin"})
    ctx = people.context(world.db, user, other)
    with pytest.raises(ApiError) as err:
        people.decide(world.db, ctx, other, _pending_id(world, "jo@example.com"), "approve", "")
    assert err.value.status == 404


def test_roles_admin_only_and_last_admin_kept(world):
    world.role("approver@example.com", "approver")
    with pytest.raises(ApiError):
        people.set_role(world.db, world.ctx("approver@example.com"), world.building, "m@example.com", "manager", True)
    roles = people.set_role(world.db, world.ctx(ADMIN), world.building, "M@example.com", "manager", True)
    assert {"email": "m@example.com", "name": "", "role": "manager"} in roles
    with pytest.raises(ApiError):
        people.set_role(world.db, world.ctx(ADMIN), world.building, ADMIN, "admin", False)


def test_me_route_shape(world):
    world.member("jo@example.com", "4", status="pending")
    body, status = world.call("GET", "/me", email="jo@example.com")
    assert status == 200 and body["ok"]
    assert body["user"]["email"] == "jo@example.com" and body["roles"] == []
    assert body["memberships"][0]["unit_label"] == "Unit 4" and body["memberships"][0]["status"] == "pending"
    assert set(body["can"]) == {"submit", "handle", "approve", "admin", "owner"} and not body["can"]["submit"]
