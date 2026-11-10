# BodyCorp portal v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A branded, multi-building body corporate portal on Catalyst: email-code sign-in, unit claims with
approval, topic forms that open tracked requests with steps and legal deadlines, a handler inbox, notices,
documents, emails, daily reminders, and a public product page. Altai on the Park is the first building.

**Architecture:** One static web client (`catalyst/client`) talks to one Python Advanced I/O function
(`catalyst/functions/bodycorp_api`) over JSON. All permission checks happen in the function against our own
membership and role tables. Each building's topics are JSON data, so new buildings change data, not code.

**Tech Stack:** Catalyst (AU, project `BodyCorp` id 694000000418109, org 7006497428), Python 3.9 Flask-style
Advanced I/O, `zcatalyst-sdk==1.3.0`, Data Store, Stratus, Catalyst Mail, Catalyst cron; vanilla HTML/CSS/JS
client (no build step); pytest with a fake store.

**Spec:** `docs/superpowers/specs/2026-11-10-bodycorp-portal-design.md`

## Global Constraints

- Every Data Store read pages by ROWID in 300s (ZCQL cap). Datetimes written as `YYYY-MM-DD HH:MM:SS` (UTC).
- Every JSON response carries `"ok": true|false`; the client treats a body without `ok: true` as failure.
- Function finishes inside 30 s; files ≤ 5 MB each, sent as base64 JSON.
- Every query is filtered by `Building_Id`; residents additionally by their **approved** unit ids.
- Every Altai topic carries `"draft": true` and the UI shows "Draft — to be checked against Altai's CMS/by-laws".
- Wording: "guidance, checked by your advisors", never "legal advice".
- No secrets in git: `catalyst-config.json` holds env vars and is git-ignored; a `catalyst-config.example.json` is committed.
- Plain, short UI copy; phone-first; small "Powered by BodyCorp" footer.

## Review Focus

1. A resident asks for a case id from another unit or building → 404, never the case. (Task 4 test.)
2. A pending or removed membership tries to submit or see owner documents → refused. (Task 4 test.)
3. A login code is guessed: 6th try, expired code, reused code → all fail; codes stored only as hashes. (Task 2 test.)
4. A tenant sees owner-only notices/documents → never. (Task 6 test.)
5. A deadline computed across midnight Brisbane time → due date in Brisbane, stored UTC. (Task 5 test.)

---

## Data Store tables (created by the coordinator via MCP before deploy)

All ids are Catalyst ROWIDs (bigint). Every table also has ROWID/CREATEDTIME/MODIFIEDTIME.

| Table | Columns |
|---|---|
| `Buildings` | `Slug` varchar unique, `Name` varchar, `Scheme_No` varchar, `Brand` text (JSON), `Settings` text (JSON) |
| `Units` | `Building_Id` bigint, `Unit_No` varchar, `Lot_No` varchar |
| `Users` | `Email` varchar unique, `Name` varchar |
| `Memberships` | `User_Id`, `Building_Id`, `Unit_Id` bigint; `Relation` varchar (`owner`/`tenant`); `Status` varchar (`pending`/`approved`/`rejected`/`removed`); `Decided_By` bigint; `Note` varchar |
| `Roles` | `User_Id`, `Building_Id` bigint; `Role` varchar (`committee`/`manager`/`approver`/`admin`) |
| `Topics` | `Building_Id` bigint, `Topic_Key` varchar, `Definition` text (JSON), `Active` boolean, `Sort` int |
| `Cases` | `Building_Id`, `Unit_Id`, `User_Id` bigint; `Ref` varchar unique; `Topic_Key`, `Title`, `Status`, `Handler` varchar; `Answers`, `Steps`, `Decision`, `Files` text (JSON); `Due_At` datetime |
| `Events` | `Case_Id`, `Building_Id`, `User_Id` bigint; `Kind` varchar; `Body` text; `Internal` boolean |
| `Notices` | `Building_Id`, `User_Id` bigint; `Title` varchar; `Body` text; `Audience` varchar (`all`/`owners`) |
| `Docs` | `Building_Id`, `User_Id` bigint; `Title`, `Category`, `Audience`, `File_Key`, `File_Name` varchar |
| `Login_Codes` | `Email` varchar, `Code_Hash` varchar, `Expires_At` datetime, `Attempts` int |
| `Sessions` | `Token_Hash` varchar unique, `User_Id` bigint, `Expires_At` datetime |

