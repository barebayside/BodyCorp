"""
BodyCorp API: one function behind the portal page.

    sign in     ->  /auth/start (code emailed)  ->  /auth/verify  ->  session token
    join        ->  /claims  ->  an approver  ->  /approvals/decide
    ask         ->  /topics  ->  /cases  ->  the handler's inbox  ->  steps, status, messages, decision
    work it     ->  /board (columns by stage)  ->  /case  ->  /case/action (the stage's button: email + move)
    vote        ->  /votes (open one outside a meeting)  ->  /vote/ballot  ->  result onto the case
    meet        ->  /meetings  ->  /meeting/attendance  ->  /meeting/vote  ->  /meeting/close
                ->  /meeting/minutes (edit)  ->  /meeting/minutes/issue (owners + Documents)
    follow up   ->  /tasks (from resolutions)  ->  /task/done
    committee   ->  /committee (who, duty map, module), /committee/settings (admin)
    read        ->  /notices, /docs
    set up      ->  /admin/bootstrap (key), /admin/building, /admin/units, /admin/topics
                    (/admin/topics {from_seed: "altai"} brings an existing building's topics up to the seed's
                    stages, deadlines and vote rules)
    every day   ->  /cron/reminders (key): retry queued email, settle votes whose time is up, decide cases
                    whose deadline passed (deemed approved / not agreed), then the due-soon digests (cases,
                    tasks, minutes), then a heartbeat
                ->  /cron/check (key): retry queued email, look for trouble, email ONE digest (health.py)
    trouble     ->  /failures (admins: their building; product admin: ?all=1), /failures/resolve
    watching    ->  /status (public): alive, and when the self-check last ran

WHEN THINGS GO WRONG
    Every email goes through mailer.send: a failed one is queued and retried, and
    logged as a Failures row (mailer.py, failures.py). Any crash in a request is
    logged as a Failures row of kind "error" (route and error type, never the
    body) before the 500, and the logging itself can never crash the answer.

WHO IS ALLOWED
    Every call but the public ones carries `X-Session: <token>`. Not
    `Authorization`: Catalyst's gateway claims that header for its own OAuth and
    answers INVALID_TOKEN before the function runs. The
    building comes from `b`. Every permission is worked out from our own Memberships
    and Roles rows on every call (people.context), never from anything the page says.
    Committee business (votes, meetings, minutes, tasks, internal notes) is for committee
    roles only: residents and the building manager get 403, another building's ids 404.

COMMITTEE ROUTES (2026-11-10; law: docs/compliance/qld-committee-rules.md)
    GET  /board                     {columns: [{key, label, cards: [case summary + stage, stage_label,
                                     owner_label, missed_label, missed, urgent, vote]}], closed, module_note}
    POST /case/action {id, action, note}           -> the case (as GET /case)
    GET  /case                      handlers also get case.missed {banner, card, date_text, days_left,
                                     urgent, citation, outcome, extendable} and case.stage {label,
                                     owner_label, instructions, rule, allowed, buttons, path}; the
                                     committee also gets votes and tasks
    GET  /committee                 {members, checks, module, module_note, secretary_contact, duties, positions}
    POST /committee/settings {duties, module, evidence, secretary_contact, unfinancial}  (admin)
    GET  /votes                     {votes, can_open, module_note};  GET /vote {id} -> {vote}
    POST /votes {words, case_id?, exempt?}         -> {vote}
    POST /vote/ballot {id, vote: yes|no|abstain, conflict, note}  -> {vote}
    GET  /meetings                  {meetings, can_call};  GET /meeting {id} -> {meeting}
    POST /meetings {title, starts_at: "YYYY-MM-DDTHH:MM" Brisbane, place, items: [{text, motion?,
                    case_id?}], short_notice}        -> {meeting}
    POST /meeting/attendance {id, people: [{user_id, how, proxy_holder?}], others}
    POST /meeting/motion {id, words, case_id?, exempt?};  POST /meeting/vote {motion_id, votes: {user_id: v}}
    POST /meeting/close {id};  POST /meeting/minutes {id, text};  POST /meeting/minutes/issue {id}
    GET  /tasks {scope: mine|all} -> {tasks, people, positions}
    POST /tasks {title, detail, due_date, assignee_user_id | assignee_position, motion_id?, case_id?,
                 meeting_id?} -> {task};  POST /task/done {id, done} -> {task}

EVERY ANSWER
    JSON with "ok": true or false. 400 bad input, 401 not signed in, 403 not allowed,
    404 not found, which is also the answer for a case or document the caller may not see.
    One exception: /cron/check answers 200 with "ok": false when it found problems,
    so an outside monitor can read health from `ok` alone.

ENVIRONMENT (catalyst-config.json)
    AUTH_SALT       mixed into sign-in code hashes
    ADMIN_KEY       X-Admin-Key for /admin/bootstrap
    CRON_KEY        X-Cron-Key for /cron/reminders and /cron/check
    MAIL_FROM       a verified Catalyst Mail sender; empty means emails are logged, not sent
    MAIL_FROM_NAME  the name emails come from
    PORTAL_URL      the portal page, for links in emails
    SUPPORT_EMAIL   the product's support address: gets the daily check's digest, and
                    (if also an admin somewhere) sees every building's failures
"""

