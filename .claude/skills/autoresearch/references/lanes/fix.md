# Lane 3 — Fix (source-patch a defect the loop surfaced)

> Loaded on demand when the operator picks this lane via [autoresearch SKILL.md](../../SKILL.md). Lane-specific Preflight / Do / Closeout. Universal hard rules and freshness sweep apply across lanes — see SKILL.md.

## Lane 3 — Fix

**Purpose:** source-patch a defect the loop surfaced but cannot patch itself. The loop is a measurement instrument; when measurement reveals a contract bug in Builder source, harness scripts, or autoresearch docs, this lane drives the fix + the full propagation chain.

### When to choose this lane

- The loop's preflight, baseline.py, or compare.py reports a contract violation (`session_scoped is False`, schema drift between TSV header and writer, anchor drift in extractor, malformed analyze.json shape).
- STATUS Recent Decisions or `docs/autoresearch/NEXT-SESSION.md`-style handoffs name a specific source defect blocking the loop.
- A kept iteration exposes a generalizable bug in Builder source that other agents will hit.
- The operator types "fix the gap", "address the blocker", or names a specific defect.

### Preflight

```bash
python3 .claude/skills/autoresearch/scripts/preflight.py --json
```

Lane-specific hard requirements (refuse to start until all three are satisfied):

- A **named gap source** — file:line, contract name, or handoff doc that names the defect. Fix lane refuses to start on vague intent. If the operator's prompt doesn't name one, ask via AskUserQuestion before proceeding.
- A **clean git state** — Fix lane creates real commits on `master` (or the active feature branch); a dirty tree means uncommitted prior work that must be resolved first.
- A **ROADMAP entry written before any code edit.** Per Hard Rule 1, the ROADMAP line lands *first*. If the existing ROADMAP has no home for this fix, add the line (typically under M2.3 for cost-aware-execution / telemetry / contract defects, M3.5 for autoresearch-loop-internal defects) and commit nothing else until the line exists. The line stays `[ ]` until the Closeout tick — but writing it is a precondition, not a closeout step.

### Do

Follow [`docs/goal/FIX-STANDARD.md`](../../../../../docs/goal/FIX-STANDARD.md): memory → explore → triggers → SDK grounding → correct layer → verify → record → memory write. Specific to autoresearch defects:

1. **Diagnose** — read the evidence, not the hypothesis. The handoff or symptom may misattribute the cause (e.g., 2026-05-23 telemetry-gap was hypothesized as chat-event persistence; actual root cause was aggregate scope in `_runtime_aggregates`).
2. **Choose the layer** — Builder source (most contract defects), harness script (schema/anchor drift in `scripts/autoresearch/`), or autoresearch doc (stale contract description in `docs/autoresearch/`). Almost never all three.
3. **Implement the smallest correct fix** per FIX-STANDARD. Don't expand surface area.
4. **Tests** — new unit/integration test that fails without the fix and passes with it. Existing tests stay green.
5. **Verify** — `pytest` on the touched suite + neighboring suites; for telemetry/contract fixes also run a real `builder logs analyze --session <id> --full --json` against a recent session and inspect the changed field.

### Closeout — the propagation chain

This is the discipline payload of Fix lane. Every Fix lane closeout MUST do all of:

1. **ROADMAP tick** — find the relevant `[ ]` line, tick `[x]` with evidence pointer, date `*(YYYY-MM-DD)*`. If no line exists, add one *before* the tick (Hard Rule 2: everything maps to ROADMAP). Common homes: M1.x (defect closure), M2.3 (cost-aware execution / telemetry honesty), M3.5 (autoresearch-loop-internal).
2. **STATUS.md Recent Decisions** — one line at the top of Recent Decisions: `**YYYY-MM-DD** — <one-sentence what + why + evidence pointer>`. Update `Last Update` field too.
3. **CHANGELOG entry** — full Added/Changed/Fixed/Validation sections per Keep-a-Changelog. Date heading at top.
4. **`docs/autoresearch/` contract docs** — if the fix changes a contract the loop depends on:
   - `README.md` activation block — append a dated line naming the fix.
   - `METRICS.md` — update the affected row(s) and any source-by-source field listing.
   - `HARNESS.md` — update composite formula notes, TSV row semantics, or the harness preflight assertions.
   - `OPTIMIZE.md` / `COMPARE.md` — only if the loop contract itself shifted.
5. **Truncate poisoned data** — if the fix invalidates prior measurements (e.g., session-scope change means pre-fix baseline σ is no longer comparable), truncate the affected TSVs to header-only so the next Baseline run starts on honest signal. Files:
   - `docs/autoresearch/baseline_runs.tsv`
   - `docs/autoresearch/optimize_results.tsv`
   - `docs/autoresearch/per_prompt_results.tsv`
   - `docs/autoresearch/baseline_runs_summary.json` (delete; baseline.py will regenerate)
6. **Run the freshness sweep** — `python3 .claude/skills/autoresearch/scripts/freshness_sweep.py`. Must exit 0 before commit. If it exits 1 with drift the Fix lane itself didn't address, expand the fix scope to cover it (this is the lane that owns drift repair) — do not paper over by skipping the sweep.
7. **Single commit** — all of the above in one commit per Hard Rule 13 from `docs/goal/README.md`. Message format: `fix(<area>): <one-line summary> (unblocks <next>)`.
8. **Push** — Hard Rule 12: a `[x]` is not closed until pushed.
9. **Retire handoff docs** — if a `NEXT-SESSION.md` or similar one-shot doc triggered the Fix, delete it as the last step.
10. **Tell the operator** which lane to run next. Typically: Baseline if the fix changed prompt shape or aggregate semantics (pre-fix σ-floor invalid); Iterate if the fix was harness-only and prior measurements remain comparable.

### Worked example — 2026-05-23 telemetry-honesty fix (commit `a3354c2`)

- **Gap named:** `docs/autoresearch/NEXT-SESSION.md` reported `prompt_count=1, agent_name=None` in autoresearch-spawned `analyze.json` despite 50-min runs.
- **Diagnosis differed from hypothesis.** Handoff blamed chat-event persistence; actual root cause was `_runtime_aggregates()` reading `agent_runs` globally with no session filter.
- **Layer:** Builder source (`cli/commands/logs.py` + `db/models.py` + `db/session.py` + `services/sprint_execution.py` + `embedded/server/agent_sprint_planning.py`) + harness (`scripts/autoresearch/run.py`) + 1 test file.
- **Closeout propagation** (this template):
  - ROADMAP M2.3 line ticked `[x]` with test-name evidence.
  - STATUS Recent Decisions + Last Update updated.
  - CHANGELOG dated entry with Added/Changed/Fixed/Validation/Notes.
  - `docs/autoresearch/README.md` activation block — appended 2026-05-23 telemetry-honesty line.
  - `docs/autoresearch/METRICS.md` — `prompt_count` row clarified (= operator turns, not model calls); session-scoping flag documented; `by_agent` named as canonical per-agent source.
  - `docs/autoresearch/HARNESS.md` — composite formula notes added; `session_scoped` assertion added; per-agent TSV-row semantics documented.
  - TSVs truncated to header-only (pre-fix measurements poisoned).
  - Single commit `a3354c2`, pushed.
  - `NEXT-SESSION.md` retired.
  - Next lane: Baseline (telemetry surface changed; σ-floor must be recomputed).

---
