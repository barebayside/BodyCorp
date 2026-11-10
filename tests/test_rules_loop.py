"""
The rules loop (rules.py, legal.py, pdfgen.py): law -> building -> products, seven stages each ending at a check,
one legal pack per change with a private link, the chair's sign-off, apply from a date, and a notify step that
sends only to the list a person approved. Spec: docs/superpowers/specs/2026-11-10-rules-loop-design.md
"""

import base64
import io
import json
from datetime import timedelta

import pypdf
import pytest

import ai
import cases
import pdfgen
import rules
import store
import topics
from conftest import ADMIN, NOW

OWNER = "support@example.com"       # SUPPORT_EMAIL: the portal owner
SEC, CHAIR, TRES, MEM, MEM2 = ("sec@example.com", "chair@example.com", "tres@example.com", "mem@example.com",
                               "mem2@example.com")
MGR, RES, TEN, LAWYER = "mgr@example.com", "res@example.com", "ten@example.com", "lawyer@lawfirm.example"
BIKES = "That bicycles must not be taken in the lifts at any time, and residents be told before the next move."


@pytest.fixture
def team(world):
    for email, role in ((SEC, "secretary"), (CHAIR, "chair"), (TRES, "treasurer"), (MEM, "member"),
                        (MEM2, "member"), (MGR, "manager"), (OWNER, "admin")):
        world.role(email, role)
    world.member(RES, "4")
    world.member(TEN, "9", "tenant")
    return world


def ok(result):
    body, status = result
    assert status == 200, body
    return body


def passed_motion(world, words=BIKES):
    vote = ok(world.call("POST", "/votes", {"words": words}, email=SEC))["vote"]
    for who in (CHAIR, TRES, MEM):
        ok(world.call("POST", "/vote/ballot", {"id": vote["id"], "vote": "yes"}, email=who))
    row = world.db.get(store.MOTIONS, vote["id"])
    assert row["Status"] == "passed"
    return vote["id"]


def start(world, motion_id):
    return ok(world.call("POST", "/rules/changes", {"source_kind": "motion", "source_id": motion_id}, email=SEC))["change"]


def check(world, cid, stage, email=SEC, note=""):
    return world.call("POST", "/rules/change/check", {"id": cid, "stage": stage, "note": note}, email=email)


BIKE_RULE = {"title": "No bikes in the lifts", "trigger": "A resident moves a bicycle through the building",
             "action": "Use the stairs or the car park ramp, never the lifts", "who": "Building manager",
             "duty": "manager", "deadline_text": "", "if_missed": "",
             "citations": [{"source": "change", "clause": "motion",
                            "quote": "bicycles must not be taken in the lifts at any time"}]}

BIKE_FIELD = {"key": "no_bikes", "label": "I won't take a bicycle in the lift", "type": "checkbox", "required": True}


def to_impact(world, rule=None):
    """A passed resolution taken through stages 01-02, with its rule linked to the moving form."""
    cid = start(world, passed_motion(world))["id"]
    ok(check(world, cid, "read"))
    detail = ok(world.call("POST", "/rules/change/rule", dict({"id": cid}, **(rule or BIKE_RULE)), email=SEC))
    key = detail["rules"][0]["key"]
    ok(check(world, cid, "rules"))
    ok(world.call("POST", "/rules/links", {"rule_key": key, "product_kind": "topic", "topic_key": "moving",
                                           "product_path": "fields"}, email=SEC))
    return cid, key


def resident_product(world, cid, key):
    detail = ok(world.call("POST", "/rules/change/product", {
        "id": cid, "topic_key": "moving", "kind": "edit_topic", "title": "Ask movers to agree: no bikes in the lift",
        "rule_keys": [key], "changes": [{"path": "fields[+]", "op": "add", "value": BIKE_FIELD}]}, email=SEC))
    pid = detail["proposals"][-1]["id"]
    ok(world.call("POST", "/rules/change/product/decide", {"id": cid, "proposal_id": pid, "decision": "approve"},
                  email=SEC))
    return pid


def send_pack(world, cid):
    body = ok(world.call("POST", "/rules/pack/send", {"id": cid, "lawyer_name": "Lee Lawyer",
                                                      "lawyer_email": LAWYER}, email=SEC))
    return body["token"], body


def public(world, method, path, body, now=NOW):
    from main import route
    return route(world.db, method, path, body, {}, now)


