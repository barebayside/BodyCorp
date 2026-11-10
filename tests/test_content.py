"""Task 6: notices, documents, admin and the bootstrap seed."""

import base64

import pytest

import admin
import content
import store
from conftest import ADMIN
from errors import ApiError

PDF = b"%PDF-1.4 minutes"


def _doc(world, email, audience, data=PDF, title="Minutes"):
    return content.add_doc(world.db, world.building, world.ctx(email), title, "Minutes", audience,
                           "minutes.pdf", base64.b64encode(data).decode())


def test_tenant_never_sees_owner_notice_or_doc(world):
    world.role("c@example.com", "committee")
    world.member("tenant@example.com", "4", "tenant")
    world.member("owner@example.com", "5", "owner")
    content.post_notice(world.db, world.building, world.ctx("c@example.com"), "Owners only", "Levy", "owners")
    content.post_notice(world.db, world.building, world.ctx("c@example.com"), "Pool closed", "Cleaning", "all")
    _doc(world, "c@example.com", "owners", title="Secret minutes")
    _doc(world, "c@example.com", "all", title="Pool rules")
    tenant = world.ctx("tenant@example.com")
    assert [n["title"] for n in content.notices(world.db, world.building, tenant)] == ["Pool closed"]
    assert [d["title"] for d in content.docs(world.db, world.building, tenant)] == ["Pool rules"]
    owners_doc = world.db.find(store.DOCS, {"Audience": "owners"})[0]["ROWID"]
    with pytest.raises(ApiError) as err:
        content.doc_file(world.db, world.building, tenant, owners_doc)
    assert err.value.status == 404
    assert not any("Owners only" in m["subject"] for m in world.db.mail_to("tenant@example.com"))
    assert any("Owners only" in m["subject"] for m in world.db.mail_to("owner@example.com"))
    owner = world.ctx("owner@example.com")
    assert len(content.notices(world.db, world.building, owner)) == 2
    assert content.doc_file(world.db, world.building, owner, owners_doc)[0] == PDF


def test_only_handlers_post_notices(world):
    world.member("owner@example.com", "5", "owner")
    world.role("approver@example.com", "approver")
    for email in ("owner@example.com", "approver@example.com", "nobody@example.com"):
        with pytest.raises(ApiError) as err:
            content.post_notice(world.db, world.building, world.ctx(email), "Hi", "x", "all")
        assert err.value.status == 403
    world.role("m@example.com", "manager")
    assert content.post_notice(world.db, world.building, world.ctx("m@example.com"), "Hi", "x", "all")


def test_pending_member_sees_no_notices(world):
    world.member("p@example.com", "4", status="pending")
    body, status = world.call("GET", "/notices", email="p@example.com")
    assert status == 403 and body["ok"] is False


def test_bootstrap_needs_key_and_is_idempotent(world):
    for key in (None, "", "wrong"):
        with pytest.raises(ApiError) as err:
            admin.bootstrap(world.db, key, "altai", ADMIN)
        assert err.value.status == 403
    counts = {t: len(rows) for t, rows in world.db.tables.items()}
    again = admin.bootstrap(world.db, "admin-key", "altai", ADMIN)
    assert again["created"] is False and again["counts"]["units_added"] == 0 and again["counts"]["topics_added"] == 0
    assert {t: len(rows) for t, rows in world.db.tables.items()} == counts
    assert again["counts"]["units"] == 10 and again["counts"]["topics"] == 8
    assert all('"draft": true' in t["Definition"] for t in world.db.find(store.TOPICS))
    body, status = world.call("POST", "/admin/bootstrap", {"seed": "altai", "admin_email": ADMIN},
                              headers={"X-Admin-Key": "admin-key"})
    assert status == 200 and body["ok"] and body["building"]["slug"] == "altai"


def test_doc_upload_over_5mb_refused(world):
    world.role("c@example.com", "committee")
    with pytest.raises(ApiError) as err:
        _doc(world, "c@example.com", "all", data=PDF + b"x" * (5 * 1024 * 1024))
    assert err.value.status == 400
    with pytest.raises(ApiError):
        _doc(world, "c@example.com", "all", data=b"<html>not a pdf</html>")
    assert world.db.find(store.DOCS) == [] and world.db.files == {}


def test_doc_delete_removes_file(world):
    world.role("c@example.com", "committee")
    _doc(world, "c@example.com", "all")
    row = world.db.find(store.DOCS)[0]
    assert content.delete_doc(world.db, world.building, world.ctx("c@example.com"), row["ROWID"]) == []
    assert world.db.files == {}


def test_admin_routes(world):
    body, status = world.call("POST", "/admin/building", {"brand": {"primary": "#123456"}}, email=ADMIN)
    assert status == 200 and body["building"]["brand"]["primary"] == "#123456"
    assert body["building"]["brand"]["accent"] == "#c9a227"
    body, status = world.call("POST", "/admin/building", {"brand": {"primary": "red"}}, email=ADMIN)
    assert status == 400
    body, status = world.call("POST", "/admin/building", {"brand": {"banner_url": "https://x.org/park.jpg"}}, email=ADMIN)
    assert status == 200 and body["building"]["brand"]["banner_url"] == "https://x.org/park.jpg"
    assert body["building"]["brand"]["primary"] == "#123456"
    body, status = world.call("POST", "/admin/building", {"brand": {"banner_url": "http://x.org/park.jpg"}}, email=ADMIN)
    assert status == 400
    body, status = world.call("POST", "/admin/units", {"units": [{"unit_no": "11", "lot_no": "21"},
                                                                 {"unit_no": "1"}]}, email=ADMIN)
    assert status == 200 and len(body["units"]) == 11
    definition = {"label": "Parking", "audience": ["owner"], "handler": "manager", "draft": True,
                  "fields": [{"key": "bay", "label": "Bay", "type": "text", "required": True}]}
    body, status = world.call("POST", "/admin/topics", {"key": "parking", "definition": definition, "sort": 90},
                              email=ADMIN)
    assert status == 200 and body["topics"][-1]["key"] == "parking"
    world.member("jo@example.com", "4")
    body, status = world.call("POST", "/admin/units", {"units": [{"unit_no": "12"}]}, email="jo@example.com")
    assert status == 403
