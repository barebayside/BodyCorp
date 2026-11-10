# Committee working view — design

2026-11-10 · Edward (owner) · builds on `2026-11-10-bodycorp-portal-design.md` · law: `docs/compliance/qld-committee-rules.md`

## Why

The v1 inbox lists requests but doesn't say who should act next, what to send, or what the law does if the
committee is silent. Edward wants a ticketing view (like Zoho Desk): committee positions see every request
by stage, press a button that emails the right person a link back to the request and moves it on, vote
outside meetings, run meetings, get minutes drafted, and turn resolutions into tasks.

## Rules that shape everything

- **Silence is shown first.** Each request type's data says what happens if nobody decides in time, in plain
  words, with the date and its legal source. It is the first thing on the case page (big, with a live
  countdown, red in the last 3 days), the first line of every email to approvers, and a label on each board
  card ("auto-approves 1 Dec", "treated as not agreed 22 Dec").
- **Everything a by-law can change is data** in the topic Definition JSON, so an AI can later propose edits.
- **Who does which step is a per-building setting** (`Buildings.Settings.duties`), because the law gives the
  treasurer almost nothing and names no minute-taker (law §3). Defaults: secretary acknowledges, sends
  notices and votes, calls meetings, takes minutes, answers records requests; chair runs meetings; every
  voting member votes.
- Residents never see votes, internal notes, tasks, meetings or minutes drafts. Other buildings get 404.

## Positions

Roles gain `chair`, `secretary`, `treasurer`, `member` (ordinary member). Holding any of these makes a person
a **voting member** (one vote however many positions, SM s 65(5)). `committee` stays as committee access
without a vote (e.g. a body corporate manager, SM s 12); `manager`, `approver`, `admin` are unchanged.
Members who owe a body corporate debt are listed in `Settings.unfinancial` and can't vote (SM s 64, s 67)
but still count to quorum (SM s 60(4)). The board shows a committee check (3–7 voting members, chair,
secretary and treasurer filled: SM s 9) as a warning, not a block.

## Topic definition, extended (backward compatible)

```json
"deadline": {"days": 21, "from": "request", "outcome": "deemed_approved", "card": "auto-approves",
             "banner": "If the committee hasn't decided by {date}, this pet request is treated as APPROVED.",
             "citation": "SM s 58A(2), s 69(3)(b)", "if_missed": "...", "extend_to_days": 84},
"vote": {"animal": true, "if_passed": "approved", "if_defeated": null, "if_no_result": "deemed_approved"},
"stages": [{"key": "received", "label": "Received", "owner": "acknowledge", "status": "new",
            "instructions": "...", "rule": "SM s 58A",
            "buttons": [{"key": "acknowledge", "label": "Acknowledge", "next": "checking",
                         "email": {"to": "resident", "subject": "...", "body": "Hi {name} ... {link}"},
                         "note": "optional|required", "needs_decision": false, "opens_vote": false}]}]
```

`outcome` is `deemed_approved`, `not_agreed` or `none` (a duty deadline, like records in 7 days). Stage `owner` is a
duty key (looked up in the building's duty map) or a role name. If nobody holds it, any voting member may act.
Placeholders: `{name} {ref} {title} {unit} {building} {link} {date} {if_missed} {note} {decision}`.
Old topics without `stages` get one generic pipeline from code. `POST /admin/topics {from_seed:"altai"}`
merges the seed's `stages`, `deadline` and `vote` into an already-loaded building's topics (migration).

## Phase A — the pipeline

- `Cases.Stage` (new column) holds the stage key; a new case starts at the first stage. Entering a stage
  sets the case status from the stage.
- `POST /case/action {b,id,action,note}` → checks the presser holds the stage's owner position, sends the
  button's email (mailer: queued and retried on failure), moves the stage, logs an event (and a resident-visible
  message when the email went to the resident).
- `GET /board?b=` → `{columns:[{key,label,cards:[...]}], checks, module}`; each card has ref, title, unit,
  stage owner, days left and `missed_label`. Columns are the stages of every committee/manager topic, merged in order.
- The daily reminders also apply deemed outcomes: a case past its deadline with `outcome` deemed_approved or
  not_agreed is decided automatically, recorded, and the resident told (SM s 69(4), s 58(7)).

## Phase B — votes, meetings, minutes, tasks

- **Vote outside a meeting** (law §5, SM s 68–70): from a case or standalone; the secretary (duty `vocm`) sends
  it to all committee members, with advice to owners at the same time. Closes 21 days after the notice, or
  21 days after the request for an animal request. Ballot yes/no/abstain, or declare a conflict (no vote).
  E = voting members − unfinancial − conflicted. Passed when yes > E/2; defeated when no ≥ E/2; otherwise at
  close: not agreed, or deemed approved for an animal request. The result is recorded, applied to the case via
  the topic's `vote` data, the record sent to members and owners, and listed for confirmation at the next meeting.
- **Committee meeting** (law §4): notice at least 7 clear days ahead (2 only when all voting members agreed,
  recorded), agenda auto-adds confirming the last minutes and each unconfirmed vote; notice to committee
  members and advice to owners. Attendance in person/electronic/proxy; quorum = ceil(voting members ÷ 2),
  proxy holder counts 2, unfinancial members count. Motions need a quorum; pass on yes > no; tie lost.
- **Minutes** are drafted from the meeting (SM s 71(6) fields), editable, due 21 days after the meeting; issue
  is blocked until the secretary's name and contact address are set; issued minutes go to members and owners
  and into Documents (owners). Resolutions get a 7-day opposition window (SM s 72–73) only when the building's
  module is recorded as Standard; animal approvals and routine items are exempt. With no module recorded,
  admins see "Module not recorded — committee rules are guidance only".
- **Tasks** from resolutions: assignee a person or a position, due date, done. "My tasks" lists them; the
  daily reminders include tasks due within 7 days or overdue.

## Tables (new)

`Motions`, `Ballots`, `Meetings`, `Tasks`, plus `Cases.Stage`. Columns are in `store.SCHEMA`.

## Not in this build

General meetings and AGM elections; notices of opposition as a form; the 15 km place rule; owner opt-outs
(everyone approved gets owner advice); spending limits.
