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
# Optional override (see "Stable" semantics below):
python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 2 --allow-unstable-promotion --json
```

Hard requirements: `.seed/devpulse` exists; `baseline_runs_summary.json` exists with **every fixture A–E in `status=stable`**; clean git on a branch suitable for cutting `autoresearch/iter-N-<ref>`.

**"Stable" semantics.** A fixture is `status=stable` when `baseline.py:compute_summary` has ≥3 runs at `gates_passed="6/6"` for that fixture and computed real μ + σ + 2σ-floor (per `baseline_runs_summary.json` schema). A fixture is **not stable** when:
- it's missing entirely from `baseline_runs_summary.json` (`render_iterations.py:parse_baseline` surfaces it as `status=not_measured`), or
- it's listed with `status="unstable"` (had baseline rows but <3 of them hit gates_passed=6/6).

Either case fails this preflight check at fail severity (per P15/P16/P17-era tightening). Without σ-floors for B–E, `loop.py`'s A→E promotion step has no σ to compare candidate composites against, so any real fixture-A keep gets discarded at the first promotion fixture with `compare.py: "baseline_runs_summary.json missing or fixture unstable"`. Hard Rule 8 ("Wins must promote A→E before merge") is unenforceable without stable σ-floors everywhere.

**`--allow-unstable-promotion` override.** Use only when knowingly iterating against a partial baseline for *exploratory* signal (e.g., debugging the loop end-to-end before committing to the full B–E baseline run). Real keeps cannot ship in this mode — A→E promotion will discard. Document the override use in the iteration's CHANGELOG so the next session understands why the result isn't a real keep.

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
