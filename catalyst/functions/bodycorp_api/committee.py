"""
The committee: who sits on it, who does which job, and the building's committee settings.

POSITIONS ARE ROLES
    chair, secretary, treasurer, member (ordinary member) are Roles rows. Holding any of
    them makes a person a voting member, with one vote however many they hold (SM s 9(3),
    s 65(5)). `committee` is committee access without a vote (e.g. a body corporate manager,
    SM s 12). Law file: docs/compliance/qld-committee-rules.md §2-3.

THE DUTY MAP (Buildings.Settings.duties)
    The law gives most duties to "the committee" or "the body corporate", the treasurer almost
    none, and names no minute-taker (law file §3, §4 Minutes). So which position does which
    job is a per-building setting with these defaults. A stage in a request type names a
    duty (or a role) as its owner; the building's map turns that into a position.
    If nobody holds the position, any voting member may act, so nothing gets stuck.

OTHER SETTINGS (Buildings.Settings)
    regulation_module   "standard" | "accommodation" | "" (not recorded). Act s 21; law file §1.
                        The 7-day opposition window exists only under the Standard Module (SM s 72-73).
    module_evidence     e.g. the CMS dealing number and date
    secretary_contact   the secretary's contact address, which minutes must carry (SM s 71(6))
    unfinancial         user ids of members who owe a body corporate debt: no vote (SM s 64, s 67),
                        but they still count towards quorum (SM s 60(4))
"""

import json

import people
import store
from errors import bad, forbidden

POSITIONS = people.POSITIONS
POSITION_LABELS = {"chair": "Chair", "secretary": "Secretary", "treasurer": "Treasurer", "member": "Ordinary member",
                   "committee": "Committee (no vote)", "manager": "Building manager", "voting": "Any voting member",
                   "admin": "Admin"}
OWNERS = POSITIONS + ("committee", "manager", "voting", "admin")
MODULES = ("standard", "accommodation", "")

# key: (label, default position, where it comes from)
DUTIES = {
    "acknowledge": ("Receive and acknowledge requests, owner motions and animal requests", "secretary",
                    "SM s 58(2), s 58A(2): given to the secretary"),
    "vocm": ("Send votes outside a meeting, with the owner advice", "secretary", "SM s 68(4)"),
    "notices": ("Call committee meetings and send the notice and agenda", "secretary", "SM s 54(1), s 55"),
    "chair_meetings": ("Run committee meetings and record the votes", "chair", "SM s 59(1)"),
    "minutes": ("Take, issue and send minutes and the record of motions", "secretary",
                "SM s 71(1)-(4): the committee must; the law names no minute-taker (practice)"),
    "records": ("Answer records requests", "secretary", "Act s 205(2); the body corporate's duty (practice)"),
    "accounts": ("Levy notices and monthly reconciliations", "treasurer",
                 "SM s 163, s 170: body corporate duties (practice, UNCONFIRMED)"),
    "tasks": ("Default owner of tasks from resolutions", "secretary", "Committee practice"),
    "vote": ("Vote on motions", "voting", "SM s 65, s 67: every voting member entitled to vote"),
}


def _settings(building):
    return building.get("settings") or {}


def duty_map(building):
    """{duty: position} with the building's choices over the defaults."""
    chosen = _settings(building).get("duties") or {}
    return {key: (chosen.get(key) if chosen.get(key) in OWNERS else default)
            for key, (_, default, _) in DUTIES.items()}


def resolve(building, owner):
    """A stage owner (a duty or a role) as the role that does it."""
    owner = str(owner or "")
    return duty_map(building).get(owner, owner if owner in OWNERS else "voting")


def module(building):
    value = _settings(building).get("regulation_module") or ""
    return value if value in MODULES else ""


def unfinancial(building):
    return {str(u) for u in _settings(building).get("unfinancial") or []}


def voting_ids(db, building):
    return people.ids_with_roles(db, building, POSITIONS)


def committee_ids(db, building):
    """Every committee member, voting and non-voting (SM s 12): who gets meeting and VOCM notices."""
    return people.ids_with_roles(db, building, people.COMMITTEE_ROLES)


def holders(db, building, position):
    if position == "voting":
        return voting_ids(db, building)
    return people.ids_with_roles(db, building, (position,))


def emails_of(db, ids):
    users = (db.get(store.USERS, i) for i in sorted(set(ids)))
    return sorted({u.get("Email") for u in users if u and u.get("Email")})


