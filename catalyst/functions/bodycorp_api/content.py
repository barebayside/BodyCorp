"""
Notices and documents for a building.

    read   ->  any approved member; tenants see audience "all" only, never "owners"
    write  ->  committee, manager or admin

A new notice is emailed to everyone in its audience, in blind-copy batches.
Documents are photos or PDFs up to 5 MB, kept in Stratus under docs/<building>/.
"""

import secrets

import mailer
import people
import store
import uploads
from errors import bad, forbidden, not_found

AUDIENCES = ("all", "owners")
MAX_BODY = 5000


def _reader(ctx):
    if not people.is_member(ctx):
        raise forbidden("You'll see this once your unit is approved.")


def _writer(ctx):
    if not ctx["can"]["handle"]:
        raise forbidden("Only the committee or building manager can do that.")


def _may_see(ctx, row):
    return row.get("Audience") == "all" or (row.get("Audience") == "owners" and ctx["can"]["owner"])


def _audience(value):
    value = str(value or "all").strip().lower()
    if value not in AUDIENCES:
        raise bad("Audience must be all or owners.")
    return value


def _title(value):
    title = str(value or "").strip()
    if not title:
        raise bad("Give it a title.")
    if len(title) > 255:
        raise bad("That title is too long.")
    return title


def _newest_first(rows):
    return sorted(rows, key=lambda r: -int(r["ROWID"]))


# ---------- notices ----------

def notice_out(row):
    return {"id": str(row["ROWID"]), "title": row.get("Title"), "body": row.get("Body") or "",
            "audience": row.get("Audience"), "created": row.get("CREATEDTIME") or ""}


def notices(db, building, ctx):
    _reader(ctx)
    rows = db.find(store.NOTICES, {"Building_Id": int(building["id"])})
    return [notice_out(r) for r in _newest_first(rows) if _may_see(ctx, r)]


def audience_emails(db, building, audience):
    """Approved members (owners only, for "owners") plus the building's handlers."""
    rows = db.find(store.MEMBERSHIPS, {"Building_Id": int(building["id"]), "Status": "approved"})
    ids = {str(m.get("User_Id")) for m in rows if audience == "all" or m.get("Relation") == "owner"}
    emails = {(db.get(store.USERS, i) or {}).get("Email") for i in sorted(ids)}
    emails |= set(people.emails_with_roles(db, building, ("committee", "manager", "admin")))
    return sorted(e for e in emails if e)


def post_notice(db, building, ctx, title, body, audience):
    _writer(ctx)
    title, audience, body = _title(title), _audience(audience), str(body or "").strip()
    if len(body) > MAX_BODY:
        raise bad("That notice is too long.")
    db.insert(store.NOTICES, {"Building_Id": int(building["id"]), "User_Id": int(ctx["user_id"]),
                              "Title": title, "Body": body, "Audience": audience})
    html = mailer.page(building, title, [body], "Open the portal")
    mailer.send_many(db, audience_emails(db, building, audience), "{}: {}".format(building["name"], title), html)
    return notices(db, building, ctx)


def _row_in(db, table, building, rowid, what):
    row = db.get(table, rowid)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That {} wasn't found.".format(what))
    return row


def delete_notice(db, building, ctx, notice_id):
    _writer(ctx)
    db.delete(store.NOTICES, _row_in(db, store.NOTICES, building, notice_id, "notice")["ROWID"])
    return notices(db, building, ctx)


# ---------- documents ----------

def doc_out(row):
    return {"id": str(row["ROWID"]), "title": row.get("Title"), "category": row.get("Category") or "",
            "audience": row.get("Audience"), "name": row.get("File_Name") or "", "created": row.get("CREATEDTIME") or ""}


def docs(db, building, ctx):
    _reader(ctx)
    rows = db.find(store.DOCS, {"Building_Id": int(building["id"])})
    return [doc_out(r) for r in _newest_first(rows) if _may_see(ctx, r)]


def add_doc(db, building, ctx, title, category, audience, name, data):
    _writer(ctx)
    title, audience = _title(title), _audience(audience)
    category = str(category or "").strip()
    if len(category) > 50:
        raise bad("That category is too long.")
    raw, kind, safe = uploads.decode({"name": name, "data": data})
    key = "docs/{}/{}-{}".format(building["id"], secrets.token_hex(6), safe)
    db.put_file(key, raw, kind)
    db.insert(store.DOCS, {"Building_Id": int(building["id"]), "User_Id": int(ctx["user_id"]), "Title": title,
                           "Category": category, "Audience": audience, "File_Key": key, "File_Name": safe})
    return docs(db, building, ctx)


def delete_doc(db, building, ctx, doc_id):
    _writer(ctx)
    row = _row_in(db, store.DOCS, building, doc_id, "document")
    db.delete(store.DOCS, row["ROWID"])
    db.delete_file(row.get("File_Key"))
    return docs(db, building, ctx)


def doc_file(db, building, ctx, doc_id):
    """(bytes, type, name). A tenant asking for an owners' document gets 404, as if it didn't exist."""
    _reader(ctx)
    row = _row_in(db, store.DOCS, building, doc_id, "document")
    if not _may_see(ctx, row):
        raise not_found("That document wasn't found.")
    data = db.get_file(row.get("File_Key"))
    if data is None:
        raise not_found("That document wasn't found.")
    return data, uploads.sniff(data) or "application/octet-stream", row.get("File_Name") or "document"
