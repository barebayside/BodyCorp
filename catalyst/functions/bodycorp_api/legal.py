"""
Stage 04 of the rules loop: ONE legal pack per change, so the lawyer is billed once.

    send      the change's draft rules (their wording) + every approved product draft (each form drawn as residents
              will see it, with example answers, and the emails filled in) + the question "must owners be told of
              this by law?" (UNCONFIRMED)  ->  a frozen snapshot (Stratus JSON), a PDF of it, Pack_Items rows, and
              an email to the lawyer with the PDF attached and a private link.
    the link  lawyer.html?t=<token>: no sign-in. The token is 32 random bytes; only its SHA-256 is stored. It opens
              THAT pack only, until Expires_At (default 30 days); a wrong, expired or superseded token is a 404,
              exactly like a pack that doesn't exist. The lawyer ticks (ok) or queries each item with a comment,
              then signs (name; the date is recorded), or sends comments back.
    by email  the lawyer may reply by email instead: whoever runs the change records "signed off by email" with
              the name, the date and the reply attached (PDF or photo).
    queried   the change goes back to stage 02 or 03 (rules.post_reopen) and a new pack (Pack_No + 1) follows.

The lawyer's verdict lives only here (Legal_Packs, Pack_Items). The snapshot is a deliberate copy: what the lawyer
was shown, which must not change when the drafts do.
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta

import ai
import ai_review
import buildings
import mailer
import pdfgen
import rules
import stages
import store
import uploads
from errors import bad, not_found

STATUS_LABELS = {"sent": "With the lawyer", "queried": "The lawyer asked for changes", "signed": "Signed off",
                 "superseded": "Replaced by a newer pack"}
KIND_LABELS = {"rule": "Rule", "product": "Form or step", "question": "Question"}
TICKS = ("ok", "query")
MAX_COMMENT = 2000
DEFAULT_DAYS = rules.PACK_DAYS
NOTIFY_QUESTION = ("Must owners or occupiers be told of this change by law, and if so how and by when? The portal "
                   "plans to tell the people listed below. UNCONFIRMED: we could not find a rule that says. Tick if the "
                   "plan is enough; query it and say what the law requires if not.")


def _hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _stamp(now):
    return store.fmt_dt(now)


def _key(change_row, name):
    return "rules/{}/changes/{}/{}".format(rules._key_part(rules.bid(change_row)), change_row["ROWID"], name)


def lawyer_link(token):
    base = os.environ.get("PORTAL_URL", "").strip()
    if not base:
        return ""
    folder = base.rsplit("/", 1)[0] if base.endswith(".html") else base.rstrip("/")
    return "{}/lawyer.html?t={}".format(folder, token)


# ---------------------------------------------------------------------------------------------- the snapshot

EXAMPLES = {"text": "Example answer", "textarea": "An example of what a resident might write here.",
            "date": "1 Dec 2026", "checkbox": "Ticked", "file": "photo.jpg (attached)"}


def _form_lines(fields):
    out = []
    for f in fields or []:
        kind = f.get("type") or "text"
        example = (f.get("options") or ["(a choice)"])[0] if kind == "select" else EXAMPLES.get(kind, "Example")
        if isinstance(example, dict):
            example = example.get("label") or example.get("value")
        out.append({"label": f.get("label") or f.get("key"), "type": kind, "required": bool(f.get("required")),
                    "options": [o.get("label") if isinstance(o, dict) else o for o in f.get("options") or []],
                    "help": f.get("help") or "", "example": str(example)})
    return out


def snapshot(db, change_row, building, now):
    """Everything the lawyer is shown, frozen."""
    items = []
    for r in rules._drafts(db, change_row):
        out = rules.rule_out(db, r, now, building=building)
        items.append({"kind": "rule", "ref_id": str(r["ROWID"]),
                      "title": ("Stop applying: " if out["retire"] else "") + out["title"],
                      "rule": {k: out[k] for k in ("key", "version", "layer_label", "trigger", "action", "who",
                                                    "deadline_text", "if_missed", "citations", "retire")}})
    for p in rules._proposals(db, change_row):
        if p.get("Status") not in ("approved", "edited"):
            continue
        b = building if str(p.get("Building_Id")) == building["id"] else buildings.from_row(
            db.get(store.BUILDINGS, p.get("Building_Id")) or {"ROWID": p.get("Building_Id")})
        defs = rules._topics_of(db, b)
        out = ai.proposal_out(db, b, p, defs)
        items.append({"kind": "product", "ref_id": str(p["ROWID"]), "title": out["title"],
                      "product": {"building": b.get("name") or "", "topic": out["topic_label"], "kind": out["kind"],
                                  "why": out["why"], "changes": out["changes"], "if_missed": out["if_missed"],
                                  "before_form": _form_lines(out["before_form"]) if out["before_form"] is not None else None,
                                  "after_form": _form_lines(out["after_form"]) if out["after_form"] is not None else None,
                                  "emails": [e for s in out["previews"] for e in s["emails"]],
                                  "steps": [{"stage": s["stage"], "instructions": s["instructions"]}
                                            for s in out["previews"]]}})
    plan = rules.notify_proposal(db, change_row, building)
    items.append({"kind": "question", "ref_id": "notify_required", "title": "Telling owners and occupiers",
                  "question": {"text": NOTIFY_QUESTION,
                               "plan": ["{}: {}".format(g["label"], g["why"]) for g in plan["groups"]]}})
    start = store.parse_dt(change_row.get("Effective_From"))
    return {"building": "Queensland (every building)" if rules.bid(change_row) == rules.LAW else building["name"],
            "change": {"id": str(change_row["ROWID"]), "title": change_row.get("Title"),
                       "summary": change_row.get("Summary") or "",
                       "entry": rules.ENTRY_LABELS.get(change_row.get("Entry_Point"), ""),
                       "source": rules.SOURCE_LABELS.get(change_row.get("Source_Kind"), ""),
                       "lawyer_why": change_row.get("Lawyer_Why") or "",
                       "starts": stages.long_date(start) if start else "the date the committee applies it"},
            "items": [dict(i, no=n) for n, i in enumerate(items, 1)]}


def pdf_bytes(snap, pack_no, link=""):
    doc = pdfgen.Pdf("Legal pack {} - {}".format(pack_no, snap["building"]))
    doc.text("LEGAL PACK {} FOR CHECKING".format(pack_no), size=9, bold=True, grey=True)
    doc.heading(snap["building"], 18)
    doc.text(snap["change"]["title"], size=13, bold=True)
    if snap["change"]["summary"]:
        doc.text(snap["change"]["summary"])
    doc.text("Where it comes from: {} ({}).".format(snap["change"]["source"], snap["change"]["entry"].lower()))
    doc.text("Starts: {}. Requests already lodged keep the rules they were lodged under.".format(
        snap["change"]["starts"]))
    if link:
        doc.text("Tick or query each item online: " + link, grey=True)
    doc.text("This pack shows what the portal will do. Please tick each item, or query it with a comment, and sign "
             "below. Guidance prepared by the portal; your sign-off is the legal check.", grey=True)
    for item in snap["items"]:
        doc.line()
        doc.text("{}. {} - {}".format(item["no"], rules_label(item["kind"]), item["title"]), size=12, bold=True)
        if item["kind"] == "rule":
            r = item["rule"]
            doc.text("{} rule {} (version {})".format(r["layer_label"], r["key"], r["version"]), grey=True)
            for label, value in (("When", r["trigger"]), ("What must happen", r["action"]), ("Who", r["who"]),
                                 ("Deadline", r["deadline_text"] or "None stated"),
                                 ("If it is missed", r["if_missed"] or "The source doesn't say")):
                doc.text("{}: {}".format(label, value), indent=10)
            for cite in r["citations"]:
                doc.text("Source: {} - \"{}\"".format(cite.get("clause"), cite.get("quote")), size=9, indent=10,
                         grey=True)
        elif item["kind"] == "product":
            p = item["product"]
            doc.text("{}{}".format(p["topic"], " ({})".format(p["building"]) if p["building"] else ""), grey=True)
            if p["why"]:
                doc.text(p["why"], indent=10)
            if p["if_missed"]:
                doc.text("If nobody decides in time - now: {}  Proposed: {}".format(
                    p["if_missed"].get("before") or "-", p["if_missed"]["after"]), indent=10, bold=True)
            for ch in p["changes"]:
                doc.text("{}: {} -> {}".format(ch["where"], ch["old"], ch["new"]), indent=10)
            if p["after_form"] is not None:
                doc.text("The form as residents will see it (with example answers):", bold=True, indent=10)
                for n, f in enumerate(p["after_form"], 1):
                    req = "" if f["required"] else " (optional)"
                    if f["type"] == "checkbox":
                        doc.text("{}. [x] {}{}".format(n, f["label"], req), indent=20)
                    else:
                        choices = " Choices: " + ", ".join(str(o) for o in f["options"]) + "." if f["options"] else ""
                        doc.text("{}. {}{}{}  Example: {}".format(n, f["label"], req, choices, f["example"]), indent=20)
            for step in p["steps"]:
                if step["instructions"]:
                    doc.text("Step \"{}\": {}".format(step["stage"], step["instructions"]), indent=10)
            for email in p["emails"]:
                doc.text("Email to {}: {}".format(email["to"], email["subject"]), indent=10, bold=True)
                doc.text(email["body"], indent=20, size=9)
        else:
            q = item["question"]
            doc.text(q["text"], indent=10)
            for line in q["plan"]:
                doc.text("- " + line, indent=20, size=9)
        doc.text("[  ] OK      [  ] Query:  ______________________________________________", indent=10, grey=True)
    doc.line()
    doc.text("Sign-off", size=12, bold=True)
    doc.text("I have checked the items above. Name: ______________________   Date: ____________", indent=10)
    return doc.bytes()


def rules_label(kind):
    return KIND_LABELS.get(kind, kind)


# ---------------------------------------------------------------------------------------------- committee side

def _pack_row(db, building, pack_id):
    pack = db.get(store.LEGAL_PACKS, pack_id)
    if not pack:
        raise not_found("That pack wasn't found.")
    rules._change_row(db, building, pack.get("Change_Id"))          # 404 for another building's pack
    return pack


def _pack_items(db, pack):
    return sorted(db.find(store.PACK_ITEMS, {"Pack_Id": int(pack["ROWID"])}), key=lambda i: int(i.get("Item_No") or 0))


def pack_out(db, pack, now):
    items = _pack_items(db, pack)
    expires = store.parse_dt(pack.get("Expires_At"))
    sent, signed = store.parse_dt(pack.get("Sent_At")), store.parse_dt(pack.get("Signed_At"))
    return {"id": str(pack["ROWID"]), "no": int(pack.get("Pack_No") or 0), "status": pack.get("Status"),
            "status_label": STATUS_LABELS.get(pack.get("Status"), ""), "lawyer_name": pack.get("Lawyer_Name") or "",
            "lawyer_email": pack.get("Lawyer_Email") or "", "sent_text": stages.long_date(sent) if sent else "",
            "expires_text": stages.long_date(expires) if expires else "", "expired": bool(expires and expires < now),
            "signed_name": pack.get("Signed_Name") or "", "signed_text": stages.long_date(signed) if signed else "",
            "signed_via": pack.get("Signed_Via") or "", "has_reply": bool(pack.get("Reply_Key")),
            "note": pack.get("Note") or "",
            "items": [{"id": str(i["ROWID"]), "no": int(i.get("Item_No") or 0), "kind": i.get("Item_Kind"),
                       "kind_label": KIND_LABELS.get(i.get("Item_Kind"), ""), "title": i.get("Title"),
                       "tick": i.get("Tick") or "", "comment": i.get("Comment") or ""} for i in items],
            "counts": {"ok": len([i for i in items if i.get("Tick") == "ok"]),
                       "query": len([i for i in items if i.get("Tick") == "query"]),
                       "open": len([i for i in items if not i.get("Tick")])}}


def _new_token(db, pack, now, days):
    token = secrets.token_urlsafe(32)
    db.update(store.LEGAL_PACKS, {"ROWID": pack["ROWID"], "Token_Hash": _hash(token),
                                  "Expires_At": _stamp(now + timedelta(days=days))})
    return token


def _lawyer_email(db, building, change_row, pack, pdf, link, resend=False):
    lines = ["Please check the attached legal pack for {}: {}.".format(
        "Queensland buildings" if rules.bid(change_row) == rules.LAW else building["name"], change_row.get("Title")),
        "It shows each rule in plain words and each form exactly as residents will see it. Tick each item, or "
        "query it with a comment, then sign off, using the link below (no sign-in needed). The link works until "
        "{}.".format(stages.long_date(store.parse_dt(pack.get("Expires_At")) or datetime(2000, 1, 1))),
        "If you'd rather reply to this email, the committee will record your sign-off."]
    if resend:
        lines.insert(0, "A new link to the same pack (the old link no longer works).")
    html = mailer.page(building, "Legal pack {} to check".format(pack.get("Pack_No")), lines, "Open the pack", link=link)
    return mailer.send(db, pack.get("Lawyer_Email"), "{}: legal pack {} to check".format(
        building["name"], pack.get("Pack_No")), html, building=building,
        attachments=[("legal-pack-{}-{}.pdf".format(change_row["ROWID"], pack.get("Pack_No")), pdf)] if pdf else None)


def post_send(c):
    row = rules._open_row(c, "legal")
    rules.require_run(c, row)
    db, building, now = c.db, c.building, c.now
    name = rules._text(c.get("lawyer_name"), "the lawyer's name", 255)
    email = str(c.get("lawyer_email") or "").strip().lower()
    if "@" not in email or len(email) > 255 or " " in email:
        raise bad("Give the lawyer's email address.")
    try:
        days = int(c.get("days") or DEFAULT_DAYS)
    except (TypeError, ValueError):
        raise bad("The link lasts a whole number of days.")
    if not 1 <= days <= 90:
        raise bad("The link can last between 1 and 90 days.")
    packs = rules._packs(db, row)
    if packs and packs[-1].get("Status") == "signed":
        raise bad("The lawyer has already signed this change off.")
    for old in packs:
        if old.get("Status") in ("sent", "queried"):
            db.update(store.LEGAL_PACKS, {"ROWID": old["ROWID"], "Status": "superseded"})
    snap = snapshot(db, row, building, now)
    number = max([int(p.get("Pack_No") or 0) for p in packs] or [0]) + 1
    pack = db.insert(store.LEGAL_PACKS, {"Building_Id": rules.bid(row), "Change_Id": int(row["ROWID"]),
                                         "Pack_No": number, "Status": "sent", "Lawyer_Name": name,
                                         "Lawyer_Email": email, "Sent_At": _stamp(now),
                                         "Sent_By": int(c.ctx["user_id"])})
    token = _new_token(db, pack, now, days)
    pack = db.get(store.LEGAL_PACKS, pack["ROWID"])
    link = lawyer_link(token)
    snap["link"] = link
    for item in snap["items"]:
        made = db.insert(store.PACK_ITEMS, {"Building_Id": rules.bid(row), "Pack_Id": int(pack["ROWID"]),
                                            "Item_No": item["no"], "Item_Kind": item["kind"],
                                            "Ref_Id": str(item["ref_id"])[:60], "Title": str(item["title"])[:255]})
        item["item_id"] = str(made["ROWID"])
    pdf = pdf_bytes(snap, number, link)
    snap_key, pdf_key = _key(row, "pack-{}.json".format(number)), _key(row, "pack-{}.pdf".format(number))
    db.put_file(snap_key, json.dumps(snap).encode("utf-8"), "application/json")
    db.put_file(pdf_key, pdf, "application/pdf")
    db.update(store.LEGAL_PACKS, {"ROWID": pack["ROWID"], "Snapshot_Key": snap_key, "Pdf_Key": pdf_key})
    pack = dict(pack, Snapshot_Key=snap_key, Pdf_Key=pdf_key)
    emailed = _lawyer_email(db, building, row, pack, pdf, link)
    out = rules.change_detail(c, row)
    out.update(pack=pack_out(db, pack, now), token=token, link=link, emailed=emailed)
    return out


def post_relink(c):
    """A new link for the same pack (the old one stops working), emailed again with the PDF."""
    pack = _pack_row(c.db, c.building, c.get("pack_id"))
    row = rules._change_row(c.db, c.building, pack.get("Change_Id"))
    rules.require_run(c, row)
    if pack.get("Status") not in ("sent", "queried"):
        raise bad("Only a pack still with the lawyer can get a new link.")
    token = _new_token(c.db, pack, c.now, DEFAULT_DAYS)
    pack = c.db.get(store.LEGAL_PACKS, pack["ROWID"])
    link = lawyer_link(token)
    _lawyer_email(c.db, c.building, row, pack, c.db.get_file(pack.get("Pdf_Key")), link, resend=True)
    return {"pack": pack_out(c.db, pack, c.now), "token": token, "link": link}


def pack_pdf(c):
    rules.require_see(c)
    pack = _pack_row(c.db, c.building, c.get("pack_id"))
    data = c.db.get_file(pack.get("Pdf_Key"))
    if data is None:
        raise not_found("That PDF wasn't found.")
    return data, "application/pdf", "legal-pack-{}-{}.pdf".format(pack.get("Change_Id"), pack.get("Pack_No"))


def reply_file(c):
    rules.require_see(c)
    pack = _pack_row(c.db, c.building, c.get("pack_id"))
    data = c.db.get_file(pack.get("Reply_Key"))
    if data is None:
        raise not_found("No reply is attached.")
    return data, uploads.sniff(data) or "application/octet-stream", "lawyer-reply-{}".format(pack.get("Pack_No"))


def _signed(db, building, row, pack, now, who):
    """The change's legal check, and a note to whoever runs it."""
    checks = rules._checks(row)
    if "legal" not in checks and row.get("Stage") == "legal":
        rules._record(db, row, "legal", who or "", now, "Signed by {} ({})".format(
            pack.get("Signed_Name"), "by email" if pack.get("Signed_Via") == "email" else "online"),
            {"pack": str(pack["ROWID"])})
    _tell_runners(db, building, row, "The lawyer signed off", [
        "{} signed off legal pack {} for \"{}\".".format(pack.get("Signed_Name"), pack.get("Pack_No"), row.get("Title")),
        "Next: the committee's sign-off."])


