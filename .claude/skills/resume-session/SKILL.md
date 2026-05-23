---
name: resume-session
description: "Synthesize 'here's where you left off' at session start by reading `.claude/session-data/CURRENT.md` (tactical context from prior session's `save-session`) + `docs/goal/STATUS.md` Current Position + recent git log. Triggers: `/resume-session`, 'resume session', 'continue where I left off', 'pick up where we left off'. Reports state in one message and waits for operator direction. Does NOT auto-execute. Project-local counterpart to `save-session`."
allowed-tools: Bash, Read
---

# resume-session — pick up where the last session stopped

Three sources of truth, each carries a different layer:

| Source | Layer | What it tells you |
|---|---|---|
| `.claude/session-data/CURRENT.md` | Tactical | Current intent, next action, blockers, mid-session learnings. Written by [`save-session`](../save-session/SKILL.md). |
| `docs/goal/STATUS.md` Current Position + Recent Decisions | Strategic | Milestone, in-flight item, evidence pointers, recent durable decisions. |
| `git log --oneline -5` | Audit | What actually shipped recently. |

## When to invoke

Operator says `/resume-session`, "resume session", "continue where I left off", "pick up where we left off". Also reasonable on `/clear` recovery when the operator wants to restore context fast.

## What to do

1. Read the three sources (Bash for git log; Read tool for the two files).
2. If `CURRENT.md` doesn't exist, say so plainly — fall back to STATUS Current Position + git log only.
3. Synthesize ONE message with five sections:
   - **Where you left off** — pull from `CURRENT.md.working_on` (or STATUS Current Position if CURRENT missing).
   - **Next action** — verbatim from `CURRENT.md.next_action`.
   - **Blockers** — if any; otherwise omit the section.
   - **Recent commits** — 3 lines of `git log --oneline`.
   - **Mid-session learnings worth remembering** — if any; otherwise omit.
4. End with: "Ready to proceed?" — wait for operator confirmation. Do **not** auto-execute the next action.

## Hard rules

1. **No auto-execution.** This skill is a context-restore briefing, not a kickoff. Operator must say "go" before any tool runs that changes state.
2. **Terse synthesis.** ≤25 lines total output. The point is fast re-orientation, not a re-read of CURRENT.md verbatim.
3. **Honest about staleness.** If `CURRENT.md.time` is more than 48h old, flag it: "checkpoint is N days old — STATUS.md and git log are more authoritative on what's current."
4. **No writes.** This skill reads only. If the operator's next move warrants updating CURRENT.md, that's [`save-session`](../save-session/SKILL.md)'s job at the end of the new session.

## Counterpart

[`save-session`](../save-session/SKILL.md) writes `.claude/session-data/CURRENT.md` for this skill to read.