def sign_all(world, token, name="Lee Lawyer"):
    pack = ok(public(world, "GET", "/pack", {"t": token}))
    for item in pack["items"]:
        ok(public(world, "POST", "/pack/item", {"t": token, "item_id": item["item_id"], "tick": "ok"}))
    return ok(public(world, "POST", "/pack/sign", {"t": token, "name": name}))


# ---------------------------------------------------------------------------------------------- the law layer

def test_law_file_section_8_is_44_rules_each_citing_the_law_file():
    found = rules.law_rules()
    assert len(found) == 44 and found[0]["key"] == "qld_sm_01" and found[-1]["key"] == "qld_sm_44"
    pet = next(r for r in found if r["number"] == 33)
    assert pet["deadline_days"] == 21 and pet["if_missed"] == "Deemed approved" and "SM s 58A" in pet["citations"][0]["clause"]
    law = rules.law_plain()
    for r in found:          # every rule's quote is really in the law file
        row = {"Title": r["title"], "Trigger_Text": r["trigger"], "Action_Text": r["action"], "Who": r["who"] or "x",
               "Citations": json.dumps(r["citations"])}
        assert rules.rule_problems(row, [], law) == [], r["key"]


def test_seed_makes_the_44_a_law_change_for_the_lawyer_and_links_altai(team):
    assert team.call("POST", "/rules/seed", {}, email=SEC)[1] == 403
    body = ok(team.call("POST", "/rules/seed", {}, email=OWNER))
    assert body["rules"] == 44 and body["linked"] > 10 and body["change"]["stage"] == "read"
    law = team.db.find(store.RULES, {"Building_Id": 0})
    assert len(law) == 44 and {r["Status"] for r in law} == {"draft"}        # nothing in force until signed
    again = ok(team.call("POST", "/rules/seed", {}, email=OWNER))
    assert again["rules"] == 0 and again["linked"] == 0                        # idempotent
    listing = ok(team.call("GET", "/rules", {}, email=CHAIR))
    pet = next(r for r in listing["in_force"] if r["key"] == "qld_sm_33")
    assert pet["state"] == "draft" and pet["lawyer_checked"] is False
    rule = ok(team.call("GET", "/rules/rule", {"key": "qld_sm_33"}, email=CHAIR))
    assert {l["topic_key"] for l in rule["links"]} == {"pet"}
    assert any("Keep a pet" in l["label"] for l in rule["links"])


def test_only_the_portal_owner_runs_a_law_change(team):
    cid = ok(team.call("POST", "/rules/seed", {}, email=OWNER))["change"]["id"]
    assert check(team, cid, "read", email=ADMIN)[1] == 403
    assert check(team, cid, "read", email=SEC)[1] == 403
    ok(check(team, cid, "read", email=OWNER))


def test_residents_and_the_manager_never_see_rules_or_drafts(team):
    cid, key = to_impact(team)
    for who in (RES, TEN, MGR):
        assert team.call("GET", "/rules", {}, email=who)[1] == 403
        assert team.call("GET", "/rules/change", {"id": cid}, email=who)[1] == 403
    resident_product(team, cid, key)
    moving = next(t for t in ok(team.call("GET", "/topics", {}, email=RES))["topics"] if t["key"] == "moving")
    assert not any(f["key"] == "no_bikes" for f in moving["fields"])           # a draft never reaches residents


