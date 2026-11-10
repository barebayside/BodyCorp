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
