---
name: start
description: "Primary session-entry skill. ONE command at the start of every new session in this repo, whether or not the prior session ran /save-session. Loads framework context (AGENTS.md root + docs/goal/README.md), STATUS Current Position + Last Update + top Recent Decisions, recent git log, optional drift warnings from check_status_drift.py, and — only if .claude/session-data/CURRENT.md exists and is <48h old — the tactical handoff from the prior session. Synthesizes ONE briefing message and waits for direction; never auto-executes. Triggers: `/start`, 'start', 'begin', 'hi', 'hi how are you', 'where are we', 'what's next', 'provide status of where we are', 'can you check AGENTS.md and docs/goal/README.md', 'can you first check the AGENTS.md and docs/goal/README.md', 'check the framework', 'what's the status', or any phrasing that pairs 'check' / 'read' / 'load' with AGENTS.md / docs/goal/README.md / STATUS.md at session entry. Sister skill to `/resume-session` — both converge to the same loaded state: `start` runs the full sequence directly; `/resume-session` reads CURRENT.md tactical context first then chains into this skill for framework + STATUS load."
allowed-tools: Bash, Read
compatibility:
  - python3 >= 3.9 (drift check; degrades gracefully if absent)
  - git on PATH
---

# start — primary session-entry briefing

The default command typed at the start of every session in this repo. Loads durable framework + recent state + optional tactical handoff. Read-only synthesis; never auto-executes.

## Why this exists (vs `/resume-session`)

`/resume-session` is the tactical-first variant — it reads `.claude/session-data/CURRENT.md` *first*, then chains into this skill for the framework + STATUS load. `/start` is framework-first — it loads STATUS / git log / drift unconditionally, and folds CURRENT.md in only when fresh. Same loaded state at the end either way. Use `/start` as the default; use `/resume-session` only when you know the prior session ran `/save-session` and want the tactical layer prioritized at the top of the synthesis.

## When to invoke

- Always, at the start of every session in this repo.
- After `/clear` when context is wiped.
- After a >2-hour gap mid-day when the operator returns and isn't sure what state things are in.

Phrases the model should treat as `start` triggers (in addition to `/start`): "begin", "hi", "where are we", "what's next", "check AGENTS.md and docs/goal/README.md" (any phrasing), "provide status".

## Workflow

### Step 1 — Read framework context (deterministic, in order)

```bash
# 1. Repo rules
test -f AGENTS.md && head -80 AGENTS.md

# 2. Goal framework rules
test -f docs/goal/README.md && cat docs/goal/README.md

# 3. STATUS — Current Position table + Recent Decisions top 5
awk '/^## Current Position/,/^## Last Completed Milestone/' docs/goal/STATUS.md
awk '/^## Recent Decisions/,/^---/' docs/goal/STATUS.md | head -30

# 4. ROADMAP — current epoch + open items in the current milestone
awk '/^### M[0-9]+\.[0-9]+/,/^### M[0-9]+\.[0-9]+/' docs/goal/ROADMAP.md | head -40

# 5. What actually shipped recently
git log --oneline -8

# 6. Last INSIGHTS entry header (so synthesis can name the most-recent run)
grep -m 1 '^## 20' docs/goal/INSIGHTS.md
```

Use the `Read` tool for any file you need to quote line-by-line; Bash for log + grep + awk slices.

### Step 2 — Drift check (deterministic, best-effort)

```bash
python3 .claude/skills/start/scripts/check_status_drift.py --json 2>/dev/null
```

Parse the JSON output. Each finding shape: `{ severity: "hard" | "soft", field, claim, evidence }`.

- **hard** finding → surface prominently in synthesis under "**Drift warnings**".
- **soft** finding → mention briefly.
- script absent or errored → skip silently; drift check is best-effort, not blocking.

### Step 3 — Tactical handoff (conditional)

```bash
CURRENT=.claude/session-data/CURRENT.md
if [ -f "$CURRENT" ]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$CURRENT") ) / 3600 ))
  if [ "$age_h" -lt 48 ]; then
    echo "--- CURRENT.md (${age_h}h old) ---"
    cat "$CURRENT"
  else
    echo "(CURRENT.md is ${age_h}h old — too stale, ignoring)"
  fi
else
  echo "(no CURRENT.md — STATUS is the authoritative starting point)"
fi
```

