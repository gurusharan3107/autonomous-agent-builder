---
name: self-optimize
description: "Analyze recent Claude Code session transcripts and git history to surface recurring mistakes, map each to its root cause and the correct surface to fix it, and apply targeted edits. Use when the operator asks 'what mistakes am I making', 'what keeps going wrong', 'self-optimize', 'analyze recurring issues', 'improve yourself', 'encode learnings from sessions', 'why do I keep correcting you', 'update surfaces for recurring mistakes', 'self-introspect on what went wrong', 'surface recurring patterns', or any variant pairing session analysis / recurring mistakes / self-improvement / surface update / recurring corrections language with execution. Also use proactively at session entry after a >3-day gap when memory contains unresolved correction entries. Reads ~/.claude/projects/ transcripts via scripts/cluster.py (which calls goal-audit's analyze-sessions.mjs) and git log for fix-commit patterns. Clusters corrections into themes with frequency counts, maps each theme to: (a) root cause — missing rule, rule exists but not enforced, or wrong surface; (b) target surface — global CLAUDE.md, local AGENTS.md, specific skill SKILL.md, tests/conftest.py, or workflow doc. Presents ranked findings to the operator, applies only operator-approved edits, and saves learnings to project memory. Also handles content-targeted 'where did the agent hit <failure X>' asks (browser-testing errors, rollback exceptions, tool failures) via scripts/mine_sessions.py, which mines agent-side evidence (assistant prose + tool_result errors) rather than operator prompts. Full procedure in references/workflow.md."
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

First action is always `AskUserQuestion` for the analysis window:

```
question: "How far back should I analyze sessions?"
header:   "Window"
options:
  - "7d"  — last week; fast; catches recent drift
  - "14d" — two weeks; good default
  - "30d" — full picture; use after a long work period or major change
```

### Two query shapes — pick the lane from the ask

| If the ask is… | Lane | Tool |
|---|---|---|
| "what mistakes am I making / why do I keep correcting you / recurring corrections" (default) | **operator-correction clustering** | `scripts/cluster.py` (mines `recent_prompts` = operator words) |
| "where did the agent hit `<failure X>`" — content-targeted mining of agent-side failures (browser-testing errors, rollback exceptions, tool failures) | **agent-failure mining** | `scripts/mine_sessions.py` (mines assistant prose + `tool_result` errors) |

Default to the clustering lane. Switch to (or add) the mining lane when the operator names a specific failure pattern to hunt. The lanes compose — clustering for "what corrections recur", mining for "where exactly did failure-type X occur".

## Preflight

1. Confirm `node --version` returns >= 18.
2. Confirm analyzer exists: `ls .claude/skills/goal-audit/scripts/analyze-sessions.mjs`
3. Confirm git is available and the working directory is a repo: `git rev-parse --show-toplevel`
4. Confirm project memory directory exists (used for step 6 memory writes).

Abort with a clear message if any precondition fails.

## Do — summary (full commands in references/workflow.md)

| Step | What |
|---|---|
| 1. Collect | **Clustering lane:** run `analyze-sessions.mjs --json --since <window>` + `git log` → write to `/tmp/self-optimize-session.json`. **Mining lane:** run `scripts/mine_sessions.py --preset <name> --since <window>` (reads transcripts directly — do NOT route content mining through the aggregate). |
| 2. Cluster / Mine | **Clustering:** `scripts/cluster.py /tmp/self-optimize-session.json` → ranked theme table. **Mining:** the `mine_sessions.py` JSON IS the result — deduped, top-N-capped findings + `project_counts_top10`. Use `--project-filter` to scope, `--errors-only` for tool-result errors. |
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
6. **Never load the aggregate to mine content; never dump unbounded scans.** `analyze-sessions.mjs` output is a ~900KB / ~236K-token token/cache-metrics aggregate — `cluster.py` reads only `recent_prompts` from it, so never `cat` the blob into context. For "where did failure X happen", use `mine_sessions.py` (reads transcripts directly, parses by message structure, dedups, caps to `--limit`). Match against extracted **prose**, never raw lines — raw greps hit tool-call params (`"timeout":30000`) and harness strings (`Shell cwd was reset`). Cap any ad-hoc scan dump to top-N; never emit a full per-project Counter.

## Cross-references

- [`references/workflow.md`](references/workflow.md) — full step-by-step procedure with exact commands
- [`scripts/cluster.py`](scripts/cluster.py) — deterministic theme clustering of operator prompts (session JSON + git log → ranked JSON)
- [`scripts/mine_sessions.py`](scripts/mine_sessions.py) — structural content-miner for agent-side failures (assistant prose + `tool_result` errors → deduped, capped findings). Complement to cluster.py; `--preset browser_testing` curated, or `--pattern REGEX`.
- [`scripts/validate.sh`](scripts/validate.sh) — self-validation wrapper
- `.claude/skills/goal-audit/scripts/analyze-sessions.mjs` — session transcript analyzer (required dependency)
- Project memory dir — write target for step 6

## Why this skill exists

Without this skill, recurring operator corrections stay as conversations that evaporate. The agent fixes the immediate issue but the pattern isn't encoded, so the same mistake reappears next session. This skill makes recurring corrections durable: one operator-approved pass turns session analysis into targeted surface edits and memory entries that load automatically in future sessions.
