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
- `docs/IMPROVEMENTS.md`
- `docs/SPRINT-PROGRESS.md`
- `docs/PROGRESS.md`
- `docs/PROMPT.md`

**Why:** these have single control owners (you, the human user). The skill's only edit surfaces are `docs/goal/INSIGHTS.md` (append-only) and `docs/autoresearch/OPTIMIZE_IDEAS.md` (reorder only, per criteria). Drafting "Suggested STATUS.md change: ..." in INSIGHTS is the entire job; applying it is not.

**Self-check before Step 7:** before reporting back to the user, mentally list the files you have edited this run. The list must be a subset of `{INSIGHTS.md, OPTIMIZE_IDEAS.md}`. If it isn't, revert before reporting.

## Purpose

Close the loop between **what the user actually wants** (intent, inferred from recent session prompts) and **what the project framework says we're working on** (`docs/goal/STATUS.md`, `ROADMAP.md`, `NORTH-STAR.md`). Additionally, surface **autoresearch focus candidates** from recurring Builder-runtime cost drivers, and reorder `docs/autoresearch/OPTIMIZE_IDEAS.md` when one item is empirically the highest-leverage next move.

This skill is **advisory** for `ROADMAP.md` and `STATUS.md` (it writes recommendations to `INSIGHTS.md`, not the source files). It is **active** on `OPTIMIZE_IDEAS.md` (it may reorder per a static mapping table — see § Autoresearch reorder rules).

## When To Use

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

External runtime requirements:

- `node` ≥ 18 (for `analyze-sessions.mjs`)
- `python3` ≥ 3.9 (for `collect.py`)
- `builder` CLI (optional — if absent, autoresearch signal degrades to session-report heuristics only)

## Workflow

### Step 1 — Collect data

Run the bundled collector. Paths are relative to the skill directory root; the agent runs commands from there.

```bash
# Full window (default — use for first run of a session or after a gap)
python3 scripts/collect.py --since 7d > /tmp/goal-audit-data.json 2>/tmp/goal-audit-errors.log

# Delta since last run (use when re-running within the same day)
python3 scripts/collect.py --since-run > /tmp/goal-audit-data.json 2>/tmp/goal-audit-errors.log
```

`--since` accepts `24h`, `7d`, `30d`, `all`, or an ISO timestamp. Default is 7d. Honor a different range if the user passes one (e.g. "audit the last month" → `--since 30d`).

`--since-run` reads the `<!-- collected_at: ... -->` comment from the last INSIGHTS.md entry and passes it as `--since`. Use this when running a follow-up audit in the same session — it shows only new signal since the last entry rather than re-analyzing the full window. Falls back to `7d` if no prior entry exists. The output JSON includes `"since_run_mode": true` when this flag was active.

The collector must be run from the project root so it can read `docs/goal/*` and `docs/autoresearch/OPTIMIZE_IDEAS.md`. If invoked from elsewhere, prefix with `cd <project-root> && ` or pass `--cwd <project-root>`.

If the script exits non-zero, read `/tmp/goal-audit-errors.log` and report the blocker to the user. Do not proceed with partial data unless explicitly told to.

### Dry-run mode (preview without writing)

If the user says "dry run", "preview", "show me what you would write", or invokes with `--dry-run` semantics: complete Steps 1-5 (collect, read, synthesize, validate), but in Step 5+ **print the draft INSIGHTS entry to chat instead of using Edit on the file**, and skip Step 6 (OPTIMIZE_IDEAS reorder) entirely. The user reviews the dry-run output and re-invokes without `--dry-run` if they want to commit.

### Step 2 — Read the data

```bash
cat /tmp/goal-audit-data.json
```

Key fields:

| Field | Use for |
| --- | --- |
| `session_report.overall` | Headline stats (sessions, hours, tokens, cache_breaks count) |
| `session_report.by_project` | Project attention distribution — does it match where STATUS says we're working? |
| `session_report.recent_prompts[]` | **Primary intent signal.** Recency-ranked human prompts (compact form: `ts`, `text`, `project`, `session`, `total_tokens`, `api_calls`). Scan top entries to see what the user is currently pushing on. Token weight is NOT a ranking key here — short recent prompts surface alongside heavy ones. |
| `session_report.cache_breaks[]` | **Pivot signal.** High-uncached prompts that broke cache prefix — usually meta-direction questions. Includes surrounding `context` array. |
| `builder_signals.<project>.analyze[]` | Per-session Builder runtime evidence: `top_cost_drivers` (per-agent), `recommended_next_change` (str), `optimization_decision.avoidable_cost_flags` (list of named flags), `cache_ratio`, `noncached_plus_output_tokens`. |
| `aggregated_drivers` | **The autoresearch signal.** Three streams: `recommended_next_change` (str→count), `avoidable_cost_flags` (flag→{sessions, workspaces, examples}), `agent_names_with_avoidable_tokens` (agent→{sessions,...}). Match against the § Driver-to-idea mapping table. |
| `goal_snapshot.STATUS.md` etc. | Current claimed state — compare against actual session activity. |

