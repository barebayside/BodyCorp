# BodyCorp portal — next

Updated 2026-11-10 · Source: build session 11-10 (v1 built and live on Development)

## Goal
- **Purpose:** a branded body corporate portal (requests, approvals, steps and legal deadlines, notices, documents)
  that each building gets as its own space. First building: Altai on the Park, Brisbane (Michael). Also the first run
  of a reusable portal kit: Altai first, then pull out the kit.
- **Success looks like:** Michael's committee and building manager run Altai's requests through it, on time and on record.

## Next
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
Online voting · invite an outside advisor to one matter (advice saved for next time) · a real inbound email address
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
- Tests: `py -3.9 -m pytest -q tests` (84 pass). Design: `docs/design.html`; plan: `docs/superpowers/plans/`.
