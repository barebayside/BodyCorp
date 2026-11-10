# BodyCorp portal

Branded body corporate portal on Zoho Catalyst. One product, one private space per building. First building:
Altai on the Park (Brisbane, QLD). The owner is not a developer: plain language, no jargon.

## Read every session
1. This file (router).
2. `NEXT.md`: what to do next, and how it runs.
3. Newest file in `handoffs/` if there is one.

## Where things are
| You want to... | Go to |
|---|---|
| Know what it is and why | `docs/design.html` (readable) or `docs/superpowers/specs/` |
| See the API, tables and build tasks | `docs/superpowers/plans/2026-11-10-bodycorp-portal-v1.md` |
| Change the back end | `catalyst/functions/bodycorp_api/` (+ `tests/`, fake store in `tests/fake_store.py`) |
| Change the pages | `catalyst/client/` (`index.html` public site, `portal.*` the portal) |
| Change a building's topics/steps/deadlines | data, not code: `seed_altai.json` for the seed, or POST `/admin/topics` |

## Rules
- Every query is filtered by building; residents only see their approved units. Never weaken this.
- Topics are data. A new building or a new business changes data, not code (this is the kit seam).
- Altai's rules stay marked Draft until checked against its CMS and by-laws. Say "guidance", never "legal advice".
- No secrets or building data in git. `catalyst-config.json` is git-ignored.