Also read `docs/goal/INSIGHTS.md` (the file the skill appends to) to see prior insights — do not repeat findings already in the last entry unless they regressed.

### Step 3 — Synthesize the audit

Produce three sections, in this order. Be specific, cite evidence, no theatre.

#### Section A — Intent vs Current Focus

Compare:
- `recent_prompts` (scan top ~30 by recency) and `cache_breaks` (pivot moments) — what the user has actually been pushing on, AND
- `STATUS.md` Current Position (current epoch, current milestone, current item in flight)

Look for:
- **Topic shift**: prompts cluster on topic X but STATUS says we're working on Y.
- **Quiet drift**: STATUS hasn't been updated in N sessions; the user has been doing meta-work (auditing, refactoring framework) that isn't on the roadmap.
- **Misalignment in project attention**: STATUS says devpulse is the active workspace, but `by_project` shows 80% of token time was in the source repo.

Write 2-5 observations. Each cites at least one specific prompt or metric as evidence (with timestamp and session id).

End the section with one explicit verdict: `aligned` / `drifting` / `ambiguous`.

If `drifting` or `ambiguous`, propose **specific** STATUS.md and ROADMAP.md edits (as text, not as auto-applied changes).

#### Section B — Autoresearch Focus Candidates

Use the pre-aggregated `aggregated_drivers` object in the collector output. It has three independent streams; check each against the § Driver-to-idea mapping table.

Build one row per matching signal:

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | (e.g. `truncate_tool_output_before_reinjection`) | N | item Y |
| avoidable_cost_flags | (e.g. `large_command_output`) | N | item Y |
| agent_names_with_avoidable_tokens | (e.g. `code-gen`) | N | item Y |

For any row with `sessions ≥ 3` AND a single-item mapping, treat it as a strong candidate for promotion (see § Autoresearch reorder rules).

Side-note from `session_report.cache_breaks`: if cache_breaks > 100K cluster around a single runtime lane, that's a cache-strategy concern (mappable to OPTIMIZE_IDEAS idea 10). Treat as advisory only — never auto-reorder for this signal because it's a heuristic, not Builder-runtime evidence.

If `aggregated_drivers.recommended_next_change` is dominated by `maintain_current_flow` AND `avoidable_cost_flags` and `agent_names_with_avoidable_tokens` are both empty, the Builder system is operating cleanly. State this explicitly: "no autoresearch action — system stable" and end Section B there.

End the section with a recommendation: which OPTIMIZE_IDEAS items should sit at top of the backlog, with cited evidence.

#### Section C — Recommended Actions

Before writing any action, **cross-check ROADMAP.md**:

1. Read `goal_snapshot.ROADMAP.md` (already in the collector output).
2. For each candidate action you are about to recommend, scan ROADMAP.md for a matching `[ ]` or `[x]` item:
   - If a matching `[x]` item exists → the action is already done. Do NOT recommend it. Note it as "closed in ROADMAP.md" in the Section A or C prose if it's evidence of progress.
   - If a matching `[ ]` item exists → the action is already tracked. Do NOT recommend it as a new action. You may say "already tracked as ROADMAP.md § MX.Y — no new action needed" to confirm it's visible.
   - If no matching item exists → the action is a genuine gap. Recommend it and note it is not yet on the roadmap.
3. Also scan the last INSIGHTS.md entry's Recommended Actions for items that were acted on since that run. Call them out explicitly as closed — this makes the INSIGHTS→ROADMAP lifecycle visible.

Concrete and scoped. Each item is a single sentence with the rationale. Examples:

