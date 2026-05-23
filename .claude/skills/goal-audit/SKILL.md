---
name: goal-audit
description: "Audit alignment between user intent (extracted from recent Claude Code session transcripts) and the Autonomous Builder docs/goal/ direction, and surface autoresearch focus candidates from Builder CLI signals. Produces a dated entry in docs/goal/INSIGHTS.md and may auto-reorder docs/autoresearch/OPTIMIZE_IDEAS.md when metrics strongly indicate a different priority. Use whenever the user asks 'are we aligned?', 'is the roadmap right?', 'what should we focus on next?', 'review the direction', 'audit goals', 'check progress vs intent', 'is the checklist updated', 'audit autoresearch focus', 'where should autoresearch go next', or after a multi-day work period. Also use proactively when starting work after a >2-day gap or after a major framework change to make sure direction still matches current intent. Reads ~/.claude/projects/ transcripts via the bundled analyzer AND queries builder logs analyze for top_cost_drivers across Builder-runtime sessions. Output is advisory for ROADMAP.md and STATUS.md (you decide); the skill may directly reorder OPTIMIZE_IDEAS.md because that is a living backlog, not a control-owned doc."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash
compatibility:
  - node >= 18  # for scripts/analyze-sessions.mjs
  - python3 >= 3.9  # for scripts/collect.py
  - builder CLI  # optional; if absent, autoresearch signal degrades to session-report heuristics only
---

# Goal Audit

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

Audit alignment between user intent (recent session prompts) and the framework direction (`docs/goal/`). Writes a dated entry to `docs/goal/INSIGHTS.md`; optionally reorders `docs/autoresearch/OPTIMIZE_IDEAS.md`. **Full 7-step workflow loads on demand from [`references/workflow.md`](references/workflow.md).**

## ⚠ HARD RULE — FILES THIS SKILL MUST NEVER EDIT

Before doing anything else, internalize this list. **The skill is advisory for these files. Recommendations go in INSIGHTS.md only. Never call Edit / Write on them, even when a recommendation in INSIGHTS feels obviously correct:**

- `docs/goal/STATUS.md`
- `docs/goal/ROADMAP.md`
- `docs/goal/NORTH-STAR.md`
- `docs/goal/EVALUATION.md`
- `docs/goal/FIX-STANDARD.md`
- `docs/goal/OPERATOR-LANGUAGE.md`
- `docs/goal/TUNING.md`
- `docs/goal/RESUME.md`
- `docs/goal/INDEX.md`
- `docs/goal/README.md`
- `docs/PROMPT.md`

**Why:** these have single control owners (you, the human user). The skill's only edit surfaces are `docs/goal/INSIGHTS.md` (append-only) and `docs/autoresearch/OPTIMIZE_IDEAS.md` (reorder only, per criteria). Drafting "Suggested STATUS.md change: ..." in INSIGHTS is the entire job; applying it is not.

**Self-check before reporting back:** mentally list the files you have edited this run. The list must be a subset of `{INSIGHTS.md, OPTIMIZE_IDEAS.md}`. If it isn't, revert before reporting.

## Purpose

Close the loop between **what the user actually wants** (intent, inferred from recent session prompts) and **what the project framework says we're working on** (`docs/goal/STATUS.md`, `ROADMAP.md`, `NORTH-STAR.md`). Additionally, surface **autoresearch focus candidates** from recurring Builder-runtime cost drivers, and reorder `docs/autoresearch/OPTIMIZE_IDEAS.md` when one item is empirically the highest-leverage next move.

This skill is **advisory** for `ROADMAP.md` and `STATUS.md` (it writes recommendations to `INSIGHTS.md`, not the source files). It is **active** on `OPTIMIZE_IDEAS.md` (it may reorder per a static mapping table — see [`references/reorder-rules.md`](references/reorder-rules.md)).

## When to use

Trigger whenever:

- The user asks meta-direction questions ("are we aligned?", "is the roadmap right?", "what should we focus on?", "where should autoresearch go next?").
- A multi-day gap in work has happened (≥2 days since last meaningful session in this project).
- A major framework change just landed (new milestone closed, new epoch started, structural migration completed).
- The user explicitly invokes via `/goal-audit` or natural language matching the description.