def _tell_runners(db, building, row, heading, lines):
    if building is None:
        return
    import committee
    ids = committee.holders(db, building, committee.resolve(building, "rules"))
    emails = committee.emails_of(db, ids)
    if rules.bid(row) == rules.LAW:
        support = os.environ.get("SUPPORT_EMAIL", "").strip()
        emails = [support] if support else []
    base = mailer.portal_link(building)
    html = mailer.page(building, heading, lines, "Open the change",
                       link="{}#/rules/change/{}".format(base, row["ROWID"]) if base else None)
    mailer.send_many(db, emails, "{}: {}".format(building["name"], heading.lower()), html, building=building)


def post_email_signoff(c):
    pack = _pack_row(c.db, c.building, c.get("pack_id"))
    row = rules._change_row(c.db, c.building, pack.get("Change_Id"))
    rules.require_run(c, row)
    if pack.get("Status") not in ("sent", "queried"):
        raise bad("Only a pack still with the lawyer can be signed off.")
    latest = rules._packs(c.db, row)[-1]
    if str(latest["ROWID"]) != str(pack["ROWID"]):
        raise bad("A newer pack was sent; record the sign-off on that one.")
    name = rules._text(c.get("name"), "the lawyer's name", 255)
    day = str(c.get("date") or "").strip()
    try:
        when = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise bad("Give the date of the lawyer's email, like 2026-11-12.")
    if c.get("file") in (None, "", {}):
        raise bad("Attach the lawyer's reply (a PDF of the email, or a photo of it).")
    data, kind, safe = uploads.decode(c.get("file"))
    key = _key(row, "pack-{}-reply-{}".format(pack.get("Pack_No"), safe))
    c.db.put_file(key, data, kind)
    change = {"ROWID": pack["ROWID"], "Status": "signed", "Signed_Name": name,
              "Signed_At": store.fmt_dt(when - timedelta(hours=10)), "Signed_Via": "email", "Reply_Key": key,
              "Recorded_By": int(c.ctx["user_id"]), "Note": str(c.get("note") or "")[:2000]}
    c.db.update(store.LEGAL_PACKS, change)
    _signed(c.db, c.building, row, dict(pack, **change), c.now, c.ctx["user_id"])
    return rules.change_detail(c, c.db.get(store.CHANGES, row["ROWID"]))