def may_act(db, building, ctx, owner):
    """May this person press a button owned by `owner`? Admins always; else the position's holders."""
    if "admin" in ctx["roles"]:
        return True
    position = resolve(building, owner)
    if position == "voting":
        return ctx["cmt"]["voting"]
    if position in ctx["roles"]:
        return True
    return ctx["cmt"]["voting"] and not holders(db, building, position)


def owner_label(building, owner):
    return POSITION_LABELS.get(resolve(building, owner), str(owner or "").capitalize())


def require_committee(ctx):
    """Committee business (votes, meetings, minutes, tasks) is never shown to residents or the manager."""
    if not ctx["cmt"]["committee"]:
        raise forbidden("Only the committee can see this.")


def members(db, building):
    """The committee as people: name, email, positions, voting, unfinancial."""
    debt = unfinancial(building)
    rows = db.find(store.ROLES, {"Building_Id": int(building["id"])})
    by_user = {}
    for r in rows:
        if r.get("Role") in people.COMMITTEE_ROLES:
            by_user.setdefault(str(r.get("User_Id")), set()).add(r.get("Role"))
    out = []
    for uid, roles in sorted(by_user.items()):
        user = db.get(store.USERS, uid) or {}
        positions = [p for p in POSITIONS if p in roles]
        out.append({"user_id": uid, "name": user.get("Name") or "", "email": user.get("Email") or "",
                    "positions": positions, "voting": bool(positions), "unfinancial": uid in debt,
                    "label": ", ".join(POSITION_LABELS[p] for p in positions) or POSITION_LABELS["committee"]})
    return out


def checks(people_list):
    """The make-up rules (SM s 9(2), (4); sch 1) as warnings: roles are added one at a time, so never a block."""
    voting = [m for m in people_list if m["voting"]]
    out = []
    if len(voting) < 3:
        out.append("The committee needs at least 3 voting members; it has {} (SM s 9(4)).".format(len(voting)))
    if len(voting) > 7:
        out.append("A scheme of 7 or more lots can have at most 7 voting members; it has {} (SM s 9(4), sch 1)."
                   .format(len(voting)))
    for position in ("chair", "secretary", "treasurer"):
        if not any(position in m["positions"] for m in voting):
            out.append("Nobody is {} yet. The chair, secretary and treasurer must be filled (SM s 9(2))."
                       .format(POSITION_LABELS[position].lower()))
    return out


def module_note(building, ctx):
    """For admins only: the rules engine stays guidance until the module is recorded (law file §1)."""
    if module(building) or "admin" not in ctx["roles"]:
        return None
    return "Module not recorded — committee rules are guidance only."


def overview(db, building, ctx):
    require_committee(ctx)
    team = members(db, building)
    settings = _settings(building)
    duties = duty_map(building)
    return {"members": team, "checks": checks(team), "module": module(building),
            "module_evidence": settings.get("module_evidence") or "", "module_note": module_note(building, ctx),
            "secretary_contact": settings.get("secretary_contact") or "",
            "duties": [{"key": k, "label": label, "position": duties[k], "position_label": POSITION_LABELS.get(duties[k]),
                        "default": default, "rule": rule} for k, (label, default, rule) in DUTIES.items()],
            "positions": [{"key": k, "label": POSITION_LABELS[k]} for k in OWNERS if k != "admin"]}


def save_settings(db, building, ctx, duties=None, regulation_module=None, evidence=None, secretary_contact=None,
                  unfinancial_ids=None):
    """Admin only. Each argument left as None is unchanged."""
    if "admin" not in ctx["roles"]:
        raise forbidden("Only an admin can change the committee settings.")
    settings = dict(_settings(building))
    if duties is not None:
        if not isinstance(duties, dict) or any(k not in DUTIES or v not in OWNERS for k, v in duties.items()):
            raise bad("Each job needs one of the positions.")
        settings["duties"] = dict(settings.get("duties") or {}, **duties)
    if regulation_module is not None:
        if regulation_module not in MODULES:
            raise bad("The module is standard or accommodation.")
        settings["regulation_module"] = regulation_module
    if evidence is not None:
        settings["module_evidence"] = str(evidence).strip()[:255]
    if secretary_contact is not None:
        settings["secretary_contact"] = str(secretary_contact).strip()[:255]
    if unfinancial_ids is not None:
        if not isinstance(unfinancial_ids, list):
            raise bad("Send a list of people.")
        settings["unfinancial"] = sorted({str(store.as_id(u)) for u in unfinancial_ids if store.as_id(u)})
    text = json.dumps(settings)
    if len(text) > store.TEXT_MAX:
        raise bad("Those settings are too long.")
    db.update(store.BUILDINGS, {"ROWID": building["id"], "Settings": text})
    building["settings"] = settings
    return overview(db, building, ctx)