Stratus bucket: `bodycorp-files` (case attachments under `cases/<building>/<case>/`, documents under `docs/<building>/`).

## Topic definition (JSON in `Topics.Definition`)

```json
{"label": "Keep a pet", "audience": ["owner", "tenant"], "handler": "committee", "draft": true,
 "intro": "Tell the committee about the animal.",
 "fields": [{"key": "animal", "label": "What animal?", "type": "text", "required": true},
            {"key": "photo", "label": "Photo", "type": "file", "required": false}],
 "deadline": {"days": 21, "if_missed": "Treated as approved (BCCM Standard Module, animals)"},
 "steps": [{"title": "Check the request against the animals by-law", "rule": "By-law (animals) — DRAFT"}]}
```
Field types: `text`, `textarea`, `date`, `select` (with `options`), `checkbox`, `file`.

## Case statuses

`new` → `in_progress` → `waiting_on_resident` → `with_committee` → `decided` → `closed`. Decision JSON:
`{"outcome": "approved"|"approved_with_conditions"|"refused", "reasons": str, "conditions": str, "by": user_id, "at": str}`.
A refusal requires reasons.

## API (all under `/server/bodycorp_api`, JSON, `Authorization: Bearer <token>` unless marked public)

| Method + path | Body / query | Returns | Who |
|---|---|---|---|
| GET `/building?b=` | — | `building{slug,name,scheme_no,brand}`, `units[{id,label}]` | public |
| POST `/auth/start` | `{email,b}` | `{ok:true}` always | public |
| POST `/auth/verify` | `{email,code}` | `{token,user{id,email,name}}` | public |
| POST `/auth/logout` | — | `{ok}` | any |
| GET `/me?b=` | — | `user, roles[], memberships[{id,unit_id,unit_label,relation,status}], can{submit,handle,approve,admin,owner}` | any |
| POST `/me/name` | `{name}` | `user` | any |
| POST `/claims` | `{b, claims[{unit_id,relation}]}` | `memberships[]`; emails approvers | any |
| GET `/approvals?b=` | — | `pending[{id,user_email,user_name,unit_label,relation,created}]` | approver/admin |
| POST `/approvals/decide` | `{b,id,decision:"approve"|"reject",note}` | `membership`; emails person | approver/admin |
| GET `/members?b=` | — | `members[...]`, `roles[{email,role}]` | approver/admin |
| POST `/members/remove` | `{b,id}` | `{ok}` | approver/admin |
| POST `/roles` | `{b,email,role,on}` | `roles[]` | admin |
| GET `/topics?b=` | — | `topics[{key,label,intro,fields,draft,deadline}]` for the caller's relation | approved member |
| POST `/cases` | `{b,unit_id,topic_key,answers,files[{name,type,data}]}` | `case` | approved member of that unit |
| GET `/cases?b=&scope=mine|inbox` | — | `cases[{id,ref,title,status,unit_label,due_at,days_left,handler}]` | mine: member; inbox: handler |
| GET `/case?b=&id=` | — | `case` + `steps[{title,rule,done}]` + `events[]` (internal hidden from residents) + `topic` | owner of case or handler |
| POST `/case/step` | `{b,id,index,done}` | `case` | handler |
| POST `/case/status` | `{b,id,status,note}` | `case`; emails resident | handler |
| POST `/case/message` | `{b,id,body,to_resident}` | `event`; emails the other side | handler or resident (resident messages never internal) |
| POST `/case/decide` | `{b,id,outcome,reasons,conditions}` | `case`; emails resident | committee (handler `committee`) or manager (handler `manager`) |
| GET `/case/file?b=&id=&n=` | — | file bytes | as `/case` |
| GET `/notices?b=` / POST `/notices` / POST `/notices/delete` | `{b,title,body,audience}` / `{b,id}` | `notices[]` | read: member (tenants see `all` only); write: handler roles |
| GET `/docs?b=` / POST `/docs` / POST `/docs/delete` / GET `/docs/file?b=&id=` | `{b,title,category,audience,name,data}` | `docs[]` | as notices |
| POST `/admin/bootstrap` | header `X-Admin-Key`; `{seed:"altai", admin_email}` | building + counts | env key |
| POST `/admin/building` | `{b,name,scheme_no,brand}` | building | admin |
| POST `/admin/units` | `{b, units:[{unit_no,lot_no}]}` (adds missing) | `units[]` | admin |
| POST `/admin/topics` | `{b, key, definition, active, sort}` | `topics[]` | admin |
| POST `/cron/reminders` | header `X-Cron-Key` | `{sent:n}` | cron |

