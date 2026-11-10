"""
A building and its units. Every request names its building by slug (`?b=altai`),
and every query after that is filtered by the building's id.

Brand and Settings are JSON text, so a new building is a new row, not new code.
"""

import json
import re

import store
from errors import bad, not_found

SLUG = re.compile(r"^[a-z0-9-]{1,100}$")
DEFAULT_BRAND = {"primary": "#24466b", "accent": "#c9a227", "logo_url": "", "footer": ""}


def _json(text, default):
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, dict) else default


def from_row(row):
    return {"id": str(row["ROWID"]), "slug": row.get("Slug") or "", "name": row.get("Name") or "",
            "scheme_no": row.get("Scheme_No") or "",
            "brand": dict(DEFAULT_BRAND, **_json(row.get("Brand"), {})),
            "settings": _json(row.get("Settings"), {})}


def find(db, slug):
    """The building for a slug, or None."""
    slug = str(slug or "").strip().lower()
    if not SLUG.match(slug):
        return None
    rows = db.find(store.BUILDINGS, {"Slug": slug})
    return from_row(rows[0]) if rows else None


def require(db, slug):
    if not str(slug or "").strip():
        raise bad("Which building? (b is missing)")
    building = find(db, slug)
    if not building:
        raise not_found("That building wasn't found.")
    return building


def public(building):
    return {key: building[key] for key in ("slug", "name", "scheme_no", "brand")}


def _unit_sort(row):
    number = str(row.get("Unit_No") or "")
    digits = re.match(r"\d+", number)
    return (int(digits.group()) if digits else 10 ** 9, number)


def unit_label(row):
    return "Unit {}".format(row.get("Unit_No") or "?")


def units(db, building):
    return sorted(db.find(store.UNITS, {"Building_Id": int(building["id"])}), key=_unit_sort)


def unit_labels(db, building):
    """{unit id: label} for the building, for showing ids as people know them."""
    return {str(u["ROWID"]): unit_label(u) for u in units(db, building)}


def unit_list(db, building):
    return [{"id": str(u["ROWID"]), "label": unit_label(u), "lot_no": u.get("Lot_No") or ""}
            for u in units(db, building)]
