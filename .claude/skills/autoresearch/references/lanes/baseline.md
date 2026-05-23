# Lane 1 — Baseline (σ-floor establishment)

> Loaded on demand when the operator picks this lane via [autoresearch SKILL.md](../../SKILL.md). Lane-specific Preflight / Do / Closeout. Universal hard rules and freshness sweep apply across lanes — see SKILL.md.

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

# 4b. Launch hang-watchdog in background (skill-owned forensic dump on stall).
# Detects builder hang within ~3 min instead of burning the full 25-min
# per-question budget; dumps logs/sessions/py-spy/DB snapshot to
# /tmp/autoresearch/diagnostics/<UTC-timestamp>-pid<PID>/.
python3 .claude/skills/autoresearch/scripts/hang_watchdog.py \
    --idle-seconds 180 --grace-seconds 90 \
    --dump-root /tmp/autoresearch/diagnostics &
WATCHDOG_PID=$!
trap "kill -TERM $WATCHDOG_PID 2>/dev/null" EXIT

# 5. Real N=5 baseline across all five fixtures (~2h wallclock, ~25 model runs, ~$5–10 cost)
#
# Launch with `Bash run_in_background: true` (NOT `nohup ... &`) so the harness
# tracks the process + auto-notifies on completion. Then pair with `Monitor`
# (or `BashOutput` for one-shot polls) so each `[baseline] fixture=X iter=Y/5`
# line streams as a notification — keeps you aware of progress without re-checking.
python3 scripts/autoresearch/baseline.py --fixtures A,B,C,D,E --n 5 \
    --evidence-root /tmp/autoresearch/baseline-$(date +%Y-%m-%d)
```

**Joining a session with an in-flight lane.** Run `python3 .claude/skills/autoresearch/scripts/lane_status.py --human` before touching anything. Preflight `--recipe 1` hard-fails on detected lanes (TSV/workspace/port collision). Wait or `kill -TERM <PID>` before starting new.

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

# 4. PROGRESS.md entry — one bullet under today's date:
#    "**Baseline N=5 across A–E** — per-fixture status + μ/σ/2σ-floor. Cost $X.YZ, wallclock Hh Mm. Commit <sha>."
#    Schema in docs/autoresearch/PROGRESS.md.

# 5. If any fixture status=unstable: re-run just that one with N=10 and document the σ tightening (in the same PROGRESS.md entry).

# 6. Universal closeout freshness sweep (Hard Rule 2) — final step, refuses lane closure on exit 1.
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
```

#### Baseline-lane completion notification

After `baseline.py` finishes (success or partial completion), call `PushNotification` with the σ summary so the operator doesn't have to poll. Baseline takes ~2h; a notification on completion is high-value.

```
PushNotification(
  title: "Autoresearch Baseline N=5 complete",
  body: "Fixtures A–E status: <stable|unstable> counts. Composite σ: <per-fixture summary>. Cost: $<actual>."
)
```

Skip when `PushNotification` is unavailable.

#### Baseline-lane cross-skill trigger

A fresh σ-floor is the highest-quality input for the next `goal-audit` Section A (Builder telemetry signal). Schedule a goal-audit 24 hours out so the day-after audit reads the new baseline numbers:

```
CronCreate(
  schedule: "in 24 hours",
  prompt: "goal-audit run — analyze last 7d (post-Baseline)",
  description: "Auto-scheduled by autoresearch Baseline closeout."
)
```

Skip when unavailable or when `CronList` already shows a goal-audit cron in the next 48h.

**Baseline writes to PROGRESS.md, not ROADMAP** — Baseline is calibration, not delivery. No ROADMAP `[x]` from this lane. ROADMAP M3.5 milestone ticks only when the Iterate lane ships a kept change.

---
