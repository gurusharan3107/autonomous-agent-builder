# docs/goal/ — Agent Entry Point

**You are here because the user pointed you at this folder. Read this file in full before doing anything else. It takes under two minutes.**

This folder is the single authoritative entry point for any agent (Claude Agent SDK lane or Codex SDK lane) working on the Autonomous Agent Builder. It owns the product north star, the roadmap to "preferred over Codex CLI and Claude Code", the tiered evaluation criteria, the live status, and the protocol for resuming after a session drop.

Everything an agent needs to know about *why* it's working, *what* "done" looks like, *where* it is on the journey, and *how* to pick up where the last session left off lives in this folder.

---

## Hard Rules (non-negotiable for every agent in every session)

1. **Read in this order on every session:** `README.md` (this file) → `NORTH-STAR.md` → `STATUS.md` → the file that matches what you're about to do (`ROADMAP.md`, `EVALUATION.md`, `FIX-STANDARD.md`, `OPERATOR-LANGUAGE.md`, `TUNING.md`, `RESUME.md`, or `INDEX.md`).
2. **STATUS.md is the live state.** Update it whenever a roadmap milestone moves between states (`pending` → `in_progress`, `in_progress` → `done`, or `in_progress` → `blocked`). Never let STATUS.md lie about what is currently in flight.
3. **ROADMAP.md is the spine.** Every meaningful piece of work must map to a roadmap item. Items that don't fit get added to the right epoch, not done ad-hoc.
4. **EVALUATION.md is the bar.** A milestone is not "done" until the tier of evaluation it claims to satisfy actually passes with evidence.
5. **INDEX.md is the owner map.** Before creating, editing, or duplicating any doc anywhere in the repo, consult INDEX.md to find the existing owner.
6. **Both runtime lanes are first-class.** Anything claimed for the product must hold in both the Claude Agent SDK lane (`claude`) and the Codex SDK lane (`codex_sdk`). If it only holds in one, mark it explicitly per-lane.
7. **Operator language is mandatory in operator-facing surfaces.** The banned-term contract, good/bad operator prompts, and operator scenarios (F/E/R) live in [OPTERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md). Banned terms are allowed in *this* folder because the audience is the agent, not the operator.
8. **The model decides tool calls; deterministic prompt routing is forbidden.** User prompts must always be processed by the model. The model infers intent and decides which tools to call. Deterministic routing on exact wording is a hard violation — the rule that the model owns prompt interpretation is what keeps the product operator-agnostic.
9. **Ground every solution in documentation and best practices.** Fix root causes, not symptoms. SDK-grounded fixes only; never workarounds. The full procedure is [FIX-STANDARD.md](FIX-STANDARD.md) — apply it for every non-trivial fix.
10. **Inspect all neighbouring surfaces when testing.** Agent, Voice, Board, Backlog, Metrics, Observability — efficiency, performance, and UX all matter. A change verified only on the surface it touched is unverified.
11. **Memory is bidirectional.** Read repo precedent before fixing ([FIX-STANDARD.md § Step 0](FIX-STANDARD.md#step-0--load-repo-precedent-first)) AND write back after fixing when the learning is durable ([FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable)). Invalidate stale memory when a fix proves it wrong. All `builder memory` commands run from the Builder source repo, not from managed-app workspaces — scopes are intentionally separate.
12. **Autoresearch (Track B) is dormant until prerequisites pass.** [`docs/autoresearch/`](../autoresearch/README.md) activates only when the prerequisites in its README are met. Running Track B before Track A optimizes around broken behavior.
13. **A checklist item is not closed until it is committed and pushed.** Ticking `[x]` in ROADMAP.md, updating STATUS.md, and committing supporting evidence files must land in a pushed commit before the item counts as done. An unpushed `[x]` is not closed.

---

## File Map

| File | Purpose | When you must read it |
| --- | --- | --- |
| `README.md` | This file. Bootstrap rules and file map. | Every session, first. |
| `NORTH-STAR.md` | The mission, the three-fold success bar (operator UX + developer economics + lifecycle completeness), and the differentiators vs Codex CLI and Claude Code. | Every session, second. Anchors *why*. |
| `STATUS.md` | Live state: current epoch, current milestone, last action, next action, blockers, evidence pointers. Agent-updated per milestone transition. | Every session, third. Tells you *where you are*. |
| `ROADMAP.md` | Three epochs (Stabilize → Differentiate → Scale), each with milestones and concrete items. The spine of all work. | When picking the next item, opening a new milestone, or proposing scope. |
| `EVALUATION.md` | Tiered scorecard (Tier 1 token+UX bars / Tier 2 lifecycle coverage / Tier 3 head-to-head benchmarks). Verification commands per tier. | Before claiming a milestone or item is "done"; before declaring an epoch complete. |
| `FIX-STANDARD.md` | The 7-step procedure every non-trivial fix must follow (load memory → explore → triggers → SDK grounding → correct layer → verify → record → write memory). | Before starting any defect closure, roadmap bug item, or quality-gate failure investigation. |
| `OPERATOR-LANGUAGE.md` | Banned operator-facing terms, good/bad operator prompt shapes, and the F1-F10 / E1-E9 / R1-R3 operator scenarios used to validate every change. | Before testing any operator-facing surface; before writing any operator-facing copy. |
| `TUNING.md` | Continuous CLI monitoring streams + per-prompt tuning loop for refining agent tools, allowlists, prompts, and boundaries based on live evidence. | When testing a live agent run; when investigating an operator-UX regression the rubrics didn't catch. |
| `RESUME.md` | Protocol for picking up after a session drop, context compaction, or fresh agent handover. | First time you join a session that already has STATUS.md content; whenever you are uncertain about continuity. |
| `INDEX.md` | Owner map: which concern lives in which file, in this folder *and* across the rest of the repo (rubrics, gates, workflows, memory, knowledge). References, does not duplicate. | Before creating any new doc; whenever you need to find the authoritative source for a topic. |
| `INSIGHTS.md` | Append-only log of direction audits produced by the `goal-audit` skill. Each entry compares user intent (from recent session transcripts) against framework state and surfaces autoresearch focus candidates. | When you want to know what the last audit found, or after invoking the `goal-audit` skill. The skill writes here; you read here. |

---

## Bootstrap Sequence For A Fresh Session

1. Read `README.md` (here).
2. Read `NORTH-STAR.md`. Internalize the three-fold success bar and the differentiator vision.
3. Read `STATUS.md`. Note the current epoch, current milestone, last action, and next action.
4. If `STATUS.md` shows in-flight work and you are uncertain about continuity, read `RESUME.md` and follow its protocol.
5. Open the file that matches your next move: `ROADMAP.md` to pick an item, `EVALUATION.md` to verify a claim, `INDEX.md` to find an existing owner.
6. Do the work, then update `STATUS.md` per the cadence rule (per milestone transition).

---

## What This Folder Does *Not* Own

- **Active bug list (operator-visible defects).** Owned by `docs/IMPROVEMENTS.md`. Roadmap items in `ROADMAP.md` may reference IMP-NNN entries; they don't duplicate them.
- **Per-sprint checklist.** Owned by `docs/SPRINT-PROGRESS.md` for the current cycle. Roadmap is longer-arc; sprint is shorter-arc.
- **Historical evidence archive.** Owned by `docs/PROGRESS.md` and `CHANGELOG.md`. Those record what happened; this folder records what should happen and where we are.
- **Runtime contracts, agent capability rubrics, quality gates, workflows.** Owned by their existing surfaces under `docs/references/`, `docs/rubric/`, `docs/quality-gate/`, `docs/workflows/`. `INDEX.md` maps to them; nothing here is duplicated from them.
- **Operator prompts.** Owned by `docs/PROMPT.md`. `EVALUATION.md` references PROMPT.md when prescribing test scripts.
- **Memory and knowledge.** Owned by `.memory/` (via `builder memory`) and the repo KB (via `builder knowledge`). Read precedent before fixing; write back when learning is durable.
- **Autoresearch optimization loop (Track B).** Owned by [`docs/autoresearch/`](../autoresearch/README.md) as a sister framework. This folder governs *what* the product must become; `docs/autoresearch/` governs *how* the agent measures, optimizes, and re-tests its own prompt shape, context size, agent use, and runtime policy once the product is stable enough to optimize. Activation gate is [ROADMAP.md § M3.5](ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b); the loop must not run before Track A bug fixes close. When [STATUS.md](STATUS.md) shows the current milestone is M3.5, descend into [`docs/autoresearch/README.md`](../autoresearch/README.md) and follow its read order.

---

## How To Use This Framework If You Are A Human

- To redirect the agent: edit `STATUS.md` and add a `Manual override` line under *Next Action*. The agent picks it up next session.
- To change the goal itself: edit `NORTH-STAR.md`. Roadmap and evaluation should follow.
- To add a new milestone or item: edit `ROADMAP.md`, then write a short note in `STATUS.md` so the next agent knows about it.
- To add a new evaluation bar: edit `EVALUATION.md` and link the bar to the roadmap milestone it gates.
