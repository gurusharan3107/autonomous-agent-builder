# Autoresearch for Autonomous Builder

This directory adapts Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) philosophy — *rapid autonomous iteration at small scale beats big runs at slow cadence* — to optimize the Autonomous Builder itself. This README is the single entry point: read it first, then descend into the file matching your task.

## Status

**ACTIVATING — 2026-05-22.** Pre-harness prerequisites are met (IMP-001..004 closed, fresh devpulse ships end-to-end, Tier-1 cache/chunk/avoidable thresholds clear by live devpulse evidence, complexity at 0 violations). Two prerequisites are deferred to in-harness validation: `gate_pass_rate=1.0` and N=5 baseline variance are both measured *during* baseline.py execution — they cannot be pre-verified without the harness existing. The loop becomes ACTIVE once Phase B (Jaeger + seed snapshot + OTEL smoke), Phase C (5 harness scripts), and Phase D1 (N=5 baseline) close cleanly.

**2026-05-23 — telemetry honesty landed.** `builder logs analyze --session <id>` is now session-scoped via `tasks.chat_session_id` FK (ROADMAP M2.3). `top_cost_drivers`, `cache_ratio`, `cached_tokens`, `raw_token_total`, `noncached_plus_output_tokens` are this session's numbers — not bled across every session in the DB. Analyze payload carries `runtime_aggregates.session_scoped: true` when scoping is active. Per-agent attribution lives in `runtime_aggregates.by_agent` (also session-scoped); per-prompt `prompts[]` keeps its operator-chat-turn semantics. The N=5 baseline σ-floor is now reliable.

The framework is spec-complete and the runner is executable today against the existing Builder CLI commands and `POST /api/agent/chat` / `POST /api/agent/chat/respond` HTTP endpoints. Source-code work that would improve diagnostic resolution is captured in [GAPS.md](GAPS.md).

## Owned freshness

Every file in this folder is kept consistent with current code, writer schemas, and activation contracts by [`.claude/skills/autoresearch/`](../../.claude/skills/autoresearch/SKILL.md). Its `freshness_sweep.py` runs at the close of every lane (Baseline / Iterate / Fix) and refuses lane closure on hard drift. 10 checks: 8 hard (metrics session-scoping, logs payload contract, `Task.chat_session_id` column, README telemetry-honesty line, METRICS `prompt_count` semantic, HARNESS session-scoped assertion, TSV header drift across all three result files, `autoresearch-explainer.html` AUTOUPDATE fences intact) and 2 soft (baseline-summary age ≤14d, CHANGELOG lane activity ≤30d). Treat the skill as the owner of this folder's correctness; don't hand-edit the contract docs without re-running the sweep.

## Read order

If you are an agent landing here and the loop is active, read in this order:

1. `README.md` (this file) — confirm activation, orient on file map.
2. [OPTIMIZE.md](OPTIMIZE.md) — the loop contract.
3. [METRICS.md](METRICS.md) — what you are measuring and where it comes from.
4. [OPTIMIZE_IDEAS.md](OPTIMIZE_IDEAS.md) — pick the next idea.
5. [HARNESS.md](HARNESS.md) — invoke the runner.
6. [COMPARE.md](COMPARE.md) — interpret the result.

If you are an agent on the source-change roadmap item ([docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b)) you also need:

- [SDK-OBSERVABILITY.md](SDK-OBSERVABILITY.md) — for the OTEL env-var prescription.
- [CONTEXT-LEDGER.md](CONTEXT-LEDGER.md) — for the context-attribution implementation.
- [GAPS.md](GAPS.md) — for the precise source-change list.

## What's in this folder

