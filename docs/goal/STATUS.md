# Status — Live Project State

> **Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.**
> **Agent: update this file whenever a [ROADMAP.md](ROADMAP.md) milestone or item transitions state.** See [Update Protocol](#update-protocol) at the bottom.

This file is the live state. If it lies, the system is blind. Keep it honest.

---

## Current Position

| Field | Value |
| --- | --- |
| Current Epoch | **Epoch 1 — Stabilize** |
| Current Milestone | **M1.2 — Both lanes ship one feature on devpulse end-to-end** |
| Current Item In Flight | **M1.2 closed (Claude lane)** — devpulse sprint 5/5 tasks done; $2.08 total |
| Active Workspace | `/home/gurusharangupta/Builder-Workspace/devpulse` |
| Active Runtime Lane | Claude Agent SDK lane (`claude`) complete; Codex SDK lane (`codex_sdk`) pending |
| Last Update | 2026-05-21 — M1.2 Claude lane complete; 3 source-repo fixes applied |

---

## Last Completed Milestone

**M1.1 — Close the open operator-facing defects** (closed 2026-05-21 by Claude Sonnet 4.6)

All 8 IMPs closed with root cause, fix, and regression test:
- IMP-001: prompt context threading on intake follow-up
- IMP-002: gates-first enforcement before code-gen dispatch
- IMP-003: metrics showing 0 tokens for in-progress runs
- IMP-004: Recover button returning 409 for gate-infra errors
- IMP-006: scaffold agent using shell heredoc instead of Write tool
- IMP-007: agent dispatching all tasks simultaneously (connection pool exhaustion)
- IMP-008: `git worktree add` failing on unborn HEAD
- IMP-009: agent dispatching before scaffold completes

Re-verify evidence: 79/79 regression tests pass (11 pre-existing `TestDispatchPhases` / `TestPlanningPhase` failures also fixed this session via `_wire_db` autouse fixture). All IMP-specific tests pass.

---

## Next Action

The next agent landing here should:

1. Read [README.md](README.md), [NORTH-STAR.md](NORTH-STAR.md), and this file in order.
2. **Complete M1.2** — Claude lane done (5/5 tasks, $2.08). Run the same sprint on the `codex_sdk` lane to satisfy the "both lanes" requirement, OR declare M1.2 done for the Claude lane and open M1.3.
3. Before starting the Codex lane run, verify the server is live at `http://localhost:9876` via `cd /home/gurusharangupta/Builder-Workspace/devpulse && builder server status --port 9876 --json`.
4. Run `builder metrics show --json --full --limit 8` to collect Tier 1 token evidence.
5. Follow [FIX-STANDARD.md](FIX-STANDARD.md) for any new regressions.

---

## Blockers

| Discovered | Blocked Item | Description | Unblock Condition |
| --- | --- | --- | --- |
*No active blockers.*

---

## Evidence Pointers

Use this section to point at the most recent authoritative evidence for the current milestone. Replace prior entries when the milestone advances; archive prior pointers to `docs/PROGRESS.md` if they're durable history.

| Concern | Where the latest evidence lives |
| --- | --- |
| Latest agent session id (Claude lane) | Task `128e02f6` **done** 11:25 — scaffold (5m17s, $0.108) + code-gen (12m, $0.271) + gates + integration + build verify. IMP-010/011/012/013 all resolved. |
| Latest agent session id (Codex lane) | *TBD — not yet exercised in M1.2* |
| Latest token telemetry | Session `5a752c0a`: cost $0.065, 2 turns — `builder logs analyze --session 5a752c0a --json` |
| Latest metrics snapshot | *TBD — run `builder metrics show --json --full --limit 8` after M1.2 dispatch* |
| Latest board snapshot | `pending=3 active=0 done=2` — 2026-05-21; `cd /home/gurusharangupta/Builder-Workspace/devpulse && builder board show --json` |
| Latest complexity report | *TBD — `builder lint --complexity-report --json`* |
| Latest IMPs status | [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) — IMP-001 through IMP-013 all resolved |
| Latest sprint detail | [docs/SPRINT-PROGRESS.md](../SPRINT-PROGRESS.md) |
| Latest changelog entry | [CHANGELOG.md](../../CHANGELOG.md) |

---

## Tier Snapshot

Last known result of running each Tier of [EVALUATION.md](EVALUATION.md). Update on each milestone closeout.

| Tier | Last Run | Status | Notes |
| --- | --- | --- | --- |
| Tier 1 — Token + UX | 2026-05-21 (M1.2 in flight) | Partial — regression tests 79/79; devpulse done=2 (domain model + UI shell); Tier 1 full bars (cache_ratio, chunk_pressure, avoidable_cost) pending 3 remaining tasks | Re-run after remaining 3 M1.2 tasks complete |
| Tier 2 — Lifecycle Coverage | Not yet run | Pending | Runs at M2.1 |
| Tier 3 — Head-to-Head | Not yet run | Pending | Runs at M3.4 |

---

## Recent Decisions

*Record one short line per decision worth preserving across sessions. Keep this to the most recent 20 — older items move to memory via `builder memory add` if durable, or get deleted if ephemeral.*

- **2026-05-21** — Framework governance: Hard Rules 13 & 14 (commit+push on `[x]`, CHANGELOG before commit) added to `docs/goal/README.md`; `.gitignore` updated for runtime artifacts; `docs/goal/` self-containment confirmed; INSIGHTS→ROADMAP completed-item lifecycle documented; goal-audit SKILL.md updated with ROADMAP cross-check rule for Section C.
- **2026-05-21** — M1.2 Claude lane complete: devpulse sprint 5/5 tasks done, $2.08. Three source-repo gate bugs found and fixed: (1) `quality_gates/testing.py` set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, blocking pytest-asyncio in generated apps; (2) `embedded/scripts/feature_acceptance.py` `_TEST_SUFFIXES` excluded `.py`, making coverage signal always fail for Python projects; (3) `feature_acceptance.py` only recognized Node.js acceptance test runners — added `run-tests.js` pattern support for Python apps via node shim.
- **2026-05-21** — Source-repo improvements applied (Claude Opus 4.7 session): `query_timeout_seconds` 90→300; code-gen prompt removes spurious "Design: " prefix when no design context; orchestrator walrus operator replaced with pre-assignment; test suite fixed from 74/75 → 79/79 by wiring `test_db` to `TestDispatchPhases`/`TestPlanningPhase` (IMP-012 short-lived-session pattern required DB tables in tests).
- **2026-05-21** — M1.1 closed. All 8 IMPs resolved; 74/75 regression tests pass. IMP-010 found and closed: monitor-task not-stopped-on-exception + rollback guard + flush-error structlog. IMP-011 found and closed same session: `board_stream`/`approval_stream` SSE endpoints holding pool connections for their full client lifetime, exhausting SQLite QueuePool during 4-min scaffold runs; fixed by scoping `get_session_factory()` to initial snapshot only.
- **2026-05-21** — IMP-007 closed: project-level dispatch guard in `dispatch_lock.py` + prompt constraint in `agent_prompt_builders.py`. IMP-009 closed: scaffold timeout 30s→300s in `builder_tool_service.py` + scaffold-running pre-dispatch guard in `routes/tasks.py`.
- **2026-05-21** — Migration of legacy strategic docs completed. `PLAN.md`, `GOAL.md`, `MISSION.md` replaced with deprecation stubs pointing to `docs/goal/`. New goal/ files created: [FIX-STANDARD.md](FIX-STANDARD.md), [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md), [TUNING.md](TUNING.md). Hard Rules in [README.md](README.md) expanded from 7 to 12. Agent Working Principles added to [NORTH-STAR.md](NORTH-STAR.md). Working / historical docs (`PROGRESS.md`, `IMPROVEMENTS.md`, `SPRINT-PROGRESS.md`, `PROMPT.md`, `QUALITY_SCORE.md`, `REFERENCE.md`, `CHANGELOG.md`) stay as-is, referenced from goal/.
- **2026-05-21** — `docs/goal/` framework initial creation. Migration target chosen; durable strategic content migrated into `docs/goal/` files; legacy files referenced (not duplicated) via [INDEX.md](INDEX.md).
- **2026-05-21** — Success bar finalized as three-fold: operator UX + developer economics + lifecycle completeness. Both lanes (`claude` and `codex_sdk`) first-class.
- **2026-05-21** — Roadmap epochs adopted: Stabilize → Differentiate → Scale. M1.1 (close 4 IMPs) is the current entry point because Track A blocks Track B autoresearch.

---

## Cross-Session Continuity Hints

When you land here and the [Current Position](#current-position) reads stale or ambiguous, do not start a new line of work. Instead:

1. Open [RESUME.md](RESUME.md) and follow the protocol.
2. Cross-check the dashboard (`builder map`, `builder board show --json`, `builder server status --port 9876 --json`) against this file.
3. If reality differs from this file, **fix this file first** before doing any new work. A wrong STATUS.md is a Tier 1 failure for resumability — it must be corrected, not patched around.

---

## Update Protocol

**When to update:**

- A [ROADMAP.md](ROADMAP.md) item transitions `[ ]` → `in_progress` → `[x]`.
- A milestone transitions `pending` → `in_progress` → `done`.
- An epoch transitions or a new epoch becomes current.
- A blocker is discovered or cleared.
- A decision worth preserving across sessions is made.
- A Tier of [EVALUATION.md](EVALUATION.md) is run; record the outcome.

**How to update:**

1. Edit the [Current Position](#current-position) table to reflect the new state.
2. Move closed milestones into [Last Completed Milestone](#last-completed-milestone).
3. Replace [Next Action](#next-action) with the new concrete next step.
4. Append a one-liner to [Recent Decisions](#recent-decisions) when the change is durable.
5. Update [Tier Snapshot](#tier-snapshot) when an evaluation tier was run.
6. Update [Evidence Pointers](#evidence-pointers) when the latest evidence sources change.
7. Set `Last Update` in [Current Position](#current-position) to today's date and the agent that made the change.

**What not to do:**

- Do not write running history here — that belongs in [docs/PROGRESS.md](../PROGRESS.md).
- Do not write bug detail here — that belongs in [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md).
- Do not write per-sprint task lists here — that belongs in [docs/SPRINT-PROGRESS.md](../SPRINT-PROGRESS.md).
- Do not let this file grow past ~120 lines. Compress, archive, or delete old entries.
