# PLAN.md — Deprecated, Migrated to docs/goal/

**This file is a redirect.** All content has been migrated into the [`docs/goal/`](goal/README.md) framework. New agents and new references should not target this file.

## Where the original 10 operating bullets now live

| Original PLAN.md bullet | Where it is now |
| --- | --- |
| "The active goal lives in `docs/GOAL.md`. Always read it first." | Superseded. [`docs/goal/README.md`](goal/README.md) is the new entry point. |
| "`docs/IMPROVEMENTS.md` is a living document for builder inefficiencies..." | Referenced from [`docs/goal/INDEX.md` External Owner Map](goal/INDEX.md#external-owner-map-the-rest-of-the-repo) and [`docs/goal/ROADMAP.md § M1.1`](goal/ROADMAP.md#m11--close-the-open-operator-facing-defects). IMPROVEMENTS.md itself remains the living bug list. |
| "`docs/PROGRESS.md` is the overall progress checklist..." | Live state is now [`docs/goal/STATUS.md`](goal/STATUS.md); PROGRESS.md remains the historical evidence archive. |
| "`docs/SPRINT-PROGRESS.md` is the per-sprint checklist..." | Still authoritative for per-sprint tactical work. Referenced from [`docs/goal/INDEX.md`](goal/INDEX.md). |
| "User prompts must always be processed by the model. The model decides which tools to call. Deterministic prompt routing based on exact wording must never happen — the model infers intent." | Hard Rule 8 in [`docs/goal/README.md`](goal/README.md#hard-rules-non-negotiable-for-every-agent-in-every-session). |
| "Always ground solutions in documentation and best practices. Fix root causes, not symptoms." | Hard Rule 9 in [`docs/goal/README.md`](goal/README.md). Full procedure in [`docs/goal/FIX-STANDARD.md`](goal/FIX-STANDARD.md). |
| "Inspect all neighbouring surfaces (Agent, Voice, Board, Backlog, Metrics, Observability) when testing..." | Hard Rule 10 in [`docs/goal/README.md`](goal/README.md). |
| "Memory is bidirectional. Read repo precedent before fixing AND write back after fixing if the learning is durable." | Hard Rule 11 in [`docs/goal/README.md`](goal/README.md). Steps detailed in [`docs/goal/FIX-STANDARD.md § Step 0`](goal/FIX-STANDARD.md#step-0--load-repo-precedent-first) and [`§ Step 7`](goal/FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable). |
| "`docs/autoresearch/` holds the dormant Track B optimization loop..." | Hard Rule 12 in [`docs/goal/README.md`](goal/README.md). Autoresearch activation gate is [`docs/goal/ROADMAP.md § M3.5`](goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b). |

## What to do instead

- **New agent landing on the project:** read [`docs/goal/README.md`](goal/README.md) first. It is the single authoritative entry point.
- **External reference still pointing here:** follow the table above to find the new owner. Update the reference when you next touch the file.
- **Looking for the bug list:** [`docs/IMPROVEMENTS.md`](IMPROVEMENTS.md) — unchanged.
- **Looking for sprint detail:** [`docs/SPRINT-PROGRESS.md`](SPRINT-PROGRESS.md) — unchanged.
- **Looking for historical evidence:** [`docs/PROGRESS.md`](PROGRESS.md) — unchanged.

This file is kept (rather than deleted) so that existing references in `docs/REFERENCE.md`, `docs/rubric/frontend-react-architecture.md`, `docs/SPRINT-PROGRESS.md`, `CHANGELOG.md`, and `.claude/session-data/` resolve to a real file that explains where the content moved. Do not add new references to this file.