| File | Role | Status | Audience |
| --- | --- | --- | --- |
| `README.md` (this file) | Folder entry point, activation status, file map, load order. | Stable | Anyone landing here |
| [OPTIMIZE.md](OPTIMIZE.md) | The loop contract: what an iteration does, hard gates, allowlist, stop condition. The agent's `program.md`. | Stable | Agent running the loop |
| [OPTIMIZE_IDEAS.md](OPTIMIZE_IDEAS.md) | Living backlog of optimization hypotheses ordered by expected impact. The agent reads top-down. | Living | Agent picking next idea |
| [METRICS.md](METRICS.md) | Master metrics reference: every measurable signal, its source (Builder CLI / Claude SDK / Codex SDK / OTEL), which TSV column it lands in, and known gaps. | Stable | Agent + harness author |
| [SDK-OBSERVABILITY.md](SDK-OBSERVABILITY.md) | Claude Agent SDK and Codex SDK observability surface. Specific env vars to set per run. OTEL configuration that turns the loop from blind to fully observable. | Stable | Harness author |
| [CONTEXT-LEDGER.md](CONTEXT-LEDGER.md) | How to capture *where* prompt context came from. Two paths: ground-truth raw API body capture (Path A, executable today) and source-level instrumentation (Path B, needs code). | Stable | Anyone optimizing prompt shape |
| [HARNESS.md](HARNESS.md) | Concrete runner contract for `scripts/autoresearch/{run,baseline,compare,loop}.py`. Uses existing Builder CLI and HTTP endpoints. Pseudo-code level — implementation is a roadmap item. | Stable | Harness author |
| [COMPARE.md](COMPARE.md) | Two-run diff protocol with 2σ statistical test, per-prompt diff, verdict format that the loop consumes for keep/discard decisions. | Stable | Harness author + agent |
| [GAPS.md](GAPS.md) | Honest list of source-code changes needed to make the loop fully autonomous. Tiered into v1-minimum (must have to run loop at all) and v2-polish (improves the loop). | Stable | Roadmap planning |
| [fixtures.md](fixtures.md) | Scripted operator prompts (A short / B long / C ambiguous / D vague / E multi-turn). Same prompt every run = comparable runs. | Stable | Agent + harness |
| [baseline_variance.md](baseline_variance.md) | N=5 baseline run protocol that establishes the 2σ noise floor below which "wins" are sampling jitter. | Stable | Harness author |
| [baseline_runs.tsv](baseline_runs.tsv) | Header-only. Filled by `scripts/autoresearch/baseline.py`. One row per baseline cycle per fixture. | Empty | Harness output |
| [optimize_results.tsv](optimize_results.tsv) | Header-only. Filled by `scripts/autoresearch/run.py`. One row per optimization iteration per fixture. | Empty | Harness output |
| [per_prompt_results.tsv](per_prompt_results.tsv) | Header-only. Filled by `scripts/autoresearch/run.py`. One row per prompt within a session. Includes `context_breakdown_json` for source attribution. | Empty | Harness output |
| [iterations.json](iterations.json) | Per-iteration verdict + composite delta data. Regenerated by `.claude/skills/autoresearch/scripts/render_iterations.py` at every Baseline + Iterate closeout. | Living | Harness output, downstream tooling |
| [autoresearch-explainer.html](autoresearch-explainer.html) | Single-file living explainer: hand-curated prose (why/when/lanes/architecture/gates/FAQ) + 4 AUTOUPDATE fences for baseline summary, scatter, raw runs, and iterations history. Fences refreshed by `.claude/skills/autoresearch/scripts/render_iterations.py` at every Baseline + Iterate closeout. Authored via the [`html-artifact`](https://github.com/anthropics/html-effectiveness) skill (`~/.claude/skills/html-artifact/`). | Living | Operator + new reader |
| [INTROSPECTION.md](INTROSPECTION.md) | "Does the loop pay for itself?" — token economics, ROI, KB-grounded leads, lean recommendations. Overwritten by `.claude/skills/autoresearch/scripts/introspect.py` at every Baseline + Iterate closeout; git history is the canonical record. | Living | Anyone tuning the loop |

## How the framework hangs together

```
fixtures.md ────┐
                ├──► HARNESS.md (run.py) ──► writes:
OPTIMIZE.md ────┤                              optimize_results.tsv
                │                              per_prompt_results.tsv
                │                              raw_evidence/<run-id>/*
                │                                ▲
                │   uses signals defined in ────┤
                │                              METRICS.md
                │                                ▲
                │   sources signals from ────────┤
                │                          ┌─────┴────────────────┐
                │                          │ Builder CLI:         │
                │                          │   builder logs       │
                │                          │   builder metrics    │
                │                          │   builder board      │
                │                          │                      │
                │                          │ Claude SDK (OTEL):   │
                │                          │   SDK-OBSERVABILITY  │
                │                          │                      │
                │                          │ Per-prompt context:  │
                │                          │   CONTEXT-LEDGER     │
                │                          └──────────────────────┘
                │
                ▼
        COMPARE.md ──► keep / discard verdict ──► loop advances or rewinds
                ▲
                │
         baseline_variance.md ──► establishes 2σ floor before any "win" counts
```

## What this is

An autonomous loop where an agent edits one bounded surface of the Builder, runs a scripted feature-creation cycle through the live devpulse workspace, measures token/cache/correctness signals via `builder` CLI, and keeps or reverts the change based on a primary metric with hard gates.

This is **Track B** in our delivery model.

- **Track A** (manual, runs first): fix the operator-facing bugs IMP-001 through IMP-004 (see git log) the normal SDK-grounded way.
- **Track B** (this loop, runs second): optimize the Builder's prompt shape, context size, agent use, and runtime policy through the autoresearch loop, only after the baseline can already ship features cleanly.

Running Track B before Track A optimizes around broken behavior. Do not do that.

## Prerequisites

Pre-harness prerequisites (verified before Phase C):

- [x] IMP-001 through IMP-004 closed with regression tests. *(closed 2026-05-19, validated 2026-05-22)*
- [x] A fresh devpulse workspace can ship one full feature end-to-end through the Agent page with no operator intervention after approval. *(validated by 8 devpulse tasks reaching `done` status; IMP-012 closeout 2026-05-21)*
- [x] Three of four Tier-1 thresholds met by the unmodified baseline (per latest devpulse `builder logs analyze`):
  - `cache_ratio > 5x` after turn 2 every turn — *18019× on session `5dc61748` (2026-05-22)*
  - `chunk_pressure_risk: false` — *confirmed (2026-05-22)*
  - `avoidable_cost_flags: []` — *confirmed (2026-05-22)*
- [x] `builder lint --complexity-report --json` reports `0 violations`. *(2026-05-22, after Phase A1 extractions: hooks_trim, runner_options, subagent_definitions)*

In-harness prerequisites (validated during baseline.py execution in Phase D1, since they require the harness to exist):

- [ ] `gate_pass_rate: 1.0` per baseline run — *measured by baseline.py as part of each N=5 fixture run; not validatable against historical aggregates (current 71.875 reflects M1.x dev-time failures since fixed). Acceptance: every fixture A–E run in the N=5 baseline reports gate_pass_rate=1.0.*
- [ ] Baseline variance measured per [baseline_variance.md](baseline_variance.md): N=5 baseline runs with means and σ recorded for each metric — *Phase D1.*

When the in-harness prerequisites close, edit this section to flip the status line above to `ACTIVE — activated YYYY-MM-DD`.

## Where execution lives

- **This folder (`docs/autoresearch/`)** owns the contract: what to measure, how to compare, what counts as a win.
- **`scripts/autoresearch/`** owns the runner: 5 Python scripts (`run.py`, `baseline.py`, `compare.py`, `loop.py`, `extract_context_breakdown.py`) that drive fixtures, capture evidence, write TSV rows, run comparisons. Landed 2026-05-22 in commits `cdf7101` (scaffold + optional Jaeger compose) and `2284ba6` (Phase C v1 harness).
- **`.seed/devpulse`** owns the immutable starting state for every run. Captured by `bash scripts/autoresearch/setup_seed.sh` on first Baseline lane invocation; `chmod -R a-w` after capture.
- **`.claude/skills/autoresearch/`** owns the discipline layer: single entry + 3 lanes (Baseline / Iterate / Fix), preflight + closeout per lane, freshness sweep enforced at every closeout.
- **Builder source** owns the telemetry. As of 2026-05-23 (commit `a3354c2`), `builder logs analyze --session <id>` is honestly session-scoped via `tasks.chat_session_id` FK; the N=5 baseline σ-floor is now reliable.
- **`docs/goal/STATUS.md`** owns the live position on Track B (currently ACTIVATING; M3.5 D1 N=5 baseline unblocked 2026-05-23).

## Mapping back to autoresearch

| Karpathy autoresearch | Autonomous Builder |
|---|---|
| `train.py` (the single mutable file) | The allowlist in [OPTIMIZE.md](OPTIMIZE.md) (initially: prompt-shape files only) |
| `prepare.py` (immutable infrastructure) | `tests/`, `docs/quality-gate/`, readiness gates, devpulse workspace contents |
| `val_bpb` (the single metric) | Composite metric defined in [OPTIMIZE.md](OPTIMIZE.md): `noncached_plus_output_tokens` under hard gates (P16 2026-05-23: dropped `× operator_turns × wallclock_s` — multiplicative form compounded correlated noise) |
| `evaluate_bpb` (the ground-truth check) | `builder logs analyze` + feature-correctness check (`npm run build && npm run test` on devpulse) |
| `program.md` (agent instructions) | [OPTIMIZE.md](OPTIMIZE.md) |
| `results.tsv` | [optimize_results.tsv](optimize_results.tsv) |
| Wall-clock budget (5 min) | Fast proxy: 2–3 min per synthetic-task run. Promotion: full 20-min ship cycle. |
| "Simpler wins ties" | Same. Smaller diff wins on equal metric. |

## Cross-references

- Activation gate and roadmap position: [docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b)
- Evaluation tiers the loop must respect: [docs/goal/EVALUATION.md](../goal/EVALUATION.md)
- Fix standard (memory step 0, evidence step 7): [docs/goal/FIX-STANDARD.md](../goal/FIX-STANDARD.md)
- Owning skill (discipline layer): [.claude/skills/autoresearch/SKILL.md](../../.claude/skills/autoresearch/SKILL.md)
- Karpathy autoresearch original: sibling repo at `/home/gurusharangupta/code/autonomous-agent-builder-codex-architecture-review/autoresearch/`