"Handler" for a case = a user with role `committee` (case handler `committee`) or `manager` (case handler
`manager`); `admin` can do everything in their building. Files download with the bearer header via fetch → blob.

---

### Task 1: Function skeleton, store and fake store

**Files:** Create `catalyst/catalyst.json`, `catalyst/.catalystrc` (project 694000000418109, env Development),
`catalyst/functions/bodycorp_api/{main.py,store.py,requirements.txt,catalyst-config.example.json}`,
`tests/fake_store.py`, `tests/conftest.py`, `.gitignore` additions (`catalyst-config.json`, `__pycache__`).

**Interfaces — Produces:** `store.Db` with `find(table, where: dict) -> list[dict]` (paged, values escaped),
`get(table, rowid) -> dict|None`, `insert(table, row) -> dict`, `update(table, row) -> dict`,
`delete(table, rowid)`, `put_file(key, bytes, type)`, `get_file(key) -> bytes|None`, `send_mail(to, subject, html) -> bool`.
`tests/fake_store.FakeDb` implements the same in memory (auto ROWID, records sent mail in `.outbox`).
`main.handler(request)` routes by `request.path` and method; `_respond(body, status)` as in the language app.

- [ ] Test: `test_unknown_route_returns_404_ok_false`; `test_find_escapes_quotes` (FakeDb + a unit test of the ZCQL builder `store.build_where({"Email": "a'b"}) == "Email = 'a''b'"`).
- [ ] Run, fail; implement; run, pass; commit `feat: function skeleton and store`.

### Task 2: Sign-in by email code

**Files:** Create `bodycorp_api/auth.py`, `tests/test_auth.py`.
**Interfaces — Produces:** `auth.start(db, email, building) -> None`, `auth.verify(db, email, code) -> (token, user)|None`,
`auth.user_for(db, bearer) -> dict|None`, `auth.logout(db, bearer)`. Codes: 6 digits, SHA-256 with `AUTH_SALT`
env, 10-minute expiry, 5 attempts, one live code per email (new start replaces). Sessions: 32-byte token, store
SHA-256, 30 days. Emails lower-cased and trimmed; invalid emails silently ignored.
- [ ] Tests: `test_code_works_once`, `test_sixth_attempt_fails`, `test_expired_code_fails`, `test_code_stored_hashed`
  (the plain code never appears in FakeDb), `test_start_sends_branded_email` (subject contains building name),
  `test_logout_kills_session`.
- [ ] Implement; pass; commit `feat: email code sign-in`.

### Task 3: People — claims, approvals, roles

**Files:** Create `bodycorp_api/people.py`, `tests/test_people.py`.
**Interfaces — Produces:** `people.context(db, user, building) -> {"roles": set, "memberships": list, "unit_ids": set(approved), "owner_unit_ids": set, "can": dict}`;
`claim(db, user, building, claims)`, `pending(db, building)`, `decide(db, actor_ctx, building, id, decision, note)`,
`remove(db, actor_ctx, building, id)`, `set_role(db, actor_ctx, building, email, role, on)`.
- [ ] Tests: `test_claim_creates_pending_and_emails_approvers`, `test_approve_gives_unit_access`,
  `test_reject_gives_no_access`, `test_remove_stops_access`, `test_one_login_two_units`,
  `test_non_approver_cannot_decide`, `test_claim_for_unit_of_other_building_refused`.
- [ ] Implement; pass; commit `feat: unit claims and approval`.

### Task 4: Topics and cases

**Files:** Create `bodycorp_api/cases.py`, `bodycorp_api/topics.py`, `tests/test_cases.py`.
**Interfaces — Produces:** `topics.for_member(db, building, ctx) -> list`, `topics.get(db, building, key) -> dict|None`;
`cases.create(db, building, user, ctx, unit_id, topic_key, answers, files) -> dict`, `cases.list_mine`, `cases.list_inbox`,
`cases.detail(db, building, ctx, id)`, `set_step`, `set_status`, `message`, `decide`. Ref = building `Settings.ref_prefix`
(Altai: `ALT`) + `-` + 4-digit sequence; retry on duplicate. Required fields enforced; unknown fields dropped.
- [ ] Tests: `test_create_sets_ref_handler_steps_and_due`, `test_missing_required_field_refused`,
  `test_resident_cannot_see_other_units_case` (404), `test_other_building_case_404`,
  `test_pending_member_cannot_submit`, `test_internal_note_hidden_from_resident`,
  `test_refusal_needs_reasons`, `test_handler_inbox_only_own_handler_type`, `test_new_case_emails_handlers`.