# ---------------------------------------------------------------------------------------------- the lawyer's link

def find_pack(db, token, now):
    """The pack this token opens, or 404. Wrong, superseded and expired all look the same."""
    token = str(token or "").strip()
    if len(token) < 20:
        raise not_found("That link isn't valid.")
    found = db.find(store.LEGAL_PACKS, {"Token_Hash": _hash(token)})
    if not found:
        raise not_found("That link isn't valid.")
    pack = found[0]
    expires = store.parse_dt(pack.get("Expires_At"))
    if pack.get("Status") == "superseded" or not expires or expires < now:
        raise not_found("That link isn't valid.")
    return pack


def _building_of(db, change_row):
    if rules.bid(change_row) == rules.LAW:
        return None
    row = db.get(store.BUILDINGS, change_row.get("Building_Id"))
    return buildings.from_row(row) if row else None


def public_pack(c):
    pack = find_pack(c.db, c.get("t"), c.now)
    snap = json.loads((c.db.get_file(pack.get("Snapshot_Key")) or b"{}").decode("utf-8"))
    items = {str(i["ROWID"]): i for i in _pack_items(c.db, pack)}
    by_no = {int(i.get("Item_No") or 0): i for i in items.values()}
    for item in snap.get("items") or []:
        row = by_no.get(int(item.get("no") or 0)) or {}
        item.update(item_id=str(row.get("ROWID") or ""), tick=row.get("Tick") or "", comment=row.get("Comment") or "")
    out = pack_out(c.db, pack, c.now)
    building = _building_of(c.db, c.db.get(store.CHANGES, pack.get("Change_Id")) or {})
    brand = (building or {}).get("brand") or {}
    return {"pack": {k: out[k] for k in ("no", "status", "status_label", "lawyer_name", "expires_text", "signed_name",
                                          "signed_text", "signed_via", "counts", "note")},
            "building": snap.get("building"), "change": snap.get("change"), "items": snap.get("items") or [],
            "brand": {"primary": brand.get("primary") or "", "accent": brand.get("accent") or ""},
            "can_edit": pack.get("Status") in ("sent", "queried"), "guidance": ai_review.GUIDANCE}


