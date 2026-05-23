# Goal-audit workflow — 7 steps (Collect → Read → Synthesize → Validate → Append → Reorder → Report)

> Loaded on demand from [goal-audit SKILL.md](../SKILL.md).

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

The collector must be run from the project root so it can read `docs/goal/*` and `docs/autoresearch/OPTIMIZE_IDEAS.md`. If invoked from elsewhere, prefix with `cd <project-root> && ` or pass `--cwd <project-run>`.

If the script exits non-zero, read `/tmp/goal-audit-errors.log` and report the blocker to the user. Do not proceed with partial data unless explicitly told to.

Then run the shared drift detector (owned by the `start` skill but consumed here too):

```bash
python3 .claude/skills/start/scripts/check_status_drift.py --json > /tmp/goal-audit-drift.json 2>/dev/null || echo '{"findings":[]}' > /tmp/goal-audit-drift.json
cat /tmp/goal-audit-drift.json
```

Drift findings get incorporated into Section A as deterministic observations (one bullet per finding, citing severity + field + claim + evidence) — alongside the prompt/cache-break inferences. If the script is missing or errors, skip silently; drift detection is best-effort, not blocking.

### Dry-run mode (preview without writing)

If the user says "dry run", "preview", "show me what you would write", or invokes with `--dry-run` semantics: complete Steps 1-5 (collect, read, synthesize, validate), but in Step 5+ **print the draft INSIGHTS entry to chat instead of using Edit on the file**, and skip Steps 6 (OPTIMIZE_IDEAS reorder) and 6.5 (prior-entry trim) entirely. The user reviews the dry-run output and re-invokes without `--dry-run` if they want to commit.

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

- Every observation in Section A must cite at least one specific prompt or metric from `session_report.recent_prompts` or `session_report.cache_breaks` (with timestamp and session id), OR a deterministic finding from `/tmp/goal-audit-drift.json`. If any observation lacks evidence, delete it or find evidence.
- Section B's driver table must match the `aggregated_drivers` counts from the collector JSON exactly. If you cannot find a driver in the JSON, do not list it.
- The alignment verdict must be `aligned` if Section A has no observations naming a mismatch — do not manufacture drift to feel useful.
- If `aggregated_drivers.recommended_next_change` is dominated by `maintain_current_flow` and the other two driver streams are empty, Section B's verdict is "no autoresearch action — system stable" and Section C must not propose autoresearch changes.
- **Recommendation gate.** Every "Suggested STATUS.md change" or "Suggested ROADMAP.md change" line must cite either a NORTH-STAR § Differentiator anchor (e.g. `protects Differentiator #6 — Cost-aware execution`) OR an EVALUATION.md tier (e.g. `unblocks Tier 1 Bar 2`). If a recommendation cannot be tied to an anchor, drop it — that is the mechanical phantom-work filter. Recommendations naming small hygiene fixes (typo, link rot, broken cross-ref) are exempt and may cite `hygiene` instead of an anchor.

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

### Step 6.5 — Trim closed actions on the prior entry

After the new entry is written and OPTIMIZE_IDEAS reorder (if any) lands, perform a narrow cleanup on the **immediately-prior** INSIGHTS entry (not older ones). This keeps the file from bloating with stale `Recommended Actions` lists.

**Scope (hard limits — do not exceed):**

- Only touch the entry written by the previous run. Never touch entries two-or-more runs back.
- Only edit the `### Recommended actions` section of that entry. Never touch its `### Intent vs current focus`, `### Autoresearch focus candidates`, alignment verdict, or any prose.
- Never delete the entry. Never delete the section header. Never compress runs into table rows. Never extract content into new reference files. Those are user-triggered cleanups, not skill actions.

**Procedure:**

