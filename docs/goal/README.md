# docs/goal/ — Operating Guide

The single authoritative entry point for any agent working on the Autonomous Agent Builder. Read this file first on every session. Two minutes.

---

## Read order (every session)

**At session entry, type `/start`.** The skill at [.claude/skills/start/](../../.claude/skills/start/SKILL.md) loads the four files below in one pass, runs the STATUS drift check, and folds in the prior session's CURRENT.md when fresh. The list below is what the skill loads and what you reach for if you're reading manually:

1. **README.md** (this file) — operating rules + file map.
2. **NORTH-STAR.md** — *why*. Mission, three-fold success bar, differentiators vs Codex CLI / Claude Code.
3. **STATUS.md** — *where you are*. Current epoch, current milestone, in-flight item, next action, blockers, evidence pointers.
4. **The file matching your next move** — ROADMAP / EVALUATION / FIX-STANDARD / OPERATOR-LANGUAGE / TUNING / RESUME / INDEX / INSIGHTS.

If STATUS is stale or ambiguous, open **RESUME.md** before doing any new work.

---

## File map

| File | Owns | Touch it when |
| --- | --- | --- |
| `README.md` | Operating rules + read order. | Operating rules change. |
| `NORTH-STAR.md` | Mission, success bar, differentiators. | The goal itself changes. |
| `STATUS.md` | Live state: current position, next action, blockers, evidence pointers, recent decisions. | A milestone/item transitions state, a blocker opens/closes, or a durable decision lands. |
| `ROADMAP.md` | Three epochs × milestones × concrete `[ ]`/`[x]` items. The spine of all work. | Picking an item, opening a milestone, proposing scope. Tick `[x]` only when evidence passes. |
| `EVALUATION.md` | Tiered bars (Tier 1 token+UX / Tier 2 lifecycle / Tier 3 head-to-head) + verification commands. | Claiming an item/milestone/epoch is done. |
| `FIX-STANDARD.md` | The 7-step fix procedure: memory → explore → triggers → SDK grounding → correct layer → verify → record → write memory. | Starting any non-trivial defect closure. |
| `OPERATOR-LANGUAGE.md` | Banned operator-facing terms, good/bad prompt shapes, F1-F10 / E1-E9 / R1-R3 scenarios. | Touching any operator-visible surface or copy. |
| `TUNING.md` | Continuous CLI monitoring + per-prompt tuning loop. | Watching a live agent run or investigating an operator-UX regression. |
| `RESUME.md` | Session-handover protocol. | Joining a session with existing STATUS content or when continuity is uncertain. |
| `INDEX.md` | Owner map (this folder + rest of repo). | Before creating or duplicating any doc. |
| `INSIGHTS.md` | Append-only log of `goal-audit` runs. | The skill writes here; you read here. |

---

## Hard rules (non-negotiable)

1. **STATUS.md must not lie.** Update it on every state transition (milestone, item, blocker, decision). A wrong STATUS is a Tier 1 resumability failure.
2. **Everything maps to ROADMAP.** No ad-hoc work. New work goes on the roadmap in the right epoch first.
3. **EVALUATION is the bar.** A milestone is done only when its claimed tier passes with evidence.
4. **INDEX is the owner map.** Before creating or editing any doc, check INDEX for the existing owner. One owner per concern.
5. **Both runtime lanes are first-class.** Anything claimed for the product must hold in both `claude` and `codex_sdk`. If only one lane, mark per-lane.
6. **Operator-language is mandatory on operator surfaces.** Banned terms allowed *only* here (this folder is for agents, not operators).
7. **The model owns prompt interpretation.** Deterministic routing on exact wording is a hard violation.
8. **Fix root causes.** SDK-grounded fixes only, per [FIX-STANDARD.md](FIX-STANDARD.md). No workarounds.
9. **Inspect neighbouring surfaces when testing.** Agent, Voice, Board, Backlog, Metrics, Observability. A change verified only on the touched surface is unverified.
10. **Memory is bidirectional.** Read repo precedent before fixing; write back when the learning is durable. Invalidate stale memory. `builder memory` runs from the Builder source repo only.
11. **Autoresearch (Track B) is ACTIVATING.** M3.5 D1 (N=5 baseline) unblocked 2026-05-23. The skill at [.claude/skills/autoresearch/](../../.claude/skills/autoresearch/SKILL.md) owns lane discipline (Baseline / Iterate / Fix) and `docs/autoresearch/` freshness. Don't run it on broken behavior.
12. **A `[x]` isn't closed until pushed.** Tick `[x]` + update STATUS + push the commit. An unpushed `[x]` does not count.
13. **Commit only on `[x]` close.** Trigger order: update CHANGELOG → tick `[x]` in ROADMAP → update STATUS → one commit covering all related changes → push.

---

## Operating loop

When picking up work:

1. Read **STATUS.md**'s Current Position. Note current milestone + in-flight item.
2. Open **ROADMAP.md** at that milestone. Pick the next `[ ]` item (or the one already in flight).
3. If it's a fix, follow **FIX-STANDARD.md**. If it's a feature, work it.
4. Verify against **EVALUATION.md** at the relevant tier.
5. When the item is done with evidence: CHANGELOG → tick `[x]` → STATUS → commit → push.
6. If you found a recurring trap or non-obvious decision: write to `builder memory` from the source repo.

When discovering new work mid-session: add it to ROADMAP under the right epoch *before* starting it.

When STATUS and reality disagree: **fix STATUS first**, then continue.

---

## What this folder does NOT own

See [INDEX.md § External Owner Map](INDEX.md#external-owner-map-the-rest-of-the-repo) — single source for every concern owned outside `docs/goal/` (IMPs, sprint state, history, rubrics, quality gates, workflows, references, prompts, memory, KB, autoresearch).

---

## Maintaining this folder

1. **Docs cost tokens** — on write and every future read. Write tight, cut explanation, sacrifice grammar for brevity. Prefer tables / bullets / pointers over prose.
2. **Before adding content, check ownership.** [INDEX.md](INDEX.md) lists every owner. New concern → either fits an existing owner here, fits an external owner (link it), or needs a new owner (add a row to INDEX before writing).
3. **Compression triggers per file:**
   - **STATUS.md** > 120 lines → compress / archive / delete.
   - **INSIGHTS.md** — `goal-audit` auto-trims prior-run closed actions; older runs may be collapsed to summary rows at milestone close.
   - **ROADMAP.md** — closed milestones stay; closed `[x]` items stay (audit trail). Don't compress the spine.
   - **Other files** — when a section's prose explains *what* instead of stating it, cut.
4. **Cross-file propagation chain.** ROADMAP item closes → CHANGELOG entry → tick `[x]` in ROADMAP → update STATUS → one commit → push. Don't break the chain (Hard Rules 12, 13).
5. **One owner per concern.** If you're about to duplicate content from another `goal/` file or an external owner, link instead. Drift between duplicates is the failure mode.

---

## Human overrides

- **Redirect the agent:** edit `STATUS.md` and add a `Manual override` line under *Next Action*. The agent picks it up next session.
- **Change the goal itself:** edit `NORTH-STAR.md`. Roadmap and evaluation should follow.
- **Add a milestone or item:** edit `ROADMAP.md`, then note it in `STATUS.md`.
- **Add an evaluation bar:** edit `EVALUATION.md` and link it to the gating milestone.
