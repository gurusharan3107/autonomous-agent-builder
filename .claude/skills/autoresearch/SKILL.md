---
name: autoresearch
description: "Drive the M3.5 Track B autoresearch optimization loop end-to-end: seed snapshot → N=5 baseline → idea-by-idea Karpathy iteration. Use whenever the user asks to 'run autoresearch', 'start the autoresearch loop', 'kick off a baseline', 'run baseline', 'try the next optimize idea', 'iterate on optimization #N', 'compare a candidate run to baseline', 'add a new optimize idea', 'pick the next autoresearch idea', or any variant that pairs autoresearch / loop / optimize / baseline / fixture language with execution. ALSO use proactively after `goal-audit` reorders `docs/autoresearch/OPTIMIZE_IDEAS.md` (the new top idea should be the next iteration's candidate), after a `roadmap-audit` flips an SDK lever from `[ ]` to `[x]` (the loop should re-baseline because the prompt shape changed), and whenever STATUS.md indicates the loop is ACTIVATING/ACTIVE but the last `baseline_runs_summary.json` is older than 14 days. Everything required is self-contained under `docs/autoresearch/` (contracts) + `scripts/autoresearch/` (5 Python entry points + setup_seed.sh + optional Jaeger docker-compose). The skill does NOT invoke the model itself for each iteration — v1 is human-in-the-loop, the operator makes the source edit per the picked idea between `run.py` invocations."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash, Write
compatibility:
  - python3 >= 3.12 (run.py / baseline.py / compare.py / loop.py / extract_context_breakdown.py)
  - requests (pip install requests)
  - tiktoken (pip install tiktoken; optional — falls back to 4-char-per-token approximation)
  - builder CLI on PATH (subprocess invocations; required)
  - npm on PATH (feature-correctness gate inside fixture workspaces; required)
  - docker (optional; only if Jaeger UI is desired — Path A raw-body capture works without it)
---

# autoresearch — drive the M3.5 Track B optimization loop

Codifies the workflow specified in [`docs/autoresearch/`](../../../docs/autoresearch/) into an agent-runnable lane. Adapts Karpathy's autoresearch philosophy ("rapid autonomous iteration at small scale beats big runs at slow cadence") to optimize the Autonomous Builder's own prompt shape, context size, agent use, and runtime policy.

## ⚠ HARD RULES — read once, internalize

1. **The harness must not import from `autonomous_agent_builder/`.** It is a runner *against* Builder, not coupled to it. All 5 scripts in `scripts/autoresearch/` use `builder` CLI as subprocess + HTTP endpoints. Preserve this when editing.
2. **`.seed/devpulse/` is read-only after capture.** `chmod -R a-w` enforces this. If the seed needs to change (devpulse template evolves), capture a NEW seed and document the drift in `baseline_variance.md`. Never edit in-place.
3. **The first content block of the system prompt is cache-stable.** When you make a source edit for an optimization idea, never insert dynamic content into `agents/execution_policy.py::build_system_prompt()` before the existing stable prefix. Doing so destroys the cache and the candidate will always lose on composite even when the idea was correct.
4. **`gate_pass_rate=1.0` is per-baseline-run, not historical aggregate.** Per `docs/autoresearch/README.md` § Prerequisites, this is validated *inside* `baseline.py` per fixture run. Do not block on the historical `builder metrics show` aggregate which folds in M1.x dev-time failures.
5. **Stop conditions are sacred.** `loop.py` honours `--max-iterations`, `--cost-budget-usd`, and SIGINT. Do not silently extend any of these in the middle of a session — abort and ask the operator.
6. **Wins must promote A→E before merge.** A keep on fixture A alone is not a real win. `loop.py` already enforces this; do not paper over it by manually editing `optimize_results.tsv decision` columns.
7. **Preflight is mandatory.** Before invoking any recipe — even read-only status checks — run the bundled preflight validator and act on its output. The recipe-specific gate (`--recipe N`) catches missing seed / baseline σ / busy ports / etc. before they bite mid-run and burn API credits.

## Mandatory preflight check

The skill bundles `scripts/preflight.py` to validate infra before any recipe. It is the discipline layer for Hard Rule 7 — without it, the skill is just prose. Always run it first and act on a non-zero exit:

```bash
# General health (every session start)
python3 .claude/skills/autoresearch/scripts/preflight.py

# Before Recipe 1 (first-time activation)
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 1

# Before Recipe 2 (iteration) — requires seed + baseline σ floor
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 2 --json

# Before Recipe 3 (manual compare) — same prereqs as Recipe 2
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 3 --json
```

What it checks:

| Layer | Checks |
| --- | --- |
| **Hard** (must pass — exits 1 on fail) | `builder` / `npm` / `python3` / `git` on PATH; `requests` importable; `~/Builder-Workspace/devpulse` exists; 5 contract docs in `docs/autoresearch/`; 6 harness files in `scripts/autoresearch/` |
| **Recipe-specific** (gated by `--recipe N`) | Recipe 2/3: `.seed/devpulse` exists + `baseline_runs_summary.json` exists + every fixture `status=stable`. Recipe 1: warns if baseline already exists (re-snapshot scenario). |
| **Soft** (warn-only — loop runs degraded) | `tiktoken` importable (else 4-char fallback); ports 9876–9880 free; `/tmp` has ≥5 GB free; docker present + Jaeger container running; git on a clean branch |

Output formats: human-readable table by default; `--json` for machine-readable consumption. Exit code 0 = pass or warn-only; 1 = hard or recipe-specific failure. **If exit is non-zero, do not proceed — run the bundled bootstrap (next section) or surface the `fix:` field of each failed check to the operator.**

## Bootstrap — one-shot auto-fix

When preflight reports failures, the skill also bundles `scripts/bootstrap.sh` to auto-fix every machine-fixable item. Idempotent and safe to re-run:

```bash
# One-shot setup (auto-installs deps, captures seed, brings up Jaeger if docker present)
bash .claude/skills/autoresearch/scripts/bootstrap.sh

# Selective skips for items you don't want
bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-seed     # don't snapshot
bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-jaeger   # don't start Jaeger
bash .claude/skills/autoresearch/scripts/bootstrap.sh --dry-run       # report only
```

What bootstrap auto-fixes:
- `pip install --user requests tiktoken` if either is missing
- `bash scripts/autoresearch/setup_seed.sh` if `.seed/devpulse` is missing (delegates to the canonical script, never re-snapshots an existing seed)
- `docker compose -f scripts/autoresearch/docker-compose.yml up -d` if docker present and Jaeger container not running

What bootstrap surfaces but cannot fix (operator action required):
- docker daemon not installed → prints the one-liner curl install command
- Ports 9876–9880 in use → operator must free or pass `--port-base`
- Git in dirty / non-main state → operator must commit / stash / checkout
- Disk space below threshold → operator must free disk

After auto-fix passes, bootstrap re-runs preflight and prints the residual manual TODO list. **If bootstrap exits cleanly and the residual list is empty, you're cleared to run any recipe.**

## Teardown — clean session shutdown

When the loop session ends, the skill bundles `scripts/teardown.sh` to release ephemeral state cleanly:

```bash
# Standard teardown — stop Jaeger, clean /tmp/devpulse-<uuid>/ workspaces
bash .claude/skills/autoresearch/scripts/teardown.sh

# Aggressive — also wipe /tmp/autoresearch/ evidence dirs
bash .claude/skills/autoresearch/scripts/teardown.sh --with-evidence

# Keep Jaeger running (e.g., for post-mortem trace inspection)
bash .claude/skills/autoresearch/scripts/teardown.sh --keep-jaeger
```

Teardown is intentionally surgical:
- ✓ Stops + removes the Jaeger container (`docker compose down`)
- ✓ Removes UUID-shaped `/tmp/devpulse-<uuid>/` workspaces (run.py leftovers if it crashed mid-iteration). Refuses to touch non-UUID paths like `/tmp/devpulse-venv` — surfaces them as "skipped, looks unrelated".
- ✓ Optional `/tmp/autoresearch/` evidence cleanup (gated by `--with-evidence`)
- ✗ Never touches `.seed/devpulse` (immutable; teardown must not delete the snapshot)
- ✗ Never touches `docs/autoresearch/*.tsv` (durable evidence rows persist across sessions)
- ✗ Never touches `baseline_runs_summary.json` (σ floor reused across iterations)
- ✗ Never touches git state (operator owns branches)

## Docker container lifecycle

