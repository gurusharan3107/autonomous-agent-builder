---
name: roadmap-audit
description: "Revalidate docs/goal/ROADMAP.md against the latest Claude Agent SDK rubric (via `workflow knowledge`) AND the live codebase (via grep src/), then append a verdict to docs/goal/INSIGHTS.md and edit ROADMAP.md with codebase-validated additions. Codebase validation is the non-obvious step: it stops the skill from recommending SDK levers that are already adopted (the prior ad-hoc rubric review recommended G8 `AskUserQuestion` which was already mature in `agent_tool_policy.py` + `agents/definitions.py`). Use this skill whenever the user asks 'revalidate the roadmap', 'audit the roadmap against SDK best practices', 'what SDK levers are we missing?', 'cross-check the roadmap with the rubric', 'is the roadmap aligned with current SDK?', or any variant that pairs ROADMAP and SDK/rubric/best-practice/feature-gap language. ALSO use proactively after every Claude Agent SDK minor release (signature surface shifts between 0.2.x versions), after a `knowledge-base` refresh that touched `claude-agent-sdk-rubric`, or when INSIGHTS gains a new ad-hoc rubric-style entry that has not yet been codebase-grounded. Complements `goal-audit` (transcript→intent→roadmap) and `knowledge-base` (SDK upstream→KB rubric) without overlapping — this is the inverse direction (KB rubric → ROADMAP → live codebase)."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash
compatibility:
  - python3 >= 3.9
  - workflow CLI at ~/.claude/bin/workflow.py (invoked as `python3 ~/.claude/bin/workflow.py` because the `workflow` shim hard-codes `python` and many WSL/Linux boxes have only `python3`)
  - ripgrep or grep available on PATH
  - ctx7 CLI on PATH (for SDK signature pre-checks cited in each ROADMAP addition)
---

# ROADMAP ↔ SDK Rubric Audit

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

Revalidate `docs/goal/ROADMAP.md` against the latest Claude Agent SDK rubric AND the live codebase, then append a verdict to `docs/goal/INSIGHTS.md`. **Full 10-step workflow loads on demand from [`references/workflow.md`](references/workflow.md).**

## ⚠ HARD RULE — FILES THIS SKILL MUST NEVER EDIT

Internalize this list before any tool call. The skill is **active** on `docs/goal/ROADMAP.md` and `docs/goal/INSIGHTS.md` only. Every other file in `docs/goal/` has a single human control owner; recommendations that touch them go in the INSIGHTS verdict, not in those files:

- `docs/goal/STATUS.md`
- `docs/goal/NORTH-STAR.md`
- `docs/goal/EVALUATION.md`
- `docs/goal/FIX-STANDARD.md`
- `docs/goal/OPERATOR-LANGUAGE.md`
- `docs/goal/TUNING.md`
- `docs/goal/RESUME.md`
- `docs/goal/INDEX.md`
- `docs/goal/README.md`
- `docs/IMPROVEMENTS.md`
- `docs/SPRINT-PROGRESS.md`
- `docs/PROGRESS.md`
- `docs/PROMPT.md`
- any file in `src/` (the skill *reads* the codebase via grep — never edits it)

**Why ROADMAP is editable here but not in `goal-audit`:** `goal-audit` derives recommendations from transcript intent, which is subjective. This skill derives recommendations from the cross-product of `workflow knowledge` (objective, dated KB) and `grep src/` (objective, current code state). Drift between those two surfaces is mechanical, not strategic — encoding the closure into the skill is safe.

**Self-check before final report:** the list of files you edited this run must be a subset of `{ROADMAP.md, INSIGHTS.md}`. If it isn't, revert before reporting.

## Purpose

The Claude Agent SDK ships hundreds of options, callbacks, and message types. A coding agent reads the rubric and notices ten "we should be using that" levers per pass. The trap: half of them are already adopted somewhere in `src/`, and recommending them anyway burns user attention and pollutes the ROADMAP backlog with phantom work. The other half are real gaps — but without a codebase check, the rationale ("Current state: …") is guessed instead of cited.

This skill closes that loop deterministically:

