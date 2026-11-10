"""Phone notifications wired into the portal: the /push routes, the brand keys, and which events push to whom.

Every push here goes to a pretend phone (a fake sender standing in for Apple/Google), which decrypts what it
was sent, so each test checks the real message: title, body and the screen it opens."""

import json
from datetime import timedelta

import pytest

pytest.importorskip("cryptography")

import push  # noqa: E402
import store  # noqa: E402
from conftest import ADMIN, NOW  # noqa: E402
from test_push import decrypt, device  # noqa: E402

PET = {"animal": "Cat", "how_many": "1", "where_kept": "Inside"}
APP = "portal.html?b=altai#/"


class Phones:
    """One pretend phone per person. `got(email)` = what that person's phone showed, oldest first."""

    def __init__(self, world, monkeypatch):
        public, private = push.make_vapid_keys()
        monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
        monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
        monkeypatch.setenv("VAPID_SUBJECT", "mailto:support@example.com")
        monkeypatch.setattr(push, "post", self)
        self.world, self.phones, self.sent, self.answer = world, {}, [], 201

    def add(self, email, building=None):
        key, keys = device()
        endpoint = "https://fcm.googleapis.com/fcm/send/" + email.replace("@", "-at-")
        if building:
            endpoint += "-" + building["slug"]
        push.subscribe(self.world.db, building or self.world.building, self.world.user(email),
                       {"endpoint": endpoint, "keys": keys}, "test")
        self.phones[endpoint] = (email, key, keys["auth"])

    def __call__(self, endpoint, headers, data):
        if isinstance(self.answer, Exception):
            raise self.answer
        self.sent.append((endpoint, data))
        return self.answer

    def got(self, email):
        out = []
        for endpoint, data in self.sent:
            who, key, auth = self.phones[endpoint]
            if who == email:
                out.append(json.loads(decrypt(data, key, auth)))
        return out

    def clear(self):
        self.sent.clear()


@pytest.fixture
def phones(world, monkeypatch):
    return Phones(world, monkeypatch)


def _committee(world):
    for position in ("chair", "secretary", "treasurer"):
        world.role("{}@example.com".format(position), position)


def _pet(world, email="jo@example.com", unit="4", now=NOW):
    if not world.db.find(store.MEMBERSHIPS, {"User_Id": int(world.user(email)["id"])}):
        world.member(email, unit)
    body, status = world.call("POST", "/cases", {"unit_id": world.units[unit], "topic_key": "pet", "answers": PET},
                              email=email, now=now)
    assert status == 200, body
    return body["case"]


def _other_building(world):
    row = world.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other Tower", "Brand": "{}", "Settings": "{}"})
    return {"id": str(row["ROWID"]), "slug": "other", "name": "Other Tower", "brand": {}, "settings": {}}


def _subscription():
    _, keys = device()
    return {"endpoint": "https://web.push.apple.com/abc", "keys": keys}


# ---------- the routes ----------

