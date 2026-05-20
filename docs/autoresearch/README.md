# Autoresearch for Autonomous Builder

This directory adapts Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) philosophy — *rapid autonomous iteration at small scale beats big runs at slow cadence* — to optimize the Autonomous Builder itself.

## Status

**DORMANT. DO NOT RUN.** This system activates only after every item in [Prerequisites](#prerequisites) is satisfied.

## What this is

An autonomous loop where an agent edits one bounded surface of the Builder, runs a scripted feature-creation cycle through the live devpulse workspace, measures token/cache/correctness signals via `builder` CLI, and keeps or reverts the change based on a primary metric with hard gates.

This is **Track B** in our delivery model.

- **Track A** (manual, runs first): fix the operator-facing bugs in `docs/IMPROVEMENTS.md` (IMP-001 through IMP-004 at minimum) the normal SDK-grounded way.
- **Track B** (this loop, runs second): optimize the Builder's prompt shape, context size, agent use, and runtime policy through the autoresearch loop, only after the baseline can already ship features cleanly.

Running Track B before Track A optimizes around broken behavior. Do not do that.

## Files

| File | Purpose |
|---|---|
| [`OPTIMIZE.md`](OPTIMIZE.md) | The agent loop contract — analogous to autoresearch's `program.md`. Loop steps, allowlist, constraints, metric, stop condition. |
| [`OPTIMIZE_IDEAS.md`](OPTIMIZE_IDEAS.md) | Living backlog of optimization hypotheses for the agent to draw from. |
| [`baseline_variance.md`](baseline_variance.md) | Protocol for measuring run-to-run noise before any optimization is declared a win. |
| [`fixtures.md`](fixtures.md) | Scripted operator prompts used for every experiment. Same prompt → comparable runs. |
| [`optimize_results.tsv`](optimize_results.tsv) | Append-only log of every experiment: branch, change, metric, gates, decision. |

## Prerequisites

This loop **must not run** until all of the following are true:

- [ ] IMP-001 through IMP-004 closed in `docs/IMPROVEMENTS.md` with regression tests.
- [ ] A fresh devpulse workspace can ship one full feature end-to-end through the Agent page with no operator intervention after approval.
- [ ] All four `docs/PROGRESS.md` thresholds met by the unmodified baseline:
  - `cache_ratio > 5x` after turn 2 every turn
  - `chunk_pressure_risk: false`
  - `avoidable_cost_flags: []`
  - `gate_pass_rate: 1.0`
- [ ] Baseline variance measured per [`baseline_variance.md`](baseline_variance.md): N=5 baseline runs with means and σ recorded for each metric.
- [ ] `builder lint --complexity-report --json` reports `0 violations`.

When all checkboxes are ticked, edit this section to record the date and move the loop to active status in [`OPTIMIZE.md`](OPTIMIZE.md).

## Mapping back to autoresearch

| Karpathy autoresearch | Autonomous Builder |
|---|---|
| `train.py` (the single mutable file) | The allowlist in [`OPTIMIZE.md`](OPTIMIZE.md) (initially: prompt-shape files only) |
| `prepare.py` (immutable infrastructure) | `tests/`, `docs/quality-gate/`, readiness gates, devpulse workspace contents |
| `val_bpb` (the single metric) | Composite metric defined in [`OPTIMIZE.md`](OPTIMIZE.md): `noncached_tokens × operator_turns × wallclock_s` under hard gates |
| `evaluate_bpb` (the ground-truth check) | `builder logs analyze` + feature-correctness check (`npm run build && npm run test` on devpulse) |
| `program.md` (agent instructions) | [`OPTIMIZE.md`](OPTIMIZE.md) |
| `results.tsv` | [`optimize_results.tsv`](optimize_results.tsv) |
| Wall-clock budget (5 min) | Fast proxy: 2–3 min per synthetic-task run. Promotion: full 20-min ship cycle. |
| "Simpler wins ties" | Same. Smaller diff wins on equal metric. |
