# Lane 2 — Iterate (pick idea → run → verdict)

> Loaded on demand when the operator picks this lane via [autoresearch SKILL.md](../../SKILL.md). Lane-specific Preflight / Do / Closeout. Universal hard rules and freshness sweep apply across lanes — see SKILL.md.

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
# Exploratory override (real keeps can't ship in this mode):
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 2 --allow-unstable-promotion --json
```

Hard requirements: `.seed/devpulse` exists; `baseline_runs_summary.json` has **every fixture A–E `status=stable`**; clean git on a branch suitable for `autoresearch/iter-N-<ref>`.

**"Stable" = `compute_summary` has ≥3 runs at `gates_passed="6/6"` with μ/σ/2σ-floor.** Both `status="unstable"` (rows exist but <3 at 6/6) and missing-from-summary (`render_iterations.py` reports `not_measured`) fail this check. Without σ-floors B–E, any fixture-A keep is discarded at promotion — Hard Rule 8 unenforceable. `--allow-unstable-promotion` downgrades fail→warn for exploratory iteration; document override use in PROGRESS.md.

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

# 1b. Launch hang-watchdog in background (see Baseline lane Step 4b — same contract).
python3 .claude/skills/autoresearch/scripts/hang_watchdog.py \
    --idle-seconds 180 --grace-seconds 90 \
    --dump-root /tmp/autoresearch/diagnostics &
WATCHDOG_PID=$!
trap "kill -TERM $WATCHDOG_PID 2>/dev/null" EXIT

# 1c. If joining a session and uncertain whether a lane is already in flight:
python3 .claude/skills/autoresearch/scripts/lane_status.py --human
# Reports any running baseline.py / loop.py + progress + ETA. The Recipe-2
# preflight also hard-fails when another lane is detected; this command is
# just the human-readable version for orientation.

# 2. Drive the iteration via loop.py (it prompts mid-flow for the source edit)
#
# Launch with `Bash run_in_background: true` (NOT `nohup ... &`) so the harness
# tracks the process + auto-notifies on completion. Pair with `Monitor` so each
# `[loop]` / `[run]` progress line streams as a notification. For interactive
# `prompt_for_edit` pauses, the bash background mode still surfaces stdin
# prompts — operator answers via the foreground.
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
# 1. Re-run introspection (does the loop pay for itself?)
python3 .claude/skills/autoresearch/scripts/introspect.py

# 2. OPTIMIZE_IDEAS.md — confirm the idea's attempt marker was appended:
#    > attempted: <decision> (<reason>, YYYY-MM-DD)
#    loop.py does this automatically; on crash, append manually.

# 3. PROGRESS.md entry — one bullet under today's date:
#    "**Iter #N <idea-ref>** — verdict KEEP|DISCARD|CRASH. composite Δ=<%>vs μ (Δσ=<x>). gates X/6. branch <name>. <reason if discard>."
#    Schema in docs/autoresearch/PROGRESS.md.
#    On KEEP that ships (merged to main): also tick ROADMAP M3.5 if the iteration closed
#    a milestone scope item; STATUS Recent Decisions only if cross-cutting.

# 4. Universal closeout freshness sweep (Hard Rule 2) — final step, refuses lane closure on exit 1.
#    Also auto-refreshes the explainer HTML data block (render_iterations.py runs inside sweep).
#    Especially important on KEEP: shipped optimizations often change prompt shape or runtime
#    policy, and METRICS.md / HARNESS.md / README.md may now describe stale measurements.
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
```

#### Iterate-lane verdict notification (every verdict — KEEP, DISCARD, CRASH)

After `loop.py` or `compare.py` reports a verdict, call the `PushNotification` deferred tool with the result so the operator doesn't have to poll. The operator's past polling pattern ("is the iteration completed?" twice in 10 minutes) is the explicit signal this is worth automating.

```
PushNotification(
  title: "Autoresearch iteration #<N> — <KEEP|DISCARD|CRASH>",
  body: "run_id=<id>, composite_delta=<%>, branch=autoresearch/iter-N-<ref>"
)
```

Skip when `PushNotification` is unavailable in the current environment.

#### Iterate-lane KEEP cross-skill triggers

On a KEEP that ships (merged to main), the kept optimization usually flips an SDK lever or changes prompt shape — both of which change inputs for `roadmap-audit` and require a re-baseline by the next `Baseline` lane invocation. Schedule both via `CronCreate`:

```
CronCreate(
  schedule: "in 24 hours",
  prompt: "roadmap-audit — autoresearch KEEP iteration #<N> flipped an SDK lever; revalidate ROADMAP",
  description: "Auto-scheduled by autoresearch Iterate KEEP closeout."
)
```

Also surface a recommendation in chat: "Iteration #<N> KEEP changed prompt shape; consider running Baseline lane to re-establish σ-floor before the next Iterate run." Do not auto-schedule Baseline — Baseline is a 2-hour, ~$5–10 lane and needs operator consent.

Skip the CronCreate when unavailable, or when `CronList` already shows a roadmap-audit cron scheduled within the next 48h.

**Hard rule:** never hand-edit `optimize_results.tsv decision` columns to fake a keep. The verdict is mechanical — if it crashed it's `crash`, if compare returned `discard` it's `discard`. Re-running is cheaper than carrying a false win into the σ floor.

---
