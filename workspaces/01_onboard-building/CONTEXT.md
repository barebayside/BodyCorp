# 01 Onboard a building

Stage contract. Repeating unit: one building. Also used when a building's CMS or by-laws change, until the
in-portal AI review exists.

## Inputs
- Working: `../../buildings/<slug>/record.md`, `../../buildings/<slug>/documents/` (CMS, by-laws, roll, minutes).
- Reference: `../../docs/compliance/qld-committee-rules.md` (§ 8 rules), `../../catalyst/functions/bodycorp_api/seed_altai.json`
  (the shape of a building's setup), `../02_design-look/CONTEXT.md`.

## Process
1. **Record** — copy `../../buildings/_template/` to `buildings/<slug>/`; fill facts, committee positions, manager,
   module (from the CMS). Open questions go in the record's Questions list.
2. **Documents** — file what the client sends in `documents/`, named `YYYY-MM-DD-what.pdf`. Note the version and the
   date it took effect.
3. **Rules** — read the CMS and by-laws against `qld-committee-rules.md`. For each request type write its fields,
   steps (with clause), handler position, deadline and **what happens if nobody decides**. Changes from the previous
   version are listed clause by clause. Output: `buildings/<slug>/rules.md` + a seed JSON.
4. **Look** — run `../02_design-look/` for the building.
5. **Set up** — load the seed (`POST /admin/bootstrap` or `/admin/topics`), units (`/admin/units`), roles.
6. **Go-live check** — run `../03_release/` for this building.

## Outputs
`buildings/<slug>/record.md`, `rules.md`, `seed.json`, the building live in the portal.

## Check
Step 3: Edward (and the client's advisor) approve `rules.md` before step 5 — every rule names its clause or
section; anything not found is marked UNCONFIRMED, never guessed. Step 6 passes.
