# OPTIMIZE — Autonomous Builder optimization loop

Status: **dormant** (see [`README.md`](README.md) prerequisites).

This is the agent's program for the autoresearch loop. The agent loops continuously, editing one bounded surface of the Builder at a time, measuring through `builder` CLI, and keeping or reverting based on a single composite metric under hard gates.

## Primary metric (lower is better)

```
composite = noncached_plus_output_tokens
```

Measured per shipped feature for a given fixture (see [`fixtures.md`](fixtures.md)). Averaged across `N=3` runs of the same fixture to suppress single-run noise. **P16 (2026-05-23):** dropped the prior `× operator_turns × wallclock_seconds` factors — they are correlated with token count (longer fixture runs produce more of each) and aren't billed, so the product compounded variance instead of averaging it (fixture-A CV went 77.5% → 14.7% after the change).

**An improvement only counts as a win if `composite_after < composite_before − 2σ_baseline`** where `σ_baseline` is computed per [`baseline_variance.md`](baseline_variance.md). Anything inside 2σ is noise.

## Hard gates (binary filters)

A run is **discarded regardless of composite metric** if any of these fail:

1. `cache_ratio > 5×` after turn 2 (every turn in the session).
2. `chunk_pressure_risk == false` for every run in the session.
3. `avoidable_cost_flags == []` for every run.
4. `gate_pass_rate == 1.0` (all quality gates pass).
5. Feature correctness: `npm run build && npm run test` passes in the devpulse workspace after the feature ships.
6. The full feature shipped (board reaches `done` state, not blocked or partial).

If any gate fails, set `decision=discard` regardless of composite.

## The loop

```
for each iteration:
  1. read top unattempted idea from docs/autoresearch/OPTIMIZE_IDEAS.md
  2. builder memory search "<idea-topic>"               # GOAL.md fix-standard step 0
  3. git worktree add ../optim-<id> -b optim/<id>       # disposable workspace
  4. modify ONE logical concern across at most 3 files from the allowlist below
  5. git commit -m "<change summary>"
  6. for fixture in fixtures.md (pick one until proxy phase complete):
       a. fresh devpulse seed:  cp -r .seed/devpulse  /tmp/devpulse-<run-id>
       b. start builder against that path on a unique port
       c. drive the scripted prompt through Agent page (browser or API harness)
       d. wait for `done` or hard timeout (proxy: 5min; ship: 25min)
       e. capture: builder logs analyze --session <id> --json
       f. capture: builder metrics show --json --full
       g. capture: builder board show --json
       h. capture: cd devpulse && npm run build && npm run test
  7. compute composite, evaluate hard gates
  8. append row to optimize_results.tsv
  9. if all gates pass AND composite improvement > 2σ:
        promote to ship-cycle validation (1 full feature, 25-min budget)
        if ship-cycle also passes: keep branch, update OPTIMIZE_IDEAS.md
        else: discard
     else:
        discard, git worktree remove ../optim-<id>
  10. mark idea as attempted in OPTIMIZE_IDEAS.md with the result
```

## Allowlist (files the agent may edit)

Start conservative. Widen only after the loop produces stable wins.

**Phase 1 — prompt shape only**:
- `src/autonomous_agent_builder/agents/execution_policy.py`
- `src/autonomous_agent_builder/embedded/server/agent_documentation_context.py`
- `src/autonomous_agent_builder/embedded/server/agent_observability_context.py`
- `src/autonomous_agent_builder/orchestrator/active_feature_scope.py`
- `src/autonomous_agent_builder/orchestrator/gate_feedback.py`
- `src/autonomous_agent_builder/orchestrator/phase_context.py`

**Phase 2 — runtime policy** (only after Phase 1 plateaus):
- `src/autonomous_agent_builder/orchestrator/agent_run_lifecycle.py`
- `src/autonomous_agent_builder/agents/definitions.py`
- Claude Agent SDK subagent definitions

**Phase 3 — context assembly** (only after Phase 2 plateaus):
- `src/autonomous_agent_builder/embedded/server/routes/agent.py` prompt-assembly sections only (no route handler signature changes)

## Forbidden surfaces (never edit during the loop)

- `tests/**`
- `docs/quality-gate/**` (gate definitions)
- Readiness checks, gate runners, complexity baselines
- The devpulse workspace contents (`/home/gurusharangupta/Builder-Workspace/devpulse`)
- The `.seed/devpulse` snapshot
- Anything outside `src/autonomous_agent_builder/`

## Constraints

- **One logical concern per commit.** Multi-file allowed if they belong to one concern; diff size is the tie-breaker.
- **No new dependencies.** No `pip install`, no `npm install <new>`.
- **Same fixture prompt per run.** The agent cannot pick easier fixtures to game the metric.
- **No edits to `prepare.py`-equivalents.** Readiness, fixtures, gate infrastructure are immutable from the loop's perspective.
- **Simpler wins ties.** Equal composite + equal gate pass → fewer lines wins. Same diff size → earlier-attempted wins.

## Stop condition

Run continuously until one of:

- 50 consecutive iterations with no win (the search has converged or is stuck).
- All ideas in `OPTIMIZE_IDEAS.md` marked attempted.
- Operator interrupts.
- Cumulative cost exceeds budget set in `optimize_results.tsv` header.

When stopped, write a closeout entry to `docs/autoresearch/PROGRESS.md` summarizing wins and updating the threshold floor.

## Promotion path

- Fast-proxy win (single fixture, 3 runs) → run on **all** fixtures.
- All-fixtures win → full ship-cycle validation (25-min budget, real Agent page).
- Ship-cycle win → merge to main, becomes new baseline, σ recomputed.

## Notes for the agent

- Read `docs/goal/FIX-STANDARD.md` before each iteration. The Fix standard ordering applies.
- Read AGENTS.md required triggers if editing files with triggers attached.
- If you're tempted to edit a forbidden surface, the answer is "no, propose a Track A bug instead."
- Optimizations must be SDK-grounded. Cite the Claude Agent SDK feature being leveraged (cache control, permissions, hooks, subagents, AskUserQuestion, compaction).
- A 200-token saving from *deleting* prompt text beats the same saving from adding 20 lines of policy.
