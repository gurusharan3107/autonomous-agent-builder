# Autoresearch progress log

Per-patch / per-run / per-decision log for the autoresearch loop. ROADMAP `M3.5` tracks milestone scope; this file tracks within-milestone iterations. Newest first.

Skill closeouts (Baseline / Iterate / Fix) write here, not to ROADMAP / CHANGELOG / STATUS § Recent Decisions. Cross-cutting decisions still land in STATUS / ROADMAP.

## 2026-05-24

- **P18 — Seed DB carries stale execution state across baseline runs** — fixture B iter 1 (v2 post-jinja2-fix) shipped `feature_correct=True` + pytest 169 passing but came back `gates_passed=4/6, status=incomplete` because the seed's `.agent-builder/agent_builder.db` carried 4 features / 8 tasks / 2 sprints / 5 chat_sessions / 53 agent_runs from prior sessions. The agent saw leftover backlog items ("DevPulse", "CSV export", "GitHub auth UI") unrelated to fixture B's "notes feature" prompt; one of them got blocked (`Wire persistence for Add GitHub authentication UI` status=failed, phase=integration) and the gate evaluator reported non-zero non-done tasks. Fix: `run.py:restore_seed` now wipes 11 stale-state tables (`agent_run_events`, `agent_runs`, `chat_events`, `chat_messages`, `chat_sessions`, `gate_results`, `design_documents`, `tasks`, `sprints`, `workspaces`, `features`) after copy + repoint. Projects row preserved (repo_url-repointed). Each iter now starts from an empty backlog on identical product code. Commit pending.
- **Autonomous self-heal + per-iter strict gate + seed pytest-collect preflight + feature_check stderr capture + summary merge** — six-layer defense after a fixture-B N=5 baseline burned ~$5 / 1.5h on 3 doomed iters before the operator noticed every iter had `feature_correct=False`. Root cause: seed `.venv` missing `jinja2`/`pytest_asyncio` + seed `requirements.txt` had uncommitted working-tree pytest-asyncio that HEAD didn't reflect. Layers: (1) `.claude/skills/autoresearch/scripts/self_heal.py` — skill-owned diagnose-and-fix probe invoked by `baseline.py` on a gate failure. Parses `feature_check.log` + seed git state for known patterns (missing python module → pip-install into seed; missing pytest plugin → install; seed uncommitted working-tree → commit), applies the mechanical fix, returns JSON record. Baseline retries the iter in a fresh `run-<N>.heal1/` evidence subdir; cap 1 fix + 1 retry per iter. Today's incident would now auto-heal at iter 1: gate fires → self_heal detects `ModuleNotFoundError: jinja2` → `pip install jinja2` into seed → retries → continues. (2) `preflight.py:check_seed_pytest_collect` runs `pytest --collect-only` against the seed before any iter spends a token — catches missing-deps for $0 in ~1.5s. (3) `preflight.py:check_seed_git_clean` flags uncommitted seed working-tree. (4) `baseline.py` strict per-iter gate aborts on any non-shipped / sub-6-of-6 / `feature_correct ≠ True` iter when self_heal can't match a pattern; `--allow-imperfect-iter` for operator-acknowledged flake. (5) `run.py:run_feature_check(evidence_dir)` captures every pip/pytest stdout+stderr to `evidence_dir/feature_check.log` so silent install failures leave a forensic trail. (6) `baseline.py` merges new summary with existing — partial re-baselines no longer clobber stable-fixture data. SKILL.md Hard Rules 11–12 updated. Commit pending.
- **Routing change: autoresearch entries → PROGRESS.md** — skill closeouts no longer touch ROADMAP/CHANGELOG/STATUS. Pointer added to ROADMAP `M3.5` + CHANGELOG. Lane closeout docs updated. Commit pending.
- **Skill compaction sweep** — KNOWN_PATTERNS P10–P17 + lane docs + SKILL.md "Before anything" section. 1356→1244 lines / 11.7k→10.3k words. Commit `0562f7a`.
- **Global doc rule** — agent-audience default for skills/, docs/, workflows/, references/, `.memory/`, ROADMAP/CHANGELOG/STATUS. Operator-friendly only on request. `~/.claude/CLAUDE.md` Rules. Commits `7d4e1f4`, `e30e025`.
- **Process awareness** — `.claude/skills/autoresearch/scripts/lane_status.py` (read-only progress reporter; auto-discovers `baseline.py`/`loop.py` from `ps -ef`); `preflight.py:check_no_inflight_lane` (hard-fail Recipes 1/2/3 on detected lane); SKILL.md "Before anything — check for in-flight lanes" + `Bash run_in_background:true` + `Monitor` launch pattern in both lane Do blocks. Commit `5d8c4fc`.
- **Skill polish before B–E re-baseline** — `preflight.py` unstable-fixture severity warn→fail for Recipes 2/3 + `--allow-unstable-promotion` override; KNOWN_PATTERNS gains P15/P16/P17; `diagnose_hang.py` gains P11/P14/P15/P16/P17 matchers; `iterate.md` "stable" semantics clarified (not_measured ≡ unstable for preflight). Commit `3e363f0`.
- **P17 — Seed dep gap: pytest-asyncio missing from `requirements.txt`** — fixture B 0/4 `feature_correct=False`; Builder's code-gen pytest passed inside `/tmp/aab-workspaces/<task_id>` (its venv installed deps ad-hoc) but harness's clean post-FF venv didn't. Fix: added `pytest-asyncio>=0.23.0` to `~/Builder-Workspace/devpulse/requirements.txt`; re-captured seed (`a9986867…` → `20af53c0…`); truncated 5 fixture-B baseline rows + 31 per-prompt rows. Bare-seed pytest 107 → 139 passing. Commit `4f4676b`.
- **iterations.html: progress chart** — 240px chart with baseline-runs scatter (B1..N) + iteration headroom (I1..M) + shaded μ ± 2σ noise band + μ line + 2σ-floor line + verdict-colored dots. Replaces 64px iteration-only sparkline. Commit `1416f53`.
- **iterations.html: baseline detail section** — fixtures grid (A–E status pills + CV%-colored σ indicator) + per-run table for baseline-only state. `render_iterations.py` reads `baseline_runs.tsv` + summary directly. Commit `bb16f3d`.
- **P16 — Composite formula compounded correlated noise** — `noncached_plus_output_tokens × operator_turns × wallclock` had CV=77.5%, 2σ-floor=-3.19e9 (useless). Switched to `composite = noncached_plus_output_tokens`. Fixture A: μ=216497, σ=31831, CV=14.7%, 2σ-floor=152835. `run.py:870` + 6 doc sites + 9 baseline rows backfilled. Commit `bae5619`.
- **P15 — Composite formula reads wrong metrics key** — `run.py:870` read `metrics["optimization"]` not `optimization_summary` (P12 fix missed parallel site). All 5 baseline composites landed as 0. Backfilled from each `metrics.json`. Commit `dcd3fd3`.
- **N=5 fixture-A Baseline + Fix-lane P11/P12/P13/P14** — 3/5 shipped at gate_pass_rate=1.0; 2/5 non-shipped (1 incomplete @ 25-turn cap, 1 crash on pre-P14 409). Substrate ready. Commit `171cd69`.
- **3-gate Fix lane** — `chunk_pressure_risk_false` (P12 metrics key), `gate_pass_rate_full` (board show vs task list), `feature_correct` (Playwright ignore-glob). Commit `4a2b8e5`.
- **autonomy-audit skill: two-layer architecture** (deterministic + model-backed). Commit `2599d3b`.
- **autoresearch first `status=shipped`** — Cycle 11, gate_pass_rate=0.5, wallclock=492s. After 7 contract-drift fixes (P1–P10) the loop produces non-crash iterations. Commit `6fa9f90`.