import json
import logging
import re

from flask import Request, make_response

import admin
import auth
import buildings
import cases
import committee
import content
import deadlines
import failures
import health
import mailer
import meetings
import people
import pipeline
import store
import tasks
import topics
import votes
from errors import ApiError, forbidden

logger = logging.getLogger("bodycorp_api")
logging.basicConfig(level=logging.INFO)

PREFIX = "/server/bodycorp_api"


class FileResult:
    """A download rather than JSON."""

    def __init__(self, data, content_type, name):
        self.data, self.content_type, self.name = data, content_type, name


class Call:
    """One request: its body, headers and clock, with the user and building looked up on first use."""

    def __init__(self, db, body, headers, now):
        self.db, self.body, self.now = db, body, now
        self.headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        self._user, self._building, self._ctx = None, None, None

    def get(self, key, default=None):
        return self.body.get(key, default)

    @property
    def user(self):
        if self._user is None:
            self._user = auth.user_for(self.db, self.headers.get("x-session"), self.now)
            if not self._user:
                raise ApiError("Please sign in.", 401)
        return self._user

    @property
    def building(self):
        if self._building is None:
            self._building = buildings.require(self.db, self.body.get("b"))
        return self._building

    @property
    def ctx(self):
        if self._ctx is None:
            self._ctx = people.context(self.db, self.user, self.building)
        return self._ctx

    def approver(self):
        if not self.ctx["can"]["approve"]:
            raise forbidden("Only an approver can do that.")
        return self.ctx


# ---------- public ----------

def get_building(c):
    return {"building": buildings.public(c.building), "units": buildings.unit_list(c.db, c.building)}


def auth_start(c):
    auth.start(c.db, c.get("email"), buildings.find(c.db, c.get("b")), c.now)
    return {}


def auth_verify(c):
    result = auth.verify(c.db, c.get("email"), c.get("code"), c.now)
    if not result:
        raise ApiError("That code didn't work. Check it, or ask for a new one.", 400)
    return {"token": result[0], "user": result[1]}


def auth_logout(c):
    auth.logout(c.db, c.headers.get("x-session"))
    return {}


def bootstrap(c):
    return admin.bootstrap(c.db, c.headers.get("x-admin-key"), c.get("seed"), c.get("admin_email"))


def _cron(c):
    if not admin.key_ok(c.headers.get("x-cron-key"), "CRON_KEY"):
        raise ApiError("Wrong cron key.", 403)


