# Harness — Runner Contract

> **The implementation is the contract.** `scripts/autoresearch/{run,baseline,compare,loop}.py` ARE the runner — read them, not this file. This doc was the pre-implementation pseudo-code spec; the code now supersedes it (2026-05-29 lean cut removed the stale ~600-line spec body).

## What the harness does

Per-fixture, per-iteration: copy the immutable seed → fresh workspace, spawn `builder start`, drive the fixture via `POST /api/agent/chat` (+ `/respond`), wait for the board to ship or time out, run the workspace's build/test correctness gate, capture `analyze.json`/`metrics.json`/`board.json`, append one row to `optimize_results.tsv` (or `baseline_runs.tsv`), tear down.

- **Metric:** `composite = noncached_plus_output_tokens`, read directly from `builder analyze`.
- **Verdict:** `compare.py` — beat the 2σ noise floor + 6 hard gates (`run.py:evaluate_hard_gates`).
- **Stuck runs:** `hang_watchdog.py` (WAL-idle) → abort + escalate; the operator inspects the dump and fixes the hang at source.

## Telemetry contract (Hard Rule 10)

Before trusting σ-floor inputs, the harness asserts `runtime_aggregates.session_scoped` is `True` in every `analyze.json` it consumes — otherwise aggregates have fallen back to global scope (DB predates the `tasks.chat_session_id` migration) and the run is invalid. This is the one invariant this doc still owns.
