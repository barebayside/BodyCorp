# Five features: design

2026-11-10 · Edward (owner) approved all five ("do those five", NEXT.md 0c) · builds on
`2026-11-10-bodycorp-portal-design.md` (base) and `2026-11-10-committee-pipeline-design.md` (stages, positions,
votes, meetings, minutes, tasks) · law: `docs/compliance/qld-committee-rules.md` (cited as "law §n")

**Status: DRAFT, guidance not legal advice.** Every legal date or limit below is cited to the law file. Anything
the law file does not hold is marked **UNCONFIRMED**, or **VERIFIED** where I read it on a qld.gov.au page on
10 Nov 2026 (link given). A VERIFIED item still has to be added to the law file before it leaves Draft.

The AI compliance helper spec does not exist yet. Feature 3 defines the small AI plumbing it needs (`ai.py`,
`Ai_Runs`); whichever of the two is built first creates it and the other reuses it.

## What every feature reuses (no new machinery)

| Existing piece | Used for |
|---|---|
| `Tasks` (+ "My tasks", daily digest) | Calendar items, contractor expiries, "put on general meeting agenda", vacant seats |
| Duty map (`Buildings.Settings.duties`) | Who owns each calendar item / roll change / contractor job. New duty keys below |
| Topics + stages + `deadlines.due_at` | Roll change is a request type with a 14-day clock; silence banner shown first |
| `Motions` / `Ballots` / `Meetings` | Spending approval goes through the existing vote outside a meeting or meeting motion |
| `Events` | History on every case (AI drafts, roll recorded, work order linked) |
| `mailer.send` / `Mail_Queue` / `Failures` | Every email below; failures logged as today |
| `/cron/reminders` | Generates the next year, applies membership end dates, expiry reminders. Each step is timed; if the 30-second limit gets close, the rest moves to a second cron `/cron/calendar` |
| Web Push (home-screen app, NEXT 0b) | Push event names below are sent through the same notify call once it exists; email is always the fallback |

**New duty keys** (defaults in `committee.DUTIES`, changeable per building): `agm` → secretary,
`calendar` → secretary, `roll` → secretary, `contractors` → manager, `fire_safety` → manager,
`insurance` → treasurer, `plant` → manager.

**New building facts** (`Buildings.Settings`, admin sets them, each with its evidence where the law asks):
`fy_end` ("06-30"), `lots` (int; the CMS figure, not a count of placeholder units), `levy_due_dates`
(["08-01", …]), `has_pool`, `has_lift`, `monthly_recs` (ordinary resolution made, SM s 170), `bcm_funds`
(a BCM runs the funds), `ch3pt5` (BCM engaged instead of a committee, law §2B), `limits` (see feature 4),
`ai` ({enabled, monthly_cap: 300, per_user_daily: 10}), `urgent` ({after_hours_phone, words: [...]}),
`library_for_owners` (false).