def test_other_buildings_get_404(team):
    import buildings
    cid, _ = to_impact(team)
    other = buildings.from_row(team.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other", "Settings": "{}"}))
    team.db.insert(store.ROLES, {"User_Id": int(team.user("boss@example.com")["id"]), "Building_Id": int(other["id"]),
                                 "Role": "admin"})
    assert team.call("GET", "/rules/change", {"b": "other", "id": cid}, email="boss@example.com")[1] == 404
    assert team.call("POST", "/rules/change/check", {"b": "other", "id": cid, "stage": "impact"},
                     email="boss@example.com")[1] == 404
    assert team.call("GET", "/rules/notify", {"b": "other", "id": cid}, email="boss@example.com")[1] == 404


# ---------------------------------------------------------------------------------------------- stage gates

def test_rules_need_real_quotes_and_a_reason_when_none(team):
    cid = start(team, passed_motion(team))["id"]
    assert check(team, cid, "rules")[1] == 400                                # stage 01 first
    ok(check(team, cid, "read"))
    assert check(team, cid, "rules")[1] == 400                                # no rule, no reason
    fake = dict(BIKE_RULE, citations=[{"source": "change", "clause": "motion", "quote": "scooters are banned in lifts"}])
    ok(team.call("POST", "/rules/change/rule", dict({"id": cid}, **fake), email=SEC))
    body, status = check(team, cid, "rules")
    assert status == 400 and "Fix 1" in body["error"]
    detail = ok(team.call("GET", "/rules/change", {"id": cid}, email=SEC))
    assert "aren't in it" in detail["rules"][0]["problems"][0]
    assert not detail["stages"][1]["gate"]["ok"]


def test_a_queensland_rule_is_never_changed_by_a_building(team):
    ok(team.call("POST", "/rules/seed", {}, email=OWNER))
    cid = start(team, passed_motion(team))["id"]
    ok(check(team, cid, "read"))
    body, status = team.call("POST", "/rules/change/rule", dict({"id": cid, "rule_key": "qld_sm_33"}, **BIKE_RULE),
                             email=SEC)
    assert status == 400 and "law change" in body["error"]


def test_impact_lists_every_linked_product_and_waits_for_each(team):
    cid, key = to_impact(team)
    detail = ok(team.call("GET", "/rules/change", {"id": cid}, email=SEC))
    assert [i["topic_key"] for i in detail["impact"]] == ["moving"] and not detail["impact"][0]["done"]
    assert check(team, cid, "impact")[1] == 400
    resident_product(team, cid, key)
    detail = ok(team.call("GET", "/rules/change", {"id": cid}, email=SEC))
    assert detail["impact"][0]["state"] == "draft approved"
    assert detail["change"]["needs_lawyer"] is True and "residents" in detail["change"]["lawyer_why"]
    ok(check(team, cid, "impact"))


def test_product_drafts_are_checked_like_the_ai_helpers(team):
    cid, key = to_impact(team)
    body, status = team.call("POST", "/rules/change/product", {
        "id": cid, "topic_key": "moving", "kind": "edit_topic", "title": "Bad", "rule_keys": [key],
        "changes": [{"path": "fields[+]", "op": "add", "value": {"key": "x", "label": "X", "type": "rocket"}}]},
        email=SEC)
    assert status == 400 and "checker refused" in body["error"]
    body, status = team.call("POST", "/rules/change/product", {"id": cid, "topic_key": "moving", "title": "No rule",
                                                               "changes": []}, email=SEC)
    assert status == 400 and "rule" in body["error"]


# ---------------------------------------------------------------------------------------------- the whole loop

def test_nothing_applies_without_the_lawyer_and_the_chair(team):
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    assert team.call("POST", "/rules/change/signoff", {"id": cid}, email=CHAIR)[1] == 400   # stage is legal
    assert team.call("POST", "/rules/change/apply", {"id": cid}, email=SEC)[1] == 400
    token, sent = send_pack(team, cid)
    assert sent["pack"]["status"] == "sent" and sent["link"].endswith("lawyer.html?t=" + token)
    mail = team.db.mail_to(LAWYER)[-1]
    name, pdf = mail["attachments"][0]
    assert name.endswith(".pdf") and token in mail["html"]
    text = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "No bikes in the lifts" in text and "won't take a bicycle in the lift" in text
    assert "Telling owners and occupiers" in text
    sign_all(team, token)
    detail = ok(team.call("GET", "/rules/change", {"id": cid}, email=SEC))
    assert detail["change"]["stage"] == "committee" and detail["packs"][-1]["signed_name"] == "Lee Lawyer"
    assert team.call("POST", "/rules/change/apply", {"id": cid}, email=SEC)[1] == 400       # chair first
    assert team.call("POST", "/rules/change/signoff", {"id": cid}, email=SEC)[1] == 403     # not the secretary
    assert team.call("POST", "/rules/change/signoff", {"id": cid}, email=ADMIN)[1] == 403   # nor an admin as such
    ok(team.call("POST", "/rules/change/signoff", {"id": cid}, email=CHAIR))
    done = ok(team.call("POST", "/rules/change/apply", {"id": cid}, email=SEC))
    assert done["change"]["stage"] == "notify"
    versions = topics.versions_of(team.db, team.building, "moving")
    assert {v["Source"] for v in versions} == {"baseline", "rules_change"}
    moving = next(t for t in ok(team.call("GET", "/topics", {}, email=RES))["topics"] if t["key"] == "moving")
    assert any(f["key"] == "no_bikes" for f in moving["fields"])
    applied = [r for r in team.db.find(store.RULES, {"Rule_Key": key})]
    assert applied[0]["Status"] == "applied" and applied[0]["Effective_From"]


def test_open_requests_keep_the_rules_they_were_lodged_under(team):
    lodged = cases.create(team.db, team.building, team.user(RES), team.ctx(RES), team.units["4"], "moving",
                          {"kind": "Moving in", "date": "2026-11-28", "time": "9am"}, [], NOW - timedelta(days=1))
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    token, _ = send_pack(team, cid)
    sign_all(team, token)
    ok(team.call("POST", "/rules/change/signoff", {"id": cid}, email=CHAIR))
    ok(team.call("POST", "/rules/change/apply", {"id": cid}, email=SEC))
    row = team.db.get(store.CASES, lodged["case"]["id"])
    pinned = topics.for_case(team.db, team.building, row)
    assert not any(f["key"] == "no_bikes" for f in pinned["fields"])


def test_a_committee_only_resolution_skips_the_lawyer_unless_the_chair_asks(team):
    cid, key = to_impact(team)
    detail = ok(team.call("POST", "/rules/change/product", {
        "id": cid, "topic_key": "moving", "kind": "edit_topic", "title": "Remind the manager about bikes",
        "rule_keys": [key], "changes": [{"path": "stages[key=received].instructions", "op": "set",
                                         "value": "Remind the mover: no bicycles in the lifts."}]}, email=SEC))
    ok(team.call("POST", "/rules/change/product/decide", {"id": cid, "proposal_id": detail["proposals"][-1]["id"],
                                                          "decision": "approve"}, email=SEC))
    after = ok(check(team, cid, "impact"))
    assert after["change"]["stage"] == "committee" and after["change"]["needs_lawyer"] is False
    assert after["stages"][3]["done"] and after["stages"][3]["check_label"] == "Lawyer not needed"
    forced = ok(team.call("POST", "/rules/change/lawyer", {"id": cid, "force": True}, email=CHAIR))
    assert forced["change"]["stage"] == "legal" and not forced["stages"][3]["done"]
    assert team.call("POST", "/rules/change/signoff", {"id": cid}, email=CHAIR)[1] == 400


# ---------------------------------------------------------------------------------------------- the lawyer's link

def test_the_link_opens_that_pack_only_and_expires(team):
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    token, sent = send_pack(team, cid)
    assert public(team, "GET", "/pack", {"t": token + "x"})[1] == 404
    assert public(team, "GET", "/pack", {"t": ""})[1] == 404
    assert public(team, "GET", "/pack", {"t": token}, NOW + timedelta(days=31))[1] == 404
    view = ok(public(team, "GET", "/pack", {"t": token}))
    assert view["building"] == "Altai on the Park" and any(i["kind"] == "product" for i in view["items"])
    form = next(i for i in view["items"] if i["kind"] == "product")["product"]["after_form"]
    assert any(f["label"] == BIKE_FIELD["label"] for f in form)
    # Another pack's item can't be ticked through this link.
    other = team.db.insert(store.PACK_ITEMS, {"Building_Id": 1, "Pack_Id": 999, "Item_No": 1, "Item_Kind": "rule",
                                              "Title": "Someone else's"})
    assert public(team, "POST", "/pack/item", {"t": token, "item_id": other["ROWID"], "tick": "ok"})[1] == 404
    assert public(team, "GET", "/pack/pdf", {"t": token}).data.startswith(b"%PDF")
    assert team.db.find(store.LEGAL_PACKS)[0]["Token_Hash"] != token            # only the hash is stored


def test_sign_needs_every_item_and_a_query_goes_back_round(team):
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    token, _ = send_pack(team, cid)
    body, status = public(team, "POST", "/pack/sign", {"t": token, "name": "Lee"})
    assert status == 400 and "every item" in body["error"]
    items = ok(public(team, "GET", "/pack", {"t": token}))["items"]
    assert public(team, "POST", "/pack/item", {"t": token, "item_id": items[0]["item_id"], "tick": "query"})[1] == 400
    ok(public(team, "POST", "/pack/item", {"t": token, "item_id": items[0]["item_id"], "tick": "query",
                                           "comment": "Say 'bicycle or e-scooter'."}))
    assert public(team, "POST", "/pack/sign", {"t": token, "name": "Lee"})[1] == 400
    ok(public(team, "POST", "/pack/comments", {"t": token, "note": "One change."}))
    assert any("asked for changes" in m["subject"] for m in team.db.mail_to(SEC))
    back = ok(team.call("POST", "/rules/change/reopen", {"id": cid, "to": "rules"}, email=SEC))
    assert back["change"]["stage"] == "rules" and back["packs"][-1]["status"] == "superseded"
    assert public(team, "GET", "/pack", {"t": token})[1] == 404                  # the old link is dead
    ok(check(team, cid, "rules"))
    ok(check(team, cid, "impact"))
    token2, sent2 = send_pack(team, cid)
    assert sent2["pack"]["no"] == 2
    sign_all(team, token2)
    assert public(team, "POST", "/pack/item", {"t": token2, "item_id": items[0]["item_id"], "tick": "ok"})[1] in (400, 404)


def test_secretary_records_an_emailed_sign_off_with_the_reply(team):
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    _, sent = send_pack(team, cid)
    pack_id = sent["pack"]["id"]
    body, status = team.call("POST", "/rules/pack/email-signoff", {"pack_id": pack_id, "name": "Lee", "date": "2026-11-12"},
                             email=SEC)
    assert status == 400 and "Attach" in body["error"]
    reply = {"name": "reply.pdf", "data": base64.b64encode(pdfgen.Pdf("reply").bytes()).decode()}
    assert team.call("POST", "/rules/pack/email-signoff", {"pack_id": pack_id, "name": "Lee", "date": "2026-11-12",
                                                           "file": reply}, email=RES)[1] == 403
    done = ok(team.call("POST", "/rules/pack/email-signoff", {"pack_id": pack_id, "name": "Lee Lawyer",
                                                              "date": "2026-11-12", "file": reply}, email=SEC))
    assert done["change"]["stage"] == "committee"
    assert done["packs"][-1]["signed_via"] == "email" and done["packs"][-1]["has_reply"]


# ---------------------------------------------------------------------------------------------- notify

def applied_change(team):
    cid, key = to_impact(team)
    resident_product(team, cid, key)
    ok(check(team, cid, "impact"))
    token, _ = send_pack(team, cid)
    sign_all(team, token)
    ok(team.call("POST", "/rules/change/signoff", {"id": cid}, email=CHAIR))
    ok(team.call("POST", "/rules/change/apply", {"id": cid}, email=SEC))
    return cid


def test_notify_proposes_who_and_sends_only_to_the_approved_list(team):
    cid = applied_change(team)
    plan = ok(team.call("GET", "/rules/notify", {"id": cid}, email=SEC))["plan"]
    groups = {g["key"] for g in plan["groups"]}
    assert groups == {"committee", "manager", "residents"} and "notice" in plan["channels"]
    ticked = {c["email"] for c in plan["candidates"] if c["ticked"]}
    assert {RES, TEN, MGR, CHAIR} <= ticked
    assert team.call("POST", "/rules/notify/send", {"id": cid}, email=SEC)[1] == 400   # save the list first
    keep = [c["user_id"] for c in plan["candidates"] if c["email"] != TEN]
    assert team.call("POST", "/rules/notify", {"id": cid, "recipients": keep + ["694000000999999"], "channels": ["email"],
                                               "subject": plan["subject"], "body": plan["body"]}, email=SEC)[1] == 400
    assert team.call("POST", "/rules/notify", {"id": cid, "recipients": keep, "channels": ["email"],
                                               "subject": plan["subject"], "body": plan["body"]}, email=RES)[1] == 403
    ok(team.call("POST", "/rules/notify", {"id": cid, "recipients": keep, "channels": ["email", "notice"],
                                           "subject": plan["subject"], "body": plan["body"],
                                           "notice_audience": "all"}, email=SEC))
    before = len(team.db.outbox)
    sent = ok(team.call("POST", "/rules/notify/send", {"id": cid}, email=SEC))
    new = team.db.outbox[before:]
    reached = {e for m in new for e in m["to"] + m["bcc"]}
    assert RES in reached and MGR in reached and TEN not in reached
    assert sent["change"]["stage"] == "done" and sent["plan"]["status"] == "sent"
    assert team.db.find(store.NOTICES, {"Title": plan["subject"]})
    assert team.call("POST", "/rules/notify/send", {"id": cid}, email=SEC)[1] == 400   # once


def test_the_next_meeting_agenda_lists_rules_changed_once(team):
    applied_change(team)
    first = ok(team.call("POST", "/meetings", {"title": "December", "starts_at": "2026-11-20T18:00"}, email=SEC))
    items = [i for i in first["meeting"]["agenda"] if i["kind"] == "rules_changed"]
    assert len(items) == 1 and "No bikes in the lifts (in force" in items[0]["text"]
    second = ok(team.call("POST", "/meetings", {"title": "January", "starts_at": "2026-11-25T18:00"}, email=SEC))
    assert not [i for i in second["meeting"]["agenda"] if i["kind"] == "rules_changed"]


def test_passed_motions_are_offered_for_implementing(team):
    motion = passed_motion(team)
    listing = ok(team.call("GET", "/rules", {}, email=SEC))
    assert [m["id"] for m in listing["motions_to_implement"]] == [str(motion)]
    start(team, motion)
    assert ok(team.call("GET", "/rules", {}, email=SEC))["motions_to_implement"] == []


# ---------------------------------------------------------------------------------------------- AI and the old path

class FakeAi:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def message(self, payload):
        self.calls += 1
        return {"id": "msg", "model": payload["model"], "stop_reason": "end_turn",
                "content": [{"type": "text", "text": json.dumps(self.answer)}],
                "usage": {"input_tokens": 1000, "output_tokens": 200}}


def test_ai_drafts_only_when_on_and_each_draft_needs_a_person(team, monkeypatch):
    cid = start(team, passed_motion(team))["id"]
    ok(check(team, cid, "read"))
    fake = FakeAi({"rules": [dict(BIKE_RULE, duty="manager", citations=BIKE_RULE["citations"]),
                             dict(BIKE_RULE, title="Invented", citations=[{"source": "law", "clause": "SM s 999",
                                                                            "quote": "bikes are forbidden everywhere"}])]})
    monkeypatch.setattr(ai, "make_client", lambda: fake)
    monkeypatch.setenv("AI_MONTHLY_CAP_AUD", "20")
    body, status = team.call("POST", "/rules/change/ai-draft", {"id": cid}, email=SEC)
    assert status == 403 and fake.calls == 0                                   # off until switched on
    ok(team.call("POST", "/ai/settings", {"enabled": True}, email=ADMIN))
    out = ok(team.call("POST", "/rules/change/ai-draft", {"id": cid}, email=SEC))
    assert out["ai"]["made"] == 1 and out["ai"]["refused"][0]["title"] == "Invented"
    assert out["rules"][0]["ai_drafted"] and check(team, cid, "rules")[1] == 400   # not accepted yet
    ok(team.call("POST", "/rules/change/rule/accept", {"id": cid, "rule_id": out["rules"][0]["id"]}, email=SEC))
    ok(check(team, cid, "rules"))
    assert team.db.find(store.AI_USAGE)


def test_an_ai_review_linked_to_a_change_applies_only_through_the_loop(team):
    ok(team.call("POST", "/ai/settings", {"enabled": True}, email=ADMIN))
    review = team.db.insert(store.RULE_REVIEWS, {"Building_Id": int(team.building["id"]), "Old_Doc_Id": 1,
                                                 "New_Doc_Id": 2, "Status": "ready"})
    team.db.insert(store.CHANGES, {"Building_Id": int(team.building["id"]), "Layer": "building",
                                   "Entry_Point": "outside", "Source_Kind": "doc", "Title": "New by-laws",
                                   "Stage": "legal", "Review_Id": int(review["ROWID"])})
    body, status = team.call("POST", "/ai/review/apply", {"id": review["ROWID"]}, email=OWNER)
    assert status == 400 and "rules change" in body["error"]


def test_pdf_writer_makes_a_readable_multi_page_pdf():
    doc = pdfgen.Pdf("Pack")
    for n in range(120):
        doc.text("Line {} — “quoted” → arrow (brackets) \\ slash".format(n))
    reader = pypdf.PdfReader(io.BytesIO(doc.bytes()))
    assert len(reader.pages) >= 2
    text = reader.pages[0].extract_text()
    assert "Line 0 — “quoted” -> arrow (brackets) \\ slash" in text
