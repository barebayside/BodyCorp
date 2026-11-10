# The rules loop — design

2026-11-10 · Edward (owner), design agreed in conversation · builds on `2026-11-10-bodycorp-portal-design.md`,
`2026-11-10-committee-pipeline-design.md`, `2026-11-10-ai-compliance-helper-design.md` · law:
`docs/compliance/qld-committee-rules.md` (§8 = the 44 rules)

**Status: built 2026-11-10, not yet deployed.** Code: `rules.py` (the loop), `legal.py` (the lawyer's pack and
link), `pdfgen.py` (the pack PDF), hooks in `meetings.py`, `ai.py`, `mailer.py`, `store.py`. Pages: `#/rules…` in
`portal.js`, the lawyer's page `lawyer.html` + `lawyer.js` + `lawyer.css`. Tests: `tests/test_rules_loop.py` (21;
232 in all). Tables created on the test copy 2026-11-10 and listed back.
**Guidance, not legal advice.** Nothing here is a lawyer's opinion until a lawyer signs the pack.

## Why

Today the portal's rules live in two places that don't know about each other: the law file (prose) and each request
type's settings (deadlines, steps, emails). When the law, the CMS or the by-laws change, or the committee passes a
resolution ("no bikes in the lifts"), a person has to find every form, step, email and date it touches, get a lawyer
to look, get the chair to agree, change them, and tell people. Edward wants that to be one loop the portal runs, with
a check at the end of every step, so nothing reaches residents unchecked and the lawyer is billed once per change.

## The three layers (Edward)

| Layer | Holds | Shared by | Who changes it |
|---|---|---|---|
| **Law** | the state Act + regulation module, broken into rules once, lawyer-checked once | every building in that state and module (QLD · Standard) | the portal owner, through the loop |
| **Building** | the building's CMS, by-laws, passed resolutions and policies, as rules | that building only | the building's committee, through the loop |
| **Products** | forms, steps/stages, buttons, emails, phone alerts, calendar dates | that building only | only by applying a change |

**Products never hold law text.** A product links to a rule; the rule cites clauses. product → rule → clause.

## ICM invariants, applied to the data

| Invariant | How the data keeps it |
|---|---|
| One home per fact | A rule's wording lives only in its `Rules` row. Clause text lives only in its source (the law file; a document's `clauses.json` in Stratus; a motion's `Words`). A product's settings live only in `Topics`/`Topic_Versions`. A lawyer's verdict lives only in `Legal_Packs`/`Pack_Items`. |
| Links, not copies | `Rule_Links` (product → rule key), `Rules.Citations` (rule → clause, with the quote that is checked to be *in* the clause), `Changes.Source_Id` (change → document version or motion), `Rule_Proposals.Change_Id` (product draft → change). The one deliberate copy: the pack **snapshot** (what the lawyer was shown, frozen), because "what was sent" is a different fact from "what the draft says now". |
| Every step ends at a check | Each of the 7 stages has a gate the code enforces and a person's tick, written into `Changes.Stage_Checks`. Nothing moves to the next stage until both pass. |
| Status lives on disk = status rows | `Changes.Stage` + `Stage_Checks` say exactly where a change is; `Legal_Packs.Status`, `Notify_Plans.Status`, `Rules.Status` say the rest. No status is kept anywhere else (not in the page, not in memory). |
| Versions | A rule change is a new `Rules` row (same `Rule_Key`, `Version`+1), in force from its `Effective_From`; old versions stay. Product changes are `Topic_Versions` rows (as today), so **open requests keep their rules**. |

## Data (new tables; created in Catalyst first, then `store.SCHEMA` with the same limits)

