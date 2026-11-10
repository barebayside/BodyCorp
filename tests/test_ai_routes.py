"""
The AI helper wired into the API (ai.py through main.route): permissions, the off switch, the cap, documents,
reviews, approving and applying, version pinning, undo, questions and the daily job. A fake client stands in
for Anthropic: NO test calls the API.
"""

import base64
import io
import json
import os
from datetime import datetime, timedelta

import pytest

import ai
import ai_client
import ai_review
import main
import store
import topics
from conftest import ADMIN, NOW

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OWNER = "support@example.com"      # SUPPORT_EMAIL in conftest: the portal owner
SEC, CHAIR, MEM, RES, MGR = "sec@example.com", "chair@example.com", "mem@example.com", "res@example.com", "mgr@example.com"

OLD = ["BY-LAWS", "9. Keeping of animals",
       "9.1 An occupier must not keep an animal on the lot without the committee's written approval.",
       "9.2 The committee must decide an application within 21 days.",
       "10. Noise", "10.1 An occupier must not make noise likely to interfere with another occupier."]
NEW = OLD[:3] + ["9.2 The committee must decide an application within 21 days and may impose reasonable conditions.",
                 "9.3 An application must include proof of council registration for a dog or cat."] + OLD[4:]


def make_pdf(lines):
    """A one-page PDF with a real text layer, so pypdf reads it the way it reads a lawyer's PDF."""
    esc = lambda l: l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    content = "BT /F1 10 Tf 12 TL 50 780 Td " + " ".join("({}) Tj T*".format(esc(l)) for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (i, o)).encode("latin-1")
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    return out


def pdf_file(lines, name="bylaws.pdf"):
    return {"name": name, "data": base64.b64encode(make_pdf(lines)).decode()}


class FakeAi:
    """Stands in for ai_client.Client. Batches stay 'in_progress' until a test finishes them."""

    def __init__(self):
        self.answers, self.messages, self.batches, self.created = [], [], {}, []

    def message(self, payload):
        self.messages.append(payload)
        return reply(self.answers.pop(0), payload["model"])

    def create_batch(self, requests):
        bid = "msgbatch_{}".format(len(self.batches) + 1)
        self.batches[bid] = None
        self.created.append((bid, requests))
        return {"id": bid, "processing_status": "in_progress"}

    def get_batch(self, bid):
        return {"id": bid, "processing_status": "in_progress" if self.batches.get(bid) is None else "ended",
                "results_url": "https://example/" + bid}

    def batch_results(self, batch):
        return self.batches[batch["id"]]

    def finish(self, bid, by_custom_id):
        self.batches[bid] = [{"custom_id": cid, "result": {"type": "succeeded", "message": reply(body, ai_client.SONNET)}}
                             if body is not None else {"custom_id": cid, "result": {"type": "errored"}}
                             for cid, body in by_custom_id.items()]


