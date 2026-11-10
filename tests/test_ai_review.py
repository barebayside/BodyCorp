"""
The AI compliance helper (ai_review.py, ai_client.py): no live calls. A fake client hands back canned
Messages responses and records what would have been sent, so we can prove nothing is sent over budget.
"""

import json
import os
from datetime import datetime

import pytest

import ai_client
import ai_review
from errors import ApiError

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(os.path.dirname(HERE), "catalyst", "functions", "bodycorp_api", "seed_altai.json")
NOW = datetime(2026, 11, 10, 2, 0, 0)

OLD = """BY-LAWS
9. Keeping of animals
9.1 An occupier must not keep an animal on the lot without the committee's written approval.
9.2 The committee must decide an application within 21 days.
10. Noise
10.1 An occupier must not make noise likely to interfere with another occupier.
11. Flooring
11.1 An occupier must not change the flooring of a lot without approval of the committee in writing.
"""

NEW = """BY-LAWS
9. Keeping of animals
9.1 An occupier must not keep an animal on the lot without the committee's written approval.
9.2 The committee must decide an application within 21 days and may impose reasonable conditions.
9.3 An application must include proof of council registration for a dog or cat.
10. Noise
10.1 An occupier must not make noise likely to interfere with another occupier.
12. Flooring
12.1 An occupier must not change the flooring of a lot without approval of the committee in writing.
13. Short-term letting
13.1 An owner must notify the committee in writing at least 7 days before a lot is let for less than 30 days.
"""

LAW = "Animal request: deemed approved if not decided within 21 days after the request is made (SM s 58A)."


@pytest.fixture
def seed_topics():
    with open(SEED, encoding="utf-8") as handle:
        data = json.load(handle)
    return {t["key"]: t["definition"] for t in data["topics"]}


@pytest.fixture
def sources():
    return {"old": ai_review.clause_map(ai_review.split_clauses(OLD)),
            "new": ai_review.clause_map(ai_review.split_clauses(NEW)), "law": LAW}


def cite(clause="9.3", quote="must include proof of council registration", doc="new"):
    return {"doc": doc, "clause": clause, "quote": quote}


def edit(changes, citations=None, key="pet"):
    return {"kind": "edit_topic", "topic_key": key, "title": "Ask for council registration", "why": "New 9.3",
            "citations": [cite()] if citations is None else citations, "changes": changes,
            "definition_json": "", "unconfirmed": False, "unconfirmed_reason": ""}


def change(path, value, op="set", clause="9.3"):
    return {"path": path, "op": op, "value_json": json.dumps(value), "clause": clause}


# ----------------------------------------------------------------------------------------- clauses and the diff

def test_split_clauses_by_number_and_keyword():
    ids = [c["id"] for c in ai_review.split_clauses("Intro words\nBy-law 9 Animals\n9.1 An occupier may.\n"
                                                    "Schedule C\nText of C\n")]
    assert ids == ["preamble", "9", "9.1", "schedule c"]


def test_find_clause_reads_paragraphs_and_sub_clauses_but_not_made_up_numbers(sources):
    assert "reasonable conditions" in ai_review.find_clause(sources["new"], "By-law 9.2(b)")
    assert "council registration" in ai_review.find_clause(sources["new"], "by-law 9")      # 9 covers 9.1-9.3
    assert ai_review.find_clause(sources["new"], "9.7") is None
    assert ai_review.find_clause(sources["new"], "99.1") is None


def test_diff_of_two_bylaw_texts_into_clause_changes():
    changes = {c["clause"]: c for c in ai_review.diff_clauses(OLD, NEW)}
    assert changes["9.2"]["change"] == "changed" and "reasonable conditions" in changes["9.2"]["new"]
    assert changes["9.3"]["change"] == "added"
    assert changes["13.1"]["change"] == "added"
    # Flooring was renumbered 11 -> 12 with the same words: a move, not a removal plus an addition.
    assert changes["12.1"]["change"] == "moved" and changes["12.1"]["old_clause"] == "11.1"
    assert "9.1" not in changes and "10.1" not in changes            # unchanged clauses are left out
    assert not [c for c in changes.values() if c["change"] == "removed" and c["clause"] == "11.1"]


