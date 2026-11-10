# catalyst — the product code

Contract for changing the app. Layout is fixed by Catalyst's tools (`catalyst.json` targets `functions/bodycorp_api`
and `client`): do not restructure this folder.

## Inputs
- Working: the feature's spec in `../docs/superpowers/specs/` and plan in `../docs/superpowers/plans/`.
- Reference: `functions/bodycorp_api/main.py` docstring (route map), `store.py` (`SCHEMA`: every table and column),
  `../tests/fake_store.py`, `../NEXT.md` § How it runs.

## Process
1. Write or change the test first in `../tests/`, then the code. Python 3.9 only (Catalyst runtime).
2. Run `py -3.9 -m pytest -q tests` from the repo root. All must pass.
3. New table or column: create it in Catalyst first (ZohoMcp `CatalystbyZoho_Create_Table` / `Create_Column`,
   project 694000000418109, org 7006497428), then add it to `store.SCHEMA` with the same limits.
4. Deploy from this folder: `catalyst deploy --only functions` and/or `--only client` (reaches the test copy only).
5. Verify on the test copy: `GET /server/bodycorp_api/` answers `{ok:true}`; walk the changed screens on phone and
   desktop widths and look at the screenshots.
6. Commit (no `catalyst-config.json`), push. Update `../NEXT.md`.

## Check
Tests pass, the live walk shows no page errors, and the screens were looked at. A 200 with no `ok:true` body is a
failure (Catalyst returns an empty 200 when a function runs out of memory).

## Traps (learned the hard way)
- Sessions go in `X-Session`. Catalyst rejects any `Authorization` header before the function runs.
- Catalyst stamps CREATEDTIME in Brisbane time, not UTC (`store.created_iso`).
- ZCQL returns at most 300 rows: every read pages by ROWID. Text columns cap at 10,000 characters.
- A deploy pushes `catalyst-config.json` env vars, replacing what's set in the console.
- `Result` is a reserved word: Create_Column refuses the whole batch ("Column name cannot contain reserved
  keywords") and creates none of it. The vote result column is `Motions.Tally`.
- More reserved words (2026-11-10): `Change`, `Month`, `Batch`. Hence `Rule_Proposals.Proposed_Json` /
  `Edited_Json` and `AI_Usage.Usage_Month` / `Is_Batch`. Try a short single-column batch first if unsure.
- The AI helper reads the law file from `functions/bodycorp_api/law_qld.md`, a COPY of
  `docs/compliance/qld-committee-rules.md` (the function can't see `docs/`). Edit the docs file, then copy it over;
  a test fails while they differ.
- AI tests never call Anthropic: `ai.make_client` is replaced by a fake. The one live check is
  `ai_smoke.py` (one Haiku call, under a cent), run by hand on the test copy.
- Any document text, clause diff or raw AI batch result goes to Stratus under `ai/<building id>/...`, never in a
  10,000-character column. A request type is still one `Definition` text column, so it must stay under 10,000.
- Once a request type has rows in `Topic_Versions`, change it through a version (admin edits record one
  automatically, `topics.note_version`); the daily job copies the version in force into `Topics`, so a direct
  edit of `Topics` alone would be overwritten.
- Varchar columns can't be longer than 255: Create_Column silently makes a longer `max_length` 255, and a column's
  type can't be changed afterwards (rename it to a 255-character use and add a new text column). Anything longer is
  `text`. TRIGGER, ACTION and SECTION are SQL words: `Trigger_Text`, `Action_Text`, `Rule_Section` (2026-11-10).
- The rules loop's law layer is `Building_Id = 0` (shared by every building of the state). Read it with the
  building's own rows (`rules._rule_rows`); only the portal owner (SUPPORT_EMAIL) writes it.
- Catalyst Mail attachments must be open files: `store.Db.deliver` writes them to the temp folder first. A queued
  retry goes WITHOUT the attachment (the queue holds HTML only); the legal pack's email carries a link to the PDF.
- The lawyer's page (`client/lawyer.html`, `lawyer.js`, `lawyer.css`) has no sign-in: `/pack*` routes are public and
  answer 404 for any wrong, expired or replaced token. Never add a building-scoped route without `b`.
- The fake store keeps whatever type `update` was given (an int id stays an int); Catalyst gives strings back.
  Compare ids as `str(...)` in tests.