def reply(body, model):
    text = body if isinstance(body, str) else json.dumps(body)
    return {"id": "msg_x", "model": model, "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                      "output_tokens": 500}}


@pytest.fixture
def fake(monkeypatch):
    client = FakeAi()
    monkeypatch.setattr(ai, "make_client", lambda: client)
    monkeypatch.setenv("AI_MONTHLY_CAP_AUD", "20")
    monkeypatch.setenv("AI_AUD_PER_USD", "1.55")
    return client


@pytest.fixture
def team(world):
    for email, role in ((SEC, "secretary"), (CHAIR, "chair"), (MEM, "member"), (MGR, "manager"), (OWNER, "admin")):
        world.role(email, role)
    world.member(RES, "4")
    return world


def switch_on(world, **extra):
    body, status = world.call("POST", "/ai/settings", dict({"enabled": True}, **extra), email=ADMIN)
    assert status == 200, body
    return body


def upload(world, lines, title, email=OWNER, **extra):
    body, status = world.call("POST", "/ai/docs", dict({"kind": "bylaws", "title": title, "file": pdf_file(lines)},
                                                       **extra), email=email)
    assert status == 200, body
    return body["doc"]


def edit_prop(title="Ask for council registration", path="fields[key=registered].required", value=True, clause="9.3",
              quote="must include proof of council registration"):
    return {"kind": "edit_topic", "topic_key": "pet", "title": title, "why": "New by-law 9.3",
            "citations": [{"doc": "new", "clause": clause, "quote": quote}],
            "changes": [{"path": path, "op": "set", "value_json": json.dumps(value), "clause": clause}],
            "definition_json": "", "unconfirmed": False, "unconfirmed_reason": ""}


def run_review(world, fake, registered="2027-02-01"):
    """Two by-law versions -> a review with one valid and one invalid proposal, ready to decide."""
    old = upload(world, OLD, "By-laws 2019")
    new = upload(world, NEW, "By-laws 2027", registered_on=registered)
    body, status = world.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"], "confirm": True},
                              email=OWNER)
    assert status == 200, body
    review = body["review"]
    bid, requests = fake.created[-1]
    assert requests[0]["custom_id"] == "rev{}-map".format(review["id"])
    fake.finish(bid, {"rev{}-map".format(review["id"]): {"clauses": [
        {"clause": "9.3", "what_changed": "Proof of registration", "matters": True, "topics": ["pet"]}],
        "new_request_types_needed": False}})
    body, _ = world.call("POST", "/ai/review/check", {"id": review["id"]}, email=SEC)
    assert body["review"]["status"] == "proposing"
    bid, requests = fake.created[-1]
    assert [r["custom_id"] for r in requests] == ["rev{}-pet".format(review["id"])]
    fake.finish(bid, {"rev{}-pet".format(review["id"]): {"proposals": [
        edit_prop(), edit_prop("Invented rule", clause="9.9", quote="no dogs over ten kilograms are allowed")]}})
    body, _ = world.call("POST", "/ai/review/check", {"id": review["id"]}, email=SEC)
    assert body["review"]["status"] == "ready"
    return review["id"], old, new


def at(world, when):
    """Move the clock: sessions made at NOW have expired by then, so everyone signs in again."""
    world.tokens.clear()
    return when


def lodge(world, email, now=NOW, registered=False):
    answers = {"animal": "Cat", "how_many": "1", "where_kept": "Inside"}
    if registered:
        answers["registered"] = True
    body, status = world.call("POST", "/cases", {"unit_id": world.units["4"], "topic_key": "pet", "answers": answers},
                              email=email, now=now)
    return body, status


# ---------------------------------------------------------------------------------------------- the basics

def test_topic_schema_knows_every_setting_the_seed_and_pipeline_use():
    with open(os.path.join(ROOT, "catalyst", "functions", "bodycorp_api", "seed_altai.json"), encoding="utf-8") as h:
        seed = json.load(h)
    for item in seed["topics"]:
        assert ai_review.unknown_keys(item["definition"]) == [], item["key"]
    for key in ("stages", "deadline", "vote", "after_decision", "steps", "fields"):
        assert key in ai_review.TOPIC
    for key in ("owner", "status", "rule", "instructions", "buttons"):
        assert key in ai_review.STAGE
    for key in ("note", "note_label", "needs_decision", "opens_vote", "motion", "extends", "email", "next"):
        assert key in ai_review.BUTTON
    for key in ("outcome", "card", "banner", "citation", "extend_to_days", "business_day", "if_missed"):
        assert key in ai_review.DEADLINE


def test_law_file_shipped_with_the_function_is_the_same_as_docs():
    with open(os.path.join(ROOT, "docs", "compliance", "qld-committee-rules.md"), encoding="utf-8") as h:
        assert ai.law_text() == h.read()