- "Move OPTIMIZE_IDEAS item 6 (cap tool-output reinjection) to position 1 — `large_command_output` recurred in 4 of 5 recent Builder sessions."
- "Update STATUS.md Current Position to reflect actual focus — devpulse validation has been paused for 3 days while framework migration happened; STATUS still says M1.1 is in flight."
- "No ROADMAP changes needed this audit — Codex lane is already tracked as M1.2 `[ ]` item."
- "Banned-term audit (M2.4) shows fresh signal — operator typed 'recover' twice this week against a non-functional Recover button. Not yet on ROADMAP; promote in priority over decomposition (M1.3)."

3-7 actions max. If there are no actions worth recommending, say so explicitly.

### Step 4 — Validate the draft against the data (before any file write)

Before calling Edit on INSIGHTS.md, self-check the draft against the collector JSON:

- Every observation in Section A must cite at least one specific prompt or metric from `session_report.recent_prompts` or `session_report.cache_breaks` (with timestamp and session id). If any observation lacks evidence, delete it or find evidence.
- Section B's driver table must match the `aggregated_drivers` counts from the collector JSON exactly. If you cannot find a driver in the JSON, do not list it.
- The alignment verdict must be `aligned` if Section A has no observations naming a mismatch — do not manufacture drift to feel useful.
- If `aggregated_drivers.recommended_next_change` is dominated by `maintain_current_flow` and the other two driver streams are empty, Section B's verdict is "no autoresearch action — system stable" and Section C must not propose autoresearch changes.

Only after these checks pass, proceed to Step 5.

### Step 5 — Append the validated entry to INSIGHTS.md

The output goes to `docs/goal/INSIGHTS.md` as a new dated entry. Use the Edit tool to append; do not rewrite the file.

Format (exact structure):

```markdown
## YYYY-MM-DD — Run #N (since X, M Builder-related sessions analyzed)
<!-- collected_at: {collected_at from the collector JSON} -->

### Intent vs current focus

- (Observation with evidence)
- (Observation with evidence)
- ...

**Alignment verdict:** aligned | drifting | ambiguous

**Suggested STATUS.md change:** (text or "none")

**Suggested ROADMAP.md change:** (text or "none")

### Autoresearch focus candidates

| Driver | Sessions in scope | OPTIMIZE_IDEAS map |
| --- | --- | --- |
| (driver) | N | item Y |

**OPTIMIZE_IDEAS.md actions taken:** (list of reorders applied, or "none")

### Recommended actions

1. ...
2. ...
```

`N` = index from prior entries (count of `## ` entries in INSIGHTS.md + 1).

`M Builder-related sessions analyzed` = count of `session_report.by_project[*].sessions` summed.

### Step 6 — Auto-reorder OPTIMIZE_IDEAS.md (plan → validate → execute)

This step uses a three-substep loop to prevent accidental reorders:

**Substep 6a — Plan.** Inspect all three streams in `aggregated_drivers`: `recommended_next_change`, `avoidable_cost_flags`, `agent_names_with_avoidable_tokens`. For each entry with `sessions ≥ 3` (or count ≥ 3 for `recommended_next_change`):

1. Look up the value in the § Driver-to-idea mapping table.
2. If the mapping is to a single OPTIMIZE_IDEAS item (not multiple — entries tagged "multi-item — advisory only" do NOT enter the reorder plan), record it as a candidate.
3. Build a plan list: `[{stream, value, sessions, target_idea, current_position}]`.

`recommended_next_change` `maintain_current_flow` is explicitly NOT a candidate — it means "no change needed."

**Substep 6b — Validate.** For each candidate in the plan, check ALL of the § Autoresearch reorder rules:

| Rule | Check |
| --- | --- |
| Single-item mapping | Mapping is to one OPTIMIZE_IDEAS item, not multiple |
| Recurrence threshold | `sessions ≥ 3` |
| Not already top | `current_position > 1` |
| Not previously attempted | The target item's section has `Attempts: none` in OPTIMIZE_IDEAS.md |

Drop any candidate that fails any rule. Note the rejection reason in INSIGHTS.md.

**Substep 6c — Execute.** For each surviving candidate, use Edit to:

1. Add a comment line above the target item:
   ```markdown
   <!-- moved to position 1 by goal-audit on YYYY-MM-DD: driver "<name>" recurred in N sessions -->
   ```
2. Move the item's section to position 1 (before the current item 1).
3. Renumber the `## N.` headers in the file so they are sequential.

Never delete an idea. Only reorder. The user can revert by inspecting the comment.

