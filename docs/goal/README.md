# docs/goal/ — Operating Guide

Single entry point for any agent on the Autonomous Agent Builder. Read first, every session.

## Read order (every session)

Type `/start` — the [start skill](../../.claude/skills/start/SKILL.md) loads these in one pass (+ STATUS drift check + fresh CURRENT.md). Manual order:

1. **README.md** — rules (this file).
2. **NORTH-STAR.md** — mission, three-fold success bar, differentiators.
3. **STATUS.md** — current epoch/milestone/in-flight item, next action, blockers.
4. **The file for your next move** — [INDEX.md](INDEX.md) maps every file (this folder + the rest of the repo).

STATUS stale/ambiguous → [RESUME.md](RESUME.md) before acting.

## Hard rules (non-negotiable)

1. **STATUS.md must not lie.** Update on every transition (milestone/item/blocker/decision). Wrong STATUS = Tier 1 resumability failure.
2. **Everything maps to ROADMAP.** No ad-hoc work; new work lands in the right epoch first.
3. **EVALUATION is the bar.** Done only when the claimed tier passes with evidence.
4. **INDEX is the owner map.** One owner per concern; check it before creating/editing any doc.
5. **Both lanes first-class.** Claims must hold in `claude` and `codex_sdk`; else mark per-lane.
6. **Operator-language mandatory on operator surfaces.** Banned terms allowed only in this folder (agents, not operators).
7. **The model owns prompt interpretation.** Deterministic routing on exact wording is a hard violation.
8. **Fix root causes** per [FIX-STANDARD.md](FIX-STANDARD.md). SDK-grounded, no workarounds.
9. **Inspect neighbouring surfaces when testing** (Agent/Voice/Board/Backlog/Metrics/Observability). One-surface verification is unverified.
10. **Memory is bidirectional.** Read precedent before fixing; write durable learnings back; invalidate stale. `builder memory` runs from the source repo only.
11. **Autoresearch (Track B) is ACTIVATING.** The [autoresearch skill](../../.claude/skills/autoresearch/SKILL.md) owns Baseline/Iterate/Fix + `docs/autoresearch/` freshness. Don't run on broken behavior.
12. **A `[x]` isn't closed until pushed.**
13. **Commit only on `[x]` close**, in order: CHANGELOG → tick `[x]` → STATUS → one commit (all related changes) → push. Don't break the chain.

## Operating loop

STATUS Current Position → ROADMAP at that milestone → pick next `[ ]` (or in-flight) → fix via FIX-STANDARD / build the feature → verify at EVALUATION's tier → close per rule 13 → durable trap/decision to `builder memory`.

New work mid-session → add to ROADMAP (right epoch) *before* starting. STATUS vs reality disagree → fix STATUS first.

## Maintaining this folder

- **Docs cost tokens on every read.** Write tight; tables/bullets/pointers over prose; one owner per concern (dup → link via [INDEX.md](INDEX.md)).
- **Compression triggers:** STATUS >120 lines → compress/archive. INSIGHTS → frozen historical log (goal-audit retired); collapse old runs at milestone close. ROADMAP → closed items stay (audit trail); don't compress the open spine. Other files → cut prose that explains *what* instead of stating it.
- **What this folder does NOT own:** [INDEX.md § External Owner Map](INDEX.md#external-owner-map-the-rest-of-the-repo).

## Human overrides

- **Redirect:** add a `Manual override` line under STATUS *Next Action*.
- **Change the goal:** edit NORTH-STAR (roadmap + evaluation follow).
- **Add milestone/item:** edit ROADMAP, note it in STATUS.
- **Add an eval bar:** edit EVALUATION, link it to the gating milestone.
