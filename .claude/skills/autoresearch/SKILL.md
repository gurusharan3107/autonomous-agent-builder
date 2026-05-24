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

## Before anything — check for in-flight lanes

`baseline.py` / `loop.py` run for hours and may have been started outside this session. **First action when this skill activates:**

```bash
python3 .claude/skills/autoresearch/scripts/lane_status.py --human
```

If anything is reported, surface it FIRST — TSV state is changing under you. Recipe-1/2/3 preflights also hard-fail on in-flight lanes (safety net for accidental concurrent starts).

**Launch pattern.** When launching a lane from Bash, use `run_in_background: true` (not `nohup ... &`) + `Monitor` for progress streaming. Harness auto-notifies on completion; each `[baseline] fixture=X iter=Y/5` line streams as a notification.

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

1. **PROGRESS.md is the autoresearch log; ROADMAP/CHANGELOG/STATUS stay out of per-patch detail.** Every Baseline / Iterate / Fix closeout appends a one-line entry to [`docs/autoresearch/PROGRESS.md`](../../../docs/autoresearch/PROGRESS.md) per its schema (date header, **lead with the change**, file:line or sha, numbers, status flag only if non-shipped). ROADMAP `M3.5` keeps milestone-scope items only; CHANGELOG carries Builder-runtime changes that happen to be autoresearch-surfaced. STATUS § Recent Decisions only for cross-cutting decisions (goal/north-star changes, not loop iterations). **Exempt — no PROGRESS.md entry required:** typo fixes, comment-only tweaks, cosmetic HTML/CSS, dead-code deletion. When in doubt: write the line.
2. **This skill owns `docs/autoresearch/` freshness.** The skill is the sole agent responsible for keeping every file under `docs/autoresearch/` consistent with current code, current loop contract, and current measurements. No stale state allowed — ever. Every lane's closeout MUST end with a freshness sweep (`scripts/freshness_sweep.py`). If the sweep finds drift the lane didn't cause, the skill stops, surfaces the drift to the operator, and asks whether to switch to Fix lane. See [`references/lifecycle.md`](references/lifecycle.md) § Universal closeout freshness sweep.
3. **The harness must not import from `autonomous_agent_builder/`.** It is a runner *against* Builder, not coupled to it. All 5 scripts in `scripts/autoresearch/` use `builder` CLI as subprocess + HTTP endpoints. Preserve this when editing.
4. **`.seed/devpulse/` is read-only after capture.** `chmod -R a-w` enforces this. If the seed needs to change (devpulse template evolves), capture a NEW seed and document the drift in `baseline_variance.md`. Never edit in-place.
5. **The first content block of the system prompt is cache-stable.** When making a source edit for an optimization idea, never insert dynamic content into `agents/execution_policy.py::build_system_prompt()` before the existing stable prefix. Doing so destroys the cache and the candidate will always lose on composite even when the idea was correct.
6. **`gate_pass_rate=1.0` is per-baseline-run, not historical aggregate.** Validated *inside* `baseline.py` per fixture run. Do not block on the historical `builder metrics show` aggregate which folds in M1.x dev-time failures.
7. **Stop conditions are sacred.** `loop.py` honours `--max-iterations`, `--cost-budget-usd`, and SIGINT. Do not silently extend any of these mid-session — abort and ask the operator.
8. **Wins must promote A→E before merge.** A keep on fixture A alone is not a real win. `loop.py` already enforces this; do not paper over it by hand-editing `optimize_results.tsv decision` columns.
9. **Preflight is mandatory.** Each lane has its own; the universal preflight runs first. The recipe-specific gate (`--recipe N`) catches missing seed / baseline σ / busy ports before they bite mid-run and burn API credits. See [`references/lifecycle.md`](references/lifecycle.md).
10. **`runtime_aggregates.session_scoped` must be `true`.** Every analyze.json the harness consumes (Baseline + Iterate) must carry this flag. `false` means the DB predates ROADMAP M2.3's `tasks.chat_session_id` migration and aggregates have fallen back to global scope — Fix lane required before anything else can proceed.
11. **Per-iter sanity gate + autonomous self-heal.** Every iter must ship 6/6 gates with `feature_correct=True`. On failure, `baseline.py` invokes the skill's `scripts/self_heal.py`, which parses `evidence_dir/feature_check.log` + seed state for catalogued patterns (missing seed deps → `pip install`; missing pytest plugin → install; seed DB pollution → SQL DELETE; untracked forbidden file → `rm`) and **auto-applies the mechanical fix, then retries the iter from scratch on a fresh evidence subdir** (`run-<N>.heal1/`). At most 1 auto-fix + 1 retry per iter. **Extending the catalog is part of the skill, not the operator's job** — when a new failure pattern surfaces, add it to `scripts/self_heal.py:LOG_PATTERNS` (or, for substrate-identity violations not yet declared, edit `seed_manifest.json § pristine_invariants`). `--allow-imperfect-iter` is for genuinely acceptable flake only; default is strict + self-heal.
12. **`scripts/preflight.py --recipe 1` is the upstream guard.** It runs `seed_verify.py` against `seed_manifest.json` (substrate identity contract) and `test_harness_contracts.py` against Builder CLI surfaces (output-shape drift) before any iter spends a token. Catches the entire P1–P18 failure class for $0 instead of $5/1.5h. Always run before launching any lane.
13. **Substrate identity is declarative — single source of truth at `seed_manifest.json`.** Both `seed_verify.py` (verifier) and `self_heal.py` (remediator) read this file. Edit the manifest when re-capturing seed (new allowed deps) or when a new past-agent artifact pattern surfaces (add to `forbidden_path_patterns` / `forbidden_commit_subject_patterns` / `must_be_empty_tables`). **Never patch `seed_verify.py` or `self_heal.py` to add a one-off check** — encode it as a manifest invariant; that way the verifier and remediator stay in sync.
14. **Deterministic auto-apply vs model-backed escalation — the boundary is "does the fix introduce new substrate divergence?"** Auto-applied (catalogued, $0 retry): missing deps, pytest plugins, untracked file rm, DB row wipe. Escalated (`applied=False` + `proposed_questions`): tracked forbidden files (rm would commit→pollute history), git history pollution (re-snapshot decision), unknown error signatures (no validated remediation). When self_heal returns `proposed_questions`, `baseline.py` emits a `SELF_HEAL_ESCALATION <json>` line — the calling agent must parse it and surface via `AskUserQuestion`, NOT abort to operator manually. False fixes are worse than no fix.
15. **Composite metric must be a single uncorrelated dimension.** Never multiply time × count × rate — correlated products amplify variance and produce negative or useless σ-floors. `noncached_plus_output_tokens` is the validated single-dimension metric (P16 root cause: product of 3 dimensions produced CV=77.5%, 2σ-floor=-3.19×10⁹). When choosing a new composite formula, ask "what am I minimizing?" and pick the one metric that captures it directly.
16. **`analyze.json` attribution is unreliable for harness-spawned sessions.** Builder sessions spawned by the autoresearch harness show `prompt_count=1` and `agent_name=unknown` — `chat_session_id` is not threaded from the harness into the Builder DB. Do not use these fields for per-session cost attribution until this gap is fixed. `runtime_aggregates.session_scoped: true` (Hard Rule 10) is the correct proxy; per-agent breakdowns are unusable until the Builder product gap is resolved.

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

## Skill-owned scripts

| Script | Purpose |
|---|---|
| `scripts/self_heal.py` | Autonomous diagnose-and-fix invoked by `baseline.py` on a failed per-iter gate. Pattern catalog at top of file — **extend it** when a new failure surfaces; that's how autonomy grows. |
| `scripts/preflight.py` | Upstream guard: hard-fails the lane before any iter spends a token when seed pytest-collect / seed git-clean / TSV / port / disk checks miss. |
| `scripts/lane_status.py` | Read-only inflight detector (`baseline.py`/`loop.py` via `ps -ef`). |
| `scripts/hang_watchdog.py` | Forensic dump trigger on idle (idle-seconds + grace-seconds). |
| `scripts/diagnose_hang.py` | Pattern matcher over hang-watchdog dumps (KNOWN_PATTERNS). |
| `scripts/render_iterations.py` | Closeout: regenerate `iterations.html` data block. |
| `scripts/introspect.py` | Closeout: regenerate `INTROSPECTION.md`. |
| `scripts/freshness_sweep.py` | Closeout gate (Hard Rule 2). |

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