If CURRENT.md is missing OR >48h: skip the tactical block; STATUS Current Position + Next Action is the authoritative starting point.

### Step 4 — Synthesize ONE briefing message

≤30 lines total. Five sections in order; **omit any section that has no content** (do not write empty headers).

1. **Where we are** — 2 sentences. Cite current epoch + milestone + active item from STATUS.
2. **What just shipped** — top 3 commits from `git log --oneline`, one line each.
3. **Recent durable decisions** — top 2 dated lines from STATUS § Recent Decisions.
4. **From prior session** *(only when CURRENT.md fresh)* — `working_on` + `next_action` + open `blockers`.
5. **Drift warnings** *(only when check_status_drift surfaced any)* — one line per finding, severity-prefixed.

End with: **"Suggested next move: \<derived from STATUS § Next Action OR first `[ ]` in current milestone\>. Ready to proceed?"** Wait for operator direction.

## Hard rules

1. **Read-only.** Never edit any file. Synthesis is advisory; the operator (or the next skill they invoke) does the writes.
2. **Always read framework context first.** Even when CURRENT.md is fresh — framework + STATUS is authoritative; CURRENT.md is supplementary.
3. **Honest about staleness.** If STATUS `Last Update` is more than 7 days ago, flag: "STATUS is N days old — verify against git log." If CURRENT.md is 24–48h old, flag the age inline.
4. **Terse synthesis.** ≤30 lines output. The point is fast orientation, not re-reading docs verbatim. The operator can `Read` more themselves.
5. **No auto-execution.** Operator must pick a direction before any state-changing tool runs.
6. **Never reorder STATUS / ROADMAP / OPTIMIZE_IDEAS.** Drift findings stay advisory in chat; durable edits route through their owner skill (`goal-audit`, `roadmap-audit`, `autoresearch`).

## Gotchas

- **`AGENTS.md` in this repo is the dev-on-source-repo instruction surface.** The project-level `CLAUDE.md` is for *Builder runtime agents*, not for Claude doing dev work on the builder. The repo `.claude/CLAUDE.md` routes here explicitly. Honor the routing; read AGENTS.md first.
- **STATUS `Current Position` vs `Last Update` can diverge.** Current Position is the *claimed* current item; Last Update is the *actual* most recent change. If they tell a different story, that's a drift signal worth surfacing even before the script runs.
- **`.claude/session-data/CURRENT.md` is gitignored.** Do not warn the operator about it being untracked — that's intentional (machine-local fast-resume; cross-machine continuity rides on STATUS).
- **If `git status` is dirty at session start, surface that early.** Uncommitted work from a prior session that didn't `/save-session` is the highest-priority context to flag; the operator may want to inspect or stash before any new work.
- **Do not auto-invoke `goal-audit` from `start`.** If drift warnings surface, *recommend* `/goal-audit` as a follow-up; let the operator choose. `start` is the entry; goal-audit is its own deliberate cycle.

## Relationship to other skills

| Skill | Relationship |
|---|---|
| [`resume-session`](../resume-session/SKILL.md) | Sister entry skill — reads CURRENT.md tactical block first, then chains into this skill for framework + STATUS load. Both paths converge to the same loaded state. |
| [`save-session`](../save-session/SKILL.md) | Writes `.claude/session-data/CURRENT.md`; `start` Step 3 optionally folds it in. |
| [`goal-audit`](../goal-audit/SKILL.md) | If `start` Step 2 surfaces drift warnings, `goal-audit` is the next-step skill. `start` does not invoke it; the operator does. |
| [`autoresearch`](../autoresearch/SKILL.md) | If STATUS Recent Decisions names an open autoresearch lane (Baseline / Iterate / Fix), `start` mentions it under "Suggested next move" so the operator can pick it up. |
| [`roadmap-audit`](../roadmap-audit/SKILL.md) | If `start` notices the SDK version in INSIGHTS rubric entry differs from current, suggest `roadmap-audit` as a follow-up. |

## Bundled script

- **`scripts/check_status_drift.py`** — read-only drift detector. 4 checks: active-workspace-path-exists, last-update-age, current-item-in-flight-matches-recent-commits, last-INSIGHTS-verdict-not-drifting. Stdlib-only Python; no network. `--json` emits machine-readable output. Exit 0 if all soft / 1 if any hard finding.