def test_removed_clause_is_reported():
    changes = ai_review.diff_clauses(OLD, NEW.replace("10.1 An occupier must not make noise likely to interfere "
                                                      "with another occupier.\n", ""))
    assert any(c["change"] == "removed" and c["clause"] == "10.1" for c in changes)


def test_scanned_pdf_is_spotted():
    assert ai_review.looks_scanned(["", " ", "x" * 500])
    assert not ai_review.looks_scanned(["x" * 500, "y" * 500, ""])


def test_redact_strips_contact_details():
    text = ai_review.redact("Unit 4 (jo@example.com, 0412 345 678) has a dog")
    assert "example.com" not in text and "0412" not in text and "has a dog" in text


# ---------------------------------------------------------------------------------------- proposal validation

def test_valid_edit_passes_and_builds_the_new_settings(seed_topics, sources):
    clean, problems = ai_review.validate_proposal(
        edit([change("fields[key=registered].required", True)]), seed_topics, sources)
    assert problems == []
    reg = [f for f in clean["after"]["fields"] if f["key"] == "registered"][0]
    assert reg["required"] is True
    assert [f for f in seed_topics["pet"]["fields"] if f["key"] == "registered"][0]["required"] is False  # untouched


def test_uncited_proposal_is_refused(seed_topics, sources):
    _, problems = ai_review.validate_proposal(edit([change("intro", "New intro")], citations=[]), seed_topics, sources)
    assert any("No clause cited" in p for p in problems)


def test_invented_clause_or_quote_is_refused(seed_topics, sources):
    _, problems = ai_review.validate_proposal(
        edit([change("intro", "x")], citations=[cite(clause="9.7")]), seed_topics, sources)
    assert any("isn't in that document" in p for p in problems)
    _, problems = ai_review.validate_proposal(
        edit([change("intro", "x")], citations=[cite(quote="pets are banned in every unit")]), seed_topics, sources)
    assert any("aren't in that clause" in p for p in problems)


def test_unknown_field_change_is_refused(seed_topics, sources):
    _, problems = ai_review.validate_proposal(edit([change("deadline.dayz", 28)]), seed_topics, sources)
    assert any("'dayz' is not a setting" in p for p in problems)
    _, problems = ai_review.validate_proposal(
        edit([change("fields[+]", {"key": "vet", "label": "Vet", "type": "text", "colour": "red"}, op="add")]),
        seed_topics, sources)
    assert any("colour" in p for p in problems)


def test_change_must_name_a_cited_clause(seed_topics, sources):
    _, problems = ai_review.validate_proposal(edit([change("intro", "x", clause="10.1")]), seed_topics, sources)
    assert any("doesn't cite" in p for p in problems)


def test_result_must_pass_the_topic_rules(seed_topics, sources):
    _, problems = ai_review.validate_proposal(edit([change("handler", "nobody")]), seed_topics, sources)
    assert any("wouldn't work" in p for p in problems)


def test_unknown_placeholder_in_email_is_refused(seed_topics, sources):
    path = "stages[key=received].buttons[key=acknowledge].email.body"
    _, problems = ai_review.validate_proposal(edit([change(path, "Hi {name}, your {pet_name} {ref}")]),
                                              seed_topics, sources)
    assert any("{pet_name}" in p for p in problems)


def test_new_topic_is_checked_and_always_draft(seed_topics, sources):
    definition = {"label": "Short-term letting notice", "audience": ["owner"], "handler": "committee",
                  "intro": "Tell the committee before a short let.", "draft": False,
                  "fields": [{"key": "dates", "label": "Dates", "type": "text", "required": True}],
                  "steps": [{"title": "Note it on the register", "rule": "By-law 13.1"}]}
    raw = {"kind": "new_topic", "topic_key": "short_let", "title": "Short-term letting notice", "why": "New 13",
           "citations": [cite("13.1", "at least 7 days before a lot is let")], "changes": [],
           "definition_json": json.dumps(definition), "unconfirmed": False, "unconfirmed_reason": ""}
    clean, problems = ai_review.validate_proposal(raw, seed_topics, sources)
    assert problems == [] and clean["after"]["draft"] is True
    raw["definition_json"] = json.dumps(dict(definition, secret_mode=True))
    _, problems = ai_review.validate_proposal(raw, seed_topics, sources)
    assert any("secret_mode" in p for p in problems)


