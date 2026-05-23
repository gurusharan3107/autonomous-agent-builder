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

This skill is the only entry point for the autoresearch loop. Three mutually exclusive lanes — **Baseline**, **Iterate**, **Fix** — each with its own preflight + do + closeout. Codifies [`docs/autoresearch/`](../../../docs/autoresearch/) into an agent-runnable shape.

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

After the lane is chosen, run that lane's preflight, do, and closeout in order. Lanes do not mix mid-session.

## ⚠ Hard rules — read once, internalize (universal across lanes)

1. **ROADMAP first for substantive changes; benign edits exempt.** Any *substantive* change driven by this skill — Builder source edits, harness script behavior changes, schema/contract changes, anything that flips a documented contract or alters runtime behavior — must have a `docs/goal/ROADMAP.md` line *before* the edit lands. Place it in the right milestone (typically M2.3 for cost-aware-execution defects, M3.5 for loop-internal defects). Fix lane preflight enforces this; the same rule binds Baseline and Iterate when they discover a defect mid-flow (switch to Fix lane). **Exempt — no ROADMAP line required:** typo fixes, comment/prose tweaks that don't change a documented contract, removing demo/sample data, cosmetic HTML/CSS, dead-code deletion, and similarly low-risk edits where the diff would be self-explanatory in a review. When in doubt, lean toward adding the ROADMAP line — it costs less than the wrong call.
2. **This skill owns `docs/autoresearch/` freshness.** The skill is the sole agent responsible for keeping every file under `docs/autoresearch/` consistent with current code, current loop contract, and current measurements. No stale state allowed — ever. Every lane's closeout MUST end with a freshness sweep (see § Universal closeout freshness sweep). If the sweep finds drift the lane didn't cause, the skill stops, surfaces the drift to the operator, and asks whether to switch to Fix lane.
3. **The harness must not import from `autonomous_agent_builder/`.** It is a runner *against* Builder, not coupled to it. All 5 scripts in `scripts/autoresearch/` use `builder` CLI as subprocess + HTTP endpoints. Preserve this when editing.
4. **`.seed/devpulse/` is read-only after capture.** `chmod -R a-w` enforces this. If the seed needs to change (devpulse template evolves), capture a NEW seed and document the drift in `baseline_variance.md`. Never edit in-place.
5. **The first content block of the system prompt is cache-stable.** When making a source edit for an optimization idea, never insert dynamic content into `agents/execution_policy.py::build_system_prompt()` before the existing stable prefix. Doing so destroys the cache and the candidate will always lose on composite even when the idea was correct.
6. **`gate_pass_rate=1.0` is per-baseline-run, not historical aggregate.** Validated *inside* `baseline.py` per fixture run. Do not block on the historical `builder metrics show` aggregate which folds in M1.x dev-time failures.
7. **Stop conditions are sacred.** `loop.py` honours `--max-iterations`, `--cost-budget-usd`, and SIGINT. Do not silently extend any of these mid-session — abort and ask the operator.
8. **Wins must promote A→E before merge.** A keep on fixture A alone is not a real win. `loop.py` already enforces this; do not paper over it by hand-editing `optimize_results.tsv decision` columns.
9. **Preflight is mandatory.** Each lane has its own; the universal preflight runs first. The recipe-specific gate (`--recipe N`) catches missing seed / baseline σ / busy ports before they bite mid-run and burn API credits.
10. **`runtime_aggregates.session_scoped` must be `true`.** Every analyze.json the harness consumes (Baseline + Iterate) must carry this flag. `false` means the DB predates ROADMAP M2.3's `tasks.chat_session_id` migration and aggregates have fallen back to global scope — Fix lane required before anything else can proceed.

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

## Lane 1 — Baseline

**Purpose:** establish or re-establish the σ noise floor across fixtures A–E. Every Iterate verdict is measured relative to this floor.

### When to choose this lane

- First-time activation (no `baseline_runs_summary.json`).
- After a `roadmap-audit` flips an SDK lever `[ ]` → `[x]` (prompt-shape change → re-baseline).
- After a Fix lane closes that changed prompt assembly, runtime policy, or telemetry surface.
- When `baseline_runs_summary.json` is older than 14 days.
- When any fixture's σ/mean > 25% (timing-fragile; re-baseline that fixture).

### Preflight

```bash
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 1 --json
```

Hard requirements: `~/Builder-Workspace/devpulse` exists; `builder` healthy; ports 9876–9880 free.
Soft: `.seed/devpulse` will be (re-)snapshotted; warns if one already exists.

