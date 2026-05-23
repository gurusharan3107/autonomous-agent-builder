# Universal lifecycle — freshness sweep, preflight, bootstrap, teardown, docker

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Universal closeout freshness sweep (every lane, every time)

Hard Rule 2 enforcement is a **bundled script**, not a prose checklist. Every lane's closeout calls `freshness_sweep.py` as its final step and **refuses to consider the lane closed on non-zero exit**:

```bash
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
# Exit 0: clean (or warn-only soft findings) → lane closes.
# Exit 1: hard drift in docs/autoresearch/ — switch to Fix lane.
```

What the sweep checks (each isolated; one drift doesn't short-circuit the rest):

| Check | Severity | What it asserts |
|---|---|---|
| `metrics_documents_session_scoped` | hard | METRICS.md still documents the `runtime_aggregates.session_scoped` flag. |
| `logs_emits_session_scoped` | hard | `src/.../cli/commands/logs.py` still emits `session_scoped` in the analyze payload. |
| `task_chat_session_id_column` | hard | `src/.../db/models.py` still defines `chat_session_id` on `Task`. |
| `readme_telemetry_honesty_line` | hard | README.md activation block still mentions the 2026-05-23 telemetry-honesty line. |
| `metrics_prompt_count_semantic` | hard | METRICS.md still clarifies `prompt_count` = operator chat turns. |
| `harness_asserts_session_scoped` | hard | HARNESS.md still references the `session_scoped` assertion. |
| `tsv_header_drift_*` | hard | `baseline_runs.tsv` / `optimize_results.tsv` / `per_prompt_results.tsv` headers match `run.py:SESSION_HEADERS` / `PROMPT_HEADERS` exactly. |
| `iterations_html_markers` | hard | `iterations.html` retains `__ITERATIONS_DATA_START__` / `__ITERATIONS_DATA_END__` markers (regenerator depends on them). |
| `baseline_summary_age` | soft | `baseline_runs_summary.json` is no older than 14 days. |
| `changelog_lane_activity` | soft | Latest autoresearch CHANGELOG entry is no older than 30 days (warns if skill is being bypassed). |

`--json` emits machine-readable output. Soft findings warn but do not block lane closure; hard findings block. If sweep reports hard drift the current lane did not cause, the skill stops, surfaces the findings to the operator, and offers to switch to Fix lane.

The sweep is the discipline counterpart to `preflight.py`: prose is vibes, scripts enforce. Both must pass for the loop to be trusted.

## Universal preflight — always run first

Bundled `scripts/preflight.py` validates the shared infrastructure. Always run it before any lane, act on a non-zero exit:

```bash
# General health (every session start, before lane choice)
python3 .claude/skills/autoresearch/scripts/preflight.py

# Then run the lane-specific preflight via --recipe N inside the lane.
```

| Layer | Checks |
| --- | --- |
| **Hard** (must pass — exit 1 on fail) | `builder` / `npm` / `python3` / `git` on PATH; `requests` importable; `~/Builder-Workspace/devpulse` exists; 5 contract docs in `docs/autoresearch/`; 6 harness files in `scripts/autoresearch/` |
| **Recipe-specific** (gated by `--recipe N`) | Baseline (`--recipe 1`): warns if baseline already exists. Iterate (`--recipe 2`/`3`): `.seed/devpulse` exists + `baseline_runs_summary.json` exists + every fixture `status=stable`. |
| **Soft** (warn-only — degraded mode) | `tiktoken` importable; ports 9876–9880 free; `/tmp` has ≥5 GB free; docker present + Jaeger running; git on clean branch |

`--json` emits machine-readable output. Exit 0 = pass or warn-only; 1 = hard or recipe-specific failure. **If exit non-zero, run bootstrap (below) or surface the `fix:` field of each failed check to the operator. Do not proceed.**

## Bootstrap — one-shot auto-fix

When preflight fails, `scripts/bootstrap.sh` auto-fixes the machine-fixable items. Idempotent:

```bash
bash .claude/skills/autoresearch/scripts/bootstrap.sh
bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-seed     # don't snapshot
bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-jaeger   # don't start Jaeger
bash .claude/skills/autoresearch/scripts/bootstrap.sh --dry-run       # report only
```

Auto-fixes: pip-install `requests`/`tiktoken`; runs `setup_seed.sh` if `.seed/devpulse` missing; `docker compose up -d` for Jaeger.

Cannot fix (operator action required): docker daemon down, ports 9876–9880 busy, dirty git, low disk. Bootstrap prints the remedy per item.

## Teardown — clean session shutdown

`scripts/teardown.sh` releases ephemeral state cleanly:

```bash
bash .claude/skills/autoresearch/scripts/teardown.sh                   # default — stop Jaeger, clean stuck workspaces
bash .claude/skills/autoresearch/scripts/teardown.sh --with-evidence   # also wipe /tmp/autoresearch/
bash .claude/skills/autoresearch/scripts/teardown.sh --keep-jaeger     # keep Jaeger for trace inspection
```

Surgical: stops Jaeger, removes UUID-pattern `/tmp/devpulse-<uuid>/` workspaces (refuses non-UUID paths), optional evidence wipe. Never touches `.seed/devpulse`.

## Docker container lifecycle (Jaeger)

Optional; only needed for live trace inspection. `scripts/autoresearch/docker-compose.yml` runs Jaeger all-in-one with `network_mode: host` (avoids WSL2 port-forwarding flake). UI: <http://127.0.0.1:16686>. Path A raw-body capture works without Jaeger; treat the UI as a debugging tool.

---
