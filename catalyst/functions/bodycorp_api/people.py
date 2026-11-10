"""
Who someone is in a building: their units (claimed, then approved) and their roles.

    claim     ->  Memberships row, Status pending  ->  approvers emailed
    decide    ->  approved (access at once) or rejected  ->  person emailed
    remove    ->  Status removed: access stops on their next call

`context` is worked out fresh on every call and every permission check reads it,
so nothing about access is ever remembered between calls.

ROLES (per building)
    committee, manager   handle cases of that handler type; post notices and documents
    approver             approves and removes unit claims
    admin                everything in that building
"""

import auth
import buildings
import mailer
import store
from errors import bad, forbidden, not_found

RELATIONS = ("owner", "tenant")
ROLE_NAMES = ("committee", "manager", "approver", "admin")
HANDLER_ROLES = ("committee", "manager")
MAX_CLAIMS = 20


def roles_of(db, user_id, building):
    rows = db.find(store.ROLES, {"User_Id": int(user_id), "Building_Id": int(building["id"])})
    return {r.get("Role") for r in rows if r.get("Role") in ROLE_NAMES}


def context(db, user, building):
    """Everything a permission check needs. Only approved memberships give access."""
    roles = roles_of(db, user["id"], building)
    memberships = db.find(store.MEMBERSHIPS, {"User_Id": int(user["id"]), "Building_Id": int(building["id"])})
    approved = [m for m in memberships if m.get("Status") == "approved"]
    unit_ids = {str(m["Unit_Id"]) for m in approved}
    owner_unit_ids = {str(m["Unit_Id"]) for m in approved if m.get("Relation") == "owner"}
    handles = bool(roles & {"committee", "manager", "admin"})
    return {
        "user": user, "user_id": str(user["id"]), "building": building, "roles": roles,
        "memberships": memberships, "unit_ids": unit_ids, "owner_unit_ids": owner_unit_ids,
        "relations": {m.get("Relation") for m in approved},
        "can": {"submit": bool(unit_ids), "handle": handles,
                "approve": bool(roles & {"approver", "admin"}), "admin": "admin" in roles,
                # Committee and managers post owner-only documents, so they must see them too.
                "owner": bool(owner_unit_ids) or handles},
    }


def is_member(ctx):
    return bool(ctx["unit_ids"]) or ctx["can"]["handle"] or ctx["can"]["admin"]


def _membership_out(row, labels, users=None):
    user = (users or {}).get(str(row.get("User_Id"))) or {}
    return {"id": str(row["ROWID"]), "unit_id": str(row.get("Unit_Id")),
            "unit_label": labels.get(str(row.get("Unit_Id")), "Unit ?"), "relation": row.get("Relation"),
            "status": row.get("Status"), "note": row.get("Note") or "", "created": store.created_iso(row),
            "user_id": str(row.get("User_Id")), "user_email": user.get("Email") or "",
            "user_name": user.get("Name") or "", "email": user.get("Email") or "", "name": user.get("Name") or ""}


def me(db, ctx):
    labels = buildings.unit_labels(db, ctx["building"])
    return {"user": ctx["user"], "roles": sorted(ctx["roles"]),
            "memberships": [_membership_out(m, labels) for m in ctx["memberships"] if m.get("Status") != "removed"],
            "can": ctx["can"]}


def emails_with_roles(db, building, wanted):
    """Email addresses of everyone in the building holding any of `wanted` roles."""
    ids = {str(r.get("User_Id")) for r in db.find(store.ROLES, {"Building_Id": int(building["id"])})
           if r.get("Role") in wanted}
    users = (db.get(store.USERS, i) for i in sorted(ids))
    return sorted({u.get("Email") for u in users if u and u.get("Email")})


def claim(db, user, building, claims):
    """Ask for access to one or more units. Everything is checked before anything is saved."""
    if not isinstance(claims, list) or not claims or len(claims) > MAX_CLAIMS:
        raise bad("Pick at least one unit.")
    labels = buildings.unit_labels(db, building)
    wanted = []
    for item in claims:
        unit_id = str(store.as_id((item or {}).get("unit_id")) or "")
        relation = str((item or {}).get("relation") or "").strip().lower()
        if unit_id not in labels:
            raise bad("That unit isn't in this building.")
        if relation not in RELATIONS:
            raise bad("Choose owner or tenant for each unit.")
        wanted.append((unit_id, relation))
    have = {(str(m.get("Unit_Id")), m.get("Relation"))
            for m in db.find(store.MEMBERSHIPS, {"User_Id": int(user["id"]), "Building_Id": int(building["id"])})
            if m.get("Status") in ("pending", "approved")}
    added = []
    for unit_id, relation in sorted(set(wanted)):
        if (unit_id, relation) not in have:
            added.append(db.insert(store.MEMBERSHIPS, {
                "User_Id": int(user["id"]), "Building_Id": int(building["id"]), "Unit_Id": int(unit_id),
                "Relation": relation, "Status": "pending"}))
    if added:
        who = user.get("name") or user["email"]
        lines = ["{} ({}) asked to join:".format(who, user["email"])]
        lines += ["{} as {}".format(labels[str(m["Unit_Id"])], m["Relation"]) for m in added]
        lines.append("Check them against the roll, then approve or reject.")
        body = mailer.page(building, "New sign-up to approve", lines, "Open approvals")
        for email in emails_with_roles(db, building, ("approver", "admin")):
            mailer.send(db, email, "{}: a sign-up to approve".format(building["name"]), body)
    return me(db, context(db, user, building))["memberships"]


