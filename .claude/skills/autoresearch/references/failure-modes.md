# Failure modes & escalation

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Failure modes & escalation

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `analyze.json.runtime_aggregates.session_scoped is False` | DB predates `tasks.chat_session_id` migration (M2.3). | Switch to Fix lane — restore the FK + scoping; per Hard Rule 8 nothing else can proceed. |
| `setup_seed.sh` says "source devpulse not found" | `~/Builder-Workspace/devpulse` missing or moved. | Confirm canonical workspace path; pass `--src` to the script. |
| `baseline.py` reports `status=unstable` for a fixture (<3 clean runs) | Timing-fragile fixture or quota interruption. | Re-run only that fixture: `baseline.py --fixtures D --n 5 --evidence-root .../retry` |
| `compare.py` returns `decision: crash, reason: no_baseline` | `baseline_runs_summary.json` missing. | Run Baseline lane first. |
| `loop.py` repeatedly picks the same idea | Attempt marker not applied. | The marker is `> attempted: <decision> (<reason>, <date>)` appended below the idea body. Add manually if needed. |
| Every candidate `discard` with `composite_within_2sigma` | Baseline σ too wide. | Re-run Baseline with N=10 to tighten σ, or pick higher-impact ideas. |
| `extract_context_breakdown.py` reports `unattributed_tokens > 10%` | Prompt-assembly anchor drift. | Switch to Fix lane — update `ANCHORS` table in the extractor to match the new prompt structure. |
| `autoresearch-explainer.html` "Live data" section stale after a real iteration ran | Closeout step skipped. | Run `render_iterations.py`. If still empty, check `optimize_results.tsv` rows have `branch=autoresearch/iter-N-…` in `notes`. |
| `render_iterations.py` exits "AUTOUPDATE regions missing in autoresearch-explainer.html" | Someone hand-edited the explainer and removed a fence. | Restore the 4 paired `<!-- AUTOUPDATE:name v=1 -->...<!-- /AUTOUPDATE:name -->` fences (`baseline-summary`, `baseline-scatter`, `baseline-raw-rows`, `iterations-list`) — pattern reference in `~/.claude/skills/html-artifact/references/auto-update-regions.md`. |
| TSV row with garbage cells | Schema drift between `run.py:SESSION_HEADERS` and the TSV header. | Switch to Fix lane — align headers; delete the corrupt row. |
| `loop.py` Ctrl-C'd mid-iteration | Operator interrupt; branch still exists. | `git status` → find `autoresearch/iter-*` branch → `git checkout main && git branch -D <branch>` → append `> attempted: interrupted` to the idea. |
| `baseline.py` quota-failed mid-run | Provider rate limit. | `compute_summary()` only counts `gates_passed=6/6` rows so partial runs auto-excluded. Restart with same `--evidence-root`; completed rows append cleanly. |

When unsure, stop and surface state via `AskUserQuestion`. Do not silently expand `--max-iterations` / `--cost-budget-usd` or skip a hard gate.