def cron_reminders(c):
    _cron(c)
    queue = mailer.retry_queue(c.db, c.now)
    votes.settle_all(c.db, c.now)          # a vote whose 21 days are up gets its result first...
    pipeline.apply_deemed(c.db, c.now)     # ...then any case still undecided past its deadline
    sent = deadlines.remind(c.db, c.now, lambda b: _due_extras(c.db, b, c.now))
    failures.heartbeat(c.db, failures.HEARTBEAT_REMINDERS, "Reminders ran: {} digest(s) sent.".format(sent))
    return {"sent": sent, "queue": queue}


def _due_extras(db, building, now):
    """Tasks and draft minutes due soon, for the daily digest."""
    lines = tasks.due_lines(db, building, now)
    for left, row in meetings.minutes_due(db, building, now):
        when = "OVERDUE by {} day(s)".format(-left) if left < 0 else "due in {} day(s)".format(left)
        line = "Minutes: {} ({}) · issue {} (SM s 71)".format(row.get("Title"), meetings.local_text(
            store.parse_dt(row["Starts_At"])), when)
        for email in committee.emails_of(db, committee.holders(db, building, committee.resolve(building, "minutes"))):
            lines.setdefault(email, []).append(line)
    return lines


def cron_check(c):
    _cron(c)
    return health.check(c.db, c.now)


def get_status(c):
    """Public, for an outside monitor. Nothing internal: alive, and when the self-check last ran."""
    return {"status": "alive", "checked_at": deadlines.iso_utc(failures.last_run(c.db, failures.HEARTBEAT_CHECK))}


# ---------- me and people ----------

def get_me(c):
    return people.me(c.db, c.ctx)


