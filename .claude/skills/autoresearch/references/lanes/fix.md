# Lane 3 — Fix (source-patch a defect the loop surfaced)

> Loaded on demand when the operator picks this lane via [autoresearch SKILL.md](../../SKILL.md). Lane-specific Preflight / Do / Closeout. Universal hard rules and freshness sweep apply across lanes — see SKILL.md.

## Lane 3 — Fix

**Purpose:** source-patch a defect the loop surfaced but cannot patch itself. The loop is a measurement instrument; when measurement reveals a contract bug in Builder source, harness scripts, or autoresearch docs, this lane drives the fix + the full propagation chain.

### When to choose this lane

- The loop's preflight, baseline.py, or compare.py reports a contract violation (`session_scoped is False`, schema drift between TSV header and writer, anchor drift in extractor, malformed analyze.json shape).
- STATUS Recent Decisions or a one-shot handoff doc (e.g., a `NEXT-SESSION.md` placed at the repo root or `docs/autoresearch/`) names a specific source defect blocking the loop.
- A kept iteration exposes a generalizable bug in Builder source that other agents will hit.
- The operator types "fix the gap", "address the blocker", or names a specific defect.

### Preflight

```bash
python3 .claude/skills/autoresearch/scripts/preflight.py --json
```

Lane-specific hard requirements (refuse to start until all three are satisfied):

- A **named gap source** — file:line, contract name, or handoff doc that names the defect. Fix lane refuses to start on vague intent. If the operator's prompt doesn't name one, ask via AskUserQuestion before proceeding.
- A **clean git state** — Fix lane creates real commits on `master` (or the active feature branch); a dirty tree means uncommitted prior work that must be resolved first.
- A **PROGRESS.md stub entry written before any code edit.** Per SKILL.md Hard Rule 1, autoresearch lane closeouts write to `docs/autoresearch/PROGRESS.md`, not ROADMAP. Pre-edit stub: append a `**WIP <pattern-name>** — investigating <symptom>. *(OPEN)*` line under today's date header in PROGRESS.md, then make the code change; on closeout, replace the WIP line with the final shipped entry. Exception: a fix that touches Builder source AND has cross-cutting Builder-runtime implications also needs a ROADMAP line (typically M2.3) — see § Closeout "Out of scope" note.

### Do

Follow [`docs/goal/FIX-STANDARD.md`](../../../../../docs/goal/FIX-STANDARD.md): memory → explore → triggers → SDK grounding → correct layer → verify → record → memory write. Specific to autoresearch defects:

1. **Diagnose** — read the evidence, not the hypothesis. The handoff or symptom may misattribute the cause (e.g., 2026-05-23 telemetry-gap was hypothesized as chat-event persistence; actual root cause was aggregate scope in `_runtime_aggregates`).
2. **Choose the layer** — Builder source (most contract defects), harness script (schema/anchor drift in `scripts/autoresearch/`), or autoresearch doc (stale contract description in `docs/autoresearch/`). Almost never all three.
3. **Implement the smallest correct fix** per FIX-STANDARD. Don't expand surface area.
4. **Tests** — new unit/integration test that fails without the fix and passes with it. Existing tests stay green.
5. **Verify** — `pytest` on the touched suite + neighboring suites; for telemetry/contract fixes also run a real `builder logs analyze --session <id> --full --json` against a recent session and inspect the changed field.

### Closeout — the propagation chain

Every Fix lane closeout MUST do all of:

1. **PROGRESS.md entry** — one bullet under today's `## YYYY-MM-DD` header in [`docs/autoresearch/PROGRESS.md`](../../../../../docs/autoresearch/PROGRESS.md). Schema: `**Title** — file:line / sha. Numbers. Status if non-shipped.` See PROGRESS.md § Schema.
2. **Contract docs** — if the fix changes a contract the loop depends on, update the relevant file:
   - `docs/autoresearch/README.md` — activation block.
   - `docs/autoresearch/METRICS.md` — affected row(s).
   - `docs/autoresearch/HARNESS.md` — composite/TSV/preflight notes.
   - `docs/autoresearch/OPTIMIZE.md` / `COMPARE.md` — only if loop contract shifted.
3. **Truncate poisoned data** — if the fix invalidates prior measurements (session-scope change, composite formula change, seed dep change), truncate the affected TSVs to header-only OR truncate only the affected rows. Delete `baseline_runs_summary.json` for full reset. Files: `baseline_runs.tsv`, `optimize_results.tsv`, `per_prompt_results.tsv`, `baseline_runs_summary.json`.
4. **Freshness sweep** — `python3 .claude/skills/autoresearch/scripts/freshness_sweep.py` must exit 0. Drift outside the Fix scope expands the Fix.
5. **Single commit** — all of the above in one commit. Subject: `fix(<area>): <one-line summary>` (concise, no template body unless landmark).
6. **Push** — closeout isn't done until pushed.
7. **Retire handoff docs** — delete any one-shot trigger doc (e.g., a `NEXT-SESSION.md`) that drove this Fix lane.
8. **Tell the operator** which lane to run next. Baseline if the fix shifted prompt shape or aggregate semantics (pre-fix σ-floor invalid); Iterate if harness-only.

**Out of scope for Fix-lane closeout:** ROADMAP `[x]` ticks, STATUS Recent Decisions, CHANGELOG sections — those land in PROGRESS.md per Hard Rule 1. Exception: a fix that touches Builder source AND has non-autoresearch implications (e.g., the M2.3 telemetry-honesty fix that affected non-autoresearch consumers) gets a STATUS Recent Decisions line and a CHANGELOG entry in addition to PROGRESS.md. When in doubt: PROGRESS.md only.

### Worked example — 2026-05-23 P15 composite formula fix (commit `dcd3fd3`)

- **Gap:** every baseline composite landed as 0 after P12; `iterations.html` empty.
- **Diagnosis:** P12 missed parallel site at `run.py:870` (read `metrics["optimization"]` not `optimization_summary`).
- **Layer:** harness (`run.py`) + 6 doc sites (`OPTIMIZE.md`, `METRICS.md`, `README.md`, `iterations.html`, `baseline.py`).
- **Closeout:**
  - PROGRESS.md entry (one line).
  - `OPTIMIZE.md`/`METRICS.md`/`README.md` composite line updated.
  - Backfilled 5 composites from each `metrics.json` (no re-run; no truncation needed).
  - Freshness sweep exit 0; commit + push.
  - Next lane: Iterate (P15 was harness-only; σ-floor now defined).
  - TSVs truncated to header-only (pre-fix measurements poisoned).
  - Single commit `a3354c2`, pushed.
  - One-shot handoff doc retired (where applicable).
  - Next lane: Baseline (telemetry surface changed; σ-floor must be recomputed).

---