Docker handling is split between **bootstrap.sh** (start) and **teardown.sh** (stop):

| Phase | What happens | Where |
|---|---|---|
| Daemon install | NOT auto-installed (requires sudo). Bootstrap prints the one-liner for WSL2 Ubuntu: `curl -fsSL https://get.docker.com \| sh && sudo usermod -aG docker $USER && sudo service docker start`. Re-login then re-run bootstrap. | Operator action |
| Daemon reachability | Bootstrap checks `docker info`; if it fails, prints `sudo service docker start` hint and skips Jaeger (Path A file-OTEL still works). | bootstrap.sh |
| Container start | `docker compose -f scripts/autoresearch/docker-compose.yml up -d`. If the container already exists but is stopped, restarts via `docker start autoresearch-jaeger` instead. | bootstrap.sh |
| Health check | Polls `http://127.0.0.1:16686` (Jaeger UI) up to 30s. Also pings `:4318/v1/traces` to confirm OTLP HTTP receiver is live. | bootstrap.sh |
| Container stop | `docker compose down`. Idempotent — handles "not present", "stopped", and "running" states uniformly. | teardown.sh |
| Cleanup of stopped container | `docker rm autoresearch-jaeger` if container exists but isn't running. | teardown.sh |

If docker isn't installed at all, the skill degrades to Path A file-OTEL — `OTEL_LOG_RAW_API_BODIES=file:<dir>` writes raw API bodies directly to disk and `extract_context_breakdown.py` parses them. No traces or spans, but the σ floor and 2σ comparison still work.

## Surface map — everything self-contained

```text
docs/autoresearch/                       # contracts (read these first)
├── README.md                            # entry point; activation status; prereqs
├── OPTIMIZE.md                          # loop contract: composite, hard gates, allowlist, stop conditions
├── METRICS.md                           # every signal → source → TSV column
├── HARNESS.md                           # runnable harness contract; pseudo-code per script
├── COMPARE.md                           # two-run diff protocol; 2σ test + per-prompt sanity
├── SDK-OBSERVABILITY.md                 # OTEL env-var prescription
├── CONTEXT-LEDGER.md                    # Path A (executable) + Path B (source instrumentation, future) anchor logic
├── GAPS.md                              # source changes that would simplify the loop (v1/v2/v3 tiers)
├── OPTIMIZE_IDEAS.md                    # living backlog of optimization hypotheses (top first)
├── fixtures.md                          # five scripted operator prompts (A short / B long / C ambiguous / D vague / E multi-turn)
├── baseline_variance.md                 # N=5 protocol + recorded σ history
├── baseline_runs.tsv                    # filled by baseline.py
├── optimize_results.tsv                 # filled by run.py (one row per iteration)
├── per_prompt_results.tsv               # filled by run.py (one row per prompt within a session)
├── baseline_runs_summary.json           # filled by baseline.py; read by compare.py for 2σ floor
├── iterations.json                      # filled by render_iterations.py per closeout
├── iterations.html                      # visual map of iteration progress (Dieter Rams + Tufte)
└── INTROSPECTION.md                     # overwritten by introspect.py per closeout (meta-loop report)

scripts/autoresearch/                    # the v1 harness
├── README.md                            # operator runbook
├── docker-compose.yml                   # optional Jaeger all-in-one (UI only)
├── setup_seed.sh                        # one-time .seed/devpulse capture
├── run.py                               # atomic fixture runner
├── baseline.py                          # N=5 σ driver
├── compare.py                           # 2σ + 6-hard-gate verdict generator
├── loop.py                              # Karpathy human-in-loop iteration
└── extract_context_breakdown.py         # Path A tiktoken + anchor attribution
```

## When to invoke this skill

Match on user intent — exact strings are not required:

- "run autoresearch" / "start the loop" / "kick off the autoresearch loop"
- "run baseline" / "kick off baseline" / "establish σ floor"
- "try the next optimize idea" / "iterate on idea N" / "pick next from OPTIMIZE_IDEAS"
- "compare a candidate against baseline" / "is this a win?"
- "add a new optimize idea" / "log this optimization hypothesis"
- "what's the autoresearch status?" / "where are we in the loop?"

Proactively engage when:

- `goal-audit` reorders `OPTIMIZE_IDEAS.md` (the new top is the next candidate).
- A `roadmap-audit` flips an SDK lever `[ ]` → `[x]` (prompt-shape change → re-baseline).
- STATUS.md says ACTIVE/ACTIVATING but `baseline_runs_summary.json` is older than 14 days.

## Execution recipes

### Recipe 1 — First-time activation (one-time bootstrap)

```bash
# 1. Verify the activation gate (everything except in-harness prereqs)
builder lint --complexity-report --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print("violations:", len(d["report"]["violations"]))'
# Expect: 0

# 2. Capture the immutable seed (only if /home/gurusharangupta/.seed/devpulse does not exist)
bash scripts/autoresearch/setup_seed.sh
# Outputs: /home/gurusharangupta/.seed/devpulse (chmod -R a-w) + /home/gurusharangupta/.seed/devpulse.sha256

# 3. (Optional) Bring up Jaeger UI for live trace inspection
docker compose -f scripts/autoresearch/docker-compose.yml up -d
# UI: http://127.0.0.1:16686

# 4. Dry-run the runner to confirm wiring
python3 scripts/autoresearch/run.py --fixture A --branch main --port 9999 --dry-run

# 5. Real N=5 baseline across all five fixtures (~2h wallclock, ~25 model runs, ~$5–10 cost)
python3 scripts/autoresearch/baseline.py --fixtures A,B,C,D,E --n 5 \
    --evidence-root /tmp/autoresearch/baseline-$(date +%Y-%m-%d)

# 6. Inspect σ floor
cat docs/autoresearch/baseline_runs_summary.json
# Tier-1 acceptance: every fixture shows status="stable" with reasonable σ
# (typically composite σ < 25% of mean; bigger σ → fixture timing-fragile, re-run)

# 7. ✱ Baseline closeout — render the visual map so docs/autoresearch/iterations.html
#    reflects the new σ floor (empty iterations list, populated baseline panel).
python3 .claude/skills/autoresearch/scripts/render_iterations.py
```

### Recipe 2 — Run one optimization iteration

```bash
# 1. Pick top unattempted idea from docs/autoresearch/OPTIMIZE_IDEAS.md (preview only)
grep -A2 "^[0-9]\+\.\s*\*\*" docs/autoresearch/OPTIMIZE_IDEAS.md | head -10

# 2. Let loop.py drive the iteration (it prompts you mid-flow for the source edit)
python3 scripts/autoresearch/loop.py --max-iterations 1 --cost-budget-usd 5
# Workflow:
#   a) loop.py creates branch autoresearch/iter-N-<ref>
#   b) loop.py prints idea + allowlist; pauses for ENTER
#   c) You make the edit, `git add` + `git commit` on the branch
#   d) You press ENTER → loop.py runs run.py on fixture A → compare.py
#   e) If keep: loop.py promotes to B,C,D,E (sequentially) → final keep/discard
#   f) On discard: loop.py rewinds (git checkout main + branch -D) and marks attempted
#   g) On keep: loop.py leaves the branch in place for human review + merge

# 3. ✱ Iteration closeout — ALWAYS run, regardless of verdict
python3 .claude/skills/autoresearch/scripts/render_iterations.py
# Aggregates the new row(s) in optimize_results.tsv into iterations.json and
# rewrites the embedded data block in docs/autoresearch/iterations.html so the
# visual map reflects current state. Idempotent and safe to re-run.

# 4. ✱ Self-introspection — meta-autoresearch (does the loop pay for itself?)
python3 .claude/skills/autoresearch/scripts/introspect.py
# Writes docs/autoresearch/INTROSPECTION.md. Sections: token economics
# (which agent costs the most), cumulative ROI vs API spend, redundant gates
# / noisy fixtures, KB leads (workflow knowledge articles relevant to making
# the loop leaner), lean recommendations ranked by token-reduction impact.
# stdout prints recommendations only; the full report goes to the file.
```

### Recipe 3 — Compare an existing candidate against baseline

```bash
# When you already ran run.py and want a verdict without loop.py orchestrating
python3 scripts/autoresearch/compare.py --fixture A \
    --candidate-run <run_id from optimize_results.tsv>
# Stdout: JSON verdict {decision, reason, detail}
# Side effect: patches optimize_results.tsv decision + composite_delta_pct columns
```