def public_pdf(c):
    pack = find_pack(c.db, c.get("t"), c.now)
    data = c.db.get_file(pack.get("Pdf_Key"))
    if data is None:
        raise not_found("That PDF wasn't found.")
    return data, "application/pdf", "legal-pack-{}.pdf".format(pack.get("Pack_No"))


def _editable(pack):
    if pack.get("Status") not in ("sent", "queried"):
        raise bad("This pack is signed off and can't be changed.")


def public_item(c):
    pack = find_pack(c.db, c.get("t"), c.now)
    _editable(pack)
    item = c.db.get(store.PACK_ITEMS, c.get("item_id"))
    if not item or str(item.get("Pack_Id")) != str(pack["ROWID"]):
        raise not_found("That item wasn't found.")
    tick = c.get("tick") or ""
    if tick not in TICKS + ("",):
        raise bad("Tick it, or query it.")
    comment = str(c.get("comment") or "").strip()
    if len(comment) > MAX_COMMENT:
        raise bad("Keep the comment under 2,000 characters.")
    if tick == "query" and not comment:
        raise bad("Say what needs to change.")
    c.db.update(store.PACK_ITEMS, {"ROWID": item["ROWID"], "Tick": tick, "Comment": comment,
                                   "Ticked_At": _stamp(c.now)})
    return public_pack(c)


