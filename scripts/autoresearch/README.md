# scripts/autoresearch — v1 harness for the autoresearch loop

Driver scripts that execute fixture-based code-gen sessions against a fresh
devpulse workspace, collect telemetry, compare runs, and steer the
Karpathy-style autoresearch loop. The spec they implement lives under
[`docs/autoresearch/`](../../docs/autoresearch/).

These scripts do **not** import from `autonomous_agent_builder`. They invoke
the `builder` CLI as subprocesses and POST to the embedded server's
`/api/agent/chat` / `/api/agent/chat/respond` / `/api/agent/chat/history`
HTTP endpoints — keeping the harness decoupled from Builder internals.

## v1 component list

| Script | Role | Status |
| --- | --- | --- |
| `run.py` | Atomic fixture runner. One fixture → one row in TSV. | Phase C1 |
| `baseline.py` | N=5 driver across fixtures A–E; computes σ floor. | Phase C2 |
| `compare.py` | Two-run verdict (keep / discard / crash) with 2σ test + 6 hard gates. | Phase C3 |
| `loop.py` | Karpathy loop; pauses at human-edit step in v1. | Phase C4 |

The composite metric (`noncached_plus_output_tokens`) is read straight from
`builder analyze` — no OTEL/Jaeger/raw-body capture required.

## Workflow

```text
.seed/devpulse  ─────┐
                     ├──► run.py ──► optimize_results.tsv (+ baseline_runs.tsv)
fixtures (in run.py) │           ├──► per_prompt_results.tsv
                     │           └──► evidence/<run-id>/{analyze,metrics,board,errors}.json
                     │
baseline.py iterates run.py × 5 × {A,B,C,D,E} → baseline_runs_summary.json (σ floor)
                     │
compare.py reads two rows + σ → keep/discard JSON verdict
                     │
loop.py reads OPTIMIZE_IDEAS.md → human edits per allowlist → run.py + compare.py per iteration
```

## See also

- [docs/autoresearch/OPTIMIZE.md](../../docs/autoresearch/OPTIMIZE.md) — loop contract
- [docs/autoresearch/HARNESS.md](../../docs/autoresearch/HARNESS.md) — runner spec