## 2026-05-22

- **M2.3 telemetry honesty** — `_runtime_aggregates(session_id=...)` honestly session-scoped (was reading `agent_runs` globally → `top_cost_drivers` and cache stats bled across sessions). New `tasks.chat_session_id` FK + analyze.json `runtime_aggregates.session_scoped: true` flag. Unblocks σ-floor.
- **M3.5 Track B Phase B+C** — 5 self-contained Python scripts in `scripts/autoresearch/` (`run.py`, `baseline.py`, `compare.py`, `loop.py`, `extract_context_breakdown.py`). None import from `autonomous_agent_builder`; all use `builder` CLI as subprocess + HTTP endpoints. Plus `setup_seed.sh`, `docker-compose.yml`, README runbook.

## Schema

- One bullet per entry. Date `## YYYY-MM-DD` header, newest first within the date.
- **Lead with the change** (bold). Then `file:line` or sha. Numbers (μ/σ/CV%/N/wallclock_s). Status flag only for non-shipped (`(OPEN)`, `(PARTIAL)`).
- Cross-link to KNOWN_PATTERNS (`P15`, `P16`) when patterns apply. Don't restate the pattern body.
- Drop "why this matters" — `git show <sha>` carries the rest.
- Future Iterate-lane entries: idea ref, composite delta vs baseline, verdict, branch.
- Future Baseline-lane closeouts: fixtures × N, σ-floor, status per fixture.
- Future Fix-lane closeouts: file:line, root cause one-liner, sha.

## What does NOT go here

- ROADMAP-scope items (milestone `[x]` ticks). Those belong in `docs/goal/ROADMAP.md § M3.5`.
- Cross-cutting decisions (e.g., goal/north-star changes). Those belong in `docs/goal/STATUS.md § Recent Decisions`.
- Builder runtime changes that surfaced through autoresearch but live in other surfaces. Those still go in CHANGELOG.