def test_law_citation_checked_against_the_law_file(seed_topics, sources):
    ok = cite("SM s 58A", "deemed approved if not decided within 21 days", doc="law")
    _, problems = ai_review.validate_proposal(edit([change("intro", "x", clause="")], citations=[ok]),
                                              seed_topics, sources)
    assert problems == []


def test_validate_all_keeps_invalid_ones_marked(seed_topics, sources):
    rows = ai_review.validate_all([edit([change("intro", "Fine")]), edit([change("deadline.dayz", 1)])],
                                  seed_topics, sources, review_id=7, building_id=1)
    assert [r["Status"] for r in rows] == ["proposed", "invalid"]
    assert all(len(r["Change"]) <= 10000 for r in rows)


def test_a_persons_edit_is_checked_too(seed_topics, sources):
    rows = ai_review.validate_all([edit([change("intro", "Fine")])], seed_topics, sources)
    _, problems = ai_review.check_edit(rows[0], {"changes": [{"path": "nonsense", "op": "set", "value": 1}]},
                                       seed_topics, sources)
    assert problems
    stored, problems = ai_review.check_edit(rows[0], {"changes": [{"path": "intro", "op": "set", "value": "Better",
                                                                   "clause": "9.3"}]}, seed_topics, sources)
    assert problems == [] and json.loads(stored)["changes"][0]["value"] == "Better"


# ------------------------------------------------------------------------------------------- cost and the cap

def test_cost_uses_the_published_prices():
    usage = {"input": 1000000, "write_5m": 0, "write_1h": 0, "read": 0, "output": 1000000}
    assert ai_client.cost_usd(ai_client.SONNET, usage) == pytest.approx(12.0)
    assert ai_client.cost_usd(ai_client.SONNET, usage, batch=True) == pytest.approx(6.0)
    small = {"input": 50000, "write_5m": 0, "write_1h": 0, "read": 0, "output": 1000}
    assert ai_client.cost_usd(ai_client.HAIKU, small) == pytest.approx((50000 * 0.10 + 1000 * 0.50) / 1e6)
    big = {"input": 60000, "write_5m": 0, "write_1h": 0, "read": 50000, "output": 1000}   # 110k prompt: higher row
    assert ai_client.cost_usd(ai_client.HAIKU, big) == pytest.approx((60000 * 0.5 + 50000 * 0.05 + 1000 * 2.5) / 1e6)


def test_cap_reached_stops_before_sending():
    with pytest.raises(ai_review.BudgetReached) as exc:
        ai_review.check_budget(9.99, 0.05, 10.0, "2026-11")
    assert exc.value.status == 402 and "Nothing was sent" in exc.value.message
    with pytest.raises(ai_review.BudgetReached):
        ai_review.check_budget(0, 0.01, 0, "2026-11")       # cap 0 = AI off
    ai_review.check_budget(1.0, 0.05, 10.0, "2026-11")
    assert ai_review.budget_status(8.5, 10)["warn"] and not ai_review.budget_status(8.5, 10)["stopped"]


def test_spent_counts_this_month_only():
    rows = [{"Month": "2026-11", "Cost_Aud": 1.5}, {"Month": "2026-10", "Cost_Aud": 9}, {"Month": "2026-11",
                                                                                       "Cost_Aud": "0.25"}]
    assert ai_review.spent_aud(rows, ai_review.month_of(NOW)) == pytest.approx(1.75)


