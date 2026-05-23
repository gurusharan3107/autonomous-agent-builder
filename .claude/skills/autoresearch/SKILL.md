---
name: autoresearch
description: "Single entry point for the M3.5 Track B autoresearch optimization loop. Three lanes — Baseline (establish σ-floor), Iterate (pick idea → run → verdict), Fix (source-patch a gap the loop surfaced and can't patch itself). On invocation, ALWAYS asks the operator which lane via AskUserQuestion; only skips the question when the typed prompt unambiguously names one (e.g. 'run baseline', 'iterate on idea 4', 'fix the telemetry gap'). Use whenever the operator asks to 'run autoresearch', 'start the loop', 'kick off baseline', 'run baseline', 'try the next optimize idea', 'iterate on optimization #N', 'compare a candidate', 'add a new optimize idea', 'fix the gap raised by autoresearch', 'address the autoresearch blocker', 'patch the telemetry/contract/schema gap', or any variant pairing autoresearch / loop / optimize / baseline / fixture / gap / blocker language with execution. ALSO use proactively after `goal-audit` reorders `docs/autoresearch/OPTIMIZE_IDEAS.md` (new top → Iterate), after `roadmap-audit` flips an SDK lever `[ ]` → `[x]` (re-baseline → Baseline), whenever STATUS.md says ACTIVATING/ACTIVE but the last `baseline_runs_summary.json` is older than 14 days (Baseline), and when STATUS Recent Decisions or autoresearch closeout artifacts surface a defect the loop can't patch itself (Fix)."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash, Write, AskUserQuestion
compatibility:
  - python3 >= 3.12 (run.py / baseline.py / compare.py / loop.py / extract_context_breakdown.py)
  - requests (pip install requests)
  - tiktoken (pip install tiktoken; optional — falls back to 4-char-per-token approximation)
  - builder CLI on PATH (subprocess invocations; required)
  - npm on PATH (feature-correctness gate inside fixture workspaces; required)
  - docker (optional; only if Jaeger UI is desired — Path A raw-body capture works without it)
---

# autoresearch — single entry, three lanes

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

This skill is the only entry point for the autoresearch loop. Three mutually exclusive lanes — **Baseline**, **Iterate**, **Fix** — each with its own preflight + do + closeout. Codifies [`docs/autoresearch/`](../../../docs/autoresearch/) into an agent-runnable shape. **Lane-specific procedure lives in `references/lanes/*.md` and loads only when that lane is chosen.**

## Entry point — always ask which lane

When this skill activates, the FIRST action is `AskUserQuestion`:

```
question: "Which autoresearch lane?"
header:   "Lane"
options:
  - "Baseline"  — Establish or re-establish the σ noise floor across fixtures A–E. Expensive (~2h, ~$5–10). Required before any iteration; required again after an SDK lever flip or a prompt-shape change.
  - "Iterate"   — Pick top unattempted idea from OPTIMIZE_IDEAS.md, run, verdict. The forward motion of the loop. Cheap per iteration; compounds over time.
  - "Fix"       — Source-patch a defect the loop surfaced but cannot patch itself (telemetry-not-session-scoped, schema mismatch, contract drift, harness bug). Drives FIX-STANDARD + the full propagation chain.
```

**Skip the question only when the typed prompt unambiguously names one lane.** Examples:

| Typed prompt | Lane | Skip the question? |
|---|---|---|
| "run baseline" / "kick off baseline" / "establish σ floor" / "re-baseline" | Baseline | Yes |
| "iterate on idea 4" / "try the next optimize idea" / "next iteration" / "pick from OPTIMIZE_IDEAS" / "compare this candidate" | Iterate | Yes |
| "fix the telemetry gap" / "address the autoresearch blocker" / "patch the schema gap" / "the loop surfaced X — fix it" | Fix | Yes |
| "run autoresearch" / "start the loop" / "what should we do next?" | *(ambiguous)* | **No — ask.** |

After the lane is chosen, run the universal preflight (load [`references/lifecycle.md`](references/lifecycle.md)), then the chosen lane's procedure. Lanes do not mix mid-session.

## ⚠ Hard rules — universal across lanes

