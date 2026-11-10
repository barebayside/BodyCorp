# Handoff 2026-11-10 — BodyCorp build day

## Session Focus
Research → design → build of the BodyCorp portal (branded body corporate portal on Catalyst), first building
**Alatai on the Park**, 391 Wickham Tce, Spring Hill (Michael). Taken from idea to a live version in one session.

## What Got Done
- **Research:** AU strata software report (`C:\Users\User\reports\Strata online application tracking software.md`);
  QLD committee law with 44 enforceable rules (`docs/compliance/qld-committee-rules.md`); 18 live reference sites +
  design brief (`docs/design/design-brief.md`); pricing research running (see Not Done).
- **Built and tested** (~211+ tests, live API + browser walks): email-code sign-in; unit claims + approval; request
  types as data; requests with steps, legal deadlines and the "if nobody decides" warning first; committee board,
  positions (chair/secretary/treasurer), stage buttons that email; votes outside meetings, meetings, minutes, tasks;
  notices; documents; failure check (mail queue + retry, failure log, 6:30 self-check digest, `/status`); home-screen
  app + phone alerts (Web Push); AI compliance helper (document versions, cited proposals, approve/apply/undo,
  "Ask about your by-laws") — OFF per building until Edward OKs sending documents to Anthropic.
- **Look:** park design (Newsreader/Hanken, greens) inside and on `alatai.html`. Landing page re-laid per Edward
  (big resident sign-in + address, "Report it now" urgent tiles, request types as boxed tiles, bunya band removed) —
  on the test copy only.
- **ICM structure** in the repo: `CLAUDE.md` router, `CONTEXT.md`, `catalyst/CONTEXT.md`, `workspaces/01–03`,
  `buildings/` (git-ignored client records; Alatai record + draft email to Michael).
- **Email works:** sender verified, barebaysidelabs.com already authenticated; real code sign-in proven on test and live.
- **Live version created** (`https://bodycorp-7006497428.catalystserverless.com.au`): function, pages, tables; keys
  copied (Edward switched auto mode off for it); Alatai bootstrapped with name/look/topics/board; Edward signed in on live.
- **Address:** `bodycorp.barebaysidelabs.com` mapping started; 2 CNAMEs added in VentraIP by Edward.

## Files Changed
Whole repo `Desktop\bodycorp-portal` (GitHub `barebayside/BodyCorp`, main). Key: `catalyst/functions/bodycorp_api/*`,
`catalyst/client/*`, `tests/*`, `docs/superpowers/specs/*` (base, committee-pipeline, home-screen-app,
ai-compliance-helper, five-features, rules-loop), `docs/design/*`, `docs/compliance/*`, `NEXT.md`, ICM files.

## What's NOT Done
- **Rules loop** — BUILT, 232 tests, on the TEST copy and committed (spec `docs/superpowers/specs/2026-11-10-rules-loop-design.md`).
  Not yet on live. To start it: Rules → "Load the 44 Queensland committee rules". Owed by Edward: which lawyer (name + email).
- **Pricing research** (competitors + strata management fees) — background agent; notes land in
  `C:\Users\User\research_notes\Strata online application tracking software\pricing_competitors.md`.
- **Daily jobs on live:** a Job Scheduling deployment ("Daily jobs to live") was at diff generation — finish it in
  Console → Settings → Environments → Deployments, then DISABLE the two test-copy crons (they now point at LIVE, so
  both would run). Test copy then has no crons (trigger manually).
- **Domain:** Console → Production → Cloud Scale → Domain Mappings → Verify, then Request SSL (DNS was still spreading).
- **Live copy of the new landing page:** deploy client to live (Create Deployment → Serverless/CloudScale untick,
  web client only) — careful: a Serverless deploy may overwrite live env vars.
- **Go-live check** (`workspaces/03_release/`), incl. real iPhone + Android home-screen test.
- **Five features** (calendar, past decisions, plain-words requests, contractors/quotes, roll changes) — spec only.
- **From Michael** (`buildings/alatai/record.md`): CMS (module), by-laws, unit roll, committee names/emails, building
  manager details, bin days, scheme number, a photo of the building (hero slot), demo testers. Draft email ready.
- **Decisions owed by Edward:** AI privacy OK (documents to Anthropic, outside AU); product name; landing tile style
  ("old-school 90s" options via the site tweaker); pricing.
- Test data on the test copy (test users, ALT-000x, TEST notice) — clear before any client demo on the test copy.

## Resolved failures (learned the hard way)
- Catalyst eats any `Authorization` header → sessions use `X-Session`.
- CREATEDTIME comes back in Brisbane time, not UTC.
- Reserved column names refuse the whole batch: Result, Keys, Change, Month, Batch.
- `.webmanifest` served as octet-stream → use `manifest-altai.json`.
- Chrome: "Browser 1" is signed in as edward@barebaysidelabs.com (Browser 2 = other Zoho account).
- Production can't be configured directly (crons, job pools): make it on the test copy, then deploy.
- Auto mode blocks writing production secrets — Edward switches it off for that step.

## Quick Context for Next Session
Open `NEXT.md` (item 00 = live go-live steps). Start with: finish the jobs deploy +
disable test crons, verify the domain + SSL, deploy the new landing page to live, then the go-live check.