### Do

```bash
# 1. Verify complexity gate (autoresearch prerequisite from M3.5 README)
builder lint --complexity-report --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print("violations:", len(d["report"]["violations"]))'
# Expect: 0

# 2. Capture the immutable seed (only if /home/gurusharangupta/.seed/devpulse does not exist)
bash scripts/autoresearch/setup_seed.sh

# 3. (Optional) Bring up Jaeger UI for live trace inspection
docker compose -f scripts/autoresearch/docker-compose.yml up -d

# 4. Dry-run the runner to confirm wiring
python3 scripts/autoresearch/run.py --fixture A --branch main --port 9999 --dry-run

# 5. Real N=5 baseline across all five fixtures (~2h wallclock, ~25 model runs, ~$5–10 cost)
python3 scripts/autoresearch/baseline.py --fixtures A,B,C,D,E --n 5 \
    --evidence-root /tmp/autoresearch/baseline-$(date +%Y-%m-%d)
```

### Closeout

Required, every time — even on partial completion:

```bash
# 1. Inspect σ floor
cat docs/autoresearch/baseline_runs_summary.json
# Tier-1 acceptance: every fixture status="stable", composite σ < 25% of mean.

# 2. Regenerate the visual map
python3 .claude/skills/autoresearch/scripts/render_iterations.py

# 3. (Re-)run introspection
python3 .claude/skills/autoresearch/scripts/introspect.py

# 4. STATUS.md Recent Decisions — append a dated line:
#    "<DATE> — Baseline N=5 across A–E. σ summary: <per-fixture composite means + σ>. Cost: $X.YZ. Wallclock: Hh Mm."

# 5. If any fixture status=unstable: re-run just that one with N=10 and document the σ tightening.

# 6. Universal closeout freshness sweep (Hard Rule 2) — final step, refuses lane closure on exit 1.
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
```

**Do not tick a ROADMAP `[x]` from inside Baseline lane** — Baseline is calibration, not delivery. Tick happens from Iterate lane when a kept iteration ships, or from Fix lane when a contract defect closes.

---

## Lane 2 — Iterate

**Purpose:** pick the top unattempted idea from `OPTIMIZE_IDEAS.md`, try it on fixture A, compare to baseline, promote A→E on keep, mark attempt result. Forward motion.

### When to choose this lane

- After Baseline closeout when the σ-floor is fresh and `OPTIMIZE_IDEAS.md` has unattempted entries.
- After `goal-audit` reorders OPTIMIZE_IDEAS (new top is the next candidate).
- After a previous iteration's verdict landed and the operator wants the next one.
- For "compare a candidate" — same lane, just runs the verdict half (compare.py) on an existing `run_id`.

### Preflight

```bash
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 2 --json
```

Hard requirements: `.seed/devpulse` exists; `baseline_runs_summary.json` exists with every fixture `status=stable`; clean git on a branch suitable for cutting `autoresearch/iter-N-<ref>`.

**Stuck-residue check:** preflight surfaces stuck `/tmp/devpulse-<uuid>/` workspaces and dangling `autoresearch/iter-*` branches from prior crashes. Resolve before proceeding — run `teardown.sh` and clean branches with `git branch -D <branch>`.

**Empty-backlog check:** if `OPTIMIZE_IDEAS.md` has no unattempted ideas, surface this to the operator and ask whether they want to add one (10-second edit per the format below) before continuing. Do not silently abort.

```text
Append a new numbered entry to docs/autoresearch/OPTIMIZE_IDEAS.md following
the existing format:
    N. **idea-ref-slug** — one-line description
       Files: <path1>, <path2>          (allowlist — bounds the edit surface)
       Hypothesis: <why this should win>
       Expected impact: <token/cache/UX>
```

### Do

```bash
# 1. Preview top unattempted idea (read-only)
grep -A2 "^[0-9]\+\.\s*\*\*" docs/autoresearch/OPTIMIZE_IDEAS.md | head -10

# 2. Drive the iteration via loop.py (it prompts mid-flow for the source edit)
python3 scripts/autoresearch/loop.py --max-iterations 1 --cost-budget-usd 5
# Flow:
#   a) loop.py creates branch autoresearch/iter-N-<ref>
#   b) loop.py prints idea + allowlist; pauses for ENTER
#   c) Operator makes the edit, `git add` + `git commit` on the branch
#   d) Operator presses ENTER → loop.py runs run.py on fixture A → compare.py
#   e) Keep: loop.py promotes to B,C,D,E → final keep/discard
#   f) Discard: loop.py rewinds (git checkout main + branch -D), marks attempted
#   g) Keep: loop.py leaves branch for human review + merge

# (Alternative — manual compare without loop.py orchestrating)
python3 scripts/autoresearch/compare.py --fixture A --candidate-run <run_id>
```

