"""The API table end to end through main.route: the shapes the portal page reads."""

import base64

import main
from conftest import ADMIN

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 50


def test_sign_up_to_decision_through_routes(world):
    # Sign in and set a name.
    assert world.call("POST", "/auth/start", {"email": "jo@example.com"}) == ({"ok": True}, 200)
    body, status = world.call("POST", "/auth/verify", {"email": "jo@example.com", "code": world.last_code("jo@example.com")})
    assert status == 200 and body["user"]["email"] == "jo@example.com"
    world.tokens["jo@example.com"] = body["token"]
    body, _ = world.call("POST", "/me/name", {"name": "Jo"}, email="jo@example.com")
    assert body["user"]["name"] == "Jo"

    # Claim, then the admin approves.
    body, status = world.call("POST", "/claims", {"claims": [{"unit_id": world.units["4"], "relation": "owner"}]},
                              email="jo@example.com")
    assert status == 200 and body["memberships"][0]["status"] == "pending"
    assert world.call("GET", "/approvals", email="jo@example.com")[1] == 403
    body, _ = world.call("GET", "/approvals", email=ADMIN)
    pending = body["pending"][0]
    assert {k: pending[k] for k in ("user_email", "user_name", "unit_label", "relation")} == {
        "user_email": "jo@example.com", "user_name": "Jo", "unit_label": "Unit 4", "relation": "owner"}
    body, status = world.call("POST", "/approvals/decide", {"id": pending["id"], "decision": "approve"}, email=ADMIN)
    assert status == 200 and body["membership"]["status"] == "approved"

    # Roles and members.
    body, _ = world.call("POST", "/roles", {"email": "c@example.com", "role": "committee", "on": True}, email=ADMIN)
    assert {"email": "c@example.com", "name": "", "role": "committee"} in body["roles"]
    body, _ = world.call("GET", "/members", email=ADMIN)
    assert body["members"][0]["unit_label"] == "Unit 4" and body["roles"]

    # Topics and a case with a photo, downloaded by the resident and the handler.
    body, _ = world.call("GET", "/topics", email="jo@example.com")
    assert {"key", "label", "intro", "fields", "draft", "deadline"} <= set(body["topics"][0])
    photo = {"name": "cat.jpg", "type": "image/jpeg", "data": "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()}
    body, status = world.call("POST", "/cases", {"unit_id": world.units["4"], "topic_key": "pet",
                                                 "answers": {"animal": "Cat", "how_many": "1", "where_kept": "In"},
                                                 "files": [photo]}, email="jo@example.com")
    assert status == 200
    case_id = body["case"]["id"]
    for email in ("jo@example.com", "c@example.com"):
        result = world.call("GET", "/case/file", {"id": case_id, "n": "0"}, email=email)
        assert isinstance(result, main.FileResult) and result.data == JPEG and result.content_type == "image/jpeg"
    assert world.call("GET", "/case/file", {"id": case_id, "n": "3"}, email="jo@example.com")[1] == 404

    # Notices and documents.
    body, status = world.call("POST", "/notices", {"title": "Pool", "body": "Closed", "audience": "all"},
                              email="c@example.com")
    assert status == 200 and body["notices"][0]["title"] == "Pool"
    body, _ = world.call("POST", "/notices/delete", {"id": body["notices"][0]["id"]}, email="c@example.com")
    assert body["notices"] == []
    pdf = base64.b64encode(b"%PDF-1.4 x").decode()
    body, _ = world.call("POST", "/docs", {"title": "By-laws", "category": "By-laws", "audience": "owners",
                                          "name": "bylaws.pdf", "data": pdf}, email="c@example.com")
    doc_id = body["docs"][0]["id"]
    result = world.call("GET", "/docs/file", {"id": doc_id}, email="jo@example.com")
    assert isinstance(result, main.FileResult) and result.content_type == "application/pdf"
    body, _ = world.call("GET", "/docs", email="jo@example.com")
    assert body["docs"][0]["name"] == "bylaws.pdf"

    # Removing Jo stops access at once; logging out kills the token.
    member_id = world.call("GET", "/members", email=ADMIN)[0]["members"][0]["id"]
    assert world.call("POST", "/members/remove", {"id": member_id}, email=ADMIN) == ({"ok": True}, 200)
    assert world.call("GET", "/case", {"id": case_id}, email="jo@example.com")[1] == 404
    assert world.call("POST", "/auth/logout", email="jo@example.com") == ({"ok": True}, 200)
    assert world.call("GET", "/me", email="jo@example.com")[1] == 401
