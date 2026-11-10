# BodyCorp portal — design

2026-11-10 · Edward (owner) · first client: Altai on the Park, Brisbane (contact Michael)

## Why

Owners and residents at Altai send requests, applications and accident reports by email, phone and
in the foyer. The right details aren't collected, it's unclear whether the building manager or the
committee should act, nobody is sure what the CMS, by-laws or Queensland law require, and things slip.
Research (`C:\Users\User\reports\Strata online application tracking software.md`) found no Australian
platform with a tracked owner-application workflow, and Queensland sets legal clocks (e.g. 21 days for a
pet request) that nobody tracks.

Edward also wants this to be the first run of a reusable kit: a branded, multi-client portal with logins
and approval, forms, an inbox, steps and deadlines, reminders and records, so later business ideas reuse
it quickly. Order agreed: **Altai first, then pull out the kit.**

## What it is

One web product on its own Catalyst project (`BodyCorp`, id 694000000418109). Each building gets its own
private, branded space. Everyone logs in and sees their own inbox.

**People (per building):**
- **Owner** — sees their units' requests, notices, owner documents (minutes, by-laws, CMS), can submit.
- **Tenant** — can submit requests and accident reports and see notices; not owner records.
- **Building manager** — handles day-to-day topics (maintenance, accidents, bookings).
- **Committee** — handles decisions (pets, renovations, by-law matters, records requests). A committee
  member is also an owner.
- **Approver** — approves sign-ups against the roll. Who this is at Altai is open; any committee or
  building-manager login can be given the approver role.
- **Admin** — Edward (product owner): sets up buildings, branding, topics.

**Sign-up:** name + email → claim one or more units as owner or tenant → "waiting for approval" →
approver checks against the roll and approves/rejects each unit → email "you're in". One login can cover
several units. Removing a person stops their access at once.

**Requests:** a resident picks a topic; the form asks exactly what that topic needs (fields, photos).
Each request gets a reference (e.g. `ALT-0042`), goes to the topic's handler (building manager or
committee), and starts that topic's steps and legal clock. The resident sees status and any message
marked for them; internal notes stay internal. Every change is kept as a permanent record.

**Steps and deadlines:** each topic carries an ordered checklist (what to do, which rule it comes from)
and an optional legal deadline (days from lodging, and what happens if missed, e.g. "deemed approved").
Handlers tick steps, change status and record the decision with reasons.

**Reminders:** a daily job emails handlers about requests due within 7 days or overdue.

**Notices and documents:** committee/manager post notices (all, or owners only) and upload documents
(minutes, by-laws, CMS) with an audience.

**Public website (Edward, 2026-11-10: "the website, all of it"):** a product page that explains what it
does and offers "book a demo", plus a building sign-in link. Product name is not chosen yet, so the page
uses the working name "BodyCorp" in one place that is easy to change.

**Email (Edward: "I also want the email"):** sign-in codes, "you're in", new-request alerts to handlers,
updates to residents, notices and reminders all go out by email. A real address per building that
*receives* email is still a later piece.

**Branding:** per building — name, scheme number, colours, logo, footer. A small "Powered by" line.

## Goals / non-goals / anti-goals

- Goals (v1): sign-up + approval; topic forms; committee/manager inbox with steps, deadlines, status,
  decisions; resident view of their requests; emails; notices; documents; multi-building ready.
- Non-goals (v1, later): e-voting; outside-advisor link (invite to one matter, advice saved to a rule
  book); a real inbound email address per building; custom domain per building; payments.
- Anti-goals: one building or unit ever seeing another's data; the product presenting itself as legal
  advice (wording is "guidance, checked by your advisors"); rules shown as final before Altai's own
  documents and advisors have checked them.

## Constraints

- Queensland BCCM Act. Altai's CMS and by-laws are not yet received; every Altai rule ships marked
  **DRAFT — to be checked against Altai's CMS/by-laws** until they are.
- Catalyst Data Store: 300-row query cap (page every read), 5,000 rows/table on Development, datetimes as
  `YYYY-MM-DD HH:MM:SS`, 30-second function limit, out-of-memory = empty 200 (page treats a body without
  `ok` as a failure).
- Personal information (incident reports, owner details) stays in Catalyst (AU data centre). GitHub holds
  code only.

## How (decided, and my calls)

- **Platform (Edward):** own Catalyst project; GitHub `barebayside/BodyCorp` for code history.
- **Stack (my call, matching the language app):** static web client in `catalyst/client`, one Python
  Advanced I/O function `bodycorp_api`, Data Store tables, Stratus bucket for files, a daily cron.
- **Login (my call):** email one-time code (no passwords). The function emails a 6-digit code, stores
  only its hash with a 10-minute expiry and 5 tries, then issues a session token (hash stored, 30 days)
  sent as a `Bearer` header. Reason: residents never forget a password, email is proven at login, and
  all permission checks live in our code against our own membership table, which multi-building needs
  anyway. Catalyst's built-in auth can replace this later without changing the data.
- **Which building (my call):** URL path `/app/?b=altai` for v1; subdomain/custom domain later.
- **Permissions:** every API call resolves user → building role/memberships server-side; every query is
  filtered by building and, for residents, by their approved units. Tested with a fake store.
- **Topics as data (my call):** each building's topics (fields, handler, audience, steps, deadline) are
  JSON rows, so a new building or a new business changes data, not code. This is the seam the kit is
  pulled out along.
- **Email (my call):** Catalyst Mail through one `mailer` module. If no sender is verified yet, emails are
  logged and the app still works (everything is visible in the inbox).

## Left to the builder

Screen layout and wording (short, phone-first), table column details, reference format, test layout.
