"""
Setting up buildings: the one-off bootstrap and the admin's own settings.

BOOTSTRAP
    POST /admin/bootstrap with header X-Admin-Key = ADMIN_KEY and {seed, admin_email}.
    It loads seed_<seed>.json: the building, its units and its topics, and makes
    admin_email the building's admin. Safe to run twice: it only adds what's missing
    and never overwrites a topic the admin has since edited.

ENVIRONMENT
    ADMIN_KEY   the bootstrap key; unset means bootstrap is refused
"""

import hmac
import json
import os
import re

import auth
import buildings
import stages
import store
import topics
from errors import ApiError, bad, forbidden

HERE = os.path.dirname(os.path.abspath(__file__))
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_UNITS = 500


def key_ok(given, env_name):
    """A header key against an env var, in constant time. An unset env var refuses everything."""
    expected = os.environ.get(env_name, "")
    return bool(expected) and hmac.compare_digest(str(given or ""), expected)


def _load_seed(name):
    if not re.match(r"^[a-z0-9_-]{1,40}$", str(name or "")):
        raise bad("Unknown seed.")
    path = os.path.join(HERE, "seed_{}.json".format(name))
    if not os.path.exists(path):
        raise bad("Unknown seed.")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _ensure_building(db, info):
    found = buildings.find(db, info["slug"])
    if found:
        return found, False
    row = db.insert(store.BUILDINGS, {"Slug": info["slug"], "Name": info["name"], "Scheme_No": info.get("scheme_no", ""),
                                      "Brand": json.dumps(info.get("brand") or {}),
                                      "Settings": json.dumps(info.get("settings") or {})})
    return buildings.from_row(row), True


def _add_units(db, building, units):
    have = {str(u.get("Unit_No")) for u in buildings.units(db, building)}
    added = 0
    for unit in units:
        number = str((unit or {}).get("unit_no") or "").strip()
        lot = str((unit or {}).get("lot_no") or "").strip()
        if not number or len(number) > 50 or len(lot) > 50:
            raise bad("Each unit needs a unit number (50 characters at most).")
        if number not in have:
            db.insert(store.UNITS, {"Building_Id": int(building["id"]), "Unit_No": number, "Lot_No": lot})
            have.add(number)
            added += 1
    return added


def _give_role(db, building, email, role):
    user = auth.find_or_make_user(db, email)
    rows = db.find(store.ROLES, {"User_Id": int(user["ROWID"]), "Building_Id": int(building["id"])})
    if not any(r.get("Role") == role for r in rows):
        db.insert(store.ROLES, {"User_Id": int(user["ROWID"]), "Building_Id": int(building["id"]), "Role": role})


def bootstrap(db, given_key, seed, admin_email):
    if not key_ok(given_key, "ADMIN_KEY"):
        raise ApiError("Wrong admin key.", 403)
    email = auth.clean_email(admin_email)
    if not email:
        raise bad("admin_email doesn't look right.")
    data = _load_seed(seed)
    building, created = _ensure_building(db, data["building"])
    units_added = _add_units(db, building, data.get("units") or [])
    have = {t["key"] for t in topics.all_topics(db, building)}
    topics_added = 0
    for item in data.get("topics") or []:
        if item["key"] not in have:
            topics.save(db, building, item["key"], item["definition"], True, item.get("sort", 0))
            topics_added += 1
    _give_role(db, building, email, "admin")
    return {"building": buildings.public(building), "created": created,
            "counts": {"units": len(buildings.units(db, building)), "units_added": units_added,
                       "topics": len(topics.all_topics(db, building)), "topics_added": topics_added}}


def _admin(ctx):
    if not ctx["can"]["admin"]:
        raise forbidden("Only an admin can do that.")


def _clean_brand(brand, current):
    brand = brand if isinstance(brand, dict) else {}
    out = dict(current)
    for key in ("primary", "accent"):
        if key in brand:
            if not HEX.match(str(brand[key])):
                raise bad("Colours look like #1f4d3a.")
            out[key] = brand[key]
    for key, what in (("logo_url", "logo"), ("banner_url", "banner image")):
        if key in brand:
            url = str(brand[key] or "").strip()
            if url and not url.startswith("https://"):
                raise bad(f"The {what} address must start with https://")
            out[key] = url
    if "footer" in brand:
        out["footer"] = str(brand["footer"] or "").strip()[:120]
    return out


def update_building(db, ctx, building, name, scheme_no, brand):
    _admin(ctx)
    change = {"ROWID": building["id"]}
    if name is not None:
        if not str(name).strip() or len(str(name).strip()) > 255:
            raise bad("The building needs a name (255 characters at most).")
        change["Name"] = str(name).strip()
    if scheme_no is not None:
        if len(str(scheme_no).strip()) > 255:
            raise bad("That scheme number is too long.")
        change["Scheme_No"] = str(scheme_no).strip()
    if brand is not None:
        change["Brand"] = json.dumps(_clean_brand(brand, building["brand"]))
    db.update(store.BUILDINGS, change)
    return buildings.public(buildings.find(db, building["slug"]))


def add_units(db, ctx, building, units):
    _admin(ctx)
    if not isinstance(units, list) or not units or len(units) > MAX_UNITS:
        raise bad("Send between 1 and {} units.".format(MAX_UNITS))
    _add_units(db, building, units)
    return buildings.unit_list(db, building)


UPGRADE_KEYS = ("stages", "deadline", "vote", "after_decision")


def upgrade_topics(db, ctx, building, seed):
    """
    Bring an already-loaded building's topics up to the seed's pipeline (POST /admin/topics {from_seed}).
    Only the pipeline keys (stages, deadline, vote, after_decision) are copied over; labels, fields and
    steps the admin may have edited are kept. A missing topic is added. Open cases of a topic that
    newly has a deadline get one, counted from when they were lodged.
    """
    _admin(ctx)
    data = _load_seed(seed)
    have = {t["key"]: t for t in topics.all_topics(db, building)}
    rows = {r.get("Topic_Key"): r for r in db.find(store.TOPICS, {"Building_Id": int(building["id"])})}
    counts = {"updated": 0, "added": 0, "cases_dated": 0}
    for item in data.get("topics") or []:
        if item["key"] in have:
            current = json.loads(rows[item["key"]].get("Definition") or "{}")
            merged = dict(current, **{k: item["definition"][k] for k in UPGRADE_KEYS if k in item["definition"]})
            topics.save(db, building, item["key"], merged, have[item["key"]]["active"], have[item["key"]]["sort"])
            counts["updated"] += 1
        else:
            topics.save(db, building, item["key"], item["definition"], True, item.get("sort", 0))
            counts["added"] += 1
    for topic in topics.all_topics(db, building):
        for row in db.find(store.CASES, {"Building_Id": int(building["id"]), "Topic_Key": topic["key"]}):
            created = store.created_utc(row)
            due = stages.due_for(topic, created) if created else None
            if due and not row.get("Due_At") and row.get("Status") not in ("decided", "closed"):
                db.update(store.CASES, {"ROWID": row["ROWID"], "Due_At": store.fmt_dt(due)})
                counts["cases_dated"] += 1
    return counts


def save_topic(db, ctx, building, key, definition, active, sort):
    _admin(ctx)
    try:
        sort = int(sort or 0)
    except (TypeError, ValueError):
        raise bad("Sort must be a number.")
    if len(json.dumps(definition)) > store.TEXT_MAX:
        raise bad("That topic is too long.")
    topics.save(db, building, key, definition, active, sort)
    return topics.all_topics(db, building)

