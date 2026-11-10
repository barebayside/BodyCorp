# BodyCorp portal — next

Updated 2026-11-10 · Source: build session 11-10 (v1 built and live on Development)

## Goal
- **Purpose:** a branded body corporate portal (requests, approvals, steps and legal deadlines, notices, documents)
  that each building gets as its own space. First building: Altai on the Park, Brisbane (Michael). Also the first run
  of a reusable portal kit: Altai first, then pull out the kit.
- **Success looks like:** Michael's committee and building manager run Altai's requests through it, on time and on record.

## Next
000. **Onboarding call with Michael (Edward, 2026-11-10)** before any Alatai-specific build: how Alatai actually runs
   (self-managed or a paid body corporate manager, who does what) and exactly what they want. Questions list:
   `buildings/alatai/record.md`. The manager hand-over feature is parked until then.
00. **Live version (Production) created 2026-11-10**: pages + function + tables deployed (`https://bodycorp-7006497428.catalystserverless.com.au`).
   Still to do on live: (a) env vars on the live function (id 694000000424769) — copy from catalyst-config.json, PORTAL_URL
   → the live address; Claude Code auto mode blocks Claude writing production secrets, so Edward approves or pastes them
   (Console → Production → Serverless → bodycorp_api → Configuration); (b) `/admin/bootstrap` Altai on live, then
   `/admin/topics {from_seed}` + brand keys; (c) both crons on live pointing at the LIVE URL; (d) DNS at VentraIP for
   `bodycorp.barebaysidelabs.com`: CNAME `bodycorp` → `catalyst.cs.zohohost.com.au` and CNAME
   `7b5e1b4471d6a340d4d5ac3e140dbdf2.bodycorp` → `catalyst.cs.zohohost.com.au`, then Verify + Request SSL in
   Console → Production → Cloud Scale → Domain Mappings; (e) go-live check (workspaces/03_release).
0. **Decided 2026-11-10 (Edward): the address is `bodycorp.barebaysidelabs.com`**, mapped to the live copy in the
   Catalyst console; DNS lines go in VentraIP (barebaysidelabs.com). Email sends from a barebaysidelabs.com address
   with the domain verified in Catalyst Mail (SPF include ADDED to the existing Zoho Mail SPF line, never a second
   SPF record; plus the DKIM record). A product domain comes later, once the product is named.
