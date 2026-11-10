"""
The AI compliance helper, wired: routes, storage, the daily job. The rules live in ai_review.py (pure functions)
and the HTTP calls in ai_client.py. Design: docs/superpowers/specs/2026-11-10-ai-compliance-helper-design.md

OFF UNTIL SWITCHED ON
    Each building's Buildings.Settings.ai = {enabled, approver, monthly_cap_aud}. `enabled` is false until an
    admin (or the portal owner) turns it on in Settings -> AI, because when on, the building's CMS, by-laws and
    committee questions are sent to Anthropic's API (outside Australia). Every /ai route but the settings ones
    answers 403 "AI isn't switched on for this building" while it is off. Nothing is decided or sent by the AI:
    a person approves every change.

WHO
    see / ask       committee roles (positions and `committee`) and admins; not residents, not the manager
    manage          upload documents, start a comparison: admins and whoever may decide
    decide          tick / edit / reject / apply / undo: the building's approver (ai_review.may_decide):
                    owner (default) = the portal owner, i.e. the user whose email is SUPPORT_EMAIL;
                    secretary; committee_vote (any voting member ticks, Apply opens a vote outside a meeting,
                    and the changes apply only when it passes). The portal owner can always see and undo.
    settings        admins and the portal owner

MONEY
    Every call is checked against the month's cap before anything is sent (ai_review.check_budget, 402).
    Reaching it logs ONE Failures row of kind `ai_cap` and emails the admins once that month; 80% of the cap
    emails them a warning once that month (Settings.ai.warned / stopped hold the month).

STORAGE (Stratus, bucket store.BUCKET; never in 10,000-character columns)
    ai/<building id>/docs/<doc id>/original.pdf | clauses.json | text.txt (AI transcription)
    ai/<building id>/reviews/<review id>/diff.json | context.txt | map.json | propose.json (raw batch results)

THE DAILY JOB (/cron/reminders calls daily()): for every building, copy versions whose date has come into
    Topics (even with AI off: the rules changed by law), apply reviews whose committee vote passed, and, when
    AI is on, collect finished batches (transcriptions, reviews, escalated questions) and warn at 80%.
"""

import base64
import hashlib
import io
import json
import logging
import os
import re
from datetime import datetime

import ai_client
import ai_review
import buildings
import committee
import failures
import mailer
import people
import stages
import store
import topics
import uploads
import votes
from errors import ApiError, bad, forbidden, not_found

logger = logging.getLogger("bodycorp_api.ai")

OFF = "AI isn't switched on for this building."
PRIVACY_NOTICE = ("When on, this building's CMS, by-laws and committee questions are sent to Anthropic's AI service "
                  "(outside Australia) to be read. Nothing is decided or sent by the AI; a person approves every "
                  "change.")
DOC_KINDS = {"cms": "CMS", "bylaws": "By-laws", "cms_bylaws": "CMS and by-laws"}
APPROVER_LABELS = {"owner": "The portal owner (during the pilot)", "secretary": "The secretary",
                   "committee_vote": "The committee, by a vote outside a meeting"}
REVIEW_LABELS = {"mapping": "Comparing (step 1 of 2)", "proposing": "Drafting proposals (step 2 of 2)",
                 "ready": "Ready to review", "voting": "Committee vote open", "applied": "Applied",
                 "failed": "Didn't finish", "cancelled": "Cancelled"}
SOURCE_LABELS = {"baseline": "Before the AI helper", "ai_review": "From a document review", "admin": "Edited by an admin",
                 "seed": "Set-up update", "undo": "Undo", "rules_change": "From a rules change"}
RUNNING = ("mapping", "proposing", "voting")
MAX_QUESTION = 2000
MAX_TEXT = 1000000
PDF_PAGE_TOKENS = 5000        # a PDF page sent as a document: text plus a page image (spec: "roughly 5k a page")
CHUNK_PAGES = 12
HERE = os.path.dirname(os.path.abspath(__file__))
_LAW = {}


def make_client():
    """The real client. Tests replace this with a fake: no test ever calls the API."""
    return ai_client.Client()


def law_text():
    """The law file, shipped beside the function (a copy of docs/compliance/qld-committee-rules.md)."""
    if "text" not in _LAW:
        with open(os.path.join(HERE, "law_qld.md"), encoding="utf-8") as handle:
            _LAW["text"] = handle.read()
    return _LAW["text"]


# ---------------------------------------------------------------------------------------------- who and when

def is_owner(user):
    """The portal owner: whoever signs in with SUPPORT_EMAIL."""
    support = os.environ.get("SUPPORT_EMAIL", "").strip().lower()
    return bool(support) and str((user or {}).get("email") or "").strip().lower() == support


