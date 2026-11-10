# BodyCorp portal — dispatcher

Layer 2: routing only. Rules and reference live in `docs/`; per-building facts in `buildings/`.

## The parts, and what they are to the reusable kit
| Folder | Role | Kit layer |
|---|---|---|
| `catalyst/` | The product code (Catalyst app: function + pages) | Product |
| `tests/` | The code's tests (fake store, no live calls) | Product |
| `workspaces/` | The jobs that repeat, each with a contract | Product (method) |
| `docs/design/`, `docs/superpowers/` | Design system; product specs and build plans | Product |
| `docs/compliance/` | Queensland body corporate law, as rules the software enforces | Strata fill-in (swap per state/industry) |
| `buildings/` | One record per client building: facts, documents, photos | Client data (git-ignored) |
| `handoffs/` | Dated session notes. History, not context | — |

## Task → where
| Task | Go to | Then load |
|---|---|---|
| Fix or add a feature | `catalyst/CONTEXT.md` | the spec in `docs/superpowers/specs/` for that feature |
| New building, or a building's first CMS/by-laws | `workspaces/01_onboard-building/CONTEXT.md` | `buildings/<slug>/record.md` |
| By-laws, CMS, the law or a resolution changed (a live building) | the portal's Rules screen (`#/rules`), the rules loop | `docs/superpowers/specs/2026-11-10-rules-loop-design.md` |
| A building's look, or the product site's look | `workspaces/02_design-look/CONTEXT.md` | `docs/design/design-brief.md` |
| Put a change on the live site | `workspaces/03_release/CONTEXT.md` | `NEXT.md` § How it runs |
| "Is the committee allowed to…?" | `docs/compliance/qld-committee-rules.md` § 8 | the building's CMS/by-laws |