def test_push_key_is_public_and_empty_when_not_set_up(world, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    assert world.call("GET", "/push/key") == ({"ok": True, "key": ""}, 200)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPublicKey")
    assert world.call("GET", "/push/key") == ({"ok": True, "key": "BPublicKey"}, 200)
    assert world.call("GET", "/push/key", {"b": "nowhere"})[1] == 404


def test_subscribe_only_for_people_of_that_building(world):
    world.member("jo@example.com", "4")
    world.member("pending@example.com", "5", status="pending")
    world.role("c@example.com", "committee")
    world.role("approver@example.com", "approver")
    sub = {"subscription": _subscription()}

    assert world.call("POST", "/push/subscribe", sub)[1] == 401
    for email in ("jo@example.com", "c@example.com", "approver@example.com", ADMIN):
        body, status = world.call("POST", "/push/subscribe", sub, email=email)
        assert (body, status) == ({"ok": True, "subscribed": True}, 200), email
    for email in ("pending@example.com", "stranger@example.com"):
        assert world.call("POST", "/push/subscribe", {"subscription": _subscription()}, email=email)[1] == 403
    # The same phone moved to whoever subscribed last; nobody outside the building got a row.
    rows = world.db.find(store.PUSH_SUBS)
    assert len(rows) == 1 and str(rows[0]["User_Id"]) == world.user(ADMIN)["id"]
    assert world.call("POST", "/push/subscribe", {"subscription": {"endpoint": "http://x"}},
                      email="jo@example.com")[1] == 400


def test_a_member_of_one_building_cannot_subscribe_in_another(world):
    world.member("jo@example.com", "4")
    _other_building(world)
    assert world.call("POST", "/push/subscribe", {"b": "other", "subscription": _subscription()},
                      email="jo@example.com")[1] == 403
    assert world.db.find(store.PUSH_SUBS) == []


def test_unsubscribe_forgets_the_device(world):
    world.member("jo@example.com", "4")
    sub = _subscription()
    world.call("POST", "/push/subscribe", {"subscription": sub}, email="jo@example.com")
    assert world.call("DELETE", "/push/subscribe", {"endpoint": sub["endpoint"]})[1] == 401
    body, status = world.call("DELETE", "/push/subscribe", {"endpoint": sub["endpoint"]}, email="jo@example.com")
    assert (body, status) == ({"ok": True, "subscribed": False, "removed": 1}, 200)
    assert world.db.find(store.PUSH_SUBS) == []
    assert world.call("DELETE", "/push/subscribe", {}, email="jo@example.com")[1] == 400


# ---------- brand keys for the app card and icons ----------

def test_admin_sets_the_app_card_and_icons_and_the_page_gets_them(world):
    brand = {"app_manifest": "manifest-altai.webmanifest", "app_icon": "icons/altai-192.png",
             "app_badge": "icons/altai-badge-96.png", "apple_touch": "icons/altai-180.png", "app_short_name": "Alatai"}
    body, status = world.call("POST", "/admin/building", {"brand": brand}, email=ADMIN)
    assert status == 200 and all(body["building"]["brand"][k] == v for k, v in brand.items())
    public = world.call("GET", "/building")[0]["building"]["brand"]
    assert all(public[k] == v for k, v in brand.items())
    for bad in ({"app_icon": "https://evil.example/x.png"}, {"app_icon": "../icons/a.png"},
                {"apple_touch": "icons/A B.png"}, {"app_manifest": "manifest.json"},
                {"app_manifest": "https://x/manifest-a.webmanifest"}, {"app_badge": "icons/x.svg"}):
        assert world.call("POST", "/admin/building", {"brand": bad}, email=ADMIN)[1] == 400, bad
    # Empty clears it (the product icons are used instead).
    body, _ = world.call("POST", "/admin/building", {"brand": {"app_icon": ""}}, email=ADMIN)
    assert body["building"]["brand"]["app_icon"] == ""


# ---------- which events push, and to whom ----------

def test_new_request_pushes_the_handlers_with_the_case_link(world, phones):
    _committee(world)
    world.member("jo@example.com", "4")
    for email in ("chair@example.com", "secretary@example.com", "jo@example.com"):
        phones.add(email)
    case = _pet(world)
    for email in ("chair@example.com", "secretary@example.com"):
        shown = phones.got(email)
        assert len(shown) == 1
        assert shown[0]["title"] == world.building["name"]
        assert shown[0]["body"] == "New request {}: Keep a pet".format(case["ref"])
        assert shown[0]["url"] == APP + "case/" + case["id"]
    assert phones.got("jo@example.com") == []


def test_new_request_leads_with_the_deadline_when_it_is_near(world, phones):
    _committee(world)
    world.member("jo@example.com", "4")
    phones.add("secretary@example.com")
    body, _ = world.call("POST", "/cases", {"unit_id": world.units["4"], "topic_key": "records",
                                            "answers": {"which": "Minutes", "how": "Email copies"}},
                         email="jo@example.com")
    ref = body["case"]["ref"]
    # Records: 7 days from 10 Nov (Brisbane) is 17 Nov.
    assert [s["body"] for s in phones.got("secretary@example.com")] == [
        "Decide by 17 Nov: New request {}: {}".format(ref, body["case"]["title"])]


def test_resident_reply_pushes_the_handlers(world, phones):
    _committee(world)
    case = _pet(world)
    phones.add("secretary@example.com")
    phones.add("jo@example.com")
    world.call("POST", "/case/message", {"id": case["id"], "body": "Here is the photo"}, email="jo@example.com")
    shown = phones.got("secretary@example.com")
    assert [s["body"] for s in shown] == ["{}: the resident replied".format(case["ref"])]
    assert shown[0]["url"] == APP + "case/" + case["id"]
    assert phones.got("jo@example.com") == []


def test_messages_status_and_decision_push_the_resident(world, phones):
    _committee(world)
    case = _pet(world)
    phones.add("jo@example.com")
    phones.add("secretary@example.com")
    phones.clear()
    who = "secretary@example.com"
    world.call("POST", "/case/message", {"id": case["id"], "body": "Hi", "to_resident": True}, email=who)
    world.call("POST", "/case/message", {"id": case["id"], "body": "internal only"}, email=who)
    world.call("POST", "/case/status", {"id": case["id"], "status": "in_progress"}, email=who)
    world.call("POST", "/case/decide", {"id": case["id"], "outcome": "approved"}, email=who)
    shown = phones.got("jo@example.com")
    ref = case["ref"]
    assert [s["body"] for s in shown] == ["{}: New message".format(ref), "{}: Now in progress".format(ref),
                                          "{}: Decision made".format(ref)]
    assert {s["url"] for s in shown} == {APP + "request/" + case["id"]}
    assert phones.got("secretary@example.com") == []


def test_stage_button_emails_push_the_same_people(world, phones):
    _committee(world)
    case = _pet(world)
    for email in ("jo@example.com", "chair@example.com", "treasurer@example.com"):
        phones.add(email)
    phones.clear()
    world.call("POST", "/case/action", {"id": case["id"], "action": "acknowledge"}, email="secretary@example.com")
    shown = phones.got("jo@example.com")
    assert [(s["body"], s["url"]) for s in shown] == [("{}: we have your request".format(case["ref"]),
                                                       APP + "request/" + case["id"])]
    assert phones.got("chair@example.com") == []
    # Into the vote stage, then the "remind the committee" button goes to the voting members.
    world.call("POST", "/case/action", {"id": case["id"], "action": "vote"}, email="secretary@example.com")
    phones.clear()
    world.call("POST", "/case/action", {"id": case["id"], "action": "nudge"}, email="secretary@example.com")
    for email in ("chair@example.com", "treasurer@example.com"):
        assert [(s["body"], s["url"]) for s in phones.got(email)] == [
            ("{}: your vote is needed".format(case["ref"]), APP + "case/" + case["id"])]
    assert phones.got("jo@example.com") == []


def test_a_vote_opened_pushes_the_committee_not_the_owners(world, phones):
    _committee(world)
    world.role("noncm@example.com", "committee")
    world.member("jo@example.com", "4")
    for email in ("chair@example.com", "noncm@example.com", "jo@example.com"):
        phones.add(email)
    body, status = world.call("POST", "/votes", {"words": "That the pool fence be repaired."},
                              email="secretary@example.com")
    assert status == 200
    vote_id = body["vote"]["id"]
    for email in ("chair@example.com", "noncm@example.com"):
        shown = phones.got(email)
        assert len(shown) == 1 and shown[0]["body"].startswith("Committee vote: closes ")
        assert shown[0]["url"] == APP + "vote/" + vote_id
    assert phones.got("jo@example.com") == []


def test_task_digest_pushes_the_assignee_to_their_tasks(world, phones):
    _committee(world)
    phones.add("treasurer@example.com")
    phones.add("chair@example.com")
    world.call("POST", "/tasks", {"title": "Get two quotes", "due_date": "2026-11-12",
                                  "assignee_position": "treasurer"}, email="secretary@example.com")
    phones.clear()
    world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"})
    assert [(s["body"], s["url"]) for s in phones.got("treasurer@example.com")] == [
        ("1 item(s) due soon or overdue", APP + "tasks")]
    assert phones.got("chair@example.com") == []


def test_request_digest_pushes_the_handlers_to_the_due_list(world, phones):
    _committee(world)
    world.member("jo@example.com", "4")
    world.call("POST", "/cases", {"unit_id": world.units["4"], "topic_key": "records",
                                  "answers": {"which": "Minutes", "how": "Email copies"}},
               email="jo@example.com", now=NOW - timedelta(days=10))
    phones.add("chair@example.com")
    phones.add("jo@example.com")
    world.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"})
    assert [(s["body"], s["url"]) for s in phones.got("chair@example.com")] == [
        ("1 item(s) due soon or overdue", APP + "inbox/due")]
    assert phones.got("jo@example.com") == []


def test_nothing_pushes_to_a_phone_registered_in_another_building(world, phones):
    _committee(world)
    other = _other_building(world)
    world.member("jo@example.com", "4")
    phones.add("jo@example.com", building=other)          # Jo's phone only follows the other building
    phones.add("secretary@example.com", building=other)
    case = _pet(world)
    world.call("POST", "/case/decide", {"id": case["id"], "outcome": "approved"}, email="secretary@example.com")
    assert phones.sent == []


def test_a_push_that_fails_never_breaks_the_request(world, phones):
    _committee(world)
    phones.add("secretary@example.com")
    phones.answer = ConnectionError("push service down")
    case = _pet(world)
    assert case["ref"].startswith("ALT-")
    assert world.db.mail_to("secretary@example.com")
    assert any(r["Kind"] == "push" for r in world.db.find(store.FAILURES))


def test_push_link_is_relative_so_it_opens_inside_the_app(world):
    assert push.app_link(world.building, "case/5") == "portal.html?b=altai#/case/5"
