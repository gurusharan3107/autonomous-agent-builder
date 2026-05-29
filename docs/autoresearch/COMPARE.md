# Compare — Two-Run Diff Protocol

> **Read [README.md](README.md), [METRICS.md](METRICS.md), [HARNESS.md](HARNESS.md), and [baseline_variance.md](baseline_variance.md) first.**

This file specifies how `scripts/autoresearch/compare.py` turns two run rows into a `keep` / `discard` / `crash` verdict that the loop in [OPTIMIZE.md](OPTIMIZE.md) consumes. The protocol exists so verdicts are mechanical and reproducible — not subject to the model's enthusiasm for its own change.

## Inputs

Comparison always takes:

| Input | Source | Notes |
| --- | --- | --- |
| `baseline_run` | A row in `baseline_runs.tsv` (or a prior `keep`-status row in `optimize_results.tsv`) | Same fixture, same `main` branch, computed σ already recorded |
| `candidate_run` | A row in `optimize_results.tsv` just written by `run.py` | Same fixture, candidate branch |
| Baseline σ | `baseline_runs_summary.json` per [baseline_variance.md](baseline_variance.md) | If absent or unstable, comparison aborts with `discard` and reason `baseline_unstable` |

Both runs must share the same `fixture_id`, `runtime_sdk`, and (where relevant) `model`. Cross-fixture or cross-lane comparisons are silently meaningless and the script must reject them.

## The decision tree

```
1. Did candidate crash?
   YES → verdict = discard, reason = "crash", detail = stop_reason
   NO → continue

2. Did all hard gates pass on candidate?
   NO → verdict = discard, reason = "hard_gate_failed", detail = which gates failed
   YES → continue

3. Is candidate.composite < baseline.mean - 2*baseline.stdev?
   NO → verdict = discard, reason = "composite_within_2sigma_of_baseline"
   YES → continue

4. Does the per-prompt diff show a healthy improvement pattern?
   NO → verdict = discard, reason = "suspicious_per_prompt_diff", detail = diff anomalies
   YES → continue

5. Did anything in the safety set degrade?
   YES → verdict = discard, reason = "safety_regression", detail = which signal degraded
   NO → continue

6. verdict = keep, reason = "composite_improved_above_noise_floor"
```

Each step is detailed below.

## Step 1 — Crash

`candidate.decision_status == "crash"` means the process failed before the fixture completed. Always discard. Capture `${EVIDENCE_DIR}/crash.log` reference in the verdict detail so the agent can post-mortem.

## Step 2 — Hard gates