If no candidates survive validation, this step is a no-op — record "no OPTIMIZE_IDEAS reorder applied" in INSIGHTS.

### Step 7 — Report back to the user

In your conversation reply (not in the files), summarize:
- Path to the new INSIGHTS.md entry.
- Headline alignment verdict.
- Whether OPTIMIZE_IDEAS.md was reordered (and which item moved).
- Top 1-3 recommended actions in one line each.

Keep it under 10 lines. The file is the durable record; chat is the pointer.

## Driver-to-idea mapping (static)

Apply this table against the three streams in `aggregated_drivers`. The first column names the stream + value; the second names the target OPTIMIZE_IDEAS item.

### Stream 1 — `recommended_next_change` (one value per session)

| Value | OPTIMIZE_IDEAS item(s) |
| --- | --- |
| `truncate_tool_output_before_reinjection` | 6 (cap tool-output reinjection) |
| `reduce_agent-chat_raw_tokens` | 1+2 (multi-item — advisory only, no auto-reorder) |
| `bounded_retrieval_shortcut` | 4+5 (multi-item — advisory only) |
| `maintain_current_flow` | no autoresearch action — record "system stable" in INSIGHTS |

### Stream 2 — `avoidable_cost_flags` (zero-or-more flags per session)

| Value | OPTIMIZE_IDEAS item(s) |
| --- | --- |
| `large_command_output` | 6 |
| `chunk_pressure_large_event` | 6 |
| `chunk_pressure_risk_large_event` | 6 |
| `repeated_retrieval` | 4+5 (multi-item — advisory only) |
| `repeated_scan` / `redundant_scan` | 4+5 (multi-item — advisory only) |
| `phase_ceremony_oversize` / `phase_ceremony_tokens` | 7 (delete inactive phase-context) |
| `gate_feedback_oversize` / `gate_feedback_oversized` | 9 (compact gate feedback) |
| `intake_loop_length` (heuristic from session-report: ≥3 intake prompts before first ship) | 3 (AskUserQuestion for intake) |

### Stream 3 — `agent_names_with_avoidable_tokens` (zero-or-more per session)

These are agent names from `top_cost_drivers` where `avoidable_token_estimate > 0`. Per-agent attribution doesn't always map cleanly to a single OPTIMIZE_IDEAS item; treat as diagnostic unless the same agent recurs.

| Agent name | OPTIMIZE_IDEAS item(s) (only when `sessions ≥ 3`) |
| --- | --- |
| `code-gen` | 8 (subagent for code-gen) |
| `agent-chat` | 1+2 (multi-item — advisory only) |
| `optimization-agent` | (no idea — usually a Builder ownership boundary issue, surface in INSIGHTS) |
| (other) | (unmapped — surface in INSIGHTS and propose adding to this table) |

### Heuristic signals from session_report (not in aggregated_drivers)

| Heuristic | OPTIMIZE_IDEAS item |
| --- | --- |
| `session_report.cache_breaks_over_100k > 5` clustering on a single runtime lane | 10 (cache header per-runtime-lane) — *advisory*, never auto-reorder |

If a value appears in any stream that is not in this table, record it in INSIGHTS § Section B as `(unmapped)` and propose adding it to this table under § Recommended actions.

## Autoresearch reorder rules

The skill MAY edit `docs/autoresearch/OPTIMIZE_IDEAS.md` when ALL of the following hold:

1. **A single driver maps to a single OPTIMIZE_IDEAS item.** If a driver maps to multiple items (e.g. `reduce_agent-chat_raw_tokens` → 1+2), do not auto-reorder — leave it as a recommendation in INSIGHTS only.
2. **The driver appeared in ≥3 Builder-runtime sessions in scope.** Lower than 3 = noise.
3. **The mapped OPTIMIZE_IDEAS item is not already at position 1.** If it's already top, no action needed.
4. **The item has `Attempts: none` in OPTIMIZE_IDEAS.md.** Never re-promote an already-attempted item without explicit user direction.

When all four hold:
- Move the mapped item to position 1 (cut the section and paste at top, before existing item 1).
- Add the timestamped reorder comment above the moved item.
- Re-number items in the file if the existing numbers (`## 1.`, `## 2.`, ...) need updating.
- Note the reorder in INSIGHTS.md § Autoresearch focus candidates → OPTIMIZE_IDEAS.md actions taken.

