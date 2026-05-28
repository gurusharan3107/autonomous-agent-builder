---
name: self-optimize
description: "Analyze recent Claude Code session transcripts and git history to surface recurring mistakes, map each to its root cause and the correct surface to fix it, and apply targeted edits. Use when the operator asks 'what mistakes am I making', 'what keeps going wrong', 'self-optimize', 'analyze recurring issues', 'improve yourself', 'encode learnings from sessions', 'why do I keep correcting you', 'update surfaces for recurring mistakes', 'self-introspect on what went wrong', 'surface recurring patterns', or any variant pairing session analysis / recurring mistakes / self-improvement / surface update / recurring corrections language with execution. Also use proactively at session entry after a >3-day gap when memory contains unresolved correction entries. Reads ~/.claude/projects/ transcripts via scripts/cluster.py (which calls goal-audit's analyze-sessions.mjs) and git log for fix-commit patterns. Clusters corrections into themes with frequency counts, maps each theme to: (a) root cause — missing rule, rule exists but not enforced, or wrong surface; (b) target surface — global CLAUDE.md, local AGENTS.md, specific skill SKILL.md, tests/conftest.py, or workflow doc. Presents ranked findings to the operator, applies only operator-approved edits, and saves learnings to project memory. Full procedure in references/workflow.md."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash, Write, AskUserQuestion
compatibility:
  - node >= 18   # for goal-audit/scripts/analyze-sessions.mjs
  - python3 >= 3.9  # for scripts/cluster.py
  - git  # for correction-commit pattern analysis
---

# self-optimize — surface recurring mistakes and encode fixes

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

Closes the loop between operator corrections and the agent surfaces that govern behavior. Analyzes session transcripts + git fix-commit patterns, clusters recurring mistake themes, maps each to the right surface to update, and applies approved edits in one operator-approved pass. **Full procedure:** [`references/workflow.md`](references/workflow.md).

## Entry

No lane selection needed — single linear flow. First action is always `AskUserQuestion` for the analysis window:

```
question: "How far back should I analyze sessions?"
header:   "Window"
options:
  - "7d"  — last week; fast; catches recent drift
  - "14d" — two weeks; good default
  - "30d" — full picture; use after a long work period or major change
```

## Preflight

1. Confirm `node --version` returns >= 18.
2. Confirm analyzer exists: `ls .claude/skills/goal-audit/scripts/analyze-sessions.mjs`
3. Confirm git is available and the working directory is a repo: `git rev-parse --show-toplevel`
4. Confirm project memory directory exists (used for step 6 memory writes).

Abort with a clear message if any precondition fails.

## Do — summary (full commands in references/workflow.md)

| Step | What |
|---|---|
| 1. Collect | Run `analyze-sessions.mjs --json --since <window>` + `git log` → write to `/tmp/self-optimize-session.json` |
| 2. Cluster | Run `scripts/cluster.py /tmp/self-optimize-session.json` → ranked theme table with counts and example prompts |
| 3. Map | For each theme: root cause (missing / exists-not-enforced / wrong-surface) + single target surface |
| 4. Present | Show ranked table to operator; `AskUserQuestion` — which themes to act on |
| 5. Edit | For each approved theme: make the targeted edit to the named surface |
| 6. Memory | Append new learnings to project memory (one file per learning) |
| 7. Closeout | `./scripts/validate.sh`; grep-verify edits landed |

## Hard rules

1. **Operator approves every surface edit.** Present findings first. Never modify AGENTS.md, CLAUDE.md, or any skill SKILL.md without explicit operator approval for that specific theme.
2. **Root cause, not symptom.** If the rule already exists in a surface but is still violated, the fix is a mechanical enforcement gate — not a duplicate rule. Adding the same rule twice creates noise.
3. **One surface per theme.** Pick the single highest-impact surface. The priority order is: skill SKILL.md (if the mistake happens inside a skill run) → local AGENTS.md (repo-wide dev rule) → global CLAUDE.md (universal doctrine). Tests/conftest.py for test-isolation gaps.
4. **Memory writes are additive only.** Never delete or overwrite existing memory entries. Append new files; update MEMORY.md index.
5. **Validate after edits.** Run `./scripts/validate.sh` before closing out.

## Cross-references

- [`references/workflow.md`](references/workflow.md) — full step-by-step procedure with exact commands
- [`scripts/cluster.py`](scripts/cluster.py) — deterministic theme clustering (session JSON + git log → ranked JSON)
- [`scripts/validate.sh`](scripts/validate.sh) — self-validation wrapper
- `.claude/skills/goal-audit/scripts/analyze-sessions.mjs` — session transcript analyzer (required dependency)
- Project memory dir — write target for step 6

## Why this skill exists

Without this skill, recurring operator corrections stay as conversations that evaporate. The agent fixes the immediate issue but the pattern isn't encoded, so the same mistake reappears next session. This skill makes recurring corrections durable: one operator-approved pass turns session analysis into targeted surface edits and memory entries that load automatically in future sessions.