Do NOT trigger for routine status questions ("what's the next item?" — that's a STATUS.md read, not an audit).

## Bundled scripts

This skill is fully self-contained. No external skills or plugins are required.

- **`scripts/collect.py`** — Data collector (Python; uses subprocess + json stdlib only). Runs `analyze-sessions.mjs`, queries `builder` CLI per Builder-related workspace, reads `docs/goal/*` and `docs/autoresearch/OPTIMIZE_IDEAS.md`, emits one consolidated JSON to stdout. Args: `--since`, `--top-sessions`, `--cwd`. See `python3 scripts/collect.py --help` for full usage.
- **`scripts/analyze-sessions.mjs`** — Claude Code transcript analyzer. Vendored from the `session-report` plugin and tailored with `--filter-pattern` (project filter at file-walk time) and `--recent-prompts` (recency-ranked compact prompt list; replaces upstream's token-weighted `top_prompts`). Not invoked directly; called by `collect.py`. See the file header for source attribution and tailoring notes.

External runtime requirements: `node ≥ 18`, `python3 ≥ 3.9`, `builder` CLI (optional — degrades to session-report heuristics only if absent).

## Workflow — load on demand

The full 7-step procedure lives in [`references/workflow.md`](references/workflow.md). One-line summaries:

| Step | What it does |
|---|---|
| 1. Collect data | Run `scripts/collect.py` to produce one consolidated JSON (transcripts + Builder telemetry + framework docs). Supports `--since`, `--dry-run`. |
| 2. Read the data | Inspect the JSON: intent themes from recent prompts, Builder `top_cost_drivers`, framework state (STATUS / ROADMAP). |
| 3. Synthesize the audit | Three sections — A: Intent vs Current Focus · B: Autoresearch Focus Candidates · C: Recommended Actions. |
| 4. Validate the draft | Re-check every claim against the underlying JSON before any file write. No hallucinated metrics. |
| 5. Append to INSIGHTS.md | Append the dated entry. Uses the canonical Run #N template (in workflow.md). |
| 6 / 6.5 / 6.6 | Auto-reorder OPTIMIZE_IDEAS.md (plan → validate → execute) · trim closed actions · compress old entries. |
| 7. Report back + self-schedule | Surface key findings to the user; schedule next run via CronCreate. |

## Reference index — load as needed

| Reference | When to load |
|---|---|
| [`references/workflow.md`](references/workflow.md) | Always — the full procedure for every run. |
| [`references/driver-mapping.md`](references/driver-mapping.md) | At Section B — translates Builder `recommended_next_change` / `avoidable_cost_flags` / `agent_names_with_avoidable_tokens` into OPTIMIZE_IDEAS candidates. |
| [`references/reorder-rules.md`](references/reorder-rules.md) | At Step 6 — the static rules governing when OPTIMIZE_IDEAS.md may be auto-reordered, and the exact reorder mechanics. |
| [`references/gotchas.md`](references/gotchas.md) | When something behaves unexpectedly (collector exit, empty signals, project-filter mismatch, etc.). |

## Notes

- If `builder_signals` is empty for all projects (Builder not initialized anywhere with sessions in scope), Section B uses only session-report heuristics (cache_break clustering, intake-loop length). Mark INSIGHTS with "(session-report only — install Builder workspaces for full autoresearch signal)".
- If the collector exits non-zero, read `/tmp/goal-audit-errors.log`, report the blocker to the user, and do not write a partial INSIGHTS entry.

## Related (read-only references — not dependencies)

- `docs/goal/README.md` — the framework this skill audits against.
- `docs/goal/INSIGHTS.md` — the output file (this skill writes; nothing else does).
- `docs/autoresearch/OPTIMIZE_IDEAS.md` — the only file this skill may auto-modify.

## Related skills

- [`start`](../start/SKILL.md) — owns `check_status_drift.py` consumed by Step 1 here. The drift script is bundled under `start/scripts/` to keep the cheap session-entry path co-located; this skill borrows it.
- [`roadmap-audit`](../roadmap-audit/SKILL.md) — companion skill that closes the inverse loop (KB rubric → ROADMAP → live codebase). Both write to INSIGHTS but on different signals: goal-audit uses transcript intent + Builder telemetry; roadmap-audit uses SDK rubric + grep.
- [`autoresearch`](../autoresearch/SKILL.md) — its OPTIMIZE_IDEAS.md is the only file goal-audit auto-modifies. When this skill reorders the backlog, autoresearch's Iterate lane sees the new top on its next invocation.
- [`knowledge-base`](../knowledge-base/SKILL.md) — when KB REFRESH detects a new SDK rubric version, the rubric-updated marker triggers roadmap-audit, whose INSIGHTS entry then becomes an input to the next goal-audit run.