The skill never:
- Deletes ideas.
- Edits ROADMAP.md, STATUS.md, NORTH-STAR.md, EVALUATION.md, FIX-STANDARD.md, OPERATOR-LANGUAGE.md, TUNING.md, RESUME.md, INDEX.md, README.md.
- Removes the reorder comment from a prior run.

## Gotchas

These are specific traps the model will fall into without being told. They are the highest-value content in this skill.

- **`maintain_current_flow` is a healthy signal, not an absence of data.** When `aggregated_drivers.recommended_next_change` is dominated by `maintain_current_flow` (e.g. 6 of 6 sessions), the correct INSIGHTS verdict is "system stable, no autoresearch action." Do not invent a driver to recommend just because the skill ran.
- **`top_cost_drivers` may be a list of dicts OR a list of strings** depending on the Builder version. The collector normalizes this; trust `aggregated_drivers.top_cost_drivers` (a dict keyed by driver name), not the raw `analyze[*].top_cost_drivers`.
- **Cache breaks ≠ user intent shift.** A cache break at >100K is a *high-cost* prompt, not necessarily a *direction-pivot* prompt. Read the `context` array on the cache_break to see surrounding prompts — pivots cluster in 2-3 prompts of the same flavor ("are we aligned?", "is X updated?"). A single isolated cache break is usually a tool result blowing up the prefix.
- **`recent_prompts` is recency-ranked, not token-weighted.** Earlier in this skill's life, a `top_prompts` field was used; it was removed because token weight meant the first heavy planning prompt of a session would dominate the list forever and silently bury fresh short prompts. Always read `recent_prompts` (newest first) AND `cache_breaks` (pivot moments) for intent — and trust short recent prompts even if their token count is low.
- **Project key encoding is lossy.** `-home-gurusharangupta-Builder-Workspace-devpulse` could decode multiple ways because real paths contain `-`. The collector tries known prefixes; if a project's `builder_signals` is empty, the path may have failed to resolve — check `warnings[]`.
- **Builder-runtime sessions ≠ Claude Code sessions.** They are different transcript universes. session-report data is Claude Code; `builder agent sessions` is Builder runtime. The same fixture run on devpulse will appear in both, but with different IDs.
- **Do not edit `docs/IMPROVEMENTS.md` or `docs/SPRINT-PROGRESS.md`.** Those are living working docs but they have a specific update protocol that is not part of this audit. Reference them in INSIGHTS for cross-link, never modify.
- **Do not run the skill more than once per day per project.** Running it multiple times in quick succession produces redundant entries with the same data and dilutes the change-over-time signal in INSIGHTS.
- **If the user asks to compare to last week's audit, do not write a new entry.** Read the last 2 entries in INSIGHTS.md and diff them in your conversation reply.
- **`session_report.by_project` is already filtered to Builder projects** by `analyze-sessions.mjs --filter-pattern`. The collector trusts the analyzer; there is no second defensive filter in Python.
- **Use `--since-run` for same-day follow-up audits; use `--since 7d` for session-opening audits.** `--since-run` only shows new signal since the last entry — if the last entry was hours ago, most of the window is empty and the audit adds little value. Use the full window when starting a new session or after a gap of ≥2 days.
- **Always embed `<!-- collected_at: ... -->` in new INSIGHTS entries** (the format in Step 5 requires it). Without it, `--since-run` falls back to midnight of the entry's date, which can re-analyze up to 24h of already-seen data.
- **Do not recommend what is already on ROADMAP.md.** Before writing Section C, scan `goal_snapshot.ROADMAP.md` for each candidate action. A `[ ]` match means it is already tracked — say so and skip. A `[x]` match means it is done — credit it as closed, do not re-recommend. Only actions with no ROADMAP match are genuine gaps worth recommending.

## Notes

- If `builder_signals` is empty for all projects (Builder not initialized anywhere with sessions in scope), Section B uses only session-report heuristics (cache_break clustering, intake-loop length). Mark INSIGHTS with "(session-report only — install Builder workspaces for full autoresearch signal)".
- If the collector exits non-zero, read `/tmp/goal-audit-errors.log`, report the blocker to the user, and do not write a partial INSIGHTS entry.

## Related (read-only references — not dependencies)

- `docs/goal/README.md` — the framework this skill audits against.
- `docs/goal/INSIGHTS.md` — the output file (this skill writes; nothing else does).
- `docs/autoresearch/OPTIMIZE_IDEAS.md` — the only file this skill may auto-modify.