def test_ai_is_off_until_switched_on(team, fake):
    body, status = team.call("GET", "/ai/docs", email=SEC)
    assert status == 403 and body["error"] == "AI isn't switched on for this building."
    assert team.call("POST", "/ai/ask", {"question": "Pets?"}, email=OWNER)[1] == 403
    # The settings screen still works, shows the notice and says it's off.
    body, status = team.call("GET", "/ai/settings", email=ADMIN)
    assert status == 200 and body["settings"]["enabled"] is False and body["settings"]["approver"] == "owner"
    assert "outside Australia" in body["notice"] and "a person approves every change" in body["notice"]
    me, _ = team.call("GET", "/me", email=SEC)
    assert me["ai"]["enabled"] is False and me["ai"]["see"] is True
    assert fake.messages == [] and fake.created == []


def test_who_may_see_and_change_the_settings(team, fake):
    assert team.call("GET", "/ai/settings", email=RES)[1] == 403          # residents
    assert team.call("GET", "/ai/settings", email=MGR)[1] == 403          # the building manager
    assert team.call("POST", "/ai/settings", {"enabled": True}, email=SEC)[1] == 403   # committee, not admin
    assert team.call("POST", "/ai/settings", {"approver": "anyone"}, email=ADMIN)[1] == 400
    body = switch_on(team, approver="secretary", monthly_cap_aud=15)
    assert body["settings"] == {"enabled": True, "approver": "secretary", "monthly_cap_aud": 15.0,
                                "default_cap_aud": 20.0}
    assert team.call("GET", "/ai/docs", email=SEC)[1] == 200
    assert team.call("GET", "/ai/docs", email=RES)[1] == 403
    assert team.call("GET", "/ai/docs", email=MGR)[1] == 403
    me, _ = team.call("GET", "/me", email=SEC)
    assert me["ai"]["decide"] is True and me["ai"]["manage"] is True


def test_other_buildings_rows_are_404(team, fake):
    switch_on(team)
    other = team.db.insert(store.BUILDINGS, {"Slug": "other", "Name": "Other Tower", "Settings": json.dumps(
        {"ai": {"enabled": True}})})
    doc = team.db.insert(store.DOC_VERSIONS, {"Building_Id": int(other["ROWID"]), "Kind": "bylaws", "Title": "Theirs",
                                              "File_Key": "x", "Status": "text_ready"})
    review = team.db.insert(store.RULE_REVIEWS, {"Building_Id": int(other["ROWID"]), "Old_Doc_Id": 1,
                                                 "New_Doc_Id": int(doc["ROWID"]), "Status": "ready"})
    prop = team.db.insert(store.RULE_PROPOSALS, {"Building_Id": int(other["ROWID"]), "Review_Id": int(review["ROWID"]),
                                                 "Seq": 1, "Kind": "flag", "Title": "x", "Citations": "[]",
                                                 "Status": "proposed"})
    assert team.call("GET", "/ai/doc", {"id": doc["ROWID"]}, email=OWNER)[1] == 404
    assert team.call("GET", "/ai/doc/file", {"id": doc["ROWID"]}, email=OWNER)[1] == 404
    assert team.call("GET", "/ai/review", {"id": review["ROWID"]}, email=OWNER)[1] == 404
    assert team.call("POST", "/ai/proposal/decide", {"id": prop["ROWID"], "decision": "approve"}, email=OWNER)[1] == 404
    assert team.call("POST", "/ai/review/apply", {"id": review["ROWID"]}, email=OWNER)[1] == 404
    # And a committee member of Altai has no role in the other building.
    assert team.call("GET", "/ai/docs", {"b": "other"}, email=SEC)[1] == 403


# ---------------------------------------------------------------------------------------------- documents