- [ ] Implement; pass; commit `feat: topics and tracked cases`.

### Task 5: Deadlines and reminders

**Files:** Create `bodycorp_api/deadlines.py`, `tests/test_deadlines.py`.
**Interfaces — Produces:** `deadlines.due_at(created_utc: datetime, days: int) -> datetime` (end of the Brisbane
day `days` later, returned UTC), `deadlines.days_left(due_utc, now_utc) -> int` (Brisbane calendar days),
`deadlines.remind(db, now_utc) -> int` (emails each building's handlers one digest of open cases due ≤ 7 days or overdue).
- [ ] Tests: `test_due_at_brisbane_end_of_day`, `test_days_left_crosses_midnight`, `test_remind_sends_one_digest_per_handler`,
  `test_closed_cases_not_reminded`.
- [ ] Implement; pass; commit `feat: deadlines and reminders`.

### Task 6: Notices, documents, admin, bootstrap seed

**Files:** Create `bodycorp_api/content.py`, `bodycorp_api/admin.py`, `bodycorp_api/seed_altai.json`, `tests/test_content.py`.
Seed: building `altai` "Altai on the Park", brand `{primary:"#1f4d3a", accent:"#c9a227", logo_url:"", footer:"Altai on the Park"}`,
`Settings {ref_prefix:"ALT", state:"QLD", timezone:"Australia/Brisbane"}`, placeholder units `1`–`10` (marked to replace with
the roll), topics (all `draft:true`): Keep a pet (committee, 21 days), Renovation or alteration (committee), Report an accident
or incident (manager), Maintenance or repair (manager), By-law concern or complaint (committee), Moving in or out / lift booking
(manager), Ask for body corporate records (committee, 7 days), Something else (manager).
- [ ] Tests: `test_tenant_never_sees_owner_notice_or_doc`, `test_only_handlers_post_notices`, `test_bootstrap_needs_key_and_is_idempotent`,
  `test_doc_upload_over_5mb_refused`.
- [ ] Implement; wire every route in `main.py`; pass whole suite; commit `feat: notices, documents, admin and Altai seed`.

### Task 7: Web client — portal

**Files:** Create `catalyst/client/{client-package.json, portal.html, portal.css, portal.js}`.
Screens (single page, hash routes): sign-in (email → code), set name, claim units, waiting for approval, home (alerts,
my requests, new request, documents), new request (topic picker → dynamic form from `fields`), request detail (status,
deadline, messages, decision), handler inbox (tabs: open / due soon / closed), handler case view (steps checklist with rule,
status, message with "send to resident" toggle, decide with reasons/conditions), approvals, members & roles, notices & documents
admin, building settings (admin). Branding from `/building` sets CSS variables `--brand`, `--accent`. Token in localStorage.
Every call: `api(path, opts)` that throws unless `body.ok === true`.
- [ ] Check in Chrome against Development after deploy (Task 9); commit `feat: portal client`.

### Task 8: Public product page

**Files:** Create `catalyst/client/index.html`, `catalyst/client/site.css`.
Plain-language page: problem (requests lost, deadlines missed), what it does (forms, inbox, steps & deadlines, records,
branded per building), how it works (3 steps), "Book a demo" mailto `edward@barebaysidelabs.com`, "Sign in to your building"
(asks building code → `portal.html?b=`). Product name only in one `<span class="product-name">`.
- [ ] Commit `feat: public product page`.

### Task 9: Deploy, seed, mail, cron, end-to-end check (coordinator)

- [ ] Create tables + bucket (MCP / console); list columns after creation and compare with the table above.
- [ ] `catalyst deploy` to Development; `POST /admin/bootstrap` with seed `altai`, admin `edward@barebaysidelabs.com`.
- [ ] Catalyst Mail sender set up and verified (console in Chrome); send a real code to Edward and read it.
- [ ] Cron daily 07:00 Australia/Brisbane → `POST /cron/reminders`.
- [ ] End-to-end in Chrome: sign in as admin; sign up as a second email, claim unit 4 as owner; approve; submit "Keep a pet";
  see it in the committee inbox with 21-day clock; tick a step; message resident; refuse without reasons (blocked) then approve
  with conditions; resident sees decision; a third account cannot open that case id.
- [ ] Commit and push to `origin main`.