### Recipe 4 — Add a new optimize idea

```text
1. Append a new numbered entry to docs/autoresearch/OPTIMIZE_IDEAS.md following
   the existing format:
       N. **idea-ref-slug** — one-line description
          Files: <path1>, <path2>          (allowlist — bounds the edit surface)
          Hypothesis: <why this should win>
          Expected impact: <token/cache/UX>
2. Order by expected impact, highest first. loop.py picks the top unattempted.
3. Do not run the idea immediately; let the operator decide when to start.
```

### Recipe 5 — Recover from a stuck or broken iteration

Different recovery paths depending on **how** the iteration broke:

**Diagnosis first — read the evidence:**

```bash
# 1. Find the run_id of the last iteration (last row in optimize_results.tsv)
tail -1 docs/autoresearch/optimize_results.tsv | cut -f1

# 2. Read the crash log (set by run.py's except handler)
cat /tmp/autoresearch/<run-id>/crash.log

# 3. Inspect raw API bodies — what was the agent doing when it stalled?
ls /tmp/autoresearch/<run-id>/raw_bodies/
# Each .jsonl file is one API turn. Last one usually shows where the run stopped.

# 4. Check the analyze.json for the agent that was active at crash time
python3 -c "import json; d = json.load(open('/tmp/autoresearch/<run-id>/analyze.json')); print(d.get('prompts', [])[-1])"
```

**Crash types and the fix per type:**

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `decision_status: crash` + `TimeoutError: No question or ship within 600s` | Fixture's `follow_ups` list exhausted while builder still waiting for operator answers | Add more `follow_ups` entries OR rely on the `default_answer: "recommended"` fallback (now built in to run.py's question loop). Re-run the fixture. |
| `feature_correct: false` + npm/pytest in crash.log | Workspace-stack mismatch (e.g., harness ran `npm` against a Python app) | `run.py:run_feature_check` now auto-detects `package.json` vs `pyproject.toml`. If your stack is something else (Go/Rust/etc.) extend that function with the right command. |
| TSV row with garbage cells ('2/6' under noncached_plus_output_tokens) | Schema drift between `run.py:SESSION_HEADERS` and the TSV header | `preflight.py` now catches this before the run. If it slipped through: align run.py and the TSV (delete the row, fix run.py, re-run). |
| `loop.py` Ctrl-C'd mid-iteration | Operator interrupt; branch still exists | `git status` → find `autoresearch/iter-*` branch → `git checkout main && git branch -D <branch>` → append `> attempted: interrupted (operator_ctrl_c, YYYY-MM-DD)` to the idea in OPTIMIZE_IDEAS.md so `loop.py` doesn't re-pick it. |
| `baseline.py` quota-failed mid-run | Provider rate limit hit; some fixtures incomplete | `baseline_runs.tsv` already has the completed rows. `compute_summary()` only counts rows with `gates_passed=6/6` so partial runs are auto-excluded. Restart `baseline.py` with the same `--evidence-root`; completed rows append cleanly. |
| Stale TSV header (drift from a long-past schema) | Header was written manually or by an older `run.py` | `preflight.py --recipe 2` flags the drift. Fix the TSV header to match `run.py:SESSION_HEADERS` exactly, preserve data rows. |
| Stuck `/tmp/devpulse-<uuid>` workspaces | Iteration crashed before teardown's workspace cleanup | `bash .claude/skills/autoresearch/scripts/teardown.sh` removes UUID-pattern workspaces; never touches non-UUID `/tmp/devpulse-*` paths like `/tmp/devpulse-venv`. |
| Builder restored after teardown is stale | Teardown's restore copied stale state | `.autoresearch-bootstrap-state` records which builders bootstrap stopped. After teardown auto-restart, verify with `curl 127.0.0.1:<port>/api/dashboard/board`. If broken, stop and restart manually. |

**Hard rule for any recovery:** never hand-edit the TSV `decision` column to fake a "keep". The verdict is mechanical — if the iteration crashed, it's `crash`, period. Re-running the fix is cheaper than carrying a false win forward into the σ floor.

## Common gotchas (collected from v1 setup)

These cost real time on the v1 first-fixture-A test. Doing them right the first time saves ~30 min per gotcha:

| Gotcha | Why it bites | Fix / discipline |
| --- | --- | --- |
| Invoking harness scripts from the wrong CWD | `cd scripts/autoresearch && python3 scripts/autoresearch/run.py` resolves as nested path. Script not found, exits immediately. | Always invoke from repo root. `bootstrap.sh` and `teardown.sh` derive the repo root from `BASH_SOURCE`; you should do the same in your shell scripts. |
| Empty `follow_ups` list on a fixture | Builder surfaces multiple intake/approval questions per feature. An empty `follow_ups` list stalls the run. | Use `default_answer: "recommended"` (now baked into run.py's question loop). All unanswered questions get auto-approved. |
| Workspace stack mismatch | Harness defaults to `npm run build && test`; if the workspace is Python, the gate silently fails. | `preflight.py --recipe N` now detects via `package.json` vs `pyproject.toml`. Extend `run_feature_check()` in `run.py` for Go/Rust/etc. |
| Jaeger image tag drift | Docker Hub removes old tags. `1.62` was stale when we set up; the compose file errored on pull. | `bootstrap.sh` pre-pulls explicitly and reports the failure with a link to query Docker Hub for current tags. |
| WSL2 + Docker bridge networking dropping port forwarding | Container UP, but `127.0.0.1:16686` from WSL host doesn't reach it. | `docker-compose.yml` uses `network_mode: host` — the container's listeners appear directly on the WSL host. |
| Live builder bound to OTEL ports | Two daemons can't share `:4318`. Existing builder on devpulse blocks Jaeger startup. | `bootstrap.sh --auto-free-ports` detects builder processes on OTEL ports, prompts/stops them, and records state to `.autoresearch-bootstrap-state` for teardown to restart. |
| Docker daemon group membership | First-time sudo for `usermod -aG docker $USER` + `chmod 666 /var/run/docker.sock`. Without it, all docker commands fail "permission denied". | One-time setup, then never again. `bootstrap.sh` distinguishes "daemon down" from "no socket access" and prints the right remedy. |
| OneCLI auth not loaded | `CLAUDE_CODE_OAUTH_TOKEN` isn't readable in the spawned `builder start` env. | NOT an autoresearch concern (per memory: `project_autoresearch_auth_scope.md`). Whatever auth Builder is configured for, the harness uses transparently. |
| TSV header drift | `run.py:SESSION_HEADERS` and `optimize_results.tsv` / `baseline_runs.tsv` headers can diverge across script versions. Silent corruption. | `preflight.py --recipe N` now verifies alignment via the canonical writer schema. Caught the drift before our 2nd fixture-A test. |

## Visual iteration map — `docs/autoresearch/iterations.html`

A single-file static HTML page that visualizes baseline + every iteration's verdict, composite delta, 6-hard-gate status, and A→E promotion. Designed per Dieter Rams (minimal chrome, generous whitespace, no decoration) and Edward Tufte (maximize data-ink, small multiples, sparklines, no chartjunk).

The page reads two data sources at load time:

1. `docs/autoresearch/iterations.json` — preferred, written by the regenerator.
2. Embedded `window.ITERATIONS` block inside the HTML — fallback when the JSON is unreachable (e.g., opening from `file://` without a server).

**Regenerator: `scripts/render_iterations.py` (bundled with this skill).** Runs as part of every iteration closeout (Recipe 1 step 7 and Recipe 2 step 3). It:

- Reads `optimize_results.tsv` and groups rows by iteration branch (`autoresearch/iter-N-<ref>`).
- Reads `baseline_runs_summary.json` for mean / σ / 2σ noise floor.
- Computes per-iteration verdict, composite delta in % and σ units, 6-gate pass mask, A→E promotion status, and diff size (via `git diff --shortstat`).
- Writes `iterations.json` (production fetch path) AND rewrites the embedded block in `iterations.html` between the `// __ITERATIONS_DATA_START__` and `// __ITERATIONS_DATA_END__` markers (so `file://` viewing still works).
- Preserves all other content in `iterations.html` (CSS, render code, example fallback data, comments) verbatim across regenerations.

Operator command:

```bash
python3 .claude/skills/autoresearch/scripts/render_iterations.py            # write json + html
python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run  # report only
python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only # skip html rewrite
```

**Do not hand-edit `iterations.html`.** The render code, CSS, and structural markers (`__ITERATIONS_DATA_START__` / `__ITERATIONS_DATA_END__`) are the contract the regenerator depends on. If the visualization needs to change shape, edit the template once in the skill's repo and let the next regeneration propagate.

## Self-introspection — `docs/autoresearch/INTROSPECTION.md`

The skill bundles `scripts/introspect.py` to answer the meta-question: **does the loop pay for itself?** It runs after `render_iterations.py` in every iteration closeout and writes (overwrites) `docs/autoresearch/INTROSPECTION.md`. Git history of the file is the canonical record of how the loop evolved.

What the report covers:

1. **Token economics** — total non-cached+output tokens consumed across all iterations; top-5 agents by cumulative cost. Identifies the *highest-leverage* targets for future lean ideas (improving cache hit rate on a 60%-of-cost agent beats improving a 5%-of-cost agent by the same percentage).
2. **Cumulative loop ROI** — total $ spent (summed from `per_prompt_results.tsv.cost_usd`) vs cumulative composite savings. Surfaces break-even: "after N future feature ships, the loop has earned back what it cost".
3. **What worked / didn't / redundant / noisy** — kept iterations, discard reasons grouped, hard gates that never discriminated (= wasted evaluation), fixtures with σ/mean > 25% (= wasted runs).
4. **KB-grounded leads** — `workflow knowledge search` results across pinned token-cost / cache / context-engineering queries. Surfaces relevant articles the operator can read for the next iteration's idea selection. KB queries are intentionally pinned (not goal-audit's "what's next?" job) so the report is stable iteration to iteration and a new article landing in the KB stands out.
5. **Lean recommendations** — ranked by `(expected token reduction × applicability)`. Each item points at a specific Builder source path / harness file with a concrete change.