1. Pull the canonical SDK rubric from `workflow knowledge` (always the latest, never hardcoded).
2. Walk it lever-by-lever, asking the rubric "do we use this?" *as a grep against `src/`*, not as a vibe check.
3. Bucket each candidate: **confirmed-missing** → add to ROADMAP; **already-present** → withdraw; **partial** → narrow the recommendation and cite the existing implementation by `path:line`.
4. Separately audit closed `[x]` items for SDK-debt — but only flag the debt if no pending `[ ]` item already covers the same lever, since re-opening covered ground is noise.
5. Append a structured verdict entry to INSIGHTS with the full validation table.

The validation table is the durable artifact: even if the skill is re-run a week later, the prior entry shows exactly what was checked, what was added, and what was deliberately withdrawn.

## When to use

Trigger whenever:

- The user asks meta-direction questions that pair ROADMAP with SDK terminology: "revalidate the roadmap", "audit roadmap vs SDK", "what SDK features are we not using?", "cross-check the rubric against the roadmap", "is the roadmap behind on SDK best practices?".
- A `knowledge-base` refresh just modified the `claude-agent-sdk-rubric` article (the rubric is the input — when it changes, the audit is stale).
- A Claude Agent SDK minor version landed (`0.2.85 → 0.2.86+`) and the prior audit was against the older version.
- INSIGHTS gains a new ad-hoc rubric-style entry (manual, not from `goal-audit`) that the author didn't codebase-ground. Re-run this skill to ground it.

Do NOT trigger for:

- Routine intent/alignment questions ("are we aligned?", "what's next?") — that's `goal-audit`.
- Pulling new SDK features INTO the KB — that's `knowledge-base` (`refresh` operation).
- Implementing one specific item from the ROADMAP — that's normal development work; the skill's output is the input to that work, not a substitute for it.

## Workflow — load on demand

The full procedure lives in [`references/workflow.md`](references/workflow.md). One-line summaries of each step:

| Step | What it does |
|---|---|
| **0. SDK-delta early-exit gate** | If rubric hasn't changed since last audit AND no new SDK minor → skip the rest. Cheapest path. |
| 1. Bootstrap | Find the latest rubric slug via `workflow knowledge search`, read it. Never hardcode the date. |
| 2. Build the candidate list | Walk the rubric lever-by-lever, build the candidate-missing list. |
| 3. Codebase validation (the core step) | For each candidate, grep `src/` for exact SDK identifiers / hook registrations / config keys. Adoption ≠ a docstring mention. |
| 4. Completed-item SDK-debt audit | Separate pass: closed `[x]` items where the SDK-native lever would be cleaner. Only flag if no pending `[ ]` already covers it. |
| 5. Map confirmed-missing to milestones | Match each gap to the right milestone in ROADMAP.md. |
| 6. Edit ROADMAP.md | Add new `[ ]` items with rationale + `ctx7 docs` pre-check + grep citation. |
| 7. Append INSIGHTS verdict | Structured entry with full validation table — confirmed-missing, withdrawn, partial. |
| 8. Final report | Surface the changes to the operator with diff-summary. |
| 9. Self-schedule heartbeat fallback | 60-day cron via CronCreate as a backstop if KB-cadence triggers don't fire. |

## Output examples

The canonical reference is the INSIGHTS entry at `docs/goal/INSIGHTS.md` titled "2026-05-22 — Codebase-grounded revalidation of the ad-hoc rubric pass" (added by commit `2613dc6`), and the ROADMAP additions in the same commit. Open them before drafting a new run's output — they show the exact shape, tone, and level of grep-citation expected.

## Reference index — load as needed

| Reference | When to load |
|---|---|
| [`references/workflow.md`](references/workflow.md) | At the start of every run — the full 10-step procedure. |
| [`references/failure-modes.md`](references/failure-modes.md) | Read once before drafting; lists the 6 real mistakes made in the unvalidated ad-hoc review (recommending pre-grep, counting docstrings as adoption, re-opening closed items, hardcoded rubric date, missing `ctx7 docs` pre-req, editing forbidden files). |

## Compatibility notes

- **`workflow` shim on Linux/WSL:** the global `workflow` shim hardcodes `python` which is often absent. Always invoke as `python3 ~/.claude/bin/workflow.py <subcommand>` from this skill.
- **`grep` vs `rg`:** either works. If `rg` is available, prefer it for speed on large `src/` trees. The workflow uses plain `grep -rn` for portability.
- **Without `workflow knowledge`:** abort. The rubric is the input; there is no fallback that's safe enough to ship a ROADMAP edit from.