def _users_by_id(db, rows):
    ids = sorted({str(r.get("User_Id")) for r in rows})
    return {i: u for i, u in ((i, db.get(store.USERS, i)) for i in ids) if u}


def pending(db, building):
    rows = db.find(store.MEMBERSHIPS, {"Building_Id": int(building["id"]), "Status": "pending"})
    labels, users = buildings.unit_labels(db, building), _users_by_id(db, rows)
    return [_membership_out(r, labels, users) for r in rows]


def _membership_in(db, building, membership_id):
    row = db.get(store.MEMBERSHIPS, membership_id)
    if not row or str(row.get("Building_Id")) != building["id"]:
        raise not_found("That sign-up wasn't found.")
    return row


def decide(db, actor_ctx, building, membership_id, decision, note):
    if not actor_ctx["can"]["approve"]:
        raise forbidden("Only an approver can do that.")
    if decision not in ("approve", "reject"):
        raise bad("Choose approve or reject.")
    row = _membership_in(db, building, membership_id)
    if row.get("Status") != "pending":
        raise bad("That sign-up has already been decided.")
    status = "approved" if decision == "approve" else "rejected"
    note = str(note or "").strip()
    change = {"ROWID": row["ROWID"], "Status": status, "Decided_By": int(actor_ctx["user_id"]), "Note": note}
    db.update(store.MEMBERSHIPS, change)
    row = dict(row, **change)
    person = db.get(store.USERS, row.get("User_Id")) or {}
    label = buildings.unit_labels(db, building).get(str(row.get("Unit_Id")), "your unit")
    if status == "approved":
        lines, subject = ["You now have access for {} as {}.".format(label, row.get("Relation"))], "You're in"
    else:
        lines, subject = ["Your request for {} wasn't approved.".format(label)], "Your sign-up wasn't approved"
    if note:
        lines.append("Note: " + note)
    mailer.send(db, person.get("Email") or "", "{}: {}".format(building["name"], subject),
                mailer.page(building, subject, lines, "Open the portal"))
    return _membership_out(row, buildings.unit_labels(db, building), {str(row.get("User_Id")): person})


def members(db, building):
    rows = [r for r in db.find(store.MEMBERSHIPS, {"Building_Id": int(building["id"])})
            if r.get("Status") in ("pending", "approved")]
    labels, users = buildings.unit_labels(db, building), _users_by_id(db, rows)
    return [_membership_out(r, labels, users) for r in rows]


def remove(db, actor_ctx, building, membership_id):
    if not actor_ctx["can"]["approve"]:
        raise forbidden("Only an approver can do that.")
    row = _membership_in(db, building, membership_id)
    db.update(store.MEMBERSHIPS, {"ROWID": row["ROWID"], "Status": "removed",
                                  "Decided_By": int(actor_ctx["user_id"])})


def roles_list(db, building):
    rows = db.find(store.ROLES, {"Building_Id": int(building["id"])})
    users = _users_by_id(db, rows)
    out = [{"email": (users.get(str(r.get("User_Id"))) or {}).get("Email") or "",
            "name": (users.get(str(r.get("User_Id"))) or {}).get("Name") or "", "role": r.get("Role")}
           for r in rows]
    return sorted(out, key=lambda r: (r["role"], r["email"]))


def set_role(db, actor_ctx, building, email, role, on):
    """Give or take a role. The person needn't have signed in yet: their user row is made now."""
    if not actor_ctx["can"]["admin"]:
        raise forbidden("Only an admin can change roles.")
    email = auth.clean_email(email)
    if not email:
        raise bad("That email address doesn't look right.")
    if role not in ROLE_NAMES:
        raise bad("Unknown role.")
    user = auth.find_or_make_user(db, email)
    rows = [r for r in db.find(store.ROLES, {"User_Id": int(user["ROWID"]), "Building_Id": int(building["id"])})
            if r.get("Role") == role]
    if on and not rows:
        db.insert(store.ROLES, {"User_Id": int(user["ROWID"]), "Building_Id": int(building["id"]), "Role": role})
    if not on and rows:
        if role == "admin" and len([r for r in roles_list(db, building) if r["role"] == "admin"]) <= 1:
            raise bad("A building needs at least one admin.")
        for row in rows:
            db.delete(store.ROLES, row["ROWID"])
    return roles_list(db, building)