`introspect.py` is **tolerant of malformed data**: if a TSV column drifts out of sync with the writer schema (we hit this in v1 testing — `run.py`'s `SESSION_HEADERS` didn't match the existing TSV header), the introspection script still completes and surfaces the drift as the highest-priority recommendation. Never silently truncates.

```bash
python3 .claude/skills/autoresearch/scripts/introspect.py             # write + stdout summary
python3 .claude/skills/autoresearch/scripts/introspect.py --quiet     # write only
python3 .claude/skills/autoresearch/scripts/introspect.py --stdout-only  # don't overwrite INTROSPECTION.md
python3 .claude/skills/autoresearch/scripts/introspect.py --skip-kb   # skip workflow knowledge queries
```

## Reading order for a fresh session

When this skill activates, follow exactly this read order to build context:

1. **`docs/autoresearch/README.md`** — current activation status; check Prerequisites section for what's open/closed today.
2. **`docs/autoresearch/OPTIMIZE.md`** — the loop contract (composite formula, 6 hard gates, allowlist policy, stop conditions).
3. **`docs/autoresearch/OPTIMIZE_IDEAS.md`** — find the top unattempted idea; this is the candidate for the next iteration.
4. **`docs/autoresearch/HARNESS.md`** — only if you need to debug or extend a harness script.
5. **`docs/autoresearch/COMPARE.md`** — only if you need to interpret a `decision: discard` JSON verdict.

Do not read METRICS.md / CONTEXT-LEDGER.md / SDK-OBSERVABILITY.md / GAPS.md unless extending the harness itself — they are reference docs for the v1 author, not for loop operators.

## Files this skill MAY edit

