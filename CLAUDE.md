# BodyCorp portal

Branded body corporate portal on Zoho Catalyst: one product, one private space per building. First building:
Alatai on the Park, 391 Wickham Tce, Spring Hill (QLD), contact Michael. The owner (Edward) is not a developer:
plain language, no jargon, say "live site" / "test copy", never Dev/Production.

Entry file is `CLAUDE.md`, not `AGENTS.md`: Edward's house rule for his own workspaces (AGENTS.md only in shared copies).

## Read every session
1. This file (router). 2. `NEXT.md` (what's next, how it runs). 3. Newest file in `handoffs/`.

## Where to go
| You want to... | Open first |
|---|---|
| Know what it is and why | `docs/design.html` (readable) → `docs/superpowers/specs/` |
| Change the app (back end or pages), test, deploy | `catalyst/CONTEXT.md` |
| Set up a new building, or load Alatai's real documents | `workspaces/01_onboard-building/CONTEXT.md` |
| Design or change a building's look / the product site | `workspaces/02_design-look/CONTEXT.md` |
| Release to the live site and prove it works | `workspaces/03_release/CONTEXT.md` |
| Find a building's facts, documents, open questions | `buildings/<slug>/record.md` |
| Check a QLD body corporate rule | `docs/compliance/qld-committee-rules.md` |
| Anything else | `CONTEXT.md` |

## Rules
- Every query is filtered by building; residents see only their approved units. Never weaken this.
- Request types, steps, deadlines, stages and email wording are DATA, not code (the reusable-kit seam).
- What happens if a decision isn't made in time is shown first, in plain words, everywhere an approver sees it.
- Rules stay marked Draft until checked against the building's CMS and by-laws. "Guidance", never "legal advice".
- No secrets or building data in git: `catalyst-config.json` and `buildings/*/` contents are git-ignored.
- No look is presented as finished until the design process has run (`workspaces/02_design-look/`).
