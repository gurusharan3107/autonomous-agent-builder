# Reading order + file-edit policy

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Reading order for a fresh session

After lane choice, build context in this order:

1. **`docs/autoresearch/README.md`** — activation status; what's open/closed today.
2. **`docs/autoresearch/OPTIMIZE.md`** — loop contract (composite formula, 6 hard gates, allowlist policy, stop conditions). Iterate + Baseline lanes both depend on this.
3. **`docs/autoresearch/OPTIMIZE_IDEAS.md`** — Iterate lane only; find the top unattempted idea.
4. **`docs/autoresearch/HARNESS.md`** — only if debugging or extending a harness script (Fix lane on harness defects).
5. **`docs/autoresearch/COMPARE.md`** — Iterate lane only; interpret `decision: discard` verdicts.
6. **`docs/autoresearch/METRICS.md`** — Fix lane on telemetry defects.

Do not read `CONTEXT-LEDGER.md` / `SDK-OBSERVABILITY.md` / `GAPS.md` unless extending the harness itself.

## Files this skill MAY edit (by lane)

- **Baseline lane:**
  - `docs/autoresearch/baseline_runs.tsv` / `baseline_runs_summary.json` (append-only via baseline.py; never hand-edit rows).
  - `docs/autoresearch/baseline_variance.md` — append observed σ context.
  - `docs/autoresearch/iterations.json` / `iterations.html` (data block only) — via render_iterations.py.
  - `docs/autoresearch/INTROSPECTION.md` — via introspect.py.
  - `docs/goal/STATUS.md` Recent Decisions — append baseline result line.

- **Iterate lane:**
  - `docs/autoresearch/OPTIMIZE_IDEAS.md` — add new ideas + attempt markers.
  - `docs/autoresearch/optimize_results.tsv` / `per_prompt_results.tsv` (append-only via run.py / loop.py).
  - `docs/autoresearch/iterations.json` / `iterations.html` (data block only).
  - `docs/autoresearch/INTROSPECTION.md`.
  - On kept-and-shipped iterations only: `docs/goal/ROADMAP.md` (tick `[x]`), `docs/goal/STATUS.md` (Recent Decisions), `CHANGELOG.md`.

- **Fix lane:**
  - `docs/goal/ROADMAP.md` (add line + tick), `docs/goal/STATUS.md` (Recent Decisions + Last Update), `CHANGELOG.md`.
  - `docs/autoresearch/README.md` / `METRICS.md` / `HARNESS.md` — when the fix changes a documented contract.
  - The TSV files — truncate to header-only when prior measurements are invalidated by the fix.
  - `src/autonomous_agent_builder/**` or `scripts/autoresearch/*.{py,sh,yml}` per FIX-STANDARD.
  - Tests under `tests/`.

## Files this skill MUST NEVER edit

- `docs/autoresearch/{OPTIMIZE,COMPARE,SDK-OBSERVABILITY,CONTEXT-LEDGER,GAPS,fixtures}.md` — stable contracts; if one must evolve, that's a separate Fix lane closeout including a versioning discussion.
- `src/autonomous_agent_builder/` from inside Iterate lane — those edits happen as part of the operator's idea attempt, on the iteration branch, not as a skill-driven edit on master.
- `optimize_results.tsv decision` column — never hand-edit; the verdict is mechanical.
- `.seed/devpulse/` — immutable after capture.
