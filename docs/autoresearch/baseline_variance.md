# Baseline variance protocol

The loop in [`OPTIMIZE.md`](OPTIMIZE.md) declares improvements only when the composite metric drops by more than **2σ of baseline noise**. This file defines how σ is measured.

Without this step, the loop will declare random LLM sampling noise as wins.

## When to run

- Once, after Track A bug fixes land and before the first optimization iteration.
- Re-run whenever a confirmed Phase-1/2/3 win merges to main — the baseline changes, σ must be recomputed.
- Re-run if the Claude Agent SDK version, model, or runtime policy materially changes.

## Protocol

1. **Lock the baseline.** Checkout `main`, no uncommitted changes. Record commit SHA.
2. **Snapshot devpulse seed.** `cp -r /home/gurusharangupta/Builder-Workspace/devpulse .seed/devpulse` — the immutable starting state for every run.
3. **Pick fixtures.** Use all fixtures listed in [`fixtures.md`](fixtures.md).
4. **For each fixture, run N=5 baseline cycles**:
   - Fresh worktree clone of `.seed/devpulse` to a unique temp dir.
   - Start `builder` on a unique port.
   - Drive the scripted prompt through the Agent page (browser or API harness).
   - Wait for `done` state or hard timeout (25 min).
   - Capture: `builder logs analyze --session <id> --json`, `builder metrics show --json --full`, `builder board show --json`, `npm run build && npm run test` exit codes.
   - Record one row in `baseline_runs.tsv` (same columns as `optimize_results.tsv`, plus `fixture_id`).
   - Tear down the worktree.
5. **Compute statistics** per fixture:
   - For `noncached_plus_output_tokens`, `operator_turns`, `wallclock_s`, and `composite`:
     - mean (µ)
     - standard deviation (σ)
     - min, max
   - For the four hard gates: pass rate across N runs (should be 1.0 — if not, the baseline is not stable enough for optimization yet).
6. **Record results** in this file under [Recorded baselines](#recorded-baselines).
7. **Set the noise floor.** A win in the loop requires `composite_after < µ_baseline − 2σ`. Smaller deltas are noise.

## Why N=5 (and when to go higher)

- 5 runs gives a usable σ estimate with reasonable wall-clock cost (~2 hours per fixture at 25-min cycles).
- If σ/µ > 30% for any metric, raise N to 10 — noise is dominating signal at N=5.
- If σ/µ > 50%, stop. The baseline is too unstable for optimization; investigate determinism (LLM sampling temperature, tool-call ordering, SDK retries) before continuing.

## Determinism hygiene

Optimization is impossible without reasonable run-to-run stability. Before running this protocol, verify:

- Claude Agent SDK temperature/seed settings are consistent across runs (check `execution_policy.py`).
- No background processes (cron, watchers) touch devpulse during a run.
- Builder process is restarted between runs — no carried-over state in memory.
- Same model version pinned (no automatic Sonnet 4.6 → 4.7 promotion mid-experiment).

## Recorded baselines

Empty until first run. Format:

```
### YYYY-MM-DD — main @ <sha>

Fixture: short-feature
  noncached_tokens: µ=12345 σ=987 (8.0%)
  operator_turns:   µ=3.2   σ=0.4 (12.5%)
  wallclock_s:      µ=865   σ=72  (8.3%)
  composite:        µ=3.4e7 σ=4.1e6 (12.1%)
  gates_passed:     5/5
  feature_correct:  5/5

Fixture: long-feature
  ...

Noise floor (composite, 2σ):
  short-feature: 8.2e6 — improvements below this are noise
  long-feature:  ...
```

## Recorded baselines

Run date: 2026-05-23

| Fixture | Status | Stable Runs | Mean Composite | σ | 2σ Noise Floor |
| --- | --- | --- | --- | --- | --- |
| A | unstable | 0/1 | — | — | — |

## Recorded baselines

Run date: 2026-05-23

| Fixture | Status | Stable Runs | Mean Composite | σ | 2σ Noise Floor |
| --- | --- | --- | --- | --- | --- |
| A | unstable | 0/1 | — | — | — |