- `docs/autoresearch/OPTIMIZE_IDEAS.md` — append new ideas; mark attempted/kept/discarded.
- `docs/autoresearch/baseline_variance.md` — append observed σ table after `baseline.py` completes (already done by baseline.py, but the skill may add prose context).
- `docs/autoresearch/baseline_runs.tsv` / `optimize_results.tsv` / `per_prompt_results.tsv` — append-only via the scripts; never hand-edit rows.
- `docs/autoresearch/baseline_runs_summary.json` — overwritten by baseline.py; never hand-edit.
- `docs/autoresearch/iterations.json` — overwritten by render_iterations.py; never hand-edit.
- `docs/autoresearch/iterations.html` — only the embedded data block between the `__ITERATIONS_DATA_START__` / `__ITERATIONS_DATA_END__` markers is rewritten by render_iterations.py. Layout / CSS / render code is preserved and should never be hand-edited (edit the skill's template instead).
- `docs/goal/STATUS.md` Recent Decisions — one-liner after a kept iteration ships, with the composite delta and the branch name.
- `docs/goal/ROADMAP.md` § M3.5 — tick `[x]` on activation milestones as they close.

## Files this skill MUST NEVER edit

- `docs/autoresearch/{README,OPTIMIZE,METRICS,HARNESS,COMPARE,SDK-OBSERVABILITY,CONTEXT-LEDGER,GAPS,fixtures}.md` — contracts, owned by the v1 author / human review. If you need to evolve a contract, write a v2 spec proposal in INSIGHTS.md instead.
- `scripts/autoresearch/*.{py,sh,yml}` — harness source; only edit when fixing a script-level bug. Optimization ideas operate on Builder source, not the harness.
- `src/autonomous_agent_builder/` — never edited by this skill directly. Edits happen as part of an iteration, and `loop.py` hands them to the operator. The skill orchestrates; the human writes the code per the idea's allowlist.

## Failure modes & escalation

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `setup_seed.sh` says "source devpulse not found" | `~/Builder-Workspace/devpulse` missing or moved | Confirm the canonical workspace path with the operator; pass `--src` to the script |
| `baseline.py` reports `status=unstable` for a fixture (<3 clean runs) | Timing-fragile fixture or quota interruption | Re-run only the unstable fixture: `baseline.py --fixtures D --n 5 --evidence-root .../retry` |
| `compare.py` returns `decision: crash, reason: no_baseline` | `baseline_runs_summary.json` missing or fixture row missing | Run Recipe 1 step 5 first |
| `loop.py` repeatedly picks the same idea | OPTIMIZE_IDEAS.md attempted marker not applied | Check the idea's section — the marker is `> attempted: <decision> (<reason>, <date>)` appended below the idea body. Add it manually if needed. |
| Every candidate `discard` with `composite_within_2sigma` | Baseline σ too wide; iteration not meaningful | Re-run baseline with N=10 to tighten σ, or pick higher-impact ideas |
| `extract_context_breakdown.py` reports `unattributed_tokens > 10%` | Prompt assembly anchor drift (a header was renamed) | Check `extractor_warnings.log` and update the `ANCHORS` table in the extractor to match the new prompt structure |
| `iterations.html` shows example data after a real iteration ran | Closeout step skipped — `render_iterations.py` was not invoked | Run the closeout: `python3 .claude/skills/autoresearch/scripts/render_iterations.py`. If still empty, check `optimize_results.tsv` actually has rows tagged `branch=autoresearch/iter-N-…` in the `notes` column. |
| `render_iterations.py` reports 0 iterations despite TSV rows | Branch tag missing from `notes` column (older rows or run.py change) | The script keys on `branch=autoresearch/iter-N-<ref>` in the `notes` field. Older rows without that tag are silently skipped — backfill or accept the gap. |

When unsure, stop and surface the state to the operator via `AskUserQuestion`. Do not silently expand `--max-iterations` or `--cost-budget-usd` or skip a hard gate.

## Cross-references

- Roadmap home: [`docs/goal/ROADMAP.md` § M3.5](../../../docs/goal/ROADMAP.md)
- Activation rationale: [`docs/autoresearch/README.md`](../../../docs/autoresearch/README.md)
- Related skills:
  - `goal-audit` — reorders OPTIMIZE_IDEAS.md based on session intent + autoresearch focus signals; do NOT duplicate that here, but check its INSIGHTS output before picking the next idea
  - `roadmap-audit` — flags SDK levers that should trigger a re-baseline when they flip from `[ ]` to `[x]`
  - `knowledge-base` — refreshes the Claude Agent SDK rubric that those audits consume

## Why this skill exists (one paragraph)

The autoresearch loop is the only Builder workflow whose value compounds with iteration count — every kept change improves the substrate that all future iterations run on. But it's also the workflow most prone to operator drift: forgetting to honor the 2σ gate, hand-editing TSV rows, picking ideas out of order, skipping the A→E promotion. This skill is the discipline layer. It locks the operator into the contract specified in `docs/autoresearch/`, surfaces the next concrete action from `OPTIMIZE_IDEAS.md`, and refuses to let the loop fall back into ad-hoc tuning.
