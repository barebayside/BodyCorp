"""Task 1: routing, the JSON envelope and the ZCQL builder."""

import main
import store


def test_unknown_route_returns_404_ok_false(world):
    body, status = main.route(world.db, "GET", "/nope", {})
    assert status == 404 and body["ok"] is False
    body, status = main.route(world.db, "DELETE", "/cases", {})
    assert status == 404 and body["ok"] is False


def test_find_escapes_quotes(world):
    assert store.build_where({"Email": "a'b"}) == "Email = 'a''b'"
    assert store.build_where({"User_Id": 5, "Active": True}) == "User_Id = 5 AND Active = true"
    world.db.insert(store.USERS, {"Email": "o'brien@example.com", "Name": ""})
    assert len(world.db.find(store.USERS, {"Email": "o'brien@example.com"})) == 1


def test_route_strips_function_prefix_and_signs_in(world):
    body, status = main.route(world.db, "GET", "/server/bodycorp_api/building/", {"b": "altai"})
    assert status == 200 and body["ok"] is True
    assert body["building"]["name"] == "Altai on the Park"
    assert [u["label"] for u in body["units"]][:3] == ["Unit 1", "Unit 2", "Unit 3"]


def test_signed_in_routes_need_a_token(world):
    body, status = world.call("GET", "/me")
    assert status == 401 and body["ok"] is False


def test_unknown_building_404(world):
    body, status = world.call("GET", "/building", {"b": "nowhere"})
    assert status == 404 and body["ok"] is False


def test_too_long_value_refused_not_crashed(world):
    body, status = world.call("POST", "/me/name", {"name": "x" * 101}, email="a@example.com")
    assert status == 400 and body["ok"] is False