def public_sign(c):
    pack = find_pack(c.db, c.get("t"), c.now)
    _editable(pack)
    items = _pack_items(c.db, pack)
    open_items = [i for i in items if not i.get("Tick")]
    queried = [i for i in items if i.get("Tick") == "query"]
    if queried:
        raise bad("You've queried {} item(s). Send your comments instead; the committee will send a revised pack."
                  .format(len(queried)))
    if open_items:
        raise bad("Tick or query every item first ({} left).".format(len(open_items)))
    name = rules._text(c.get("name"), "your name", 255)
    change = {"ROWID": pack["ROWID"], "Status": "signed", "Signed_Name": name, "Signed_At": _stamp(c.now),
              "Signed_Via": "link", "Note": str(c.get("note") or "")[:2000]}
    c.db.update(store.LEGAL_PACKS, change)
    row = c.db.get(store.CHANGES, pack.get("Change_Id"))
    building = _building_of(c.db, row) or _first_building(c.db)
    _signed(c.db, building, row, dict(pack, **change), c.now, "")
    return public_pack(c)


def _first_building(db):
    rows = db.find(store.BUILDINGS)
    return buildings.from_row(rows[0]) if rows else None


def public_comments(c):
    pack = find_pack(c.db, c.get("t"), c.now)
    _editable(pack)
    note = str(c.get("note") or "").strip()[:2000]
    items = _pack_items(c.db, pack)
    if not note and not any(i.get("Tick") == "query" for i in items):
        raise bad("Query at least one item, or write a note.")
    c.db.update(store.LEGAL_PACKS, {"ROWID": pack["ROWID"], "Status": "queried", "Note": note})
    row = c.db.get(store.CHANGES, pack.get("Change_Id"))
    building = _building_of(c.db, row) or _first_building(c.db)
    lines = ["{} has comments on legal pack {} for \"{}\".".format(pack.get("Lawyer_Name") or "The lawyer",
                                                                   pack.get("Pack_No"), row.get("Title"))]
    lines += ["Item {}: {}".format(i.get("Item_No"), i.get("Comment")) for i in items if i.get("Tick") == "query"]
    if note:
        lines.append("Note: " + note)
    lines.append("Open the change, go back to the rules or the products, fix them, and send a new pack.")
    _tell_runners(c.db, building, row, "The lawyer asked for changes", lines)
    return public_pack(c)