def settings_of(building):
    raw = ((building or {}).get("settings") or {}).get("ai") or {}
    raw = raw if isinstance(raw, dict) else {}
    approver = raw.get("approver") if raw.get("approver") in ai_review.APPROVER_MODES else ai_review.DEFAULT_APPROVER
    cap = raw.get("monthly_cap_aud")
    cap = float(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap >= 0 else None
    return {"enabled": raw.get("enabled") is True, "approver": approver, "monthly_cap_aud": cap}


def flags(ctx):
    owner = is_owner(ctx["user"])
    building = ctx["building"]
    ai = settings_of(building)
    committee_side = bool(ctx["cmt"]["committee"]) or owner
    admin = bool(ctx["can"]["admin"]) or owner
    decide = ai_review.may_decide({"ai": {"approver": ai["approver"]}}, ctx["roles"], owner)
    return {"enabled": ai["enabled"], "approver": ai["approver"], "see": committee_side, "ask": committee_side,
            "manage": admin or decide, "decide": decide, "admin": admin, "owner": owner}


_REFUSED = {"see": "Only the committee can see this.", "ask": "Only the committee can ask the AI helper.",
            "manage": "Only an admin or the approver can do that.",
            "decide": "Only the approver chosen in Settings → AI can decide these.",
            "admin": "Only an admin can change the AI settings."}


def gate(c, need, allow_off=False):
    """Signed in (401), the building exists (404), allowed (403), then switched on (403)."""
    f = flags(c.ctx)
    if not f[need]:
        raise forbidden(_REFUSED[need])
    if not allow_off and not f["enabled"]:
        raise ApiError(OFF, 403)
    return f


def me_flags(ctx):
    """For GET /me: what the page should offer. Never raises."""
    try:
        f = flags(ctx)
        return {k: f[k] for k in ("enabled", "approver", "see", "ask", "manage", "decide", "admin")}
    except Exception:  # noqa: BLE001 — the page just hides the AI parts
        logger.exception("ai flags")
        return {"enabled": False}


def _stamp(now):
    return store.fmt_dt(now)


def _clean(row):
    return {k: v for k, v in row.items() if v is not None}


def _int(value):
    return int(store.as_id(value) or 0) or None


def _name(db, user_id):
    user = db.get(store.USERS, user_id) if store.as_id(user_id) else None
    return (user or {}).get("Name") or (user or {}).get("Email") or ""


def _date(value, what="date"):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise bad("The {} must be a date like 2027-02-01.".format(what))
    return text


def _long_date(day):
    """'2027-02-01' -> '1 Feb 2027'."""
    try:
        d = datetime.strptime(str(day)[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return "{} {} {}".format(d.day, d.strftime("%b"), d.year)


def _wrap_ai(call):
    """An AiError (key missing, service down) as a plain 502; nothing half-saved is left claiming success."""
    try:
        return call()
    except ai_client.AiError as exc:
        raise ApiError(exc.message, 502)


# ---------------------------------------------------------------------------------------------- Stratus

def _put_json(db, key, value):
    db.put_file(key, json.dumps(value).encode("utf-8"), "application/json")


def _get_json(db, key, default):
    raw = db.get_file(key) if key else None
    if raw is None:
        return default
    try:
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        return default


def _get_text(db, key):
    raw = db.get_file(key) if key else None
    if raw is None:
        return ""
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _prefix(building, *parts):
    return "/".join(["ai", str(building["id"])] + [str(p) for p in parts])


# ---------------------------------------------------------------------------------------------- the budget

def _month_word(month):
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%B")
    except ValueError:
        return month


def budget(db, building, now):
    month = ai_review.month_of(now)
    rows = db.find(store.AI_USAGE, {"Building_Id": int(building["id"]), "Usage_Month": month})
    spent = ai_review.spent_aud(rows, month)
    cap = ai_client.monthly_cap_aud({"ai": {"monthly_cap_aud": settings_of(building)["monthly_cap_aud"]}})
    return month, spent, cap, rows


def budget_out(db, building, now):
    month, spent, cap, rows = budget(db, building, now)
    out = dict(ai_review.budget_status(spent, cap), month=month, month_name=_month_word(month))
    out["rows"] = len(rows)
    return out


def _save_ai(db, building, **changes):
    settings = dict(building.get("settings") or {})
    settings["ai"] = dict(settings.get("ai") or {}, **changes)
    text = json.dumps(settings)
    if len(text) > store.TEXT_MAX:
        raise bad("Those settings are too long.")
    db.update(store.BUILDINGS, {"ROWID": building["id"], "Settings": text})
    building["settings"] = settings


def _admin_emails(db, building):
    return people.emails_with_roles(db, building, ("admin",))


def cap_reached(db, building, now, spent, cap):
    """Once a month: a Failures row (kind ai_cap) and one email to the admins. Never raises."""
    month = ai_review.month_of(now)
    try:
        if ((building.get("settings") or {}).get("ai") or {}).get("stopped") == month:
            return
        _save_ai(db, building, stopped=month)
        words = ("This building's AI budget for {} is used up (A${:.2f} of A${:.2f}). Nothing was sent."
                 .format(_month_word(month), spent, cap))
        failures.log(db, "ai_cap", words, building["id"])
        html = mailer.page(building, "AI budget used up", [words, "An admin can raise the monthly limit in "
                                                                  "Settings → AI, or wait for next month."],
                           "Open the portal")
        mailer.send_many(db, _admin_emails(db, building), "{}: AI budget used up".format(building["name"]), html,
                         building=building)
    except Exception:  # noqa: BLE001
        logger.exception("cap notice")


def warn_if_near(db, building, now):
    """At 80% of the cap, one email to the admins that month. Never raises."""
    try:
        month, spent, cap, _ = budget(db, building, now)
        status = ai_review.budget_status(spent, cap)
        if not status["warn"] or ((building.get("settings") or {}).get("ai") or {}).get("warned") == month:
            return
        _save_ai(db, building, warned=month)
        html = mailer.page(building, "AI budget nearly used", [
            "This building has used A${:.2f} of its A${:.2f} AI budget for {}.".format(spent, cap, _month_word(month)),
            "When it's used up, nothing more is sent until next month or until an admin raises the limit."],
            "Open the portal")
        mailer.send_many(db, _admin_emails(db, building), "{}: AI budget at 80%".format(building["name"]), html,
                         building=building)
    except Exception:  # noqa: BLE001
        logger.exception("cap warning")


def _check(db, building, now, estimate_aud):
    """Raise BudgetReached (402) before anything is sent, telling the admins once."""
    month, spent, cap, _ = budget(db, building, now)
    try:
        ai_review.check_budget(spent, estimate_aud, cap, month)
    except ai_review.BudgetReached as exc:
        cap_reached(db, building, now, spent, cap)
        raise exc
    return spent, cap


def _save_usage(db, rows, ref_id=None):
    total = 0.0
    for row in rows:
        row = dict(row, Ref_Id=_int(ref_id) or row.get("Ref_Id"), Cost_Usd=round(float(row["Cost_Usd"]), 4),
                   Cost_Aud=round(float(row["Cost_Aud"]), 4))
        row["Building_Id"] = int(row["Building_Id"])
        if row.get("User_Id") is not None:
            row["User_Id"] = int(row["User_Id"])
        db.insert(store.AI_USAGE, _clean(row))
        total += row["Cost_Aud"]
    return round(total, 4)


# ---------------------------------------------------------------------------------------------- settings

def settings_out(db, building, ctx, now):
    s = settings_of(building)
    month, spent, cap, _ = budget(db, building, now)
    return {"settings": {"enabled": s["enabled"], "approver": s["approver"],
                         "monthly_cap_aud": s["monthly_cap_aud"],
                         "default_cap_aud": ai_client.monthly_cap_aud({})},
            "budget": dict(ai_review.budget_status(spent, cap), month=month, month_name=_month_word(month)),
            "notice": PRIVACY_NOTICE, "guidance": ai_review.GUIDANCE,
            "approvers": [{"key": k, "label": APPROVER_LABELS[k]} for k in ai_review.APPROVER_MODES],
            "can_edit": flags(ctx)["admin"]}


def get_settings(c):
    gate(c, "see", allow_off=True)
    return settings_out(c.db, c.building, c.ctx, c.now)


def post_settings(c):
    gate(c, "admin", allow_off=True)
    changes = {}
    if c.get("enabled") is not None:
        changes["enabled"] = c.get("enabled") in (True, "true", 1, "1")
    if c.get("approver") is not None:
        if c.get("approver") not in ai_review.APPROVER_MODES:
            raise bad("Choose who approves: owner, secretary or committee_vote.")
        changes["approver"] = c.get("approver")
    if "monthly_cap_aud" in c.body:
        cap = c.get("monthly_cap_aud")
        if cap in (None, ""):
            changes["monthly_cap_aud"] = None
        else:
            try:
                cap = round(float(cap), 2)
            except (TypeError, ValueError):
                raise bad("The monthly limit is a number of dollars.")
            if not 0 <= cap <= 1000:
                raise bad("The monthly limit must be between A$0 and A$1,000.")
            changes["monthly_cap_aud"] = cap
    _save_ai(c.db, c.building, **changes)
    return settings_out(c.db, c.building, c.ctx, c.now)


def get_usage(c):
    gate(c, "see", allow_off=True)
    month, spent, cap, rows = budget(c.db, c.building, c.now)
    out = dict(ai_review.budget_status(spent, cap), month=month, month_name=_month_word(month))
    out["rows"] = [{"kind": r.get("Kind"), "model": r.get("Model"), "cost_aud": float(r.get("Cost_Aud") or 0),
                    "batch": r.get("Is_Batch") in (True, "true"), "at": store.created_iso(r)}
                   for r in sorted(rows, key=lambda r: -int(r["ROWID"]))][:100]
    return out


# ---------------------------------------------------------------------------------------------- documents

def _doc(db, building, doc_id):
    row = db.get(store.DOC_VERSIONS, doc_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That document wasn't found.")
    return row


def _usable(row):
    """Text a review or an answer may rely on: read from the PDF's own text, or checked by a person."""
    return bool(row.get("Text_Key")) and (row.get("Text_Source") == "pdf_text"
                                          or row.get("Text_Checked") in (True, "true"))


def doc_out(row):
    return {"id": str(row["ROWID"]), "kind": row.get("Kind"), "kind_label": DOC_KINDS.get(row.get("Kind"), ""),
            "title": row.get("Title") or "", "version_label": row.get("Version_Label") or "",
            "registered_on": str(row.get("Registered_On") or "")[:10],
            "registered_text": _long_date(row.get("Registered_On")) if row.get("Registered_On") else "",
            "dealing_no": row.get("Dealing_No") or "", "text_source": row.get("Text_Source") or "",
            "text_checked": row.get("Text_Checked") in (True, "true"), "clause_count": int(row.get("Clause_Count") or 0),
            "status": row.get("Status"), "usable": _usable(row), "error": row.get("Error") or "",
            "needs_check": bool(row.get("Text_Key")) and not _usable(row),
            "uploaded": store.created_iso(row), "supersedes_id": str(row.get("Supersedes_Id") or "") or None}


def _docs(db, building):
    return sorted(db.find(store.DOC_VERSIONS, {"Building_Id": int(building["id"])}), key=lambda r: -int(r["ROWID"]))


def get_docs(c):
    f = gate(c, "see")
    return {"docs": [doc_out(r) for r in _docs(c.db, c.building) if r.get("Status") != "withdrawn"],
            "can_manage": f["manage"], "kinds": [{"key": k, "label": v} for k, v in DOC_KINDS.items()]}


def get_doc(c):
    f = gate(c, "see")
    row = _doc(c.db, c.building, c.get("id"))
    return {"doc": doc_out(row), "clauses": _get_json(c.db, row.get("Text_Key"), []), "can_manage": f["manage"]}


def doc_file(c):
    """(bytes, type, name) of the PDF, for main to send as a download."""
    gate(c, "see")
    row = _doc(c.db, c.building, c.get("id"))
    data = c.db.get_file(row.get("File_Key"))
    if data is None:
        raise not_found("That file wasn't found.")
    return data, "application/pdf", uploads.safe_name(row.get("Title") or "document") + ".pdf"


def pdf_chunks(data, size=CHUNK_PAGES):
    """A scanned PDF as [(first page, last page, base64 PDF of those pages)], at most `size` pages each."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    total, out = len(reader.pages), []
    for start in range(0, total, size):
        writer = pypdf.PdfWriter()
        for n in range(start, min(total, start + size)):
            writer.add_page(reader.pages[n])
        buf = io.BytesIO()
        writer.write(buf)
        out.append((start + 1, min(total, start + size), base64.b64encode(buf.getvalue()).decode("ascii")))
    return out


def _transcribe_estimate_aud(chunks):
    """Worst case for a transcription batch: ~5k tokens a page in, full max_tokens out, batch price."""
    rate = ai_client.PRICES[ai_client.SONNET]
    usd = 0.0
    for first, last, _ in chunks:
        payload = ai_review.transcribe_payload("", first, last)
        prompt = (last - first + 1) * PDF_PAGE_TOKENS + ai_review.estimate_tokens(payload)
        usd += (prompt * rate["write_1h"] + payload["max_tokens"] * rate["output"]) / 1e6
    return ai_client.aud(usd * ai_client.BATCH_FACTOR)


def post_docs(c):
    gate(c, "manage")
    db, building = c.db, c.building
    kind = c.get("kind")
    if kind not in DOC_KINDS:
        raise bad("Choose CMS, by-laws, or one document with both.")
    title = str(c.get("title") or "").strip()
    if not title or len(title) > 255:
        raise bad("Give the document a title (255 characters at most).")
    label = str(c.get("version_label") or "").strip()[:100]
    dealing = str(c.get("dealing_no") or "").strip()[:100]
    registered = _date(c.get("registered_on"), "registration date")
    data, kind_of_file, _ = uploads.decode(c.get("file"))
    if kind_of_file != "application/pdf":
        raise bad("Upload the document as a PDF.")
    sha = hashlib.sha256(data).hexdigest()
    existing = _docs(db, building)
    same = next((r for r in existing if r.get("Sha256") == sha and r.get("Status") != "withdrawn"), None)
    if same:
        raise bad("That PDF is already uploaded, as \"{}\".".format(same.get("Title")))
    pages = ai_review.pdf_page_texts(data)
    scanned = ai_review.looks_scanned(pages)
    chunks = []
    if scanned:
        chunks = pdf_chunks(data)
        _check(db, building, c.now, _transcribe_estimate_aud(chunks))
    family = [r for r in existing if r.get("Kind") == kind and r.get("Status") != "withdrawn"]
    row = {"Building_Id": int(building["id"]), "Kind": kind, "Title": title, "Version_Label": label,
           "Dealing_No": dealing, "File_Key": "pending", "Sha256": sha, "Status": "uploaded", "Text_Checked": False,
           "Uploaded_By": int(c.ctx["user_id"]), "Registered_On": registered or None,
           "Supersedes_Id": int(family[0]["ROWID"]) if family else None}
    made = db.insert(store.DOC_VERSIONS, _clean(row))
    key = _prefix(building, "docs", made["ROWID"], "original.pdf")
    db.put_file(key, data, "application/pdf")
    change = {"ROWID": made["ROWID"], "File_Key": key}
    warning = ""
    if not scanned:
        clauses = ai_review.split_clauses("\n".join(pages))
        text_key = _prefix(building, "docs", made["ROWID"], "clauses.json")
        _put_json(db, text_key, clauses)
        change.update(Text_Key=text_key, Text_Source="pdf_text", Clause_Count=len(clauses), Status="text_ready")
    else:
        requests = [{"custom_id": "doc{}-p{}".format(made["ROWID"], first),
                     "params": ai_review.transcribe_payload(b64, first, last)} for first, last, b64 in chunks]
        try:
            batch = make_client().create_batch(requests)
            change.update(Batch_Id=str(batch.get("id") or "")[:100], Status="transcribing")
        except ai_client.AiError as exc:
            warning = ("This PDF is a scan with no text in it, and the AI couldn't be asked to read it ({}). "
                       "Paste the text instead.").format(exc.message)
            change.update(Error=warning[:255])
    db.update(store.DOC_VERSIONS, change)
    out = {"doc": doc_out(dict(made, **change))}
    if scanned and not warning:
        out["warning"] = ("This PDF is a scan, so the AI is reading it (usually under an hour). Check its text "
                          "against the PDF before using it.")
    elif warning:
        out["warning"] = warning
    return out


def post_doc_text(c):
    """A person pastes the text, corrects clauses, or ticks "text checked"."""
    gate(c, "manage")
    db, building = c.db, c.building
    row = _doc(db, building, c.get("id"))
    change = {"ROWID": row["ROWID"]}
    clauses = None
    if c.get("text") not in (None, ""):
        text = str(c.get("text"))
        if len(text) > MAX_TEXT:
            raise bad("That text is too long.")
        clauses = ai_review.split_clauses(text)
        change["Text_Source"] = "pasted"
        change["Text_Checked"] = False
    elif c.get("clauses") is not None:
        items = c.get("clauses")
        if not isinstance(items, list) or not items:
            raise bad("Send the clauses as a list.")
        clauses = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("id") or "").strip() \
                    or not str(item.get("text") or "").strip():
                raise bad("Each clause needs its number and its words.")
            clauses.append({"id": str(item["id"]).strip()[:60], "heading": str(item.get("heading") or "")[:255],
                            "text": str(item["text"])})
        if len(json.dumps(clauses)) > MAX_TEXT:
            raise bad("That text is too long.")
        change["Text_Source"] = row.get("Text_Source") or "pasted"
    if clauses is not None:
        if not clauses:
            raise bad("No clauses were found in that text. Each clause should start on its own line with its number.")
        key = _prefix(building, "docs", row["ROWID"], "clauses.json")
        _put_json(db, key, clauses)
        change.update(Text_Key=key, Clause_Count=len(clauses), Error="")
        if row.get("Status") in ("uploaded", "transcribing"):
            change.update(Status="text_ready", Batch_Id="")
    if c.get("checked") is not None:
        if not (change.get("Text_Key") or row.get("Text_Key")):
            raise bad("There's no text to check yet.")
        change["Text_Checked"] = c.get("checked") in (True, "true", 1, "1")
    registered = _date(c.get("registered_on"), "registration date")
    if registered:
        change["Registered_On"] = registered
    for key in ("dealing_no", "version_label"):
        if c.get(key) is not None:
            change["Dealing_No" if key == "dealing_no" else "Version_Label"] = str(c.get(key)).strip()[:100]
    db.update(store.DOC_VERSIONS, change)
    return {"doc": doc_out(dict(row, **change))}


def _collect_doc(db, building, row, client, now):
    batch = client.get_batch(row["Batch_Id"])
    if batch.get("processing_status") != "ended":
        return False
    results = client.batch_results(batch)
    pieces, usage, missing = [], [], 0
    for line in results:
        result = line.get("result") or {}
        match = re.search(r"-p(\d+)$", str(line.get("custom_id") or ""))
        if result.get("type") != "succeeded" or not match:
            missing += 1
            continue
        message = result.get("message") or {}
        usage.append(ai_review.usage_row(int(building["id"]), "transcribe", message.get("model") or ai_client.SONNET,
                                         message, True, now))
        texts = [b.get("text") for b in message.get("content") or [] if b.get("type") == "text"]
        if message.get("stop_reason") == "max_tokens" or not texts:
            missing += 1
            continue
        pieces.append((int(match.group(1)), texts[-1]))
    _save_usage(db, usage, row["ROWID"])
    change = {"ROWID": row["ROWID"], "Batch_Id": ""}
    if missing or not pieces:
        change.update(Status="uploaded", Error="Some pages couldn't be read by the AI. Paste the text instead.")
    else:
        text = "\n".join(t for _, t in sorted(pieces))
        db.put_file(_prefix(building, "docs", row["ROWID"], "text.txt"), text.encode("utf-8"), "text/plain")
        clauses = ai_review.split_clauses(text)
        key = _prefix(building, "docs", row["ROWID"], "clauses.json")
        _put_json(db, key, clauses)
        change.update(Status="text_ready", Text_Key=key, Text_Source="ai_transcribed", Text_Checked=False,
                      Clause_Count=len(clauses), Error="")
    db.update(store.DOC_VERSIONS, change)
    return True


def question_docs(db, building):
    """{"cms": clauses, "bylaws": clauses} in force now: the in-force version, else the newest usable one."""
    rows = [r for r in _docs(db, building) if _usable(r) and r.get("Status") not in ("withdrawn", "superseded")]
    picks = {}
    for family in ("cms", "bylaws"):
        cands = [r for r in rows if r.get("Kind") in (family, "cms_bylaws")]
        live = [r for r in cands if r.get("Status") == "in_force"] or cands
        if live:
            picks[family] = live[0]
    if "cms" in picks and "bylaws" in picks and picks["cms"]["ROWID"] == picks["bylaws"]["ROWID"]:
        picks.pop("cms")
    return {k: _get_json(db, r.get("Text_Key"), []) for k, r in picks.items()}


# ---------------------------------------------------------------------------------------------- reviews

def _review(db, building, review_id):
    row = db.get(store.RULE_REVIEWS, review_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That review wasn't found.")
    return row


def _topics_now(db, building):
    """{key: definition} and {key: active} of the live Topics rows."""
    rows = db.find(store.TOPICS, {"Building_Id": int(building["id"])})
    defs, active = {}, {}
    for row in rows:
        try:
            value = json.loads(row.get("Definition") or "{}")
        except ValueError:
            continue
        defs[row.get("Topic_Key")] = value
        active[row.get("Topic_Key")] = row.get("Active") not in (False, "false", 0, "0")
    return defs, active


def review_out(db, row):
    old = db.get(store.DOC_VERSIONS, row.get("Old_Doc_Id")) or {}
    new = db.get(store.DOC_VERSIONS, row.get("New_Doc_Id")) or {}
    return {"id": str(row["ROWID"]), "status": row.get("Status"), "status_label": REVIEW_LABELS.get(row.get("Status"), ""),
            "old_doc_id": str(row.get("Old_Doc_Id")), "new_doc_id": str(row.get("New_Doc_Id")),
            "old_title": old.get("Title") or "", "new_title": new.get("Title") or "",
            "change_count": int(row.get("Change_Count") or 0),
            "estimate_aud": float(row.get("Estimate_Aud") or 0), "cost_aud": float(row.get("Cost_Aud") or 0),
            "error": row.get("Error") or "", "started": store.created_iso(row),
            "started_by": _name(db, row.get("Started_By")),
            "applied_at": str(row.get("Applied_At") or "")[:19]}


def get_reviews(c):
    gate(c, "see")
    rows = sorted(c.db.find(store.RULE_REVIEWS, {"Building_Id": int(c.building["id"])}), key=lambda r: -int(r["ROWID"]))
    return {"reviews": [review_out(c.db, r) for r in rows]}


def post_reviews(c):
    """Without confirm: the clause changes (free) and the estimate. With confirm: step 1 goes to the AI."""
    gate(c, "manage")
    db, building, now = c.db, c.building, c.now
    old, new = _doc(db, building, c.get("old_doc_id")), _doc(db, building, c.get("new_doc_id"))
    if str(old["ROWID"]) == str(new["ROWID"]):
        raise bad("Pick two different versions.")
    for row in (old, new):
        if not _usable(row):
            raise bad("Check the text of \"{}\" against the PDF first (tick \"Text checked\").".format(row.get("Title")))
    old_clauses, new_clauses = _get_json(db, old["Text_Key"], []), _get_json(db, new["Text_Key"], [])
    current, _ = _topics_now(db, building)
    law = law_text()
    confirm = c.get("confirm") in (True, "true", 1, "1")
    preview = ai_review.start_review(old_clauses, new_clauses, current, law, building["name"], 0, float("inf"),
                                     now, 0)
    month, spent, cap, _ = budget(db, building, now)
    out = {"changes": preview["changes"], "estimate_aud": preview["estimate_aud"],
           "budget": dict(ai_review.budget_status(spent, cap), month=month, month_name=_month_word(month)),
           "fits": cap > 0 and spent + preview["estimate_aud"] <= cap, "review": None}
    if not confirm:
        return out
    if not preview["changes"]:
        raise bad("The two versions have the same clauses: there's nothing to compare.")
    if any(r.get("Status") in RUNNING for r in db.find(store.RULE_REVIEWS, {"Building_Id": int(building["id"])})):
        raise bad("A comparison is already running or waiting for a vote. Finish that one first.")
    _check(db, building, now, preview["estimate_aud"])
    row = db.insert(store.RULE_REVIEWS, {"Building_Id": int(building["id"]), "Old_Doc_Id": int(old["ROWID"]),
                                         "New_Doc_Id": int(new["ROWID"]), "Status": "mapping",
                                         "Change_Count": len(preview["changes"]),
                                         "Estimate_Aud": preview["estimate_aud"], "Cost_Aud": 0.0,
                                         "Started_By": int(c.ctx["user_id"])})
    diff_key = _prefix(building, "reviews", row["ROWID"], "diff.json")
    _put_json(db, diff_key, preview["changes"])
    db.put_file(_prefix(building, "reviews", row["ROWID"], "context.txt"), preview["context"].encode("utf-8"),
                "text/plain")
    request = dict(preview["batch_requests"][0], custom_id="rev{}-map".format(row["ROWID"]))
    try:
        batch = make_client().create_batch([request])
    except ai_client.AiError as exc:
        db.update(store.RULE_REVIEWS, {"ROWID": row["ROWID"], "Status": "failed", "Diff_Key": diff_key,
                                       "Error": exc.message[:255]})
        failures.log(db, "ai", "A by-law comparison couldn't start: {}".format(exc.message), building["id"])
        raise ApiError(exc.message + " Nothing was charged.", 502)
    change = {"ROWID": row["ROWID"], "Diff_Key": diff_key, "Batch_Id": str(batch.get("id") or "")[:100]}
    db.update(store.RULE_REVIEWS, change)
    out["review"] = review_out(db, dict(row, **change))
    return out


def _approver_emails(db, building):
    mode = settings_of(building)["approver"]
    if mode == "owner":
        support = os.environ.get("SUPPORT_EMAIL", "").strip()
        return [support] if support else []
    if mode == "secretary":
        return committee.emails_of(db, committee.holders(db, building, "secretary"))
    return committee.emails_of(db, committee.voting_ids(db, building))


def _review_link(building, review_id):
    base = mailer.portal_link(building)
    return "{}#/ai/review/{}".format(base, review_id) if base else ""


def _fail_review(db, building, row, words):
    change = {"ROWID": row["ROWID"], "Status": "failed", "Batch_Id": "", "Error": words[:255]}
    db.update(store.RULE_REVIEWS, change)
    failures.log(db, "ai", "By-law comparison #{}: {}".format(row["ROWID"], words), building["id"])
    return dict(row, **change)


def advance_review(db, building, row, client, now):
    """Collect a finished batch and take the review one step on. Returns the row as it is now."""
    status = row.get("Status")
    if status not in ("mapping", "proposing") or not row.get("Batch_Id"):
        return row
    batch = client.get_batch(row["Batch_Id"])
    if batch.get("processing_status") != "ended":
        return row
    results = client.batch_results(batch)
    review_id = row["ROWID"]
    _put_json(db, _prefix(building, "reviews", review_id, "map.json" if status == "mapping" else "propose.json"),
              results)
    answers, errors, usage = ai_review.read_batch(results, int(building["id"]), now,
                                                  "review_map" if status == "mapping" else "review_propose")
    cost = round(float(row.get("Cost_Aud") or 0) + _save_usage(db, usage, review_id), 4)
    current, _ = _topics_now(db, building)
    law = law_text()
    if status == "mapping":
        answer = answers.get("rev{}-map".format(review_id))
        if not answer:
            db.update(store.RULE_REVIEWS, {"ROWID": review_id, "Cost_Aud": cost})
            return _fail_review(db, building, dict(row, Cost_Aud=cost), "The first step didn't come back ({}). "
                                "Start the comparison again.".format(", ".join(errors.values()) or "no answer"))
        changes = _get_json(db, row.get("Diff_Key"), [])
        context = _get_text(db, _prefix(building, "reviews", review_id, "context.txt"))
        plan = ai_review.plan_proposals(answer, changes, current, law, context, review_id)
        if not plan:
            change = {"ROWID": review_id, "Status": "ready", "Batch_Id": "", "Cost_Aud": cost,
                      "Error": "The AI found no change the request types need."}
            db.update(store.RULE_REVIEWS, change)
            _tell_ready(db, building, review_id, 0)
            return dict(row, **change)
        try:
            made = client.create_batch(plan)
        except ai_client.AiError as exc:
            if exc.retryable:
                db.update(store.RULE_REVIEWS, {"ROWID": review_id, "Cost_Aud": cost})
                return dict(row, Cost_Aud=cost)          # the map is kept; tried again next time
            return _fail_review(db, building, row, exc.message)
        change = {"ROWID": review_id, "Status": "proposing", "Batch_Id": str(made.get("id") or "")[:100],
                  "Cost_Aud": cost}
        db.update(store.RULE_REVIEWS, change)
        return dict(row, **change)
    old = db.get(store.DOC_VERSIONS, row.get("Old_Doc_Id")) or {}
    new = db.get(store.DOC_VERSIONS, row.get("New_Doc_Id")) or {}
    sources = {"old": ai_review.clause_map(_get_json(db, old.get("Text_Key"), [])),
               "new": ai_review.clause_map(_get_json(db, new.get("Text_Key"), [])), "law": law}
    raws = []
    for cid in sorted(answers):
        raws += answers[cid].get("proposals") or []
    rows = ai_review.validate_all(raws, current, sources, int(review_id), int(building["id"]))
    for item in rows:
        db.insert(store.RULE_PROPOSALS, _clean(item))
    words = ""
    if errors:
        words = "{} part(s) of the review didn't come back; their request types weren't checked.".format(len(errors))
    change = {"ROWID": review_id, "Status": "ready", "Batch_Id": "", "Cost_Aud": cost, "Error": words}
    db.update(store.RULE_REVIEWS, change)
    _tell_ready(db, building, review_id, len(rows))
    return dict(row, **change)


def _tell_ready(db, building, review_id, count):
    lines = ["The AI has compared the new CMS/by-laws with the old ones and made {} proposal(s) for the request "
             "types.".format(count) if count else "The AI compared the new CMS/by-laws and found nothing the request "
             "types need to change.",
             "Nothing changes until a person approves each proposal and presses Apply.", ai_review.GUIDANCE]
    html = mailer.page(building, "By-law review ready", lines, "Open the review", link=_review_link(building, review_id))
    mailer.send_many(db, _approver_emails(db, building), "{}: by-law review ready".format(building["name"]), html,
                     building=building)


def post_review_check(c):
    gate(c, "see")
    row = _review(c.db, c.building, c.get("id"))
    row = _wrap_ai(lambda: advance_review(c.db, c.building, row, make_client(), c.now))
    row = settle_vote(c.db, c.building, row, c.now)
    return {"review": review_out(c.db, row)}


# ---------------------------------------------------------------------------------------------- words for people

TOP_WORDS = {"label": "name", "intro": "introduction", "audience": "who may use it", "handler": "who handles it",
             "draft": "marked draft", "after_decision": "step after the decision", "fields": "form",
             "steps": "steps", "stages": "step", "deadline": "deadline", "vote": "vote rules"}
LEAF_WORDS = {"required": "required", "label": "label", "type": "answer type", "options": "choices",
              "help": "help text", "days": "days", "outcome": "if nobody decides", "banner": "warning wording",
              "card": "board label", "citation": "legal source", "if_missed": "if-missed wording",
              "extend_to_days": "can be extended to (days)", "business_day": "counts business days only",
              "from": "counted from", "subject": "email subject", "body": "email wording", "to": "email goes to",
              "instructions": "instructions", "owner": "whose step", "status": "status", "rule": "rule",
              "next": "moves to", "note": "note", "note_label": "note label", "needs_decision": "needs a decision",
              "opens_vote": "opens a vote", "motion": "motion wording", "extends": "extends the deadline",
              "email": "email", "buttons": "button", "title": "title", "animal": "animal request",
              "if_passed": "if the vote passes", "if_defeated": "if the vote is defeated",
              "if_no_result": "if there's no result"}
APPEND_WORDS = {"fields": "new question on the form", "stages": "new step", "steps": "new checklist step",
                "buttons": "new button"}
OUTCOME_WORDS = {"deemed_approved": "treated as APPROVED", "not_agreed": "treated as NOT AGREED",
                 "none": "nothing happens automatically"}
_MISSING = object()


def _value_words(value):
    if value is _MISSING or value is None:
        return "(none)"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if all(isinstance(v, (str, int, float)) for v in value):
            return ", ".join(str(v) for v in value) or "(none)"
        return ", ".join(str(v.get("label") or v.get("title") or v.get("key") or "…") if isinstance(v, dict)
                         else str(v) for v in value)
    if isinstance(value, dict):
        if value.get("label") or value.get("title"):
            return "'{}'".format(value.get("label") or value.get("title"))
        return "; ".join("{}: {}".format(LEAF_WORDS.get(k, k), _value_words(v)) for k, v in value.items())[:400]
    text = str(value)
    return text if len(text) <= 400 else text[:400] + "…"


def _walk(definition, path):
    """(the value at path or _MISSING, [plain words for each step])."""
    node, words = definition, []
    for name, sel in ai_review.parse_path(path):
        word = TOP_WORDS.get(name) if not words else LEAF_WORDS.get(name, name.replace("_", " "))
        word = word or name
        if node is _MISSING or not isinstance(node, dict):
            node = _MISSING
            words.append(word)
            continue
        node = node.get(name, _MISSING)
        if sel is None:
            words.append(word)
            continue
        items = node if isinstance(node, list) else []
        if sel[0] == "append":
            words.append(APPEND_WORDS.get(name, "new " + word))
            node = _MISSING
            continue
        if sel[0] == "index":
            item = items[sel[1]] if sel[1] < len(items) else _MISSING
        else:
            item = next((i for i in items if isinstance(i, dict) and i.get("key") == sel[1]), _MISSING)
        label = item.get("label") or item.get("title") if isinstance(item, dict) else None
        words.append("{} '{}'".format(word, label or (sel[1] if sel[0] == "key" else "#{}".format(sel[1] + 1))))
        node = item
    return node, words


def describe(topic_label, before, change):
    """One change in plain words: {where, old, new, clause}. 'Pet request · form 'Registered' · required: No -> Yes'."""
    old, words = _walk(before or {}, change["path"])
    op = change.get("op")
    new = "(removed)" if op == "remove" else _value_words(change.get("value"))
    old_words = "(not there)" if op == "add" else _value_words(old)
    return {"where": " · ".join([topic_label] + words), "old": old_words, "new": new, "clause": change.get("clause") or ""}


def missed_words(definition):
    deadline = (definition or {}).get("deadline")
    if not isinstance(deadline, dict) or not deadline.get("days"):
        return "No deadline."
    text = "If nobody decides within {} {}days: {}.".format(
        deadline["days"], "business " if deadline.get("business_day") else "",
        OUTCOME_WORDS.get(deadline.get("outcome") or "none", "nothing happens automatically"))
    if deadline.get("citation"):
        text += " ({})".format(deadline["citation"])
    return text


def _sample_values(building, topic_label, definition):
    return {"name": "Jo Citizen", "ref": "ALT-0042", "title": topic_label, "unit": "Unit 4",
            "building": building["name"], "link": "(link to the request)", "date": "1 Dec 2026",
            "short_date": "1 Dec", "if_missed": missed_words(definition), "note": "(the note typed in)",
            "note_line": "", "decision": "Approved", "sender": "Sarah (Secretary)"}


def stage_previews(building, label, after, changes):
    """For changes to steps or emails: the step's instructions and each email filled with sample data."""
    keys, buttons = [], {}
    for change in changes:
        match = re.match(r"^stages\[key=([a-z0-9_-]+)\](?:\.buttons\[key=([a-z0-9_-]+)\])?", change["path"])
        if match and match.group(1) not in keys:
            keys.append(match.group(1))
        if match and match.group(2):
            buttons.setdefault(match.group(1), set()).add(match.group(2))
    out = []
    values = _sample_values(building, label, after)
    for stage in (after or {}).get("stages") or []:
        if stage.get("key") not in keys:
            continue
        emails = [{"button": b.get("label"), "to": (b.get("email") or {}).get("to") or "",
                   "subject": stages.render((b.get("email") or {}).get("subject"), values),
                   "body": stages.render((b.get("email") or {}).get("body"), values)}
                  for b in stage.get("buttons") or [] if b.get("email")
                  and (stage.get("key") not in buttons or b.get("key") in buttons[stage.get("key")])]
        out.append({"stage": stage.get("label"), "instructions": stage.get("instructions") or "",
                    "rule": stage.get("rule") or "", "emails": emails})
    return out


def _form(definition):
    return [{k: f.get(k) for k in ("key", "label", "type", "required", "options", "help")}
            for f in (definition or {}).get("fields") or [] if isinstance(f, dict)]


def proposal_out(db, building, row, current, users=None):
    kind, key = row.get("Kind"), row.get("Topic_Key") or ""
    before = current.get(key)
    stored = _json(row.get("Edited_Json")) or _json(row.get("Proposed_Json")) or {}
    changes = stored.get("changes") or []
    after, broken = None, ""
    if kind == "edit_topic" and before is not None:
        try:
            after = ai_review.apply_changes(before, changes)
        except ValueError as exc:
            broken = str(exc)
    elif kind == "new_topic":
        after = stored.get("after")
    elif kind == "retire_topic":
        after = None
    label = (after or before or {}).get("label") or key or "New request type"
    missed = None
    if kind in ("edit_topic", "new_topic") and (before or {}).get("deadline") != (after or {}).get("deadline"):
        missed = {"before": missed_words(before) if before else "", "after": missed_words(after)}
    problems = _json(row.get("Problems")) or []
    if broken:
        problems = problems + ["It no longer fits the current settings: " + broken]
    return {"id": str(row["ROWID"]), "seq": int(row.get("Seq") or 0), "kind": kind, "topic_key": key,
            "topic_label": label, "title": row.get("Title") or "", "why": row.get("Why") or "",
            "citations": _json(row.get("Citations")) or [], "problems": problems,
            "invalid": row.get("Status") == "invalid" or bool(broken), "status": row.get("Status"),
            "unconfirmed": row.get("Unconfirmed") in (True, "true"),
            "unconfirmed_reason": row.get("Unconfirmed_Reason") or "",
            "edited": bool(row.get("Edited_Json")), "note": row.get("Decision_Note") or "",
            "decided_by": _name(db, row.get("Decided_By")) if row.get("Decided_By") else "",
            "changes": [describe(label, before, ch) for ch in changes] if kind == "edit_topic" else [],
            "raw_changes": changes, "if_missed": missed,
            "before_form": _form(before) if before is not None else None,
            "after_form": _form(after) if after is not None else None,
            "previews": stage_previews(building, label, after, changes) if kind == "edit_topic" and after else [],
            "before": before, "after": after}


def _json(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def _appliable(props):
    """Approved changes. A flag is a question for a person: ticking it records that it was checked, nothing more."""
    return [p for p in props if p.get("Status") in ("approved", "edited") and p.get("Kind") != "flag"]


def _proposals(db, review_id):
    return sorted(db.find(store.RULE_PROPOSALS, {"Review_Id": int(review_id)}), key=lambda r: int(r.get("Seq") or 0))


def _open_cases(db, building, keys):
    return [r for r in db.find(store.CASES, {"Building_Id": int(building["id"])})
            if r.get("Topic_Key") in keys and r.get("Status") not in ("decided", "closed")]


def get_review(c):
    f = gate(c, "see")
    db, building, now = c.db, c.building, c.now
    row = settle_vote(db, building, _review(db, building, c.get("id")), now)
    current, _ = _topics_now(db, building)
    props = [proposal_out(db, building, p, current) for p in _proposals(db, row["ROWID"])]
    new = db.get(store.DOC_VERSIONS, row.get("New_Doc_Id")) or {}
    old = db.get(store.DOC_VERSIONS, row.get("Old_Doc_Id")) or {}
    keys = {p["topic_key"] for p in props if p["status"] in ("approved", "edited", "proposed")}
    registered = str(new.get("Registered_On") or "")[:10]
    lodged_since = []
    if registered:
        start = store.parse_dt(ai_review.effective_from(registered))
        if start and start <= now:
            lodged_since = [{"id": str(r["ROWID"]), "ref": r.get("Ref"), "title": r.get("Title")}
                            for r in db.find(store.CASES, {"Building_Id": int(building["id"])})
                            if r.get("Topic_Key") in keys and (store.created_utc(r) or now) >= start]
    vote = None
    motion_id = next((p.get("Motion_Id") for p in _proposals(db, row["ROWID"]) if p.get("Motion_Id")), None)
    if motion_id and row.get("Status") == "voting":
        motion = db.get(store.MOTIONS, motion_id)
        if motion:
            vote = {"id": str(motion["ROWID"]), "status": motion.get("Status"),
                    "closes": str(motion.get("Closes_At") or "")[:19]}
    approved = [p for p in props if p["status"] in ("approved", "edited") and p["kind"] != "flag"]
    return {"review": review_out(db, row), "changes": _get_json(db, row.get("Diff_Key"), []),
            "proposals": props, "old_doc": doc_out(old) if old else None, "new_doc": doc_out(new) if new else None,
            "registered_on": registered, "registered_text": _long_date(registered) if registered else "",
            "open_cases_pinned": len(_open_cases(db, building, keys)), "lodged_since_registration": lodged_since,
            "approved_count": len(approved), "can_decide": f["decide"] and row.get("Status") == "ready",
            "can_apply": f["decide"] and row.get("Status") == "ready" and bool(approved) and bool(registered),
            "approver": f["approver"], "approver_label": APPROVER_LABELS[f["approver"]], "vote": vote,
            "guidance": ai_review.GUIDANCE}


def post_decide(c):
    gate(c, "decide")
    db, building, now = c.db, c.building, c.now
    row = db.get(store.RULE_PROPOSALS, c.get("id"))
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That proposal wasn't found.")
    review = _review(db, building, row.get("Review_Id"))
    if review.get("Status") != "ready":
        raise bad("These proposals can't be changed now ({}).".format(REVIEW_LABELS.get(review.get("Status"), "")))
    decision, note = c.get("decision"), str(c.get("note") or "").strip()[:255]
    change = {"ROWID": row["ROWID"], "Decided_By": int(c.ctx["user_id"]), "Decided_At": _stamp(now),
              "Decision_Note": note}
    if decision == "reject":
        if not note:
            raise bad("Say briefly why it's rejected.")
        change["Status"] = "rejected"
    elif decision in ("approve", "edit"):
        if row.get("Status") == "invalid":
            raise bad("The checker refused this proposal, so it can't be approved.")
        if row.get("Status") in ("applied", "undone"):
            raise bad("This proposal has already been applied.")
        if decision == "approve":
            change["Status"] = "approved"
        else:
            current, _ = _topics_now(db, building)
            old = db.get(store.DOC_VERSIONS, review.get("Old_Doc_Id")) or {}
            new = db.get(store.DOC_VERSIONS, review.get("New_Doc_Id")) or {}
            sources = {"old": ai_review.clause_map(_get_json(db, old.get("Text_Key"), [])),
                       "new": ai_review.clause_map(_get_json(db, new.get("Text_Key"), [])), "law": law_text()}
            edited = c.get("edited")
            if not isinstance(edited, dict):
                raise bad("Send the edited change.")
            stored, problems = ai_review.check_edit(row, edited, current, sources)
            if problems:
                raise bad("The checker refused that edit: " + " ".join(problems))
            if len(stored) > store.TEXT_MAX:
                raise bad("That edit is too long to store.")
            change.update(Status="edited", Edited_Json=stored)
    else:
        raise bad("Choose approve, edit or reject.")
    db.update(store.RULE_PROPOSALS, change)
    current, _ = _topics_now(db, building)
    return {"proposal": proposal_out(db, building, dict(row, **change), current)}


def _vote_words(building, new, approved):
    lines = ["That the committee approve these {} change(s) to {}'s request types, made to follow the new {} "
             "\"{}\"{}:".format(len(approved), building["name"], DOC_KINDS.get(new.get("Kind"), "document"),
                                new.get("Title"), " registered on " + _long_date(new.get("Registered_On"))
                                if new.get("Registered_On") else "")]
    for n, p in enumerate(approved, 1):
        lines.append("{}. {} ({})".format(n, p.get("Title"), p.get("Topic_Key") or "new"))
    words = "\n".join(lines)
    return words if len(words) <= votes.MAX_WORDS else words[:votes.MAX_WORDS - 40] + "\n… (see the portal)"


def post_apply(c):
    gate(c, "decide")
    db, building, now = c.db, c.building, c.now
    row = _review(db, building, c.get("id"))
    if row.get("Status") != "ready":
        raise bad("This review can't be applied now ({}).".format(REVIEW_LABELS.get(row.get("Status"), "")))
    for change in db.find(store.CHANGES, {"Building_Id": int(building["id"])}):
        if str(change.get("Review_Id") or "") == str(row["ROWID"]) and change.get("Stage") not in ("cancelled",):
            raise bad("This review is part of rules change \"{}\": it applies there, once the lawyer and the "
                      "committee have signed off.".format(change.get("Title")))
    props = _proposals(db, row["ROWID"])
    approved = _appliable(props)
    if not approved:
        raise bad("Approve at least one change first.")
    new = db.get(store.DOC_VERSIONS, row.get("New_Doc_Id")) or {}
    if not new.get("Registered_On"):
        raise bad("Enter the date the new CMS/by-laws were registered before applying changes.")
    if settings_of(building)["approver"] == "committee_vote":
        motion = votes.open_vocm(db, building, c.ctx, _vote_words(building, new, approved), None, "", now)
        for p in approved:
            db.update(store.RULE_PROPOSALS, {"ROWID": p["ROWID"], "Motion_Id": int(motion["ROWID"])})
        db.update(store.RULE_REVIEWS, {"ROWID": row["ROWID"], "Status": "voting"})
        return {"review": review_out(db, dict(row, Status="voting")), "voting": True,
                "motion_id": str(motion["ROWID"])}
    return apply_now(db, building, row, approved, int(c.ctx["user_id"]), now)


def apply_now(db, building, row, approved, user_id, now, act_from=None):
    """Approved proposals become Topic_Versions rows in force from the registration date (or later)."""
    new = db.get(store.DOC_VERSIONS, row.get("New_Doc_Id")) or {}
    current, _ = _topics_now(db, building)
    versions = topics.versions_of(db, building)
    rows = ai_review.plan_apply(approved, current, versions, str(new.get("Registered_On") or "")[:10],
                                int(building["id"]), user_id, now, int(new["ROWID"]) if new else None)
    start = None
    for item in rows:
        if item["Source"] == "ai_review":
            if act_from and act_from > item["Effective_From"]:
                item["Effective_From"] = act_from      # a passed vote can be acted on only from Act_From
            start = item["Effective_From"]
    made = [db.insert(store.TOPIC_VERSIONS, _clean(item)) for item in rows]
    by_key = {m["Topic_Key"]: m for m in made if m.get("Source") == "ai_review"}
    for p in approved:
        version = by_key.get(p.get("Topic_Key"))
        db.update(store.RULE_PROPOSALS, _clean({"ROWID": p["ROWID"], "Status": "applied",
                                                "Version_Id": int(version["ROWID"]) if version else None}))
    db.update(store.RULE_REVIEWS, {"ROWID": row["ROWID"], "Status": "applied", "Applied_At": _stamp(now)})
    if new:
        db.update(store.DOC_VERSIONS, {"ROWID": new["ROWID"], "Status": "in_force"})
    old = db.get(store.DOC_VERSIONS, row.get("Old_Doc_Id")) or {}
    if old and str(old["ROWID"]) != str(new.get("ROWID")):
        db.update(store.DOC_VERSIONS, {"ROWID": old["ROWID"], "Status": "superseded"})
    promote(db, building, now)
    return {"versions": [version_out(db, m, now) for m in made], "effective_from": start,
            "effective_text": _long_date(new.get("Registered_On")) if new else "", "review": review_out(
                db, dict(row, Status="applied"))}


def settle_vote(db, building, row, now):
    """A review waiting on a committee vote: apply it when the vote passes; back to ready if it doesn't."""
    if row.get("Status") != "voting":
        return row
    props = _proposals(db, row["ROWID"])
    motion_id = next((p.get("Motion_Id") for p in props if p.get("Motion_Id")), None)
    motion = db.get(store.MOTIONS, motion_id) if motion_id else None
    if not motion:
        change = {"ROWID": row["ROWID"], "Status": "ready", "Error": "The committee vote wasn't found."}
        db.update(store.RULE_REVIEWS, change)
        return dict(row, **change)
    motion = votes.settle(db, building, motion, now) or motion
    status = motion.get("Status")
    if status == "passed":
        act = store.parse_dt(motion.get("Act_From"))
        approved = _appliable(props)
        apply_now(db, building, row, approved, _int(row.get("Started_By")), now, _stamp(act) if act else None)
        return dict(row, Status="applied")
    if status in ("defeated", "not_agreed", "lost"):
        change = {"ROWID": row["ROWID"], "Status": "ready",
                  "Error": "The committee vote didn't pass ({}). Nothing was changed.".format(
                      votes.STATUS_LABELS.get(status, status).lower())}
        db.update(store.RULE_REVIEWS, change)
        for p in props:
            if p.get("Motion_Id"):
                db.update(store.RULE_PROPOSALS, {"ROWID": p["ROWID"], "Motion_Id": None})
        return dict(row, **change)
    return row


# ---------------------------------------------------------------------------------------------- versions

def promote(db, building, now):
    """Copy every version whose date has come into Topics (the live request types). Returns how many."""
    versions = topics.versions_of(db, building)
    if not versions:
        return 0
    current, active = _topics_now(db, building)
    rows = {r.get("Topic_Key"): r for r in db.find(store.TOPICS, {"Building_Id": int(building["id"])})}
    count = 0
    for item in ai_review.due_promotions(versions, current, now, active):
        existing = rows.get(item["key"])
        sort = int(existing.get("Sort") or 0) if existing else max([int(r.get("Sort") or 0) for r in rows.values()]
                                                                    or [0]) + 1
        topics.save(db, building, item["key"], item["definition"], item["active"], sort)
        count += 1
    return count


def version_out(db, row, now, docs=None):
    stamp = _stamp(now)
    try:
        label = json.loads(row.get("Definition") or "{}").get("label") or row.get("Topic_Key")
    except ValueError:
        label = row.get("Topic_Key")
    baseline = row.get("Source") == "baseline"        # made from the settings before the document changed
    doc = db.get(store.DOC_VERSIONS, row.get("Doc_Version_Id")) if row.get("Doc_Version_Id") and not baseline else None
    starts = str(row.get("Effective_From") or "")[:19]
    when = store.parse_dt(starts)
    return {"id": str(row["ROWID"]), "topic_key": row.get("Topic_Key"), "label": label,
            "version": int(row["Version"]), "source": row.get("Source"),
            "source_label": SOURCE_LABELS.get(row.get("Source"), row.get("Source")),
            "effective_from": deadlines_iso(when),
            "effective_text": "from the start" if starts.startswith("2000-01-01") else (
                stages.long_date(when) if when else ""),
            "future": starts > stamp, "withdrawn": row.get("Active") in (False, "false"),
            "offered": row.get("Topic_Active") not in (False, "false"),
            "by": _name(db, row.get("Created_By")), "doc_title": (doc or {}).get("Title") or "",
            "note": row.get("Note") or ""}


def deadlines_iso(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ") if when else ""


def get_versions(c):
    f = gate(c, "see")
    db, building, now = c.db, c.building, c.now
    key = str(c.get("topic_key") or "").strip()
    versions = topics.versions_of(db, building, key or None)
    if not key:
        out = []
        for topic in topics.all_topics(db, building):
            mine = [v for v in versions if v.get("Topic_Key") == topic["key"]]
            live = topics.in_force(mine, topic["key"], _stamp(now))
            out.append({"key": topic["key"], "label": topic["label"], "count": len(mine),
                        "in_force": int(live["Version"]) if live else None,
                        "upcoming": any(str(v.get("Effective_From"))[:19] > _stamp(now) and
                                        v.get("Active") not in (False, "false") for v in mine)})
        return {"topics": out}
    live = topics.in_force(versions, key, _stamp(now))
    active = [v for v in versions if v.get("Active") not in (False, "false")]
    rows = sorted(versions, key=lambda v: -int(v["Version"]))
    label = (topics.get(db, building, key) or {}).get("label") or key
    return {"topic_key": key, "label": label, "versions": [version_out(db, v, now) for v in rows],
            "in_force": int(live["Version"]) if live else None, "can_undo": f["decide"] and len(active) >= 2,
            "open_cases": len(_open_cases(db, building, {key}))}


def post_undo(c):
    gate(c, "decide")
    db, building, now = c.db, c.building, c.now
    key = str(c.get("topic_key") or "").strip()
    versions = topics.versions_of(db, building, key)
    plan = ai_review.plan_undo(versions, key, now, int(c.ctx["user_id"]))
    if "withdraw" in plan:
        latest = plan["withdraw"]
        db.update(store.TOPIC_VERSIONS, {"ROWID": latest["ROWID"], "Active": False,
                                         "Note": "Withdrawn before it came into force"})
        undone = latest
        out = {"withdrawn": version_out(db, dict(latest, Active=False), now)}
    else:
        row = dict(plan["insert"], Building_Id=int(building["id"]), Note="Undo of version {}".format(
            max(int(v["Version"]) for v in versions if v.get("Active") not in (False, "false"))))
        made = db.insert(store.TOPIC_VERSIONS, _clean(row))
        undone = max([v for v in versions if v.get("Active") not in (False, "false")], key=lambda v: int(v["Version"]))
        promote(db, building, now)
        out = {"version": version_out(db, made, now)}
    for p in db.find(store.RULE_PROPOSALS, {"Building_Id": int(building["id"])}):
        if str(p.get("Version_Id") or "") == str(undone["ROWID"]):
            db.update(store.RULE_PROPOSALS, {"ROWID": p["ROWID"], "Status": "undone"})
    return out


# ---------------------------------------------------------------------------------------------- questions

def question_out(db, row):
    return {"id": str(row["ROWID"]), "question": row.get("Question") or "", "answer": row.get("Answer") or "",
            "citations": _json(row.get("Citations")) or [], "model": row.get("Model") or "",
            "escalated": row.get("Escalated") in (True, "true"), "unconfirmed": row.get("Unconfirmed") in (True, "true"),
            "status": row.get("Status"), "asked": store.created_iso(row), "asked_by": _name(db, row.get("User_Id")),
            "label": ai_review.GUIDANCE}


def post_ask(c):
    gate(c, "ask")
    db, building, now = c.db, c.building, c.now
    question = str(c.get("question") or "").strip()
    if not question:
        raise bad("Type your question.")
    if len(question) > MAX_QUESTION:
        raise bad("Keep the question under 2,000 characters.")
    docs = question_docs(db, building)
    if not docs:
        raise bad("Upload the building's CMS and by-laws first, and check their text.")
    month, spent, cap, _ = budget(db, building, now)
    client = make_client()
    try:
        out = ai_review.ask(client, question, docs, law_text(), spent, cap, now, int(building["id"]),
                            int(c.ctx["user_id"]))
    except ai_review.BudgetReached:
        cap_reached(db, building, now, spent, cap)
        raise
    except ai_client.AiError as exc:
        raise ApiError(exc.message + " Nothing was charged.", 502)
    stopped = any("budget" in str(p) for p in out.get("problems") or [])
    status = "stopped_budget" if stopped else out["status"]
    row = db.insert(store.AI_QUESTIONS, _clean({
        "Building_Id": int(building["id"]), "User_Id": int(c.ctx["user_id"]),
        "Question": ai_review.redact(question)[:MAX_QUESTION], "Answer": str(out.get("answer") or "")[:9500],
        "Citations": ai_review._fit_json(out.get("citations")) or "[]", "Model": (out.get("model") or "")[:40],
        "Escalated": bool(out.get("escalated")), "Unconfirmed": bool(out.get("unconfirmed")), "Status": status}))
    _save_usage(db, out.get("usage") or [], row["ROWID"])
    if stopped:
        cap_reached(db, building, now, *budget(db, building, now)[1:3])
    if out.get("batch_request"):
        try:
            batch = client.create_batch([dict(out["batch_request"], custom_id="q{}".format(row["ROWID"]))])
            db.update(store.AI_QUESTIONS, {"ROWID": row["ROWID"], "Batch_Id": str(batch.get("id") or "")[:100]})
        except ai_client.AiError:
            db.update(store.AI_QUESTIONS, {"ROWID": row["ROWID"], "Status": "unconfirmed"})
            row = dict(row, Status="unconfirmed")
    warn_if_near(db, building, now)
    return {"question": question_out(db, row), "status": row.get("Status"), "answer": row.get("Answer") or "",
            "citations": _json(row.get("Citations")) or [], "label": ai_review.GUIDANCE, "model": row.get("Model"),
            "escalated": bool(out.get("escalated")), "unconfirmed": bool(out.get("unconfirmed"))}


def _collect_question(db, building, row, client, now):
    batch = client.get_batch(row["Batch_Id"])
    if batch.get("processing_status") != "ended":
        return False
    answers, errors, usage = ai_review.read_batch(client.batch_results(batch), int(building["id"]), now, "escalation")
    _save_usage(db, [dict(u, User_Id=row.get("User_Id")) for u in usage], row["ROWID"])
    answer = answers.get("q{}".format(row["ROWID"]))
    change = {"ROWID": row["ROWID"], "Batch_Id": ""}
    if not answer:
        change.update(Status="unconfirmed", Unconfirmed=True)
    else:
        sources = ai_review.question_sources(question_docs(db, building), law_text())
        done = ai_review.finish_escalation(answer, sources)
        change.update(Status=done["status"], Answer=str(done["answer"])[:9500], Model=ai_client.SONNET,
                      Citations=ai_review._fit_json(done["citations"]) or "[]", Unconfirmed=bool(done["unconfirmed"]),
                      Escalated=True)
    db.update(store.AI_QUESTIONS, change)
    asker = db.get(store.USERS, row.get("User_Id")) or {}
    base = mailer.portal_link(building)
    html = mailer.page(building, "Your question has been checked", [
        "The AI helper has checked your question more carefully:", row.get("Question") or "",
        ai_review.GUIDANCE], "See the answer", link="{}#/ask".format(base) if base else None)
    mailer.send(db, asker.get("Email") or "", "{}: your by-law question".format(building["name"]), html,
                building=building)
    return True


def get_questions(c):
    gate(c, "see")
    db, building = c.db, c.building
    rows = sorted(db.find(store.AI_QUESTIONS, {"Building_Id": int(building["id"])}), key=lambda r: -int(r["ROWID"]))
    if any(r.get("Status") == "pending" and r.get("Batch_Id") for r in rows):
        try:
            collect(db, building, make_client(), c.now, only=("questions",))
            rows = sorted(db.find(store.AI_QUESTIONS, {"Building_Id": int(building["id"])}),
                          key=lambda r: -int(r["ROWID"]))
        except Exception:  # noqa: BLE001 — the log still shows; the answer comes later
            logger.exception("collect questions")
    return {"questions": [question_out(db, r) for r in rows[:100]], "guidance": ai_review.GUIDANCE}


# ---------------------------------------------------------------------------------------------- the daily job

def collect(db, building, client, now, only=("docs", "reviews", "questions")):
    """Collect every finished batch for one building. A retryable failure waits for the next run."""
    done = 0
    bid = int(building["id"])
    if "docs" in only:
        for row in db.find(store.DOC_VERSIONS, {"Building_Id": bid, "Status": "transcribing"}):
            if row.get("Batch_Id") and _guard(db, building, "transcription", lambda: _collect_doc(
                    db, building, row, client, now)):
                done += 1
    if "reviews" in only:
        for row in db.find(store.RULE_REVIEWS, {"Building_Id": bid}):
            if row.get("Status") in ("mapping", "proposing") and _guard(db, building, "review", lambda: advance_review(
                    db, building, row, client, now) is not row):
                done += 1
    if "questions" in only:
        for row in db.find(store.AI_QUESTIONS, {"Building_Id": bid, "Status": "pending"}):
            if row.get("Batch_Id") and _guard(db, building, "question", lambda: _collect_question(
                    db, building, row, client, now)):
                done += 1
    return done


def _guard(db, building, what, work):
    try:
        return work()
    except ai_client.AiError as exc:
        if not exc.retryable:
            failures.log(db, "ai", "Collecting an AI {} failed: {}".format(what, exc.message), building["id"])
        return False


def daily(db, now):
    """The daily job's AI part (from /cron/reminders). Never raises: trouble is a Failures row."""
    out = {"promoted": 0, "collected": 0, "applied": 0}
    client = None
    for building in (buildings.from_row(r) for r in db.find(store.BUILDINGS)):
        try:
            for row in db.find(store.RULE_REVIEWS, {"Building_Id": int(building["id"]), "Status": "voting"}):
                if settle_vote(db, building, row, now).get("Status") == "applied":
                    out["applied"] += 1
            out["promoted"] += promote(db, building, now)
            if not settings_of(building)["enabled"]:
                continue
            client = client or make_client()
            out["collected"] += collect(db, building, client, now)
            warn_if_near(db, building, now)
        except Exception as exc:  # noqa: BLE001 — one building's trouble never stops the others
            logger.exception("daily ai job")
            failures.log(db, "ai", "Daily AI job: {}: {}".format(type(exc).__name__, failures.scrub(exc)),
                         building["id"])
    return out