1. **ROADMAP first for substantive changes; benign edits exempt.** Any *substantive* change driven by this skill — Builder source edits, harness script behavior changes, schema/contract changes, anything that flips a documented contract or alters runtime behavior — must have a [`docs/goal/ROADMAP.md`](../../../docs/goal/ROADMAP.md) line *before* the edit lands. Place it in the right milestone (typically M2.3 for cost-aware-execution defects, M3.5 for loop-internal defects). Fix lane preflight enforces this; the same rule binds Baseline and Iterate when they discover a defect mid-flow (switch to Fix lane). **Exempt — no ROADMAP line required:** typo fixes, comment/prose tweaks that don't change a documented contract, removing demo/sample data, cosmetic HTML/CSS, dead-code deletion, and similarly low-risk edits where the diff would be self-explanatory in a review. When in doubt, lean toward adding the ROADMAP line — it costs less than the wrong call.
2. **This skill owns `docs/autoresearch/` freshness.** The skill is the sole agent responsible for keeping every file under `docs/autoresearch/` consistent with current code, current loop contract, and current measurements. No stale state allowed — ever. Every lane's closeout MUST end with a freshness sweep (`scripts/freshness_sweep.py`). If the sweep finds drift the lane didn't cause, the skill stops, surfaces the drift to the operator, and asks whether to switch to Fix lane. See [`references/lifecycle.md`](references/lifecycle.md) § Universal closeout freshness sweep.
3. **The harness must not import from `autonomous_agent_builder/`.** It is a runner *against* Builder, not coupled to it. All 5 scripts in `scripts/autoresearch/` use `builder` CLI as subprocess + HTTP endpoints. Preserve this when editing.
4. **`.seed/devpulse/` is read-only after capture.** `chmod -R a-w` enforces this. If the seed needs to change (devpulse template evolves), capture a NEW seed and document the drift in `baseline_variance.md`. Never edit in-place.
5. **The first content block of the system prompt is cache-stable.** When making a source edit for an optimization idea, never insert dynamic content into `agents/execution_policy.py::build_system_prompt()` before the existing stable prefix. Doing so destroys the cache and the candidate will always lose on composite even when the idea was correct.
6. **`gate_pass_rate=1.0` is per-baseline-run, not historical aggregate.** Validated *inside* `baseline.py` per fixture run. Do not block on the historical `builder metrics show` aggregate which folds in M1.x dev-time failures.
7. **Stop conditions are sacred.** `loop.py` honours `--max-iterations`, `--cost-budget-usd`, and SIGINT. Do not silently extend any of these mid-session — abort and ask the operator.
8. **Wins must promote A→E before merge.** A keep on fixture A alone is not a real win. `loop.py` already enforces this; do not paper over it by hand-editing `optimize_results.tsv decision` columns.
9. **Preflight is mandatory.** Each lane has its own; the universal preflight runs first. The recipe-specific gate (`--recipe N`) catches missing seed / baseline σ / busy ports before they bite mid-run and burn API credits. See [`references/lifecycle.md`](references/lifecycle.md).
10. **`runtime_aggregates.session_scoped` must be `true`.** Every analyze.json the harness consumes (Baseline + Iterate) must carry this flag. `false` means the DB predates ROADMAP M2.3's `tasks.chat_session_id` migration and aggregates have fallen back to global scope — Fix lane required before anything else can proceed.

## Lane index — load only the lane the operator picked

| Lane | When | Procedure |
|---|---|---|
| **Baseline** | First-time activation, after SDK lever flip, after Fix that changed prompt assembly, when `baseline_runs_summary.json` > 14 days old | [`references/lanes/baseline.md`](references/lanes/baseline.md) |
| **Iterate** | After Baseline closeout when σ-floor is fresh and OPTIMIZE_IDEAS has unattempted entries; after `goal-audit` reorder; verdict half via `compare.py` | [`references/lanes/iterate.md`](references/lanes/iterate.md) |
| **Fix** | Loop surfaces a contract violation, named gap in handoff doc, kept iteration exposes generalizable bug, operator types "fix the gap" | [`references/lanes/fix.md`](references/lanes/fix.md) |

## Reference index — load as needed

| Reference | When to load |
|---|---|
| [`references/lifecycle.md`](references/lifecycle.md) | At session start (universal preflight) and at lane closeout (freshness sweep). Also: bootstrap auto-fix, teardown, Docker / Jaeger lifecycle. |
| [`references/gotchas.md`](references/gotchas.md) | When a wiring / setup issue bites mid-flow. |
| [`references/artifacts.md`](references/artifacts.md) | At Baseline/Iterate closeout — regenerate iterations.html + INTROSPECTION.md. |
| [`references/reference-policy.md`](references/reference-policy.md) | At lane start — what `docs/autoresearch/` files to read in what order; what files the lane MAY and MUST NEVER edit. |
| [`references/hang-detection.md`](references/hang-detection.md) | When the watchdog dumps to `/tmp/autoresearch/diagnostics/` — match against `KNOWN_PATTERNS.md` before diagnosing by hand. |
| [`references/failure-modes.md`](references/failure-modes.md) | When a known symptom appears (`session_scoped=False`, fixture status=unstable, compare returns crash, etc.). |
| [`KNOWN_PATTERNS.md`](KNOWN_PATTERNS.md) | When `scripts/diagnose_hang.py` identifies (or fails to identify) a hang class. |

## Cross-references

- Roadmap home: [`docs/goal/ROADMAP.md` § M3.5](../../../docs/goal/ROADMAP.md) (autoresearch activation) and § M2.3 (cost-aware execution surface — Fix lane's most frequent home).
- Activation status: [`docs/autoresearch/README.md`](../../../docs/autoresearch/README.md).
- Fix procedure: [`docs/goal/FIX-STANDARD.md`](../../../docs/goal/FIX-STANDARD.md).
- Related skills:
  - `goal-audit` — reorders `OPTIMIZE_IDEAS.md` based on session intent + autoresearch focus signals; check its INSIGHTS output before Iterate.
  - `roadmap-audit` — flags SDK levers that should trigger re-baseline when flipped `[ ]` → `[x]`.
  - `knowledge-base` — refreshes the Claude Agent SDK rubric those audits consume.

## Why this skill exists

The autoresearch loop is the only Builder workflow whose value compounds with iteration count — every kept change improves the substrate all future iterations run on. But it's also the workflow most prone to operator drift: forgetting the 2σ gate, hand-editing TSV rows, picking ideas out of order, skipping A→E promotion, and — most expensively — running iterations on a contract-broken substrate (the 2026-05-23 telemetry-gap case). This skill is the discipline layer. One entry point, three lanes, each with explicit preflight and closeout. The Fix lane exists because the loop is a measurement instrument that occasionally needs its measurement contract repaired before any further measurement is meaningful.