def test_upload_reads_the_pdf_text_into_clauses(team, fake):
    switch_on(team)
    assert team.call("POST", "/ai/docs", {"kind": "bylaws", "title": "x", "file": pdf_file(OLD)}, email=SEC)[1] == 403
    doc = upload(team, OLD, "By-laws 2019", email=ADMIN, registered_on="2019-05-01", dealing_no="719000123")
    assert doc["status"] == "text_ready" and doc["text_source"] == "pdf_text" and doc["usable"]
    body, _ = team.call("GET", "/ai/doc", {"id": doc["id"]}, email=SEC)
    assert [c["id"] for c in body["clauses"]][:3] == ["preamble", "9", "9.1"]
    assert team.db.files["ai/{}/docs/{}/original.pdf".format(team.building["id"], doc["id"])][1] == "application/pdf"
    result = team.call("GET", "/ai/doc/file", {"id": doc["id"]}, email=SEC)
    assert isinstance(result, main.FileResult) and result.data.startswith(b"%PDF")
    body, status = team.call("POST", "/ai/docs", {"kind": "bylaws", "title": "again", "file": pdf_file(OLD)}, email=ADMIN)
    assert status == 400 and "already uploaded" in body["error"]
    jpeg = {"name": "x.jpg", "data": base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 50).decode()}
    assert team.call("POST", "/ai/docs", {"kind": "bylaws", "title": "photo", "file": jpeg}, email=ADMIN)[1] == 400
    assert fake.created == []                         # a text PDF costs nothing


def test_scanned_pdf_is_transcribed_by_batch_and_must_be_checked(team, fake, monkeypatch):
    switch_on(team)
    monkeypatch.setattr(ai_review, "pdf_page_texts", lambda data: ["", ""])
    monkeypatch.setattr(ai, "pdf_chunks", lambda data: [(1, 2, "JVBERi0=")])
    doc = upload(team, ["scan"], "Scanned CMS")
    assert doc["status"] == "transcribing"
    bid, requests = fake.created[-1]
    assert requests[0]["custom_id"] == "doc{}-p1".format(doc["id"])
    assert requests[0]["params"]["messages"][0]["content"][0]["type"] == "document"
    fake.finish(bid, {"doc{}-p1".format(doc["id"]): "\n".join(NEW)})
    assert ai.daily(team.db, NOW)["collected"] == 1
    body, _ = team.call("GET", "/ai/doc", {"id": doc["id"]}, email=SEC)
    assert body["doc"]["text_source"] == "ai_transcribed" and body["doc"]["needs_check"] and not body["doc"]["usable"]
    other = upload(team, OLD, "Old")
    body, status = team.call("POST", "/ai/reviews", {"old_doc_id": other["id"], "new_doc_id": doc["id"]}, email=OWNER)
    assert status == 400 and "Text checked" in body["error"]
    body, _ = team.call("POST", "/ai/doc/text", {"id": doc["id"], "checked": True}, email=OWNER)
    assert body["doc"]["usable"]
    usage = team.db.find(store.AI_USAGE, {"Kind": "transcribe"})
    assert len(usage) == 1 and usage[0]["Is_Batch"] is True


def test_pasted_text_replaces_the_clauses(team, fake):
    switch_on(team)
    doc = upload(team, OLD, "By-laws")
    body, status = team.call("POST", "/ai/doc/text", {"id": doc["id"], "text": "\n".join(NEW)}, email=OWNER)
    assert status == 200 and body["doc"]["text_source"] == "pasted" and not body["doc"]["usable"]
    body, _ = team.call("POST", "/ai/doc/text", {"id": doc["id"], "checked": True}, email=OWNER)
    assert body["doc"]["usable"] and body["doc"]["clause_count"] == len(ai_review.split_clauses("\n".join(NEW)))


# ---------------------------------------------------------------------------------------------- reviews