def test_building_cap_overrides_env(monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_CAP_AUD", "10")
    assert ai_client.monthly_cap_aud({}) == 10.0
    assert ai_client.monthly_cap_aud({"ai": {"monthly_cap_aud": 25}}) == 25.0
    monkeypatch.delenv("AI_MONTHLY_CAP_AUD")
    assert ai_client.monthly_cap_aud({}) == 0.0


# ------------------------------------------------------------------------------------------ everyday questions

class FakeClient:
    """Answers each message() with the next canned answer; records every payload it was sent."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def message(self, payload):
        self.sent.append(payload)
        body = self.answers.pop(0)
        return {"id": "msg_{}".format(len(self.sent)), "model": payload["model"], "stop_reason": "end_turn",
                "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": json.dumps(body)}],
                "usage": {"input_tokens": 200, "cache_creation_input_tokens": 30000, "cache_read_input_tokens": 0,
                          "cache_creation": {"ephemeral_5m_input_tokens": 30000, "ephemeral_1h_input_tokens": 0},
                          "output_tokens": 800}}


DOCS = {"bylaws": ai_review.split_clauses(NEW)}


def answer(quote="may impose reasonable conditions", clause="9.2", **kw):
    body = {"answer": "You can approve it with reasonable conditions.", "confidence": "high",
            "citations": [{"doc": "bylaws", "clause": clause, "quote": quote}], "needs_escalation": False,
            "unconfirmed": False}
    body.update(kw)
    return body


def test_question_answered_by_haiku_with_checked_quote():
    client = FakeClient(answer())
    out = ai_review.ask(client, "Can we refuse this pet? Owner is jo@example.com", DOCS, LAW, 0, 10, NOW, 1, 2)
    assert out["status"] == "answered" and out["model"] == ai_client.HAIKU and not out["escalated"]
    assert out["label"].startswith("Guidance, not legal advice")
    assert len(client.sent) == 1 and client.sent[0]["model"] == "claude-haiku-5-5"
    assert "jo@example.com" not in json.dumps(client.sent[0]["messages"])          # redacted before sending
    assert "temperature" not in client.sent[0]                                      # refused by 2026-10-21
    assert out["usage"][0]["Kind"] == "question" and out["usage"][0]["Cost_Aud"] > 0


def test_made_up_quote_escalates_to_sonnet():
    client = FakeClient(answer(quote="no pets are allowed in any lot"), answer())
    out = ai_review.ask(client, "Can we refuse this pet?", DOCS, LAW, 0, 10, NOW, escalate="sync")
    assert [p["model"] for p in client.sent] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert out["escalated"] and out["status"] == "answered" and out["model"] == ai_client.SONNET
    assert [u["Kind"] for u in out["usage"]] == ["question", "escalation"]


def test_escalation_can_go_by_batch():
    client = FakeClient(answer(needs_escalation=True))
    out = ai_review.ask(client, "Is the by-law valid under the Act?", DOCS, LAW, 0, 10, NOW)   # batch by default
    assert out["status"] == "pending" and out["batch_request"]["params"]["model"] == ai_client.SONNET
    assert len(client.sent) == 1


def test_no_quote_from_sonnet_either_is_unconfirmed():
    client = FakeClient(answer(confidence="low"), answer(quote="something invented entirely"))
    out = ai_review.ask(client, "Can we charge a pet bond?", DOCS, LAW, 0, 10, NOW, escalate="sync")
    assert out["status"] == "unconfirmed" and out["unconfirmed"] and out["citations"] == []


def test_question_over_budget_sends_nothing():
    client = FakeClient(answer())
    with pytest.raises(ai_review.BudgetReached):
        ai_review.ask(client, "Can we refuse this pet?", DOCS, LAW, 9.9999, 10, NOW)
    assert client.sent == []


def test_budget_runs_out_before_escalation():
    client = FakeClient(answer(needs_escalation=True))
    haiku_worst = ai_client.aud(ai_review.estimate_usd(ai_review.question_payload("q", DOCS, LAW)))
    out = ai_review.ask(client, "q", DOCS, LAW, 10 - haiku_worst - 0.0001, 10, NOW)
    assert len(client.sent) == 1 and out["status"] == "unconfirmed"
    assert any("budget" in p for p in out["problems"])


def test_cut_short_answer_is_not_used():
    with pytest.raises(ApiError):
        ai_review.response_json({"stop_reason": "max_tokens", "content": [{"type": "text", "text": "{"}]})


# ----------------------------------------------------------------------------------------------- the review

def test_review_builds_cached_batch_requests_within_budget(seed_topics):
    start = ai_review.start_review(OLD, NEW, seed_topics, LAW, "Altai", 0, 100, NOW, review_id=3)
    params = start["batch_requests"][0]["params"]
    assert start["batch_requests"][0]["custom_id"] == "rev3-map" and params["model"] == "claude-sonnet-5-5"
    assert params["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "13.1" in params["messages"][0]["content"][1]["text"]
    with pytest.raises(ai_review.BudgetReached):
        ai_review.start_review(OLD, NEW, seed_topics, LAW, "Altai", 0, 0.01, NOW, review_id=3)


def test_map_then_proposals_from_batch_results(seed_topics, sources):
    changes = ai_review.diff_clauses(OLD, NEW)
    context = ai_review.review_context(ai_review.split_clauses(OLD), ai_review.split_clauses(NEW), seed_topics, "A")
    plan = ai_review.plan_proposals({"clauses": [
        {"clause": "9.3", "what_changed": "Registration proof", "matters": True, "topics": ["pet"]},
        {"clause": "13.1", "what_changed": "Short lets", "matters": True, "topics": []},
        {"clause": "12.1", "what_changed": "Renumbered", "matters": False, "topics": ["renovation"]}],
        "new_request_types_needed": True}, changes, seed_topics, LAW, context, 3)
    assert [p["custom_id"] for p in plan] == ["rev3-new", "rev3-pet"]
    # Same system and first block in every request: one cache write, then reads.
    assert plan[0]["params"]["system"] == plan[1]["params"]["system"]
    assert plan[0]["params"]["messages"][0]["content"][0] == plan[1]["params"]["messages"][0]["content"][0]

    message = {"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 100,
               "output_tokens": 50}, "content": [{"type": "text", "text": json.dumps({"proposals": [
                   edit([change("fields[key=registered].required", True)])]})}]}
    answers, errors, usage = ai_review.read_batch(
        [{"custom_id": "rev3-pet", "result": {"type": "succeeded", "message": message}},
         {"custom_id": "rev3-new", "result": {"type": "expired"}}], 1, NOW, "review_propose")
    assert errors == {"rev3-new": "expired"} and usage[0]["Batch"] is True
    rows = ai_review.validate_all(answers["rev3-pet"]["proposals"], seed_topics, sources, 3, 1)
    assert rows[0]["Status"] == "proposed"


# ------------------------------------------------------------------------------------- versions, undo, approver

def test_apply_versions_from_registration_date_and_undo(seed_topics, sources):
    rows = ai_review.validate_all([edit([change("fields[key=registered].required", True)])], seed_topics, sources)
    rows[0]["Status"] = "approved"
    with pytest.raises(ApiError):
        ai_review.plan_apply(rows, seed_topics, [], "", 1, 2, NOW)
    versions = ai_review.plan_apply(rows, seed_topics, [], "2027-02-01", 1, 2, NOW)
    assert [(v["Version"], v["Source"]) for v in versions] == [(1, "baseline"), (2, "ai_review")]
    assert versions[1]["Effective_From"] == "2027-01-31 14:00:00"          # midnight Brisbane, in UTC
    # A request lodged today keeps the old rules; one lodged after registration gets the new ones.
    assert ai_review.pick_version(versions, "2026-11-10 02:00:00")["Version"] == 1
    assert ai_review.pick_version(versions, "2027-02-02 00:00:00")["Version"] == 2
    assert ai_review.due_promotions(versions, seed_topics, NOW) == []
    later = datetime(2027, 2, 2)
    assert ai_review.due_promotions(versions, seed_topics, later)[0]["version"] == 2
    # Undo before it's in force = withdraw it; after = a new version restoring the old settings.
    assert "withdraw" in ai_review.plan_undo(versions, "pet", NOW)
    undo = ai_review.plan_undo(versions, "pet", later)["insert"]
    assert undo["Version"] == 3 and json.loads(undo["Definition"]) == seed_topics["pet"]


def test_who_may_decide_is_a_building_setting():
    assert ai_review.may_decide({}, {"secretary"}, False) is False                       # default: portal owner
    assert ai_review.may_decide({}, set(), True) is True
    assert ai_review.may_decide({"ai": {"approver": "secretary"}}, {"secretary"}, False) is True
    assert ai_review.may_decide({"ai": {"approver": "secretary"}}, {"chair"}, False) is False
    assert ai_review.may_decide({"ai": {"approver": "committee_vote"}}, {"member"}, False) is True
    assert ai_review.may_decide({"ai": {"approver": "committee_vote"}}, {"manager"}, False) is False