0c. **Approved 2026-11-10 (Edward: "do those five"), build after the pipeline, home-screen app and AI helper:**
   (1) compliance calendar (the legal year as dated tasks), (2) past-decisions library + reusable standard conditions,
   (3) plain-words requests (AI picks the form, pre-fills, drafts the handler's reply; a person signs off),
   (4) contractors + quotes checked against the legal spending limits, insurance/licence expiry,
   (5) roll + change of tenancy (roll updated within 14 days; leavers lose access). Spec:
   `docs/superpowers/specs/2026-11-10-five-features-design.md`. Later: lift/amenity bookings, general-meeting voting
   with proxies, incident/insurance register, levies via StrataMax.
0b. **Decided 2026-11-10 (Edward): home-screen app, NO App Store / Google Play** ("too much compliance").
   Build after the committee pipeline: per-building web app manifest (name, icon, colours), a service worker,
   phone notifications by Web Push (VAPID keys as env vars; a subscriptions table; iPhone needs iOS 16.4+ and the
   app added to the Home Screen first), an "Add to Home Screen" prompt with iPhone/Android steps, email stays as
   the fallback. Prove it on a real iPhone and a real Android in the go-live check.
0d. **Committee working view: built 2026-11-10, not yet deployed** (spec
   `docs/superpowers/specs/2026-11-10-committee-pipeline-design.md`). Board, stage buttons that email and move a
   request on, votes outside a meeting, meetings, minutes, tasks. Tables `Motions`, `Ballots`, `Meetings`, `Tasks`
   and column `Cases.Stage` already exist on the test copy. To turn it on: deploy functions and client, then as admin
   `POST /admin/topics {b:"altai", from_seed:"altai"}` (copies the seed's stages, deadlines and vote rules onto
   Altai's existing topics, keeps label/field edits, dates open cases that newly have a clock). Then Edward gives
   people positions (Members → Give someone a role: Chair, Secretary, Treasurer, Committee member) and, once the CMS
   arrives, records the regulation module and the secretary's contact address (Board → Who does what). Until the
   module is recorded admins see "Module not recorded — committee rules are guidance only".
0f. **The rules loop: built 2026-11-10, not yet deployed** (spec
   `docs/superpowers/specs/2026-11-10-rules-loop-design.md`). Law → building rules → products; one change goes round
   seven checked stages (read, rules, impact, ONE legal pack to the lawyer by email with the PDF and a private
   expiring link, the chair's sign-off, apply from a date, tell the right people from a list a person ticks). Tables
   `Rules`, `Rule_Links`, `Changes`, `Legal_Packs`, `Pack_Items`, `Notify_Plans` and column
   `Rule_Proposals.Change_Id` already exist on the test copy. To turn it on: deploy functions and client (the client
   now includes `lawyer.html`, `lawyer.js`, `lawyer.css`), then sign in as edward@ (the portal owner) and press
   Rules → "Load the 44 Queensland committee rules" (or `POST /rules/seed {b:"altai", from:"qld"}`): the 44 become a
   law change at stage 01 and Altai's request types are linked to them. Then walk that change to the lawyer once.
   **Open for Edward:** which lawyer (name, email); whether the chair is the right sign-off (duty `rules_signoff`,
   changeable per building); whether a resolution that changes no resident form may skip the lawyer (built that way).
0e. **AI compliance helper: wired 2026-11-10, not yet deployed** (spec
   `docs/superpowers/specs/2026-11-10-ai-compliance-helper-design.md`). Tables `Doc_Versions`, `Rule_Reviews`,
   `Rule_Proposals`, `Topic_Versions`, `AI_Usage`, `AI_Questions` and column `Cases.Topic_Version` already exist on the
   test copy. To turn it on: deploy functions and client, run the one live check (`ai_smoke.py`, under a cent), then
   Edward as admin opens Settings → AI helper → switches it on for Altai. **It is OFF until then** (when on, the
   CMS, by-laws and committee questions go to Anthropic, outside Australia). Still open for Edward: who approves
   (default: you), who may ask (committee only now), the monthly limit (A$20 now).
1. **Edward: verify the email sender.** Catalyst console (signed in as edward@barebaysidelabs.com) → BodyCorp →
   Cloud Scale → Mail → Email configuration → `edward@barebaysidelabs.com` → Verify (code is in your inbox, from
   noreply@notifications.zohocatalyst.com.au). Until then no email goes out, so nobody can sign in by code.
   (Other emails wait in the mail queue and go once it's verified; ones still failing after 5 tries are given up.)
2. **Deploy the failure check and add its cron** (built 11-10, not yet deployed). After `--only functions`, add a
   second cron `daily_check`, e.g. 06:30 Brisbane → `POST /cron/check` with `X-Cron-Key`, same as the reminders.
   The client still needs its "Needs attention" panel (reads `GET /failures`).
3. **Read Michael's documents** (CMS, by-laws, info) when they arrive and turn them into Altai's real topics, steps
   and deadlines. Every topic is marked Draft until then.
4. **Load Altai's real units** (Settings → Paste units) and remove placeholder units 1–10 (needs a small "remove
   unit" addition; none exist yet).
5. **Decide who approves sign-ups** at Altai, then give them the Approver role (Members → Give someone a role).
6. **Clear the test data** once Edward has looked: test users `*.test@example.com`, request ALT-0001, the
   "TEST owners notice", and the four test sessions (expire 17 Nov).
7. **Pick the product name** (one `<span class="product-name">` per page + `MAIL_FROM_NAME`).
8. **Go live:** promote Development → Production in the console (tables, bucket, mail sender, cron, env vars must
   be set again on Production).

## Later (v2)
General-meeting and AGM voting · notices of opposition as a form · owners opting out of committee advice · invite an outside advisor to one matter (advice saved for next time) · a real inbound email address
per building · the building's own web address · pull out the reusable kit.

## How it runs
- Site: https://bodycorp-7006497428.development.catalystserverless.com.au/app/index.html
- Altai portal: https://bodycorp-7006497428.development.catalystserverless.com.au/app/portal.html?b=altai
- Catalyst project `BodyCorp` 694000000418109 (org 7006497428, AU), Development only. Function `bodycorp_api`
  (Python 3.9), client `catalyst/client`. Deploy: `cd catalyst && catalyst deploy --only functions` / `--only client`.
- Secrets live in `catalyst/functions/bodycorp_api/catalyst-config.json` (git-ignored). A deploy pushes its env vars.
- Sessions travel in the `X-Session` header: Catalyst rejects any `Authorization` header before the function runs.
- Catalyst stamps CREATEDTIME in Brisbane time, not UTC (`store.created_iso` converts).
- Daily reminders: cron `daily_reminders` 07:00 Brisbane → `POST /cron/reminders` with `X-Cron-Key`. It retries
  queued email first and stamps a heartbeat when done.
- Daily self-check: cron `daily_check` → `POST /cron/check` with `X-Cron-Key`. Retries queued email, then looks
  for: reminders not run in 26 h, email stuck over 24 h, overdue cases untouched for 3+ days, unresolved
  failures. If any, ONE digest goes to `SUPPORT_EMAIL` (env var, edward@barebaysidelabs.com) and one to each
  affected building's admins. Answers `{ok, problems}`; `ok` is false when there are problems.
- Failed emails are queued in `Mail_Queue` and retried (5 min, 30 min, 2 h, 6 h; gives up after 5 tries), and
  every failure or crash is a row in `Failures`. Admins see theirs at `GET /failures`; whoever is an admin and
  signs in as `SUPPORT_EMAIL` sees every building's with `?all=1`. Public `GET /status` for an outside monitor.
- Committee working view (2026-11-10). Positions are roles: `chair`, `secretary`, `treasurer`, `member` (voting);
  `committee` = committee access with no vote. Which position does which step is `Buildings.Settings.duties`
  (defaults in `committee.py`: secretary acknowledges, sends votes and notices, takes minutes, answers records
  requests; chair runs meetings; every voting member votes). Stages, buttons, email wording, deadlines and what
  silence means are topic data (`topics.py` docstring; Altai's in `seed_altai.json`).
  Routes: `GET /board`, `POST /case/action {id, action, note}`, `GET /committee`, `POST /committee/settings`,
  `GET /votes`, `GET /vote`, `POST /votes`, `POST /vote/ballot`, `GET /meetings`, `GET /meeting`, `POST /meetings`,
  `POST /meeting/attendance|motion|vote|close|minutes|minutes/issue`, `GET /tasks`, `POST /tasks`, `POST /task/done`
  (shapes in the `main.py` docstring). Portal screens: `#/board`, `#/votes`, `#/vote/<id>`, `#/meetings`,
  `#/meeting/<id>`, `#/minutes/<id>`, `#/tasks`, `#/committee`.
- The daily reminders now also settle votes whose 21 days are up, decide cases past a deadline whose topic says
  "deemed approved" or "not agreed" (and email the resident), and add tasks and draft minutes due to the digests.
- AI compliance helper (2026-11-10, `ai.py`). Off per building until an admin switches it on (Settings → AI helper,
  `#/settings/ai`); while off its routes answer 403 and nothing is sent. When on: committee roles and admins get a
  "By-laws" menu (`#/ai`): upload a new CMS/by-laws version (PDF with text is read free; a scan goes to the AI by
  batch and a person ticks "text checked"), compare two versions (clause changes free, estimate shown, Start sends
  step 1), the review (`#/ai/review/<id>`: if-missed change first, the clause quoted, current → proposed in plain
  words, form preview, Approve/Edit/Reject; refused ones greyed), Apply (versions in force from the registration
  date; open requests keep the version they were lodged under, `Cases.Topic_Version`), history with Undo
  (`#/ai/history`), and "Ask about your by-laws" (`#/ask`). Approver per building: owner (default, the SUPPORT_EMAIL
  user), secretary, or committee_vote (Apply opens a vote outside a meeting; applies only if it passes).
  Budget: `AI_MONTHLY_CAP_AUD` (20) per building, A$ at `AI_AUD_PER_USD` (1.55); checked before every call (402);
  reaching it = one `ai_cap` failure + one email to admins a month; 80% = one warning email. The daily reminders
  also collect finished AI batches and copy versions whose date has come into the live request types.
  Long text lives in Stratus `ai/<building id>/...`. Live check: `py -3.9 <scratchpad>/ai_smoke.py` (one Haiku call).
  Headless AI screens: `py -3.9 <scratchpad>/mock/ai_backend.py catalyst/client 8795` (fake AI, no API calls).
- Headless check of the committee screens: `py -3.9 <scratchpad>/mock/mock_api.py catalyst/client 8790 --real`
  runs the real function code over the tests' fake store (sign in with any seeded email, code 123456).
- The rules loop (2026-11-10, `rules.py`, `legal.py`, `pdfgen.py`). Committee screens `#/rules`, `#/rules/new`,
  `#/rules/change/<id>`, `#/rules/rule/<key>`; the lawyer's page `lawyer.html?t=<token>` (no sign-in, 30-day link,
  only that pack). Who runs a change: duty `rules` (secretary); who signs for the committee: duty `rules_signoff`
  (chair). A law change: the portal owner only. Nothing applies without the lawyer (where needed) and the committee;
  open requests keep their rules (Topic_Versions). Every applied change is listed on the next committee meeting's
  agenda ("Rules changed since the last meeting") and in the minutes draft (item 7). An AI by-law review that is
  part of a change can only apply through the loop. Headless walk: `py -3.9 <scratchpad>/mock/rules_backend.py
  catalyst/client 8797` (every stage seeded), then `py -3.13 <scratchpad>/mock/shots_rules.py http://127.0.0.1:8797 out`.
- Tests: `py -3.9 -m pytest -q tests` (84 pass before the committee view; 122 with it; 211 with the AI helper wired;
  232 with the rules loop). Design: `docs/design.html`; plan: `docs/superpowers/plans/`.