def test_compare_preview_is_free_and_start_is_capped(team, fake):
    switch_on(team)
    old, new = upload(team, OLD, "Old"), upload(team, NEW, "New")
    body, status = team.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"]}, email=OWNER)
    assert status == 200 and body["review"] is None and fake.created == []
    assert {c["clause"]: c["change"] for c in body["changes"]} == {"9.2": "changed", "9.3": "added"}
    assert body["estimate_aud"] > 0 and body["budget"]["cap_aud"] == 20.0
    team.call("POST", "/ai/settings", {"monthly_cap_aud": 0.01}, email=ADMIN)
    body, status = team.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"], "confirm": True},
                             email=OWNER)
    assert status == 402 and "Nothing was sent" in body["error"] and fake.created == []
    assert len(team.db.find(store.FAILURES, {"Kind": "ai_cap"})) == 1
    team.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"], "confirm": True}, email=OWNER)
    assert len(team.db.find(store.FAILURES, {"Kind": "ai_cap"})) == 1           # told once a month
    assert len([m for m in team.db.outbox if "budget used up" in m["subject"]]) == 1


def test_review_end_to_end_proposals_decide_and_apply(team, fake):
    switch_on(team)
    review_id, old, new = run_review(team, fake)
    assert any("by-law review ready" in m["subject"] for m in team.db.mail_to(OWNER))
    body, _ = team.call("GET", "/ai/review", {"id": review_id}, email=SEC)
    good, bad_one = body["proposals"]
    assert not good["invalid"] and good["changes"][0]["new"] == "Yes" and good["changes"][0]["old"] == "No"
    assert "form" in good["changes"][0]["where"] and good["after_form"] and good["before_form"]
    assert bad_one["invalid"] and bad_one["problems"]
    assert body["can_decide"] is False                            # approver = the portal owner, by default
    assert body["guidance"].startswith("Guidance, not legal advice")
    assert body["registered_text"] == "1 Feb 2027"

    assert team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=SEC)[1] == 403
    assert team.call("POST", "/ai/proposal/decide", {"id": bad_one["id"], "decision": "approve"}, email=OWNER)[1] == 400
    assert team.call("POST", "/ai/proposal/decide", {"id": bad_one["id"], "decision": "reject"}, email=OWNER)[1] == 400
    body, status = team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "edit",
                                                            "edited": {"changes": [{"path": "nonsense", "op": "set",
                                                                                    "value": 1, "clause": "9.3"}]}},
                             email=OWNER)
    assert status == 400 and "refused" in body["error"]
    assert team.call("POST", "/ai/proposal/decide", {"id": bad_one["id"], "decision": "reject", "note": "Made up"},
                     email=OWNER)[0]["proposal"]["status"] == "rejected"
    body, _ = team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    assert body["proposal"]["status"] == "approved"

    body, status = team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)
    assert status == 200, body
    assert [(v["version"], v["source"]) for v in body["versions"]] == [(1, "baseline"), (2, "ai_review")]
    assert body["versions"][1]["future"] is True
    # Not in force until the registration date: the live form is unchanged.
    pet = topics.get(team.db, team.building, "pet")
    assert next(f for f in pet["fields"] if f["key"] == "registered").get("required") is False
    assert team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)[1] == 400   # only once


def test_apply_needs_the_registration_date(team, fake):
    switch_on(team)
    review_id, old, new = run_review(team, fake, registered="")
    good = team.call("GET", "/ai/review", {"id": review_id}, email=OWNER)[0]["proposals"][0]
    team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    body, status = team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)
    assert status == 400 and "registered" in body["error"]
    team.call("POST", "/ai/doc/text", {"id": new["id"], "registered_on": "2027-02-01"}, email=OWNER)
    assert team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)[1] == 200