The Data Store caps varchar at 255 (it silently shortens a longer `max_length`), so anything longer is `text`.
Reserved words avoided: `Trigger_Text`/`Action_Text` (TRIGGER, ACTION), `Rule_Section` (SECTION),
`Stage_Checks`, `Entry_Point`, `Product_Path`, `Reg_Module`.
`Building_Id = 0` means the law layer (shared); every read still filters by building **or** by
(law layer AND the building's state).

**`Rules`** — one row per version of a rule.
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | 0 = law layer |
| Layer | varchar(10) | yes | `law`, `building` |
| Jurisdiction | varchar(10) | yes | `QLD` |
| Reg_Module | varchar(20) | | `standard`, `accommodation`, `any` (law layer) |
| Rule_Key | varchar(60) | yes | `qld_sm_33`; a building rule: `b_no_bikes_in_lifts` |
| Version | int | yes | 1, 2, 3… per key |
| Rule_Section | varchar(100) | | "Owner applications" |
| Title | varchar(255) | yes | "Animal request received" |
| Trigger_Text | text | yes | what starts it |
| Action_Text | text | yes | what must happen |
| Who | varchar(255) | yes | as the source says it ("Secretary (chair if absent)") |
| Duty | varchar(60) | | the duty/position key the building's duty map turns into a person |
| Deadline_Text | varchar(255) | | "21 days" |
| Deadline_Days | int | | when it is a plain number of days |
| If_Missed | text | | "Deemed approved"; empty = the source doesn't say |
| Citations | text | yes | JSON `[{source: "law"|"change", clause, quote}]`; every quote is checked to be in its source |
| Status | varchar(20) | yes | `draft` (in a change), `applied`, `withdrawn` (dropped from its change) |
| Retire | boolean | | this version ends the rule |
| Effective_From | datetime | | set at apply; in force = latest applied version with Effective_From ≤ now |
| Change_Id | bigint | | the change that made this version |
| Ai_Drafted | boolean | | drafted by the AI helper |
| Approved_By | bigint | | the person who accepted an AI draft |
| Sort | int | | |

**`Rule_Links`** — a product implements a rule. Product → rule **key** (not version), so a link survives new versions.
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | the building whose product it is |
| Rule_Key | varchar(60) | yes | law or building rule |
| Product_Kind | varchar(20) | yes | `topic` (data: forms, stages, buttons, emails, deadlines) or `feature` (code: meeting notice, minutes, votes, phone alerts, calendar) |
| Topic_Key | varchar(60) | | for `topic` |
| Product_Path | varchar(255) | yes | inside the topic, in the AI helper's path language (`deadline`, `fields[key=animal]`, `stages[key=decided].buttons[key=notify].email`); for `feature`, its name (`meetings.notice`) |
| Note | varchar(255) | | |
| Created_By | bigint | | |

**`Changes`** — one per change going round the loop.
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | 0 = a law-layer change |
| Layer | varchar(10) | yes | `law`, `building` |
| Entry_Point | varchar(10) | yes | `outside` (new Act / regulation / CMS / by-laws) or `inside` (a resolution passed at a meeting or by a vote) |
| Source_Kind | varchar(20) | yes | `doc` (Doc_Versions), `motion` (Motions), `law_file` (the law file), `manual` |
| Source_Id | bigint | | the Doc_Versions or Motions row |
| Review_Id | bigint | | an AI by-law review (Rule_Reviews) whose proposals feed stage 03 |
| Title | varchar(255) | yes | |
| Summary | text | | |
| Stage | varchar(20) | yes | `read`, `rules`, `impact`, `legal`, `committee`, `apply`, `notify`, `done`, `cancelled` |
| Stage_Checks | text | | JSON `{read: {by, at, note}, rules: {...}, …}` — the person's tick per stage |
| Items_Key | varchar(255) | | Stratus: the stage-01 items (`rules/<building or law>/changes/<id>/items.json`) |
| Impact_Json | text | | stage 03: `{"<topic>|<path>": {decision: change|no_change|code, note}}` |
| Needs_Lawyer | boolean | | worked out at stage 03 (see below) |
| Lawyer_Why | text | | the reason, in plain words |
| Lawyer_Forced | boolean | | the chair (or an admin) asked for the lawyer anyway |
| Effective_From | datetime | | when the new rules start |
| Applied_At | datetime | | |
| Created_By | bigint | | |
| Error | varchar(255) | | |

**`Legal_Packs`** — the ONE pack per change round that goes to the lawyer (billed once).
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | 0 for law |
| Change_Id | bigint | yes | |
| Pack_No | int | yes | 1, then 2 if the lawyer asked for changes |
| Status | varchar(20) | yes | `sent`, `queried`, `signed`, `superseded` |
| Lawyer_Name, Lawyer_Email | varchar(255) | | |
| Token_Hash | varchar(128) | | SHA-256 of the link token; the token itself is never stored |
| Expires_At | datetime | | the link answers 404 after this (default 30 days) |
| Sent_At / Sent_By | datetime / bigint | | |
| Pdf_Key / Snapshot_Key | varchar(255) | | Stratus: the PDF, and the frozen JSON of what was sent |
| Signed_Name | varchar(255) | | typed by the lawyer, or recorded by the secretary |
| Signed_At | datetime | | |
| Signed_Via | varchar(10) | | `link` or `email` |
| Reply_Key | varchar(255) | | Stratus: the lawyer's emailed reply (PDF or image), when signed by email |
| Recorded_By | bigint | | who recorded an email sign-off |
| Note | text | | the lawyer's covering note |

**`Pack_Items`** — one per item in a pack; the lawyer's tick and comment live here.
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | |
| Pack_Id | bigint | yes | |
| Item_No | int | yes | order in the pack |
| Item_Kind | varchar(20) | yes | `rule`, `product`, `question` |
| Ref_Id | varchar(60) | | the Rules or Rule_Proposals row, or the question key |
| Title | varchar(255) | yes | |
| Tick | varchar(10) | | `ok`, `query` |
| Comment | text | | up to 2,000 characters (checked in code) |
| Ticked_At | datetime | | |

**`Notify_Plans`** — who is told, how, with what words; one per building per applied change.
| Column | Type | Req | Notes |
|---|---|---|---|
| Building_Id | bigint | yes | a law change makes one for every building in the state |
| Change_Id | bigint | yes | |
| Status | varchar(20) | yes | `proposed`, `approved`, `sent` |
| Groups_Json | text | | the proposed groups and why (`residents`, `committee`, `manager`) |
| Channels | varchar(100) | | `email,push,notice` |
| Notice_Audience | varchar(20) | | `all` or `owners` for the notice board |
| Subject | varchar(255) | | |
| Body | text | | |
| Recipients | text | | JSON user ids: THE approved list; Send goes to these and nobody else |
| Approved_By / Approved_At | bigint / datetime | | |
| Sent_By / Sent_At / Sent_Count | bigint / datetime / int | | |
| Notice_Id | bigint | | the notice-board post |
| Meeting_Id | bigint | | the committee meeting whose agenda listed it ("Rules changed since last meeting") |

**Existing tables, reused, not duplicated**
- `Doc_Versions` — an outside change's source (a CMS/by-laws version). Its clauses stay in its `clauses.json`.
- `Motions` — an inside change's source (a passed resolution). Its `Words` are the clause.
- `Rule_Reviews` — an AI by-law comparison; a change may link one (`Review_Id`) so its proposals become stage-03
  product drafts. **New rule:** `POST /ai/review/apply` refuses a review linked to a change: it applies through the
  loop (lawyer + chair).
- `Rule_Proposals` — every product draft (form, stage, button, email, deadline change) in the AI helper's validated
  shape. **New column `Change_Id` (bigint).** A draft made inside the loop (not from a review) has `Review_Id = 0`.
- `Topic_Versions` — applying a change writes versions in force from its date; open requests stay pinned.
- `AI_Usage` + `Settings.ai` — the AI helper's budget and off switch, unchanged.
- `Notices`, `Push_Subs`, `Mail_Queue` — the notify step sends through them.
- `Meetings.Agenda` — gains an item kind `rules_changed`.

## The loop: stages and their checks

Every stage = **a gate the code enforces** + **a person's tick** (`POST /rules/change/check {id, stage, note}`),
stored in `Stage_Checks`. Who ticks: the building's duty `rules` (default secretary) or an admin; on a law change,
the portal owner.

| # | Stage | What happens | Gate (code) | Check (person) |
|---|---|---|---|---|
| 01 | **read** | The source is split into items: a document → its clauses diffed against the version it replaces (new / changed / removed, free, `ai_review.diff_clauses`); a motion → its words as one decision; the law file → the 44 rules of §8. | at least one item | "Read correctly" |
| 02 | **rules** | Draft rule changes: trigger → action → who (position) → deadline → if missed, each citing items or the law file. New rule, new version of a rule, or retire one. The AI may draft (if switched on); every AI draft must be accepted by a person. | every draft has trigger, action, who and a citation whose quote is really in its source; every AI draft accepted; or "no rule changes" with a reason | "Rules drafted" |
| 03 | **impact** | Follow `Rule_Links` from every rule in the change to every form, step, button, email, deadline, phone alert and calendar date. Draft the changed and new products (`Rule_Proposals`, validated exactly like the AI helper's). Links can be added here. The portal works out whether the lawyer is needed. | every affected product has a decision: a valid, approved draft; "no change needed" with a note; or "needs a code change" (a `feature`) with a note | "Impact checked" |
| 04 | **legal** | ONE pack per change: every draft rule's wording + every affected form exactly as residents will see it, with example answers + the question "must this change be notified to owners by law?" (UNCONFIRMED). Sent by email with the PDF attached **and** a private link (no sign-in, expires). The lawyer ticks or queries each item, comments, and signs (name, date). If they reply by email instead, the secretary records "signed off by email" and attaches the reply. A query sends the change back to stage 02 or 03 and a new pack follows. | the latest pack is signed; **or** the lawyer is not needed and not forced (reason recorded) | (the signature is the check) |
| 05 | **committee** | The chair signs off (or the position the building's duty map sets for `rules_signoff`). A law change: the portal owner signs. | stage 04 passed | the sign-off |
| 06 | **apply** | Draft rules become applied versions; product drafts become `Topic_Versions`; all in force from the change's date. Open requests keep their rules. | stages 04 and 05 passed | pressing Apply |
| 07 | **notify** | The portal proposes WHO needs to know and HOW (below), with draft wording. The responsible person sees the exact list, ticks/unticks, edits the words, presses Send. | Send goes ONLY to the saved, approved list; anyone who has left the building since is dropped | pressing Send |

**When is the lawyer needed** (stage 03, `rules.lawyer_needed`, in plain words on the screen):
- law-layer change → always ("Changes to the Queensland rules are always checked by a lawyer");
- outside change (new CMS / by-laws) → always;
- inside change (a resolution) → only if it changes a form residents fill in, a deadline or its outcome, a vote rule,
  an email to residents, or adds/retires a request type. Otherwise "Only committee steps change …: the lawyer can be
  skipped". The chair or an admin can **force** the lawyer.
- Deviation from the conversation: the reason is worked out by these rules, not by the AI. It is cheaper, always
  available (AI off) and can't be talked round. The AI isn't needed to say why.

**Who is told** (stage 07, `rules.notify_proposal`):
| What the change touches | Proposed recipients | Channels |
|---|---|---|
| anything resident-facing (a form, a deadline, an email to residents, a request type offered or retired) | the owners/tenants who can use the affected request types + committee + manager | email, phone alert, notice board post (owners or all) |
| committee/manager process only | committee + manager | email, phone alert |
| a law change (Act deadline) | committee + manager; residents only if a resident-facing product changes | email, phone alert (+ notice when residents) |

**Every change, always:** it stays in the change history (`GET /rules/changes`), and the next committee meeting's
agenda gets one item "Rules changed since the last meeting" listing each applied change (`Notify_Plans.Meeting_Id`
marks it listed), which the drafted minutes carry under item 7.

**Whether some changes must by law be notified:** UNCONFIRMED. Every pack asks the lawyer (a `question` item).

## Routes (all `{ok}`; committee roles and admins; residents and the manager 403; another building's ids 404)

```
GET  /rules                               -> {in_force: [rule], changes: [summary], motions_to_implement, can_start,
                                              can_law, module_note, lawyer}
GET  /rules/rule {key}                    -> {rule, versions, links, layer}
POST /rules/seed {from: "qld"}            (portal owner) the 44 rules as a law-layer change at stage 01, and
                                          Altai's request types linked to the rules they implement (idempotent)
POST /rules/links {rule_key, topic_key?, product_kind, product_path, note, remove?}
GET  /rules/changes                       -> {changes}
POST /rules/changes {source_kind: doc|motion|manual, source_id?, title, summary, layer?: law}  -> {change}
GET  /rules/change {id}                   -> {change, stages, items, rules, impact, proposals, packs, notify, can}
POST /rules/change/check {id, stage, note}            the person's tick; refused (400) while the gate fails
POST /rules/change/rule {id, rule_key?, title, trigger, action, who, duty, deadline_text, deadline_days,
                         if_missed, citations, retire?, remove?, rule_id?}        draft / edit / drop a rule
POST /rules/change/ai-draft {id}          (AI on) the AI drafts rules from the items; each a proposal to accept
POST /rules/change/rule/accept {id, rule_id}
POST /rules/change/product {id, topic_key, kind, title, why, changes, citations}   a product draft (validated)
POST /rules/change/product/decide {id, proposal_id, decision: approve|reject, note}
POST /rules/change/impact {id, key, decision: no_change|code, note}
POST /rules/change/lawyer {id, force: true|false}     the chair or an admin
POST /rules/pack/send {id, lawyer_name, lawyer_email, days?}  -> {pack, link}   (email + PDF + link)
POST /rules/pack/email-signoff {pack_id, name, date, file}     the secretary records an emailed sign-off
POST /rules/change/reopen {id, to: rules|impact}      after a query
POST /rules/change/signoff {id}           stage 05 (the chair / the rules_signoff position / owner for law)
POST /rules/change/apply {id, effective_from?}        stage 06
GET  /rules/notify {id}                   -> {plan, candidates}   the proposed list, ticked
POST /rules/notify {id, recipients, channels, subject, body, notice_audience}  -> saves the approved list
POST /rules/notify/send {id}              stage 07
GET  /rules/pack/pdf {pack_id}            the PDF (committee)
POST /rules/change/cancel {id}

PUBLIC (no sign-in; the token is the key; expired, wrong or superseded token = 404, as if it didn't exist)
GET  /pack {t}                            -> {pack, items, building_name, change}   only THAT pack
GET  /pack/pdf {t}
POST /pack/item {t, item_id, tick: ok|query, comment}
POST /pack/sign {t, name, note}           refused while any item is queried or unticked
POST /pack/comments {t, note}             "send my comments": status queried, the secretary is emailed
```

## Screens (approved park look: serif headings, hairline rows, no cards-as-pills, Rust only for overdue)

1. **Rules** (`#/rules`, committee): "Changes" (title, entry, stage) · "Passed motions to implement" (a passed
   resolution with no change yet: *Start a change*) · "Rules in force" (law and building, each with its source
   label: "Queensland law, not yet lawyer-checked" until its change was signed).
2. **One change** (`#/rules/change/<id>`): the seven stages as a numbered hairline list, each with its gate state and
   who ticked it; the current stage open below with its form. Stage 04 shows the pack items with the lawyer's ticks
   and comments, "Copy link", "Open the PDF", "Record an emailed sign-off".
3. **One rule** (`#/rules/rule/<key>`): versions (in force / coming / replaced), citations quoted, linked products.
4. **Start a change** (`#/rules/new`).
5. **Notify** (inside stage 07): groups and why, the list of people with ticks, channels, the words, Send.
6. **The lawyer's page** (`lawyer.html?t=…`): no sign-in, the building's name, each item with its wording and each
   form drawn as residents see it (example answers), Tick / Query + comment per item, "Sign off" (name), "Send my
   comments", "Download the PDF". "Guidance for the lawyer: this pack is what the portal will do; your sign-off is
   recorded with your name and the date."

## PDF

`pdfgen.py` writes the PDF itself (pure Python, no dependency): Helvetica, A4, wrapped text, page numbers. Checked
locally with `pypdf` (already a dependency) reading the text back. Reason: Catalyst's deploy installs with
`--only-binary=:all:` for manylinux2014; a pure-Python writer can't fail there and needs no Pillow. Characters
outside Windows-1252 print as "?" (forms and rules are plain English). The lawyer's link also prints cleanly
(Print → Save as PDF) as a fallback.

The email carries the PDF as an attachment (Catalyst Mail `attachments`, a file object). If the email fails it is
queued **without** the attachment (the queue holds HTML only); the link in it still opens the pack and its PDF.

## AI

Off per building unless switched on (`ai.flags`, same gate, same budget). It drafts stage-02 rules from the items
(Haiku 5.5, structured JSON, citations checked like the helper's) — each a draft a person must accept. The notify
wording is a template, not AI. Nothing the AI writes is applied without the stage checks.

## Not in this build

Automatic change creation when any motion passes (the Rules screen lists passed motions instead: not every
resolution changes a rule) · calendar-date products (the compliance calendar isn't built; links of kind `feature`
name them) · a law change re-mapped to the Accommodation Module · lawyer billing.

## UNCONFIRMED (ask the lawyer / Edward)

- Whether a rule change must be notified to owners, and how (the pack asks).
- That a resolution which changes no resident form may skip the lawyer (Edward's call, made in conversation).
- That the chair is the right default sign-off (the law gives the chair no extra authority, law §3; a committee
  vote may be the better default; the duty map can change it per building).
- The 44 rules come from the law file, itself DRAFT and unchecked; they are seeded as a law change at stage 01 so the
  first lawyer pack checks all 44 once.
- Link expiry of 30 days, and that a typed name is an acceptable sign-off.
