"""
Failures: anything that went wrong out of sight, kept until a person says it's dealt with.

The portal is run by people who never read logs, so a failed email or a crash
must land somewhere a human is told about: a Failures row. The daily self-check
(health.py) emails a digest of the unresolved ones, and building admins see
their own building's in the portal (GET /failures) and mark them resolved.

KINDS
    mail                an email couldn't be sent now (queued for retry, or not, see Detail)
    mail_too_long       an email bigger than a queued copy can hold (Html is text(10000))
    mail_gave_up        a queued email still failed after 5 tries
    error               an unexpected crash in a request (route + error type only)
    push                a phone notification couldn't be delivered (host + status only)
    ai                  the AI helper couldn't start or collect something (a batch, a comparison)
    ai_cap              a building's monthly AI budget was reached: nothing was sent (once a month)
    heartbeat_*         not a failure: a "this job ran" stamp, written already resolved

`log` never raises. A failure while recording a failure is written to the
function log and dropped, so it can never turn a working answer into a crash.

NO PERSONAL DATA
    Detail never holds an email address, a request body or a sign-in code. An
    error's message is scrubbed of addresses and quoted values and cut short,
    because database errors like to quote the row they choked on.

PRODUCT ADMIN
    Whoever holds `admin` in any building AND signs in with SUPPORT_EMAIL. They
    see every building's failures and the product-wide ones (Building_Id empty).
"""

import logging
import os
import re

import buildings
import store
from errors import not_found

logger = logging.getLogger("bodycorp_api.failures")

HEARTBEAT_REMINDERS = "heartbeat_reminders"
HEARTBEAT_CHECK = "heartbeat_check"
DETAIL_MAX = 2000
LIST_MAX = 200

_EMAIL = re.compile(r"[^\s@'\"<>]+@[^\s@'\"<>]+")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _yes(value):
    return value in (True, "true", 1, "1")


def log(db, kind, detail, building_id=None):
    """Record one failure. Returns the row, or None if even that failed. Never raises."""
    try:
        row = {"Kind": str(kind)[:40], "Detail": str(detail or "")[:DETAIL_MAX], "Resolved": False}
        number = store.as_id(building_id)
        if number:
            row["Building_Id"] = number
        return db.insert(store.FAILURES, row)
    except Exception:  # noqa: BLE001 — see the module note
        logger.exception("could not record a %s failure", kind)
        return None


def scrub(message, limit=200):
    """An error message with addresses and quoted values taken out, cut to `limit`."""
    text = _QUOTED.sub("'…'", _EMAIL.sub("<email>", str(message or "")))
    return " ".join(text.split())[:limit]


def log_error(db, method, path, slug, exc):
    """A crash in a request, as route + error type + a scrubbed short message. Never raises."""
    try:
        building = None
        try:
            building = buildings.find(db, slug) if db is not None and slug else None
        except Exception:  # noqa: BLE001 — the database may be what broke
            building = None
        detail = "{} {}: {}: {}".format(str(method).upper(), path, type(exc).__name__, scrub(exc))
        if db is not None:
            log(db, "error", detail, building["id"] if building else None)
    except Exception:  # noqa: BLE001
        logger.exception("could not record an error")


# ---------- heartbeats ----------

def heartbeat(db, kind, detail=""):
    """
    Stamp "this job ran now": a new resolved row, and the older stamps of the same
    kind deleted so the table doesn't grow by one a day. Never raises.
    """
    try:
        made = db.insert(store.FAILURES, {"Kind": kind, "Detail": str(detail)[:DETAIL_MAX], "Resolved": True})
        for row in db.find(store.FAILURES, {"Kind": kind}):
            if str(row["ROWID"]) != str(made["ROWID"]):
                db.delete(store.FAILURES, row["ROWID"])
    except Exception:  # noqa: BLE001
        logger.exception("could not stamp %s", kind)


def last_run(db, kind):
    """When a heartbeat of `kind` was last stamped (naive UTC), or None if never."""
    times = [store.created_utc(r) for r in db.find(store.FAILURES, {"Kind": kind})]
    times = [t for t in times if t]
    return max(times) if times else None


# ---------- reading and resolving ----------

def unresolved(db, building=None):
    """Open failures, newest first: one building's, or every one (with product-wide) when building is None."""
    where = {"Resolved": False}
    if building:
        where["Building_Id"] = int(building["id"])
    rows = [r for r in db.find(store.FAILURES, where) if not str(r.get("Kind") or "").startswith("heartbeat_")]
    return sorted(rows, key=lambda r: -int(r["ROWID"]))


def is_product_admin(db, user):
    support = os.environ.get("SUPPORT_EMAIL", "").strip().lower()
    if not support or str(user.get("email") or "").lower() != support:
        return False
    return any(r.get("Role") == "admin" for r in db.find(store.ROLES, {"User_Id": int(user["id"])}))


def _slugs(db):
    return {str(r["ROWID"]): (r.get("Slug") or "", r.get("Name") or "") for r in db.find(store.BUILDINGS)}


def out(row, slugs):
    slug, name = slugs.get(str(row.get("Building_Id") or ""), (None, None))
    return {"id": str(row["ROWID"]), "kind": row.get("Kind"), "detail": row.get("Detail") or "",
            "building": slug, "building_name": name, "at": store.created_iso(row),
            "resolved": _yes(row.get("Resolved"))}


def listing(db, building, product_admin):
    """GET /failures: one building's open failures, or everyone's when building is None."""
    rows = unresolved(db, building)
    slugs = _slugs(db)
    return {"failures": [out(r, slugs) for r in rows[:LIST_MAX]], "total": len(rows),
            "product_admin": bool(product_admin)}


def resolve(db, user, building, failure_id):
    """
    Mark one failure dealt with. `building` None means the product admin, who may
    resolve any. Anything else outside the caller's reach is 404, like a missing id.
    """
    row = db.get(store.FAILURES, failure_id)
    if not row or str(row.get("Kind") or "").startswith("heartbeat_"):
        raise not_found("That wasn't found.")
    if building is not None and str(row.get("Building_Id") or "") != building["id"]:
        raise not_found("That wasn't found.")
    change = {"ROWID": row["ROWID"], "Resolved": True, "Resolved_By": int(user["id"])}
    db.update(store.FAILURES, change)
    return out(dict(row, **change), _slugs(db))