def test_open_requests_keep_the_rules_they_were_lodged_under(team, fake):
    switch_on(team)
    first, status = lodge(team, RES)                                 # before any history: the baseline
    assert status == 200
    review_id, _, _ = run_review(team, fake)
    good = team.call("GET", "/ai/review", {"id": review_id}, email=OWNER)[0]["proposals"][0]
    team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)
    second, _ = lodge(team, RES)                                     # after Apply, before the date: still v1
    row2 = team.db.get(store.CASES, second["case"]["id"])
    assert int(row2["Topic_Version"]) == 1

    later = at(team, datetime(2027, 2, 2, 0, 0, 0))
    # The new rules are in force from midnight Brisbane on the registration date, even before the daily job runs.
    body, status = lodge(team, RES, now=later)
    assert status == 400 and "registered" in body["error"]
    body, status = lodge(team, RES, now=later, registered=True)
    assert status == 200 and int(team.db.get(store.CASES, body["case"]["id"])["Topic_Version"]) == 2
    # The daily job copies the version into the live request type.
    assert team.call("POST", "/cron/reminders", headers={"X-Cron-Key": "cron-key"}, now=later)[0]["ai"]["promoted"] == 1
    pet = topics.get(team.db, team.building, "pet")
    assert next(f for f in pet["fields"] if f["key"] == "registered")["required"] is True
    # The two older requests still run under version 1.
    for case in (first, second):
        pinned = topics.for_case(team.db, team.building, team.db.get(store.CASES, case["case"]["id"]))
        assert next(f for f in pinned["fields"] if f["key"] == "registered").get("required") is False
        assert pinned["version"] == 1


def test_undo_withdraws_then_restores(team, fake):
    switch_on(team)
    review_id, _, _ = run_review(team, fake)
    good = team.call("GET", "/ai/review", {"id": review_id}, email=OWNER)[0]["proposals"][0]
    team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)
    body, _ = team.call("GET", "/ai/versions", {"topic_key": "pet"}, email=SEC)
    assert [v["version"] for v in body["versions"]] == [2, 1] and body["in_force"] == 1 and body["can_undo"] is False
    assert team.call("POST", "/ai/versions/undo", {"topic_key": "pet"}, email=SEC)[1] == 403
    body, _ = team.call("GET", "/ai/versions", {"topic_key": "pet"}, email=OWNER)
    assert body["can_undo"] is True
    body, status = team.call("POST", "/ai/versions/undo", {"topic_key": "pet"}, email=OWNER)
    assert status == 200 and body["withdrawn"]["version"] == 2
    assert team.db.get(store.RULE_PROPOSALS, good["id"])["Status"] == "undone"
    assert team.call("POST", "/ai/versions/undo", {"topic_key": "pet"}, email=OWNER)[1] == 400   # nothing left

    # Once in force, undo is a new version restoring the one before.
    review2, _, _ = run_review_again(team, fake)
    good = team.call("GET", "/ai/review", {"id": review2}, email=OWNER)[0]["proposals"][0]
    team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    team.call("POST", "/ai/review/apply", {"id": review2}, email=OWNER, now=at(team, datetime(2027, 3, 1)))
    later = at(team, datetime(2027, 3, 2))
    assert team.call("POST", "/ai/versions/undo", {"topic_key": "pet"}, email=OWNER, now=later)[0]["version"]["source"] == "undo"
    pet = topics.get(team.db, team.building, "pet")
    assert next(f for f in pet["fields"] if f["key"] == "registered").get("required") is False


def run_review_again(world, fake):
    """A second comparison of the same two documents (the first review is finished)."""
    docs = world.call("GET", "/ai/docs", email=OWNER)[0]["docs"]
    new, old = docs[0], docs[1]
    body, _ = world.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"], "confirm": True},
                         email=OWNER)
    rid = body["review"]["id"]
    bid, _ = fake.created[-1]
    fake.finish(bid, {"rev{}-map".format(rid): {"clauses": [{"clause": "9.3", "what_changed": "x", "matters": True,
                                                             "topics": ["pet"]}], "new_request_types_needed": False}})
    world.call("POST", "/ai/review/check", {"id": rid}, email=OWNER)
    bid, _ = fake.created[-1]
    fake.finish(bid, {"rev{}-pet".format(rid): {"proposals": [edit_prop()]}})
    world.call("POST", "/ai/review/check", {"id": rid}, email=OWNER)
    return rid, old, new


