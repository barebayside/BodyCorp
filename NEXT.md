# BodyCorp portal — next

Updated 2026-11-10 · Source: build session 11-10 (v1 built and live on Development)

## Goal
- **Purpose:** a branded body corporate portal (requests, approvals, steps and legal deadlines, notices, documents)
  that each building gets as its own space. First building: Altai on the Park, Brisbane (Michael). Also the first run
  of a reusable portal kit: Altai first, then pull out the kit.
- **Success looks like:** Michael's committee and building manager run Altai's requests through it, on time and on record.

## Next
1. **Edward: verify the email sender.** Catalyst console (signed in as edward@barebaysidelabs.com) → BodyCorp →
   Cloud Scale → Mail → Email configuration → `edward@barebaysidelabs.com` → Verify (code is in your inbox, from
   noreply@notifications.zohocatalyst.com.au). Until then no email goes out, so nobody can sign in by code.
2. **Read Michael's documents** (CMS, by-laws, info) when they arrive and turn them into Altai's real topics, steps
   and deadlines. Every topic is marked Draft until then.
3. **Load Altai's real units** (Settings → Paste units) and remove placeholder units 1–10 (needs a small "remove
   unit" addition; none exist yet).
4. **Decide who approves sign-ups** at Altai, then give them the Approver role (Members → Give someone a role).
5. **Clear the test data** once Edward has looked: test users `*.test@example.com`, request ALT-0001, the
   "TEST owners notice", and the four test sessions (expire 17 Nov).
6. **Pick the product name** (one `<span class="product-name">` per page + `MAIL_FROM_NAME`).
7. **Go live:** promote Development → Production in the console (tables, bucket, mail sender, cron, env vars must
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
- Daily reminders: cron `daily_reminders` 07:00 Brisbane → `POST /cron/reminders` with `X-Cron-Key`.
- Tests: `py -3.9 -m pytest -q tests` (63 pass). Design: `docs/design.html`; plan: `docs/superpowers/plans/`.
