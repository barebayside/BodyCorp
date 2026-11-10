# 03 Release and prove it works

Stage contract. Repeating unit: one release, or one building going live. Based on BBL's member-zone go-live check
(`products/member-zone/events/04_qa-approved.md` § Before pressing), written after a customer email pointed at an
address that had never been set up.

## Inputs
- Working: what changed (commits since the last release), the building(s) affected.
- Reference: `../../NEXT.md` § How it runs, `../../catalyst/CONTEXT.md`.

## Process
1. Tests pass; the change is on the test copy and walked.
2. **Live copy is complete**: tables, bucket, mail sender (verified), env vars, both crons (`daily_reminders`,
   `daily_check`) all exist on the live copy — none of these carry over by themselves.
3. **Every address in every email opens** from a signed-out browser.
4. **A real sign-in works end to end**: request a code to a real inbox, receive it, sign in, claim a unit, approve.
5. **Every email lands** (inbox, not spam) and reads right on a phone: code, you're in, new request, update,
   decision, notice, reminder, self-check digest.
6. `GET /status` answers, and the outside monitor (Zoho Site24x7) is watching it.
7. Two days after real residents are invited, check they got in. If not, tell Edward.

## Outputs
`check.md` in `../../handoffs/` for the release: first line `pass` or `fail: <why>`, then each step's result.

## Check
Any fail stops the release. Nothing is sent to a client's residents until this passes.