def test_committee_vote_approver_applies_when_the_vote_passes(team, fake):
    switch_on(team, approver="committee_vote")
    review_id, _, _ = run_review(team, fake)
    good = team.call("GET", "/ai/review", {"id": review_id}, email=MEM)[0]["proposals"][0]
    assert team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=MEM)[1] == 200
    assert team.call("POST", "/ai/review/apply", {"id": review_id}, email=MEM)[1] == 403   # votes go out from the secretary
    body, status = team.call("POST", "/ai/review/apply", {"id": review_id}, email=SEC)
    assert status == 200 and body["voting"] is True
    assert team.db.find(store.TOPIC_VERSIONS) == []                   # nothing applied yet
    for who in (SEC, CHAIR):
        team.call("POST", "/vote/ballot", {"id": body["motion_id"], "vote": "yes"}, email=who)
    body, _ = team.call("GET", "/ai/review", {"id": review_id}, email=SEC)
    assert body["review"]["status"] == "applied"
    assert [int(v["Version"]) for v in team.db.find(store.TOPIC_VERSIONS)] == [1, 2]


# ---------------------------------------------------------------------------------------------- questions

def answer(quote="may impose reasonable conditions", clause="9.2", **kw):
    body = {"answer": "Yes, with reasonable conditions.", "confidence": "high",
            "citations": [{"doc": "bylaws", "clause": clause, "quote": quote}], "needs_escalation": False,
            "unconfirmed": False}
    body.update(kw)
    return body


def test_ask_answers_with_checked_quotes_for_the_committee_only(team, fake):
    switch_on(team)
    upload(team, NEW, "By-laws 2027")
    fake.answers.append(answer())
    body, status = team.call("POST", "/ai/ask", {"question": "Can we refuse a cat? Owner jo@example.com 0412 345 678"},
                             email=CHAIR)
    assert status == 200 and body["status"] == "answered" and body["label"].startswith("Guidance, not legal advice")
    assert body["citations"][0]["clause"] == "9.2"
    sent = json.dumps(fake.messages[0]["messages"])
    assert "jo@example.com" not in sent and "0412" not in sent
    log = team.call("GET", "/ai/questions", email=SEC)[0]["questions"]
    assert "[email]" in log[0]["question"] and log[0]["asked_by"] == CHAIR
    assert team.db.find(store.AI_USAGE, {"Kind": "question"})[0]["Usage_Month"] == "2026-11"
    assert team.call("POST", "/ai/ask", {"question": "x"}, email=RES)[1] == 403
    assert team.call("POST", "/ai/ask", {"question": "x"}, email=MGR)[1] == 403


def test_hard_question_escalates_by_batch_and_is_collected(team, fake):
    switch_on(team)
    upload(team, NEW, "By-laws 2027")
    fake.answers.append(answer(needs_escalation=True))
    body, _ = team.call("POST", "/ai/ask", {"question": "Is by-law 9 valid under the Act?"}, email=CHAIR)
    assert body["status"] == "pending"
    qid = body["question"]["id"]
    bid, requests = fake.created[-1]
    assert requests[0]["custom_id"] == "q{}".format(qid) and requests[0]["params"]["model"] == ai_client.SONNET
    fake.finish(bid, {"q{}".format(qid): answer(quote="must include proof of council registration", clause="9.3")})
    log = team.call("GET", "/ai/questions", email=CHAIR)[0]["questions"]
    assert log[0]["status"] == "answered" and log[0]["escalated"] and log[0]["model"] == ai_client.SONNET
    assert any("your by-law question" in m["subject"] for m in team.db.mail_to(CHAIR))