def set_name(c):
    name = str(c.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ApiError("Please give your name (100 characters at most).")
    c.db.update(store.USERS, {"ROWID": c.user["id"], "Name": name})
    return {"user": dict(c.user, name=name)}


def post_claims(c):
    return {"memberships": people.claim(c.db, c.user, c.building, c.get("claims"))}


def get_approvals(c):
    c.approver()
    return {"pending": people.pending(c.db, c.building)}


def decide_approval(c):
    return {"membership": people.decide(c.db, c.ctx, c.building, c.get("id"), c.get("decision"), c.get("note"))}


def get_members(c):
    c.approver()
    return {"members": people.members(c.db, c.building), "roles": people.roles_list(c.db, c.building)}


def remove_member(c):
    people.remove(c.db, c.ctx, c.building, c.get("id"))
    return {}


def post_roles(c):
    on = c.get("on") not in (False, "false", 0, "0")
    return {"roles": people.set_role(c.db, c.ctx, c.building, c.get("email"), c.get("role"), on)}


# ---------- topics and cases ----------

def get_topics(c):
    if not people.is_member(c.ctx):
        raise forbidden("You'll see the forms once your unit is approved.")
    return {"topics": topics.for_member(c.db, c.building, c.ctx)}


def post_case(c):
    return cases.create(c.db, c.building, c.user, c.ctx, c.get("unit_id"), c.get("topic_key"),
                        c.get("answers"), c.get("files"), c.now)


def get_cases(c):
    if c.get("scope") == "inbox":
        return {"cases": cases.list_inbox(c.db, c.building, c.ctx, c.now)}
    return {"cases": cases.list_mine(c.db, c.building, c.ctx, c.now)}


def get_case(c):
    out = cases.detail(c.db, c.building, c.ctx, c.get("id"), c.now)
    if c.ctx["cmt"]["committee"] and out["case"]["can_handle"]:
        votes.settle_building(c.db, c.building, c.now)
        out = cases.detail(c.db, c.building, c.ctx, c.get("id"), c.now)
        out["votes"] = votes.case_votes(c.db, c.building, c.ctx, c.get("id"), c.now)
        out["tasks"] = [t for t in tasks.listing(c.db, c.building, c.ctx, "all", c.now)["tasks"]
                        if t["case_id"] == out["case"]["id"]]
        out["can_open_vote"] = committee.may_act(c.db, c.building, c.ctx, "vocm")
    return out


def case_action(c):
    def open_vote(row, words):
        votes.open_vocm(c.db, c.building, c.ctx, words, row["ROWID"], "", c.now)
    pipeline.action(c.db, c.building, c.ctx, c.get("id"), c.get("action"), c.get("note"), c.now, open_vote)
    return get_case(c)


# ---------- the committee ----------

def get_board(c):
    votes.settle_building(c.db, c.building, c.now)
    return pipeline.board(c.db, c.building, c.ctx, c.now, votes.open_by_case(c.db, c.building, c.now)
                          if c.ctx["cmt"]["committee"] else {})


def get_committee(c):
    return committee.overview(c.db, c.building, c.ctx)


def post_committee_settings(c):
    return committee.save_settings(c.db, c.building, c.ctx, c.get("duties"), c.get("module"), c.get("evidence"),
                                   c.get("secretary_contact"), c.get("unfinancial"))


def get_votes(c):
    return votes.listing(c.db, c.building, c.ctx, c.now)


def get_vote(c):
    return votes.detail(c.db, c.building, c.ctx, c.get("id"), c.now)


def post_vote(c):
    motion = votes.open_vocm(c.db, c.building, c.ctx, c.get("words"), c.get("case_id"), c.get("exempt") or "", c.now)
    return votes.detail(c.db, c.building, c.ctx, motion["ROWID"], c.now)


def post_ballot(c):
    return votes.ballot(c.db, c.building, c.ctx, c.get("id"), c.get("vote"), c.get("conflict"), c.get("note"), c.now)


def get_meetings(c):
    return meetings.listing(c.db, c.building, c.ctx, c.now)


def get_meeting(c):
    return meetings.detail(c.db, c.building, c.ctx, c.get("id"), c.now)


def post_meeting(c):
    return meetings.create(c.db, c.building, c.ctx, c.get("title"), c.get("starts_at"), c.get("place"),
                           c.get("items"), c.get("short_notice"), c.now)


def meeting_attendance(c):
    return meetings.record_attendance(c.db, c.building, c.ctx, c.get("id"), c.get("people"), c.get("others"), c.now)


def meeting_motion(c):
    return meetings.add_motion(c.db, c.building, c.ctx, c.get("id"), c.get("words"), c.get("case_id"),
                               c.get("exempt") or "", c.now)


def meeting_vote(c):
    return meetings.record_votes(c.db, c.building, c.ctx, c.get("motion_id"), c.get("votes"), c.now)


def meeting_close(c):
    return meetings.close(c.db, c.building, c.ctx, c.get("id"), c.now)


def meeting_minutes(c):
    return meetings.save_minutes(c.db, c.building, c.ctx, c.get("id"), c.get("text"), c.now)


def meeting_issue(c):
    return meetings.issue_minutes(c.db, c.building, c.ctx, c.get("id"), c.now)


def get_tasks(c):
    return tasks.listing(c.db, c.building, c.ctx, c.get("scope") or "mine", c.now)


def post_task(c):
    return tasks.create(c.db, c.building, c.ctx, c.get("title"), c.get("detail"), c.get("due_date"),
                        c.get("assignee_user_id"), c.get("assignee_position"), c.get("motion_id"),
                        c.get("case_id"), c.get("meeting_id"), c.now)


def task_done(c):
    return tasks.set_done(c.db, c.building, c.ctx, c.get("id"), c.get("done"), c.now)


def case_step(c):
    return cases.set_step(c.db, c.building, c.ctx, c.get("id"), c.get("index"), c.get("done"), c.now)


def case_status(c):
    return cases.set_status(c.db, c.building, c.ctx, c.get("id"), c.get("status"), c.get("note"), c.now)


def case_message(c):
    return {"event": cases.message(c.db, c.building, c.ctx, c.get("id"), c.get("body"), c.get("to_resident"), c.now)}


def case_decide(c):
    return cases.decide(c.db, c.building, c.ctx, c.get("id"), c.get("outcome"), c.get("reasons"),
                        c.get("conditions"), c.now)


def case_file(c):
    return FileResult(*cases.file(c.db, c.building, c.ctx, c.get("id"), c.get("n")))


# ---------- notices and documents ----------

def get_notices(c):
    return {"notices": content.notices(c.db, c.building, c.ctx)}


def post_notice(c):
    return {"notices": content.post_notice(c.db, c.building, c.ctx, c.get("title"), c.get("body"), c.get("audience"))}


def delete_notice(c):
    return {"notices": content.delete_notice(c.db, c.building, c.ctx, c.get("id"))}


def get_docs(c):
    return {"docs": content.docs(c.db, c.building, c.ctx)}


def post_doc(c):
    return {"docs": content.add_doc(c.db, c.building, c.ctx, c.get("title"), c.get("category"),
                                    c.get("audience"), c.get("name"), c.get("data"))}


def delete_doc(c):
    return {"docs": content.delete_doc(c.db, c.building, c.ctx, c.get("id"))}


def doc_file(c):
    return FileResult(*content.doc_file(c.db, c.building, c.ctx, c.get("id")))


# ---------- failures ----------

def get_failures(c):
    if c.get("all") in (True, 1, "1", "true"):
        if not failures.is_product_admin(c.db, c.user):
            raise forbidden("Only the product admin can see every building.")
        return failures.listing(c.db, None, True)
    if not c.ctx["can"]["admin"]:
        raise forbidden("Only an admin can see this.")
    return failures.listing(c.db, c.building, failures.is_product_admin(c.db, c.user))


def resolve_failure(c):
    """The product admin may resolve any; a building admin only their own building's."""
    if failures.is_product_admin(c.db, c.user):
        return {"failure": failures.resolve(c.db, c.user, None, c.get("id"))}
    if not c.ctx["can"]["admin"]:
        raise forbidden("Only an admin can do that.")
    return {"failure": failures.resolve(c.db, c.user, c.building, c.get("id"))}


# ---------- admin ----------

def admin_building(c):
    return {"building": admin.update_building(c.db, c.ctx, c.building, c.get("name"), c.get("scheme_no"),
                                              c.get("brand"))}


def admin_units(c):
    return {"units": admin.add_units(c.db, c.ctx, c.building, c.get("units"))}


def admin_topics(c):
    if c.get("from_seed"):
        counts = admin.upgrade_topics(c.db, c.ctx, c.building, c.get("from_seed"))
        return {"topics": topics.all_topics(c.db, c.building), "counts": counts}
    return {"topics": admin.save_topic(c.db, c.ctx, c.building, c.get("key"), c.get("definition"),
                                       c.get("active", True), c.get("sort", 0))}


ROUTES = {
    ("GET", "/building"): get_building,
    ("POST", "/auth/start"): auth_start,
    ("POST", "/auth/verify"): auth_verify,
    ("POST", "/auth/logout"): auth_logout,
    ("GET", "/me"): get_me,
    ("POST", "/me/name"): set_name,
    ("POST", "/claims"): post_claims,
    ("GET", "/approvals"): get_approvals,
    ("POST", "/approvals/decide"): decide_approval,
    ("GET", "/members"): get_members,
    ("POST", "/members/remove"): remove_member,
    ("POST", "/roles"): post_roles,
    ("GET", "/topics"): get_topics,
    ("POST", "/cases"): post_case,
    ("GET", "/cases"): get_cases,
    ("GET", "/case"): get_case,
    ("POST", "/case/step"): case_step,
    ("POST", "/case/status"): case_status,
    ("POST", "/case/message"): case_message,
    ("POST", "/case/decide"): case_decide,
    ("GET", "/case/file"): case_file,
    ("POST", "/case/action"): case_action,
    ("GET", "/board"): get_board,
    ("GET", "/committee"): get_committee,
    ("POST", "/committee/settings"): post_committee_settings,
    ("GET", "/votes"): get_votes,
    ("GET", "/vote"): get_vote,
    ("POST", "/votes"): post_vote,
    ("POST", "/vote/ballot"): post_ballot,
    ("GET", "/meetings"): get_meetings,
    ("GET", "/meeting"): get_meeting,
    ("POST", "/meetings"): post_meeting,
    ("POST", "/meeting/attendance"): meeting_attendance,
    ("POST", "/meeting/motion"): meeting_motion,
    ("POST", "/meeting/vote"): meeting_vote,
    ("POST", "/meeting/close"): meeting_close,
    ("POST", "/meeting/minutes"): meeting_minutes,
    ("POST", "/meeting/minutes/issue"): meeting_issue,
    ("GET", "/tasks"): get_tasks,
    ("POST", "/tasks"): post_task,
    ("POST", "/task/done"): task_done,
    ("GET", "/notices"): get_notices,
    ("POST", "/notices"): post_notice,
    ("POST", "/notices/delete"): delete_notice,
    ("GET", "/docs"): get_docs,
    ("POST", "/docs"): post_doc,
    ("POST", "/docs/delete"): delete_doc,
    ("GET", "/docs/file"): doc_file,
    ("POST", "/admin/bootstrap"): bootstrap,
    ("POST", "/admin/building"): admin_building,
    ("POST", "/admin/units"): admin_units,
    ("POST", "/admin/topics"): admin_topics,
    ("POST", "/cron/reminders"): cron_reminders,
    ("POST", "/cron/check"): cron_check,
    ("GET", "/status"): get_status,
    ("GET", "/failures"): get_failures,
    ("POST", "/failures/resolve"): resolve_failure,
}


def clean_path(path):
    path = str(path or "")
    if path.startswith(PREFIX):
        path = path[len(PREFIX):]
    return re.sub(r"/+$", "", path) or "/"


def route(db, method, path, body, headers=None, now=None):
    """Returns (body, status) or a FileResult. Kept apart from Flask so tests can call it directly."""
    action = ROUTES.get((str(method).upper(), clean_path(path)))
    if not action:
        return {"ok": False, "error": "Not found."}, 404
    try:
        result = action(Call(db, body if isinstance(body, dict) else {}, headers, now or store.utc_now()))
    except ApiError as exc:
        return {"ok": False, "error": exc.message}, exc.status
    except store.RowRefused as exc:
        return {"ok": False, "error": str(exc)}, 400
    if isinstance(result, FileResult):
        return result
    return dict({"ok": True}, **result), 200     # a result may set ok itself (/cron/check)


def _respond(body, status=200):
    response = make_response(json.dumps(body, default=str), status)
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    return response


def _file_response(result):
    response = make_response(result.data)
    response.headers["Content-Type"] = result.content_type
    name = re.sub(r"[^A-Za-z0-9._-]", "_", result.name)
    response.headers["Content-Disposition"] = 'inline; filename="{}"'.format(name)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def handler(request: Request):
    if clean_path(request.path) in ("/", "/health"):
        return _respond({"ok": True, "status": "alive"})
    db, body = None, {}
    try:
        db = store.Db()
        sent = request.get_json(force=True, silent=True)
        body = dict(request.args.to_dict(), **(sent if isinstance(sent, dict) else {}))
        result = route(db, request.method, request.path, body, dict(request.headers.items()))
        if isinstance(result, FileResult):
            return _file_response(result)
        return _respond(*result)
    except Exception as exc:  # noqa: BLE001 — the page shows this rather than a blank failure
        logger.exception("failed on %s", request.path)
        # Route and error type only: the body may hold anything a person typed. log_error never raises.
        failures.log_error(db, request.method, clean_path(request.path), body.get("b"), exc)
        return _respond({"ok": False, "error": "Something went wrong ({}).".format(type(exc).__name__)}, 500)