1. Locate the prior entry: the second-most-recent `## YYYY-MM-DD — Run #N` header in INSIGHTS.md.
2. Read its `### Recommended actions` section. If it already starts with `**All actions closed**` (any case/punctuation variant), this step is a no-op — record `"prior entry already trimmed"` in the new entry's Section B closing line.
3. For each numbered action in the prior entry's list, classify it:
   - **Closed (ROADMAP):** matching `[x]` item exists in current `goal_snapshot.ROADMAP.md`.
   - **Closed (shipped):** action explicitly references a commit, CHANGELOG entry, or memory write that exists.
   - **Tracked (ROADMAP):** matching `[ ]` item exists (the action is now a roadmap line — counts as closed *from this entry's perspective* because the action's job was to escalate the work onto the roadmap).
   - **Open:** none of the above.
4. If **every** action classifies as closed/tracked, use Edit to replace the entire numbered-list body of `### Recommended actions` with a single line:

   ```markdown
   **All actions closed.** <≤25-word summary citing ROADMAP milestones, commits, or CHANGELOG entries that absorbed them>.
   ```

   Keep the `### Recommended actions` header itself. Do not add a date — the entry header already has it.
5. If **any** action remains open, leave the section unchanged. Record `"prior entry still has open actions"` in the new entry's Section B closing line so the audit trail shows the cleanup was considered.

**Self-check before Step 7 (extend the existing self-check):** files edited this run must still be a subset of `{INSIGHTS.md, OPTIMIZE_IDEAS.md}`. The Step 6.5 edit lands on INSIGHTS.md, so the set is unchanged.

### Step 6.6 — Compress old INSIGHTS entries (>14 days, all actions closed)

After Step 6.5 trims the immediately-prior entry, do a second compression pass on entries **older** than that:

1. Walk every `## YYYY-MM-DD — Run #N` header in INSIGHTS.md from oldest to newest.
2. For each header older than 14 days from today:
   - If its `### Recommended actions` section starts with `**All actions closed**` (i.e. already trimmed) AND the entry isn't already in the "Closed audit runs" summary table at the top, append a row to that table: `| #N | YYYY-MM-DD | <verdict> | <≤25-word outcome summary, salvaged from the closed-actions line> |` and delete the full entry from the body.
   - If its `### Recommended actions` section still has open numbered actions, leave it alone — open actions block compression even at >14 days.
3. Cap the compression at the oldest 3 entries per run to keep the audit trail readable. If more than 3 entries qualify, compress the oldest 3 and leave the newer ones for the next run.

The "Closed audit runs" table at INSIGHTS.md top is the canonical durable home for compressed entries. Git history retains the full prose of every retired entry — the table is just the agent-readable summary.

If no entries qualify for compression, this substep is a no-op — record "no INSIGHTS entries compressed this run" silently (not in the new entry body; chat reply only).

### Step 7 — Report back to the user + self-schedule next run

In your conversation reply (not in the files), summarize:
- Path to the new INSIGHTS.md entry.
- Headline alignment verdict.
- Whether OPTIMIZE_IDEAS.md was reordered (and which item moved).
- Whether the prior entry's Recommended Actions were trimmed (Step 6.5 outcome: trimmed / already-trimmed / open-actions-remain).
- Whether any older entries were compressed (Step 6.6 outcome).
- Top 1-3 recommended actions in one line each.

Keep it under 10 lines. The file is the durable record; chat is the pointer.

#### Self-schedule the next run

After reporting back, call the `CronCreate` deferred tool to schedule the next weekly goal-audit. This is what keeps the cadence honest without the operator having to remember.

Default schedule: weekly on Sunday at 09:00 in the operator's local timezone, with the prompt `"weekly goal-audit run — analyze last 7d"`. The prompt is shaped to match this skill's description so the next firing auto-triggers `goal-audit` via description matching.

```
CronCreate(
  schedule: "weekly on Sunday at 09:00",
  prompt: "weekly goal-audit run — analyze last 7d",
  description: "Auto-scheduled by goal-audit Step 7. Self-rescheduling chain; safe to delete if cadence needs to change."
)
```

Skip the CronCreate call when:
- The `CronCreate` tool is not available in the current environment (the call would error; report this in the chat reply and ask the operator to schedule manually).
- A weekly goal-audit cron is already scheduled (check `CronList` first — duplicate schedules are pollution). If `CronList` shows an existing entry matching this prompt, do NOT create a second one.
- The operator passed `--no-schedule` or explicitly said "don't reschedule" in the invoking prompt.