The six gates from [METRICS.md § Hard Gates](METRICS.md#hard-gates-binary-filters):

1. `cache_ratio_gt_5x_after_turn_2`
2. `chunk_pressure_risk_false`
3. `avoidable_cost_flags_empty`
4. `gate_pass_rate_full`
5. `feature_correct`
6. `fully_shipped`

ALL must be true on the candidate. A single failure → discard. The verdict detail names which gate(s) failed and includes the specific evidence pointer (which prompt had `cache_ratio ≤ 5`, which avoidable_cost_flag fired).

Hard gates are *binary*. There is no "almost passed cache ratio with 4.8×" — the threshold is the threshold. The reason is that ratios degrade gradually over many turns; if 4.8× is acceptable today, 4.2× becomes acceptable tomorrow.

## Step 3 — 2σ test on composite

The single most important test:

```python
noise_floor = baseline.mean - 2 * baseline.stdev
if candidate.composite >= noise_floor:
    return discard("composite_within_2sigma_of_baseline")
```

This rule is non-negotiable. Without it, the loop will declare random LLM sampling jitter as wins and will drift over many iterations. See [baseline_variance.md § Why N=5](baseline_variance.md#why-n5-and-when-to-go-higher) for the statistical reasoning.

If `baseline.stdev / baseline.mean > 0.30`, the baseline is too noisy for honest comparison; rerun the baseline with `N=10` before continuing. The compare script should refuse to run with σ/µ > 0.30 and tell the operator to widen N.

## Step 4 — Per-prompt diff sanity

A composite win can be real or it can be an accident — for example, the candidate happens to ship in 2 fewer turns because the model got lucky on intake. The per-prompt diff catches accidents.

Diff procedure:

1. Pair candidate prompts with baseline prompts by `prompt_index` (the i-th prompt of one with the i-th of the other).
2. Compute per-prompt deltas for `tokens_input`, `tokens_cached`, `noncached_plus_output_tokens`, `cache_ratio`, `tool_calls_count`, `duration_ms`.
3. Compute per-block deltas from `context_breakdown_json` (the `blocks[*].tokens` per block name).

A healthy improvement looks like:

- One or two blocks shrink significantly (the ones the optimization targeted).
- Stable prefix (`stable_system_prefix`) unchanged.
- `cache_ratio` ≥ baseline on every turn past turn 2.
- `tool_calls_count` similar (slightly lower acceptable, much higher suspicious).
- `prompt_count` (operator turns) similar or one less.

A suspicious pattern (any of which triggers `discard` with `suspicious_per_prompt_diff`):

- **`stable_system_prefix` shrank.** This usually means the agent moved stuff out of the cache prefix into per-turn context, which kills cache hits on subsequent runs. Almost always a regression masquerading as a win.
- **`unattributed_tokens` jumped.** The anchor strings in CONTEXT-LEDGER.md are stale. Fix the anchors before trusting the comparison.
- **`tool_calls_count` halved.** The model probably stopped calling a tool it needed. The win is likely brittle.
- **`prompt_count` halved.** The operator-turn count dropped because the model skipped an intake question; the resulting feature probably loses scope alignment. Cross-check with the fixture's `expected_intake`.
- **One turn lost > 50% of tokens but `cache_ratio` on that turn dropped.** The change kills caching on that turn. Long-run regression.

Each anomaly is enumerable; the compare script encodes them as named checks so verdicts are mechanical.

## Step 5 — Safety regression

Some signals are not in the composite but must not silently degrade. If the candidate degrades any of these vs the baseline, discard with `safety_regression`:

| Signal | Threshold |
| --- | --- |
| `cost_usd` | Must not exceed baseline by more than 50% (a 50%+ cost increase for a token saving means the cost saving is illusory — Anthropic billed differently than the token count predicts). |
| `recent_risky_runs` | Must remain 0 (per Tier 1 in [docs/goal/EVALUATION.md](../goal/EVALUATION.md)). |
| Any new error in `errors.json` not present in baseline | Discard. New errors are not free. |
| `stop_reason` patterns | If baseline had `completed` on every agent run and candidate has `max_turns` or `capability_limit` on any, discard. |
| Cache creation tokens (when measurable) | Must not exceed baseline by 2× for any block (cache churn — keeps creating the cache instead of reading it). |

## Step 6 — Keep

If all five filters pass, the candidate is kept. The compare script:

1. Writes `decision = "keep"` to the candidate's row in `optimize_results.tsv`.
2. Computes `composite_delta_pct = (candidate.composite - baseline.mean) / baseline.mean * 100` and writes it.
3. Returns a verdict JSON to stdout for the loop to consume.
4. Optionally renders a one-line summary into `OPTIMIZE_IDEAS.md` under the idea's attempt log, per the format `- Attempted YYYY-MM-DD branch:<id> result:keep composite_delta:-7.3% notes:<one line>`.

## Verdict JSON shape

`compare.py` always prints exactly one JSON object to stdout:

```json
{
  "decision": "keep",
  "reason": "composite_improved_above_noise_floor",
  "fixture": "A",
  "candidate_run_id": "abc123",
  "baseline_summary": {
    "mean": 3.41e7,
    "stdev": 4.10e6,
    "noise_floor_2sigma": 2.59e7,
    "n": 5
  },
  "candidate_summary": {
    "composite": 2.48e7,
    "composite_delta_pct": -7.34,
    "noncached_plus_output_tokens": 12450,
    "operator_turns": 4,
    "wallclock_s": 498,
    "cost_usd": 0.31
  },
  "gates": {
    "cache_ratio_gt_5x_after_turn_2": true,
    "chunk_pressure_risk_false": true,
    "avoidable_cost_flags_empty": true,
    "gate_pass_rate_full": true,
    "feature_correct": true,
    "fully_shipped": true
  },
  "per_prompt_diff": {
    "biggest_shrinkages": [
      {"prompt_index": 2, "block": "observability_context", "tokens_delta": -340, "pct": -100.0},
      {"prompt_index": 3, "block": "board_state", "tokens_delta": -820, "pct": -45.0}
    ],
    "biggest_growths": [],
    "stable_prefix_drift_pct": 0.0,
    "unattributed_tokens_max": 12,
    "suspicious_patterns": []
  },
  "safety": {
    "cost_delta_pct": -28.0,
    "new_errors": [],
    "stop_reason_regressions": []
  }
}
```

A `discard` verdict has the same shape with `"decision": "discard"` and a populated `"detail"` field that names the failing check.

## Aggregate cumulative view (for the loop)

`compare.py --history` prints a Karpathy-style cumulative trajectory:

```
iteration  branch                    fixture  composite     delta_pct  decision  reason
0          main                      A        3.41e7        baseline   keep      baseline
1          optim/idea-3-1716       A        2.48e7        -27.3%     keep      composite_improved
2          optim/idea-7-1717       A        2.61e7        -23.5%     discard   composite_within_2sigma
3          optim/idea-12-1718      A        2.32e7        -32.0%     keep      composite_improved
...
```

This is the "are we converging" view the loop operator reads to know whether the search is producing real progress.

## What this protocol explicitly does not do

- **Does not compare across fixtures.** A win on Fixture A says nothing about Fixture B. The promotion path in [OPTIMIZE.md](OPTIMIZE.md) requires re-running on all fixtures after a Fixture A win before a branch is considered for merge.
- **Does not compare across runtime lanes.** A win on `claude` says nothing about `codex_sdk`. Cross-lane comparison is for declaring "preferred" (Tier 3 in [docs/goal/EVALUATION.md](../goal/EVALUATION.md)), not for the optimization loop.
- **Does not auto-merge.** A `keep` verdict means "branch is kept locally"; merge to main is a human decision after the branch passes all five fixtures.
- **Does not learn from prior discards.** The loop reads OPTIMIZE_IDEAS.md top-down; the compare script doesn't reorder ideas based on past results. Ordering is a meta-loop concern, not a comparison concern.

## Honest limitations

- The 2σ rule depends on baseline stability. If devpulse changes structurally between baseline runs and optimization runs (e.g., a new dependency is added, the seed snapshot drifts), the baseline becomes invalid and σ-based decisions become meaningless. The harness must verify `.seed/devpulse` content hash matches between baseline and run; if not, refuse to compare.
- LLM sampling temperature must be pinned. If the runtime policy varies temperature between baseline and run, σ will be misestimated. The compare script asserts the `execution_policy.py` SHA in baseline matches the SHA in the candidate's parent commit — if not, the result is suspect.
- Per-block attribution depends on `context_breakdown_json`. If anchors are stale (Path A) or the ledger is incomplete (Path B), the per-prompt diff is unreliable. The compare script flags this via `unattributed_tokens_max > 5% of total` and treats the candidate as `discard` even if composite improved — the win cannot be trusted.

## Related

- [OPTIMIZE.md](OPTIMIZE.md) — the loop that consumes verdicts
- [HARNESS.md](HARNESS.md) — where `compare.py` is invoked
- [METRICS.md](METRICS.md) — composite definition and gate definitions
- [baseline_variance.md](baseline_variance.md) — how σ is established
- CONTEXT-LEDGER.md — what `unattributed_tokens` means