**Look (all screens):** the approved park look. Light serif headings (Source Serif 4), Public Sans body,
11–12px uppercase labels. Lists are full-width rows split by 1px hairlines (Gardner Vaughan / Netstrata rows).
No cards, no pill tags, no shadows. Rust (#C02B0A) only for overdue or a missed legal deadline. Content shows
without animation. Phone first.

---

## 1. Compliance calendar

The building's legal year as dated tasks with owners and reminders. Generated from `fy_end` and the module;
the list of obligations is data per building.

### Stories
- **Secretary:** I see the year on one page and get reminded before the nomination window opens and closes.
- **Treasurer:** I'm told 30 days before each levy due date to send the notices.
- **Building manager:** I see insurance, fire safety, lift and pool dates and tick them off with proof.
- **Chair / any voting member:** I see what is overdue and who owns it.
- **Admin:** I switch items on or off and change dates or owners for one building without code.

### The obligations (seed `compliance_qld.json`, strata fill-in layer)

F = financial year end. Dates count per law §8 "Counting days". The weekend move to the next business day
(`business_day: true`) is only for "within N days after" deadlines. "At least N days before" deadlines
(nomination notice, levy notice, AGM notice) never move later; if one lands on a weekend the task is due the
business day **before** (my reading of AIA s 38, **UNCONFIRMED**).

| Key | Item | When | Owner (duty) | Source |
|---|---|---|---|---|
| `nominations_notice` | Nomination notice to every owner on the roll, inviting motions, with the debtor warning | Window opens F − 6 weeks, must be sent by F − 3 weeks | agm | SM s 16(2),(3); s 86(8); law §2, §8.41 |
| `nominations_close` | Nominations and AGM owner motions close | F | agm | SM s 16; s 86(5)–(8); law §2, §6 |
| `budgets` | Committee prepares proposed admin and sinking fund budgets for the AGM | Before the AGM notice; **date UNCONFIRMED** (law gives none) | accounts | SM s 160(5); law §3 |
| `sinking_forecast` | Sinking fund budget covers likely spending for at least 9 years after this FY; a professional forecast is not required | With `budgets` | accounts | **VERIFIED**, not in law file: [qld.gov.au Sinking fund](https://www.qld.gov.au/law/housing-and-neighbours/body-corporate/finance-insurance/funds/sinking) (updated 7 Feb 2018). How often to refresh a professional forecast: **UNCONFIRMED** |
| `audit` | Audit of the statement of accounts | Before the AGM notice; **date UNCONFIRMED** | accounts | SM s 176; law §3 |
| `agm_notice` | AGM notice with ballot papers, voting papers and the register of reserved issues | AGM − 21 days. **UNCONFIRMED for an AGM**: the law file gives 21 days' notice only for a requested EGM | agm | SM s 22, 27, 230; s 91 (EGM); law §3, §6, §7 |
| `agm_held` | AGM held | Within 3 months after F | agm | SM s 83; law §8.42 |
| `agm_gaps` | If the AGM left an executive seat empty or under 3 members: call an EGM within 1 month, hold within 2 months | Made when the secretary records "AGM left gaps" | agm | SM s 41; law §2, §8.8 |
| `levy_notice` | Contribution notice to owners | 30 days before each `levy_due_dates` entry | accounts | SM s 163; law §3, §8.44 |
| `monthly_recs` | Reconciliation for each fund account | 21 days after each month end. Only when `monthly_recs` and not `bcm_funds` | accounts | SM s 170; law §3 |
| `fee_units` | Records and certificate fees change (fee units × new value) | 1 July each year | admin | law §7 |
| `records_disposal` | Yearly disposal review (never minutes, roll, registers, policies) | 1 month after the AGM (**practice choice**) | records | SM s 231; law §7, §8.40 |
| `bcm_quarterly` | Ch 3 pt 5 BCM report to every owner | 21 days after each quarter. Only when `ch3pt5` | admin | SM s 74–78; law §2B |
| `insurance_renewal` | Renew compulsory insurance: common property, body corporate assets, public risk (at least $10 million per event), every building that contains a lot | Policy expiry date (a fact the building enters), reminders 60/30/7 days | insurance | **VERIFIED**, not in law file: [qld.gov.au Compulsory insurance](https://www.qld.gov.au/law/housing-and-neighbours/body-corporate/finance-insurance/insurance/compulsory) (updated 9 Jul 2025). Renewal is within the committee's power above its spending limit (SM s 172, law §6) |
| `insurance_valuation` | Independent replacement-value valuation | **UNCONFIRMED** (commonly every 5 years; the qld.gov.au page I needed returned 404) | insurance | UNCONFIRMED |
| `occupier_statement` | Occupier statement for the prescribed fire safety installations; copy to the Queensland Fire Department commissioner within 10 business days | Yearly (interval set by QDC MP6.1) | fire_safety | **VERIFIED**: Building Fire Safety Regulation 2008 s 55A(1),(3) ([legislation](https://www.legislation.qld.gov.au/view/whole/html/inforce/current/sl-2008-0160)); [business.qld.gov.au Fire safety installations](https://www.business.qld.gov.au/industries/building-property-development/building-construction/laws-codes-standards/queensland-development-code/fire-safety-installations) (updated 10 Jul 2026: "yearly occupier's statement"; body corporate decides who signs) |
| `evacuation_practice` | Evacuation practice, with a record (date, start and end times) | At intervals of not more than 1 year | fire_safety | **VERIFIED text**: BFSR s 44(2)(c); evacuation coordination instructions s 38(1) and general evacuation instructions s 35(1) also ≤ 1 year. **How these apply to a residential class 2 building and who is "the occupier": UNCONFIRMED** (QFD has a separate low-occupancy class 2 info sheet) |
| `fire_maintenance` | Routine fire safety installation maintenance | Contractor's schedule (data). Interval **UNCONFIRMED** | fire_safety | QDC MP6.1 (not read) |
| `lift_registration` | Lift item registration renewal | Due 31 January each year. Only when `has_lift` | plant | **VERIFIED**: lifts are registrable plant, WHS Regulation 2011 sch 5 pt 2 ([business.qld.gov.au](https://www.business.qld.gov.au/running-business/whs/plant-registration/required), updated 22 Jul 2019); "Renewals are due on 31 January each year" ([business.qld.gov.au](https://www.business.qld.gov.au/running-business/whs/plant-registration/register-renew)). **Whether the body corporate is the registration holder for Alatai's lifts: UNCONFIRMED** (the 2026 High Risk Plant amendment page returned 403) |
| `pool_certificate` | Shared pool safety certificate | Valid 1 year; reminder 30 days before expiry. Only when `has_pool` | plant | **VERIFIED**: [QBCC Inspect and certify a pool](https://www.qbcc.qld.gov.au/home-owner-hub/swimming-pools/inspect-certify-pool) ("1 year for shared pools"; needed when selling or leasing; reviewed 30 Aug 2021). That the body corporate holds it: **UNCONFIRMED** |

Shown on the calendar but not generated (they already have their own clocks): committee minutes in 21 days
(SM s 71, pipeline), records requests in 7 days and certificates in 5 business days (Act s 205, records topic),
roll updates in 14 days (feature 5), contractor expiries (feature 4). Not built: debt recovery within 2 months
after a levy is 2 years unpaid (SM s 166(2)) needs levy data (StrataMax, later).

Module: Standard by default. If `regulation_module` is "accommodation" every citation shows "re-map to AM:
UNCONFIRMED" (law §1). If it is not recorded, the calendar shows "Module not recorded: dates are guidance only".

### Definition (data, one `Obligations` row each)
```json
{"label": "Nomination notice to owners", "owner": "agm",
 "anchor": "fy_end", "due_offset_days": -21, "opens_offset_days": -42, "repeat": "yearly",
 "business_day": "before", "remind_days": [7, 1], "needs": null, "modules": ["standard", "accommodation"],
 "if_missed": "Nominations for the committee can't be validly invited for this AGM.",
 "citation": "SM s 16(2),(3); law §8.41", "source": "law", "source_url": "", "evidence": "required"}
```
`anchor`: `fy_end` | `fixed` ("MM-DD") | `monthly` | `quarterly` | `levy_dates` | `fact` (a date the building
enters, e.g. `insurance_expiry`) | `after:<key>` (e.g. after `agm_held`). `needs`: a fact that must be true
(`has_pool`). `source`: `law` | `verified` | `unconfirmed`, shown as a label on every row.

### Screens
- **Calendar** (committee, manager, admin): serif heading "The year at Altai", FY dates under it. One hairline
  row per item, grouped by month: date on the left in serif, label and owner in the middle, status on the
  right ("opens 19 May", "due in 6 days", "done 2 Jun"). Overdue rows in Rust. Small source label
  ("Law", "Checked on qld.gov.au", "Not confirmed"). Tap a row → task page: what to do, if missed (first),
  citation and link, "Mark done" with a note and an optional file (proof).
- **Calendar settings** (admin): rows of obligations with on/off, owner, offset and the building facts above.

### Data
New table **`Obligations`**: `Building_Id` bigint M · `Obligation_Key` varchar(60) M · `Definition` text M
(JSON, ≤10,000) · `Active` boolean M · `Sort` int.

New columns on **`Tasks`**: `Obligation_Key` varchar(60) · `Period` varchar(20) ("FY2027", "2027-03",
"2027-Q1") · `Opens_At` datetime (not before) · `Gen_Key` varchar(120) ("{building}:{key}:{period}",
checked in code before insert so a rerun makes nothing twice) · `Evidence` text (JSON: note, file keys,
who, when).

### Routes
- `GET /calendar?b=&fy=2027` → `{fy: {start, end}, module_note, facts_missing: ["levy_due_dates"],
  items: [{id, key, label, owner_label, opens_on, due_on, status: "upcoming|open|due_soon|overdue|done",
  if_missed, citation, source, source_url, kind: "task|clock", link}]}`
- `POST /calendar/generate {b, fy}` (secretary, admin) → `{created, skipped}`
- `GET /calendar/obligations?b=` / `POST /calendar/obligation {b, key, definition?, active?}` (admin) →
  `{obligation}`. A change affects future generations; `regenerate_open: true` also moves open tasks.
- `POST /admin/obligations {b, from_seed: "qld"}` (admin) → `{loaded}`
- `POST /building/facts {b, ...facts}` (admin) → `{facts}`
- `POST /task/done` (existing) gains `evidence {note, file}`.

### Emails / push
- Daily digest gains calendar items at each `remind_days` step and when a window opens
  ("The nomination window opens today; send by 9 June"). Push `calendar.due_soon`, `calendar.overdue`.
- Day after F: `/cron/reminders` generates next year if missing, and emails the secretary "Next year's
  calendar is ready".

### Tests
- FY end 30 June 2027: nomination task opens 19 May, due 9 June (3 weeks before); AGM due 30 Sept; levy
  notices 30 days before each due date. A "before" deadline landing on a Saturday is due the Friday; a
  "within" deadline landing on a Saturday is due the Monday.
- Generate twice → no duplicates. Pool item absent when `has_pool` is false. `monthly_recs` absent when
  `bcm_funds`. `ch3pt5` makes the BCM quarterly items.
- Owner resolves through the duty map; nobody holding it → any voting member (as today).
- Residents get 403; another building's tasks 404.
- Every seed item has a citation and a `source`; any `source: law` item's citation names an SM/Act section.

---

## 2. Past-decisions library and standard conditions

### Stories
- **Committee member:** before I vote on a pet request I see the 5 most similar past decisions and the
  conditions we used.
- **Secretary:** I save "standard conditions" per request type and add them to a decision in one tap.
- **Chair:** I search every past decision by type, outcome, clause or date, to be consistent (the committee
  must act reasonably, Act s 100–101, law §3).
- **Owner** (only if `library_for_owners`): I can read anonymised outcomes (no names, no unit numbers).

### How it works
- When a case is decided (by a person, a vote, or a deemed outcome) or a motion is settled, one `Decisions`
  row is written: topic, outcome, how, date, clauses (the topic's citation plus any by-law the handler names),
  conditions, and an **anonymised summary** built from the answer fields the topic marks `"library": true`
  (e.g. animal type, size; never name, email, phone or unit). Unit numbers are replaced with "a lot".
- Committee and manager see a link to the real case; owners never do.
- **Similar decisions** on a case (below the silence banner and the stage, never above): same topic first,
  then overlap of library answers, shared clauses, then newest. Top 5. Plain code, no AI.
- **Standard conditions**: rows per request type. On the decide screen each shows with a tick box; ticking
  adds the words to the decision's conditions. Which ones were used is recorded.

### Screens
- **Decisions** (committee, manager; owners if switched on): serif heading, a search line, filters as plain
  text links (type, outcome, year). Rows: date in serif, request type and outcome, one-line summary, clause on
  the right.
- **Case page**: "Decided before" section, 5 hairline rows, each "Approved with conditions · 2026 · small dog
  kept inside", tap to read.
- **Standard conditions** (secretary, chair, admin): rows per request type, edit in place.

### Data
New table **`Decisions`**: `Building_Id` bigint M · `Source_Key` varchar(40) M ("case:123", "motion:45",
checked in code, one row per source) · `Case_Id` bigint · `Motion_Id` bigint · `Topic_Key` varchar(60) ·
`Outcome` varchar(30) M (approved, approved_conditions, refused, deemed_approved, not_agreed, passed,
defeated) · `How` varchar(20) M (handler, vocm, meeting, deemed) · `Decided_On` date M · `Clauses`
varchar(255) · `Summary` text M (≤2,000 in code) · `Conditions` text · `Condition_Ids` varchar(255) ·
`Library` text (JSON of the library answers, for matching) · `Hidden` boolean (secretary can hide one).

New table **`Standard_Conditions`**: `Building_Id` bigint M · `Topic_Key` varchar(60) M · `Title`
varchar(255) M · `Words` text M (≤2,000 in code) · `Citation` varchar(255) · `Sort` int · `Active` boolean M
· `Created_By` bigint.

### Routes
- `GET /decisions?b=&q=&topic=&outcome=&clause=&from=&to=` → `{decisions: [{id, topic_label, outcome,
  outcome_label, how, decided_on, clauses, summary, conditions, case_ref (committee only)}], total}`.
  Filtering is done in code over the building's rows (paged by `find`).
- `GET /case/similar?b=&id=` → `{similar: [same shape, max 5]}`
- `POST /decision/edit {b, id, summary?, clauses?, hidden?}` (secretary, chair) → `{decision}`; refuses a
  summary containing a name, email or unit number from that building.
- `GET /conditions?b=&topic=` → `{conditions}`; `POST /conditions {b, id?, topic_key, title, words,
  citation, active}` (secretary, chair, admin) → `{condition}`
- `POST /case/decide` (existing) gains `condition_ids: []`.
- `POST /admin/decisions/backfill {b}` (admin) → `{created}` for cases and motions decided before this build.

### Emails / push
None new. The decision email to the resident already exists; it now includes the chosen conditions.

### Tests
- Deciding, a VOCM result and a deemed outcome each write exactly one row; a rerun writes none.
- Summary never contains the resident's name, email, phone or unit label (fixture with all four).
- Similar: same topic ranks above others; never returns another building's rows.
- Owners: 403 unless `library_for_owners`; even then no `case_ref`.
- Ticking two standard conditions puts both texts into the decision and their ids into `Condition_Ids`.

---

## 3. Plain-words requests

### Stories
- **Resident (owner or tenant):** I type "my ceiling is dripping from upstairs" and get the right form
  already filled in, with one question for what's missing.
- **Resident, urgent:** a leak or a safety risk tells me straight away to call the after-hours number, and the
  building manager is told the moment I send.
- **Handler (manager, secretary):** I get a drafted reply I can edit and send, or ignore.
- **Admin:** I set a monthly cap per building and see how much is used.

### How it works
1. Resident types freely (≤2,000 characters) on "Start a request". The old topic list stays under it.
2. `ai.ask` sends **claude-haiku-5-5**: this building's topics the person may use (labels, field
   definitions), the text with emails and phone numbers removed, and the building's urgent words. It must
   answer JSON: `{topic_key, confidence, answers, missing, question, urgency, urgency_reason}`.
3. Bad JSON or confidence below 0.6 → one retry on **claude-sonnet-5-5**, only if at least 15 seconds of the
   30-second limit are left. Still unsure → the resident gets the normal topic list (nothing is lost).
4. Urgency: the building's `urgent.words` (water, leak, flood, fire, smoke, gas, sparks, lift stuck, …) are
   checked in code first; the model can add urgency but never remove it. Urgent → the screen shows the
   after-hours number first and a "Send to the building manager now" button.
5. The pre-filled topic form opens, missing fields marked, one question at the top. At most 2 follow-up
   rounds. **The resident presses Send**; the case is made by the existing `POST /cases`.
6. Handler: "Draft a reply" on the case → haiku drafts from the case answers, the stage instructions, the
   silence date, the building's standard conditions and up to 5 similar decisions (all this building's,
   anonymised). The draft fills the message box. **A person always presses Send**; nothing is sent,
   decided or moved by the AI. The event records "drafted with AI, edited by {name}".

### Guardrails
- Never sends, decides, votes or moves a stage. No route the AI result can reach does any of these.
- Per-building cap (`ai.monthly_cap`, default 300 runs) and per-person cap (`ai.per_user_daily`, 10). Over
  the cap → the normal form, no error shown.
- Only that building's data in a prompt: the prompt builder takes one building id and reads nothing else;
  emails and phone numbers stripped; names of other residents never included.
- **Privacy decision needed (Edward):** resident text goes to Anthropic's API, outside the AU data centre the
  base design keeps personal information in. Proposed: one line on the screen ("Your words are read by an AI
  service to fill in the form"), stripping as above, `ai.enabled` off until Edward agrees. **UNCONFIRMED**
  against the Privacy Act (cross-border disclosure); check before turning it on.
- Key in env var `ANTHROPIC_API_KEY` (catalyst-config.json, git-ignored). Timeout 20 s per call.

### Screens
- **Start a request**: serif heading "What's happening?", one large text box, "Continue". Under it, a hairline
  rule and the usual "Or choose" rows. Urgent: a full-width Canopy band with the after-hours number in serif,
  then the button. Then the filled form with a small "Filled in from what you wrote, please check" line.
- **Case page (handler)**: "Draft a reply" text link above the message box; the draft appears editable.
- **Settings → AI** (admin): on/off, caps, this month's use as plain numbers.

### Data
New table **`Ai_Runs`** (shared with the AI compliance helper): `Building_Id` bigint M · `User_Id` bigint M ·
`Kind` varchar(20) M (ask, reply, …) · `Model` varchar(60) M · `Status` varchar(20) M (ok, escalated,
fallback, capped, error) · `Case_Id` bigint · `Tokens_In` int · `Tokens_Out` int · `Output` text (the JSON
or draft, ≤10,000; cleared after 90 days by the daily job) · `Urgency` varchar(20).

New column on **`Cases`**: `Urgent` boolean. New key in topic definitions: field `"library": true` (feature 2)
and topic `"urgent_handler": "manager"`.

### Routes
- `POST /ask {b, text, unit_id}` → `{ask_id, topic_key, topic_label, answers, missing: [{key, label}],
  question, urgency: "none|urgent", urgent_note, after_hours, fallback, reason}`
- `POST /ask/answer {b, ask_id, text}` → same shape
- `POST /cases` (existing) gains `ask_id`, `urgent`
- `POST /case/draft-reply {b, id}` (that case's handler) → `{draft, model, sources: {decisions, conditions},
  capped}`
- `GET /ai/usage?b=` (admin) → `{month, runs, cap, by_kind}`

### Emails / push
- Urgent case: immediate email to the building manager (and push `ask.urgent`) titled "URGENT: {title}, unit
  {unit}", the after-hours number, link. Not held for the digest.
- Nothing else new: the resident and handler emails are the existing ones.

### Tests (Anthropic client faked)
- A leak text → maintenance topic, `urgency: urgent` even when the fake model says none (code words win).
- Bad JSON from haiku → sonnet called once; bad again → `fallback: true` and the topic list.
- No sonnet call when under 15 s remain.
- Cap reached → `fallback: true`, no model call, an `Ai_Runs` row with `capped`.
- The prompt for building A contains no text from building B (two buildings in the fake store), and no email
  or phone number.
- `/case/draft-reply` sends nothing: no mail queued, no event other than the draft log, stage unchanged.
- Residents get 403 on `/case/draft-reply`; other building 404.

---

## 4. Contractors and quotes

### Stories
- **Building manager:** I keep a register of contractors (ABN, licence, insurance) and get told 30 days
  before their insurance or licence runs out.
- **Building manager:** from a request I make a work order, attach quotes and ask the committee to approve.
- **Treasurer / committee:** the portal tells me whether the committee may approve this, how many quotes the
  law needs, and stops me approving above our limit.
- **Secretary:** above the limit it puts the item on my list for the next general meeting, with the quotes.

### The limits (law §6, §8.2, §8.24–25)
For `lots` = L (Altai 48):
- **Committee spending limit** = $200 × L **including GST** ($9,600). SM sch 1; s 172.
- **Major spending limit** = the lesser of $1,100 × L and $10,000 ($10,000). SM sch 1; s 173–174.
- **Routine admin** = the greater of $200 and $5 × L ($240): can be acted on at once. SM s 73(1)(d).
- Overrides only with a recorded ordinary resolution: `limits.committee = {cents, resolution, date}` (law §8.2).

The check (`spending.check`) for a work order:
1. **Project total** = chosen quotes of every work order with the same `Project_Key`, incl. GST (a project
   can't be split, BCCM-Office "Committee spending", law §6).
2. Total > major limit → **2 or more quotes** needed (or 1 with a recorded exceptional reason, law §8.25);
   they are attached to the vote notice or meeting notice and kept with the minutes (SM s 174).
3. Total > committee limit → **committee approval blocked** unless one SM s 172(1) exception is recorded:
   ordinary resolution, all owners' written consent, adjudicator emergency order, statutory/court/QCAT order,
   or required insurance (law §6). Otherwise route = **general meeting**: a task for the secretary (duty
   `agm`) "Put on the next general meeting, with the quotes". (General meetings themselves are not built yet;
   pipeline spec "Not in this build".)
4. "It's in this year's budget" must be ticked for committee approval (BCCM-Office, law §6). How the portal
   could check the budget: **UNCONFIRMED** (no budget data yet).
5. Improvements to common property: show the basic limit $300 × L ($14,400) for information; the committee is
   still capped by its spending limit (SM s 186, law §6).

Approval runs through existing votes: "Ask the committee" opens a vote outside a meeting (or a meeting motion)
with the words filled in and the quotes linked. When that motion passes and its opposition window allows
action (pipeline rules, SM s 72–73), the work order becomes Approved.

Contractor checks: a work order can't be issued to a contractor whose insurance has expired, unless the
manager records a reason. Which licences are needed per trade (QBCC, electrical): **UNCONFIRMED**, so the
licence fields are recorded and reminded, not judged.

### Screens
- **Contractors** (manager, committee): rows: name in serif, trade, insurance "to 3 Mar 2027" (Rust when
  expired, "in 21 days" when close).
- **Work order** page: title, linked request, quotes as hairline rows (contractor, amount, valid until,
  file). A plain-words check block first: "Total $12,400 incl. GST. That's over the committee's $9,600 limit,
  so the committee can't approve it. It needs a general meeting with at least 2 quotes (you have 2). SM s 172,
  s 174." Then the buttons that are allowed.
- **Limits** (admin): the three numbers, how they're worked out, any resolution that changed them.

### Data
New table **`Contractors`**: `Building_Id` bigint M · `Name` varchar(255) M · `ABN` varchar(20) (11 digits,
checksum checked in code) · `Trade` varchar(60) · `Licence_No` varchar(60) · `Licence_Expiry` date ·
`Insurer` varchar(255) · `Policy_No` varchar(60) · `Insurance_Expiry` date · `Public_Liability_Cents` bigint
· `Phone` varchar(40) · `Email` varchar(255) · `Files` text (JSON file keys) · `Notes` text · `Status`
varchar(20) M (active, paused, archived).

New table **`Work_Orders`**: `Building_Id` bigint M · `Ref` varchar(30) M **unique** ("ALT-W-0001") ·
`Case_Id` bigint · `Project_Key` varchar(60) · `Contractor_Id` bigint · `Title` varchar(255) M · `Scope`
text · `Status` varchar(30) M (draft, quoting, needs_committee, needs_general_meeting, approved, issued, done,
cancelled) · `Total_Cents` bigint · `Route` varchar(30) · `Exception` varchar(255) (which s 172(1) exception +
note) · `In_Budget` boolean · `Motion_Id` bigint · `Task_Id` bigint · `Approved_At` datetime ·
`Created_By` bigint M.

New table **`Quotes`**: `Building_Id` bigint M · `Work_Order_Id` bigint M · `Contractor_Id` bigint M ·
`Amount_Cents` bigint M (incl. GST) · `Valid_Until` date · `File_Key` varchar(255) · `File_Name`
varchar(255) · `Chosen` boolean M · `Note` varchar(255).

### Routes
- `GET /contractors?b=` → `{contractors: [{id, name, abn, trade, licence_no, licence_expiry,
  insurance_expiry, public_liability, status, insurance_state: "ok|soon|expired"}]}`;
  `POST /contractors {b, id?, ...}` (manager, committee) → `{contractor}`
- `GET /work-orders?b=&status=` → `{work_orders}`; `GET /work-order?b=&id=` → `{work_order, quotes,
  check: {total_cents, committee_limit_cents, major_limit_cents, routine_cents, quotes_needed, quotes_have,
  route: "routine|committee|general_meeting|exception", blocked, reasons: [{text, citation}]}}`
- `POST /work-orders {b, case_id?, title, scope, project_key?}` → `{work_order}`
- `POST /quote {b, work_order_id, contractor_id, amount_cents, valid_until, file}` (upload as docs) →
  `{quote, check}`; `POST /work-order/choose {b, id, quote_id}` → `{work_order, check}`
- `POST /work-order/ask {b, id, how: "vote|meeting", exception?, in_budget}` → `{work_order, vote|task}`;
  400 with the plain reason when blocked.
- `POST /work-order/status {b, id, status}` → `{work_order}`
- `GET /limits?b=`; `POST /limits {b, committee_cents, major_cents?, resolution, date}` (admin)

### Emails / push
- Contractor insurance or licence expiring in 30 days and on the day: task + digest line to `contractors`
  duty; push `contractor.expiring`.
- Work order needs the committee: the vote email (existing) with the check block and quote links first.
- Needs a general meeting: email to the secretary; push `work_order.needs_meeting`.
- Approved: email to the manager "Approved, you can issue it".

### Tests
- 48 lots: $9,600 committee, $10,000 major, $240 routine; `lots` 5 → major $5,500.
- $9,600 exactly → committee may approve; $9,600.01 → blocked, route general meeting, task made.
- Two work orders, same `Project_Key`, $6,000 each → blocked (no splitting).
- $10,500 with 1 quote → needs 2; with 2 → allowed if the committee limit was raised by recorded resolution.
- Insurance exception recorded → committee may approve over the limit.
- Expired insurance → issuing refused without a reason.
- Passing the linked motion approves the work order only after the opposition window rules allow.
- Residents 403; other building 404.

---

## 5. Roll and change of tenancy

### Stories
- **Owner:** I report that I've sold, have a new tenant, or my address changed, with the date and the new
  people's details.
- **Tenant:** I report I'm moving out, or my address changed.
- **Secretary (duty `roll`):** I check the evidence and confirm; the roll updates and the clock stops.
- **Leaving resident:** my access ends on the date I leave, not before and not after.
- **Committee:** I see the roll's history: who held each lot and when.

### How it works
- A report is a request of a new seeded topic **`roll_change`** (fields: kind, effective date, new people
  with name, email, address for service, lease length, evidence file). It uses the pipeline: deadline
  `{days: 14, from: "request", outcome: "none", banner: "The roll must be updated by {date}."}`
  (SM s 224–225; law §7, §8.39). Stages: Received → Checking evidence → Recorded. Manager or secretary can
  lodge one for a lot (e.g. from a solicitor's notice).
- "Record on the roll" (secretary) applies it: current entries for that lot and kind get `To_Date` = the
  effective date; new entries start that day. Nothing is ever deleted (the roll is kept permanently, SM s 231,
  law §7).
- Leases under 6 months are recorded for portal access only, marked "not a roll item" (the roll records
  leases of 6 months or more, SM s 224, law §7).
- **Access**: each leaver's membership for that unit gets `Ends_On` = effective date. The daily job ends it
  that day (status `ended`); access is worked out on every call, so it stops at once. Incoming people with an
  email get a membership `approved` from `Starts_On` and a "Join the portal" email (the secretary's check
  replaces the approver's for that unit).
- A **committee member who sells** their only lot becomes ineligible (SM s 44(2), law §2): the secretary gets
  a task "Seat may be vacant: confirm; fill within 1 month" (SM s 48, law §8.7).

### Screens
- **Report a change** (resident): serif heading, three plain rows ("I've sold", "New tenant", "My address
  changed", "I'm moving out") → the topic form.
- **Roll** (committee positions, admin; BCM): one hairline row per lot: lot in serif, current owner(s),
  tenant, address for service. Tap → history rows with dates. Pending changes on top with days left (Rust when
  overdue). The manager sees lot, occupant names and move dates only, no addresses for service.

### Data
New table **`Roll_Entries`**: `Building_Id` bigint M · `Unit_Id` bigint M · `Kind` varchar(20) M (owner,
tenant, mortgagee, agent, nominee, representative) · `Name` varchar(255) M · `Email` varchar(255) ·
`Address_For_Service` varchar(255) · `Postal_Address` varchar(255) · `ACN` varchar(20) · `Share`
varchar(20) · `Lease_Months` int · `From_Date` date M · `To_Date` date · `User_Id` bigint · `Change_Id`
bigint.

New table **`Roll_Changes`**: `Building_Id` bigint M · `Unit_Id` bigint M · `Case_Id` bigint M · `Kind`
varchar(20) M (sale, new_tenant, tenant_leaving, address, agent, nominee) · `Effective_Date` date M ·
`Due_At` datetime M (14 days) · `Details` text M (JSON: people, evidence keys) · `Status` varchar(20) M
(received, recorded, rejected) · `Recorded_By` bigint · `Recorded_At` datetime.

New columns on **`Memberships`**: `Starts_On` date · `Ends_On` date. New `Status` value `ended`.

### Routes
- `POST /cases` with `topic: "roll_change"` (existing) also writes the `Roll_Changes` row → the case.
- `GET /roll?b=&unit=&history=1` (committee positions, admin) → `{lots: [{unit_id, unit_label, current:
  [entries], pending: [changes]}]}`; manager gets the reduced shape.
- `GET /roll/changes?b=&status=` → `{changes: [{id, case_ref, unit_label, kind, effective_date, due_on,
  days_left, overdue}]}`
- `POST /roll/record {b, change_id, decision: "record|reject", note}` (duty `roll`) → `{change, entries,
  memberships_ending, memberships_starting}`; also moves the case to Recorded.
- `POST /roll/entry {b, unit_id, ...}` (secretary, admin) for loading the existing roll at onboarding.

### Emails / push
- Change received: secretary email (silence line first: "The roll must be updated by {date}"); push
  `roll.change_received`. Reminders through the existing case digest.
- Recorded: the reporter gets "Recorded on the roll". New people get "Join {building}'s portal".
- Leaver, 7 days before and on the day: "Your access to {building}'s portal ends on {date}".
- Committee seat task as above.

### Tests
- Report on Saturday 2 Jan 2027 → day 14 is Saturday 16th → due end of Monday 18th; overdue shows in Rust.
- Record a sale effective the 20th: old owner entry `To_Date` 20th, new entry from the 20th; old owner's
  membership ends on the 20th by the daily job, not before; history keeps both.
- Short lease (3 months) → membership yes, marked not a roll item.
- Selling committee member → task with a 1-month due date.
- A tenant can't report a sale (403); a resident of another unit can't report for this one (404);
  the manager's `/roll` has no addresses for service.

---

## Build order

| # | Piece | Size | Why this order |
|---|---|---|---|
| 0 | Building facts, new duty keys, `Tasks` columns, `Memberships` dates | S | Everything below reads them |
| 1 | Compliance calendar (seed, generate, screen, digest) | M | Pure law dates, no new risk; uses Tasks as is |
| 2 | Roll and change of tenancy | M | A 14-day legal clock and it controls who gets in |
| 3 | Contractors, work orders, quotes, limit check | L | Biggest; uses votes; blocks unlawful approvals |
| 4 | Decisions library, similar decisions, standard conditions (+ backfill) | M | Needs decided cases; feeds 5 |
| 5 | Plain-words requests and drafted replies (+ `ai.py`, `Ai_Runs`) | L | Needs Edward's privacy decision and the API key; draws on 4 |

Each piece ships with its tests in `tests/` (fake store, fake Anthropic client), `store.SCHEMA` entries for
its tables, and the tables made in the Catalyst console on the test copy first.

## Open questions for Edward / Michael
- Send resident text to the AI service (feature 3 privacy line)? Until yes, `ai.enabled` stays off.
- Alatai's financial year end, levy due dates, number of lots on the CMS, pool and lift: yes or no.
- Is there a BCM, and does it run the funds or hold the secretary's powers (changes the owners in feature 1)?
- Has Alatai changed its spending limits by resolution (law "Points to verify")?
- Should owners see the anonymised decisions library?
- Add the VERIFIED items (insurance, sinking fund forecast, fire safety, lift, pool) to the law file.