### Closeout

Required, every time — kept OR discarded OR crashed:

```bash
# 1. Regenerate visual map
python3 .claude/skills/autoresearch/scripts/render_iterations.py

# 2. Re-run introspection (does the loop pay for itself?)
python3 .claude/skills/autoresearch/scripts/introspect.py

# 3. OPTIMIZE_IDEAS.md — confirm the idea's attempt marker was appended:
#    > attempted: <decision> (<reason>, YYYY-MM-DD)
#    loop.py does this automatically; on crash, append manually.

# 4. On KEEP that shipped (merged to main):
#    - tick the relevant ROADMAP `[x]` if the iteration closed a milestone item.
#    - update STATUS.md Recent Decisions with composite delta + branch name.
#    - CHANGELOG entry under "Changed" + "Validation".
#    - single commit + push.
#
#    On DISCARD or CRASH: no roadmap/status changes. Just the closeout regen above.

# 5. Universal closeout freshness sweep (Hard Rule 2) — final step, refuses lane closure on exit 1.
#    Especially important on KEEP: shipped optimizations often change prompt shape or runtime
#    policy, and METRICS.md / HARNESS.md / README.md may now describe stale measurements.
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
```

**Hard rule:** never hand-edit `optimize_results.tsv decision` columns to fake a keep. The verdict is mechanical — if it crashed it's `crash`, if compare returned `discard` it's `discard`. Re-running is cheaper than carrying a false win into the σ floor.

---

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

Follow [`docs/goal/FIX-STANDARD.md`](../../../docs/goal/FIX-STANDARD.md): memory → explore → triggers → SDK grounding → correct layer → verify → record → memory write. Specific to autoresearch defects:

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

## Common gotchas (collected from v1 setup)

These cost real time on the v1 first-fixture-A test. Doing them right the first time saves ~30 min per gotcha:

| Gotcha | Why it bites | Fix / discipline |
| --- | --- | --- |
| Invoking harness scripts from the wrong CWD | `cd scripts/autoresearch && python3 scripts/autoresearch/run.py` resolves as nested path. Script not found. | Always invoke from repo root. `bootstrap.sh` / `teardown.sh` derive root from `BASH_SOURCE`; do the same in your shell scripts. |
| Empty `follow_ups` list on a fixture | Builder surfaces multiple intake/approval questions. Empty list stalls the run. | `default_answer: "recommended"` (baked into run.py's question loop) auto-approves unanswered questions. |
| Workspace stack mismatch | Harness defaults to `npm run build && test`; against a Python app the gate silently fails. | `preflight.py --recipe N` detects via `package.json` vs `pyproject.toml`. Extend `run_feature_check()` in `run.py` for Go/Rust/etc. |
| Jaeger image tag drift | Docker Hub removes old tags. | `bootstrap.sh` pre-pulls explicitly and surfaces the failure with a tag-lookup link. |
| WSL2 + Docker bridge networking | Container UP but `127.0.0.1:16686` unreachable from WSL host. | `docker-compose.yml` uses `network_mode: host` — listeners appear directly on the WSL host. |
| Live builder bound to OTEL ports | Two daemons can't share `:4318`. | `bootstrap.sh --auto-free-ports` detects + offers to stop conflicting processes; records state for teardown to restart. |
| Docker daemon group membership | First-time `usermod -aG docker $USER` + `chmod 666 /var/run/docker.sock`. | `bootstrap.sh` distinguishes "daemon down" from "no socket access" and prints the right remedy. |
| OneCLI auth not loaded | `CLAUDE_CODE_OAUTH_TOKEN` not in the spawned `builder start` env. | NOT an autoresearch concern (memory: `project_autoresearch_auth_scope.md`). Harness uses whatever auth Builder has. |
| TSV header drift | `run.py:SESSION_HEADERS` and the TSV header diverge across versions. Silent corruption. | `preflight.py --recipe N` verifies alignment via the canonical writer schema. |
| Stuck `/tmp/devpulse-<uuid>` workspaces | Iteration crashed before teardown's workspace cleanup. | `teardown.sh` removes UUID-pattern workspaces only; never touches `/tmp/devpulse-venv` etc. |

## Visual iteration map — `docs/autoresearch/iterations.html`

Single-file static page that visualizes baseline + every iteration's verdict, composite delta, 6-hard-gate status, A→E promotion. Reads `iterations.json` first, then the embedded `window.ITERATIONS` block as fallback (for `file://` viewing).

**Regenerator:** `scripts/render_iterations.py`, bundled with this skill. Runs as part of every Baseline + Iterate closeout. Reads `optimize_results.tsv` + `baseline_runs_summary.json`, computes per-iteration verdict + composite delta in % + σ units, writes `iterations.json` and rewrites the embedded data block between `// __ITERATIONS_DATA_START__` and `// __ITERATIONS_DATA_END__`.

```bash
python3 .claude/skills/autoresearch/scripts/render_iterations.py            # write json + html
python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run  # report only
python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only # skip html rewrite
```

**Do not hand-edit `iterations.html`.** Layout, CSS, render code, and the structural markers are the contract the regenerator depends on. To change shape, edit the skill's template once and let the next regeneration propagate.

## Self-introspection — `docs/autoresearch/INTROSPECTION.md`

`scripts/introspect.py` answers the meta-question: **does the loop pay for itself?** Runs as part of every Baseline + Iterate closeout; overwrites `INTROSPECTION.md`. Git history is the canonical record.

Sections: token economics (which agent costs most); cumulative loop ROI ($ spent vs composite savings); what worked / didn't / redundant / noisy; KB-grounded leads from pinned `workflow knowledge` queries; lean recommendations ranked by `(expected token reduction × applicability)`.

Tolerant of malformed data — TSV column drift surfaces as the highest-priority recommendation rather than crashing.

```bash
python3 .claude/skills/autoresearch/scripts/introspect.py             # write + stdout summary
python3 .claude/skills/autoresearch/scripts/introspect.py --quiet     # write only
python3 .claude/skills/autoresearch/scripts/introspect.py --stdout-only  # don't overwrite
python3 .claude/skills/autoresearch/scripts/introspect.py --skip-kb   # skip workflow knowledge queries
```

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
| `iterations.html` shows example data after a real iteration ran | Closeout step skipped. | Run `render_iterations.py`. If still empty, check `optimize_results.tsv` rows have `branch=autoresearch/iter-N-…` in `notes`. |
| TSV row with garbage cells | Schema drift between `run.py:SESSION_HEADERS` and the TSV header. | Switch to Fix lane — align headers; delete the corrupt row. |
| `loop.py` Ctrl-C'd mid-iteration | Operator interrupt; branch still exists. | `git status` → find `autoresearch/iter-*` branch → `git checkout main && git branch -D <branch>` → append `> attempted: interrupted` to the idea. |
| `baseline.py` quota-failed mid-run | Provider rate limit. | `compute_summary()` only counts `gates_passed=6/6` rows so partial runs auto-excluded. Restart with same `--evidence-root`; completed rows append cleanly. |

When unsure, stop and surface state via `AskUserQuestion`. Do not silently expand `--max-iterations` / `--cost-budget-usd` or skip a hard gate.

## Cross-references

- Roadmap home: [`docs/goal/ROADMAP.md` § M3.5](../../../docs/goal/ROADMAP.md) (autoresearch activation) and § M2.3 (cost-aware execution surface — Fix lane's most frequent home).
- Activation status: [`docs/autoresearch/README.md`](../../../docs/autoresearch/README.md).
- Fix procedure: [`docs/goal/FIX-STANDARD.md`](../../../docs/goal/FIX-STANDARD.md).
- Related skills:
  - `goal-audit` — reorders `OPTIMIZE_IDEAS.md` based on session intent + autoresearch focus signals; check its INSIGHTS output before Iterate.
  - `roadmap-audit` — flags SDK levers that should trigger re-baseline when flipped `[ ]` → `[x]`.
  - `knowledge-base` — refreshes the Claude Agent SDK rubric those audits consume.

## Why this skill exists (one paragraph)

The autoresearch loop is the only Builder workflow whose value compounds with iteration count — every kept change improves the substrate all future iterations run on. But it's also the workflow most prone to operator drift: forgetting the 2σ gate, hand-editing TSV rows, picking ideas out of order, skipping A→E promotion, and — most expensively — running iterations on a contract-broken substrate (the 2026-05-23 telemetry-gap case). This skill is the discipline layer. One entry point, three lanes, each with explicit preflight and closeout. The Fix lane exists because the loop is a measurement instrument that occasionally needs its measurement contract repaired before any further measurement is meaningful.