def test_ask_over_the_cap_is_402_and_sends_nothing(team, fake):
    switch_on(team, monthly_cap_aud=0.001)
    upload(team, NEW, "By-laws 2027")
    fake.answers.append(answer())
    body, status = team.call("POST", "/ai/ask", {"question": "Pets?"}, email=CHAIR)
    assert status == 402 and fake.messages == [] and "Nothing was sent" in body["error"]
    assert team.db.find(store.FAILURES, {"Kind": "ai_cap"})


def test_ask_needs_documents_first(team, fake):
    switch_on(team)
    body, status = team.call("POST", "/ai/ask", {"question": "Pets?"}, email=CHAIR)
    assert status == 400 and "CMS and by-laws" in body["error"]


# ---------------------------------------------------------------------------------------------- the daily job

def test_daily_job_with_ai_off_never_makes_a_client(team, monkeypatch):
    def boom():
        raise AssertionError("no client while AI is off")
    monkeypatch.setattr(ai, "make_client", boom)
    assert ai.daily(team.db, NOW) == {"promoted": 0, "collected": 0, "applied": 0}


def test_daily_job_collects_a_review_and_warns_at_80_percent(team, fake):
    switch_on(team)
    old, new = upload(team, OLD, "Old"), upload(team, NEW, "New")
    body, _ = team.call("POST", "/ai/reviews", {"old_doc_id": old["id"], "new_doc_id": new["id"], "confirm": True},
                        email=OWNER)
    rid = body["review"]["id"]
    assert ai.daily(team.db, NOW)["collected"] == 0                  # still running
    bid, _ = fake.created[-1]
    fake.finish(bid, {"rev{}-map".format(rid): {"clauses": [], "new_request_types_needed": False}})
    assert ai.daily(team.db, NOW)["collected"] == 1
    assert team.db.get(store.RULE_REVIEWS, rid)["Status"] == "ready"   # nothing to change: ready, no step 2
    team.db.insert(store.AI_USAGE, {"Building_Id": int(team.building["id"]), "Usage_Month": "2026-11",
                                    "Kind": "question", "Model": "claude-haiku-5-5", "Cost_Usd": 10.0,
                                    "Cost_Aud": 16.5})
    ai.daily(team.db, NOW)
    ai.daily(team.db, NOW)
    warned = [m for m in team.db.outbox if "AI budget at 80%" in m["subject"]]
    assert len(warned) == 1
    body, _ = team.call("GET", "/ai/usage", email=SEC)
    assert body["warn"] is True and body["cap_aud"] == 20.0


def test_daily_job_failure_in_one_building_is_logged_not_raised(team, fake, monkeypatch):
    switch_on(team)

    def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(ai, "collect", broken)
    ai.daily(team.db, NOW)
    assert team.db.find(store.FAILURES, {"Kind": "ai"})


def test_an_admin_edit_after_versions_exist_is_kept(team, fake):
    switch_on(team)
    review_id, _, _ = run_review(team, fake, registered="2026-11-01")     # already registered: in force at once
    good = team.call("GET", "/ai/review", {"id": review_id}, email=OWNER)[0]["proposals"][0]
    team.call("POST", "/ai/proposal/decide", {"id": good["id"], "decision": "approve"}, email=OWNER)
    body, _ = team.call("POST", "/ai/review/apply", {"id": review_id}, email=OWNER)
    assert body["versions"][1]["future"] is False
    pet = topics.get(team.db, team.building, "pet")
    assert next(f for f in pet["fields"] if f["key"] == "registered")["required"] is True
    definition = json.loads(team.db.find(store.TOPICS, {"Topic_Key": "pet"})[0]["Definition"])
    definition["intro"] = "Edited by hand."
    assert team.call("POST", "/admin/topics", {"key": "pet", "definition": definition}, email=ADMIN)[1] == 200
    ai.daily(team.db, NOW + timedelta(minutes=1))
    assert topics.get(team.db, team.building, "pet")["intro"] == "Edited by hand."
