# Insights — Direction Audit Log

> **This file is the output surface for the `goal-audit` skill.** Read [README.md](README.md) first; this file is not the framework entry point.

The `goal-audit` skill (project-local at `.claude/skills/goal-audit/`) appends a dated entry here each time it runs. Each entry contains:

- **Intent vs current focus**: alignment between what the user has been pushing on across recent sessions (extracted from Claude Code transcripts) and what [STATUS.md](STATUS.md) / [ROADMAP.md](ROADMAP.md) claim is in flight.
- **Autoresearch focus candidates**: recurring `top_cost_drivers` from Builder CLI evidence, mapped to [`docs/autoresearch/OPTIMIZE_IDEAS.md`](../autoresearch/OPTIMIZE_IDEAS.md) items.
- **Recommended actions**: concrete next moves with cited evidence.

## How to invoke

From the project root:

```text
"audit alignment"
"are we aligned?"
"is the roadmap right?"
"what should we focus on next?"
"where should autoresearch go next?"
```

Or invoke the skill directly. Default window is the last 7 days; pass `--since 24h|30d|all` to widen or narrow.

## What the skill does and does not do

| Action | The skill | The user |
| --- | --- | --- |
| Append new entry to this file | ✓ | — |
| Reorder [`docs/autoresearch/OPTIMIZE_IDEAS.md`](../autoresearch/OPTIMIZE_IDEAS.md) when a single driver recurs in ≥3 sessions | ✓ (auditable comment added) | — |
| Edit [STATUS.md](STATUS.md), [ROADMAP.md](ROADMAP.md), [NORTH-STAR.md](NORTH-STAR.md), [EVALUATION.md](EVALUATION.md), or any control-owned file | — | ✓ (after reading skill recommendations) |

## Lifecycle of an insight

When a skill recommendation from this file has been acted on and verified:

1. **Move it to [ROADMAP.md](ROADMAP.md)** as a `[x]` item under the correct milestone. This is the canonical completed-work checklist — not a separate file.
2. **Remove it from the open Recommended Actions list** in the entry it came from (or note it as closed with a brief one-liner).
3. Open insight recommendations stay here as `[ ]` items until acted on. Do not delete them silently.

## Entries

## 2026-05-21 — Run #1 (since 7d, 28 Builder-related sessions analyzed)

### Intent vs current focus

- **The framework-migration / skill-building work has dominated the last 7 days but is not reflected as in-flight work.** 25.1 active hours / 157 human messages went into the architecture-review repo on framework migration (`PLAN.md`/`GOAL.md`/`MISSION.md` → `docs/goal/`, new `FIX-STANDARD.md` / `OPERATOR-LANGUAGE.md` / `TUNING.md`, autoresearch framework, goal-audit skill creation). STATUS.md `Current Item In Flight` still reads "End-to-end re-verify" — that's an honest description of where M1.1 sits in code, but the operational reality of the past week was meta-framework, not M1.1 re-verify. Evidence: prompts `"its time for the migration of our existing goal system sitting in docs folder directly"` (2026-05-21T07:21, session `6d0300b4`, 432K uncached cache-break), `"can you check the docs/goal/README.md and continue"` (2026-05-21T07:50, 8.7M tokens), `"i will go with your recommendation"` (2026-05-20T20:35, 412K uncached cache-break).
- **Devpulse — the named Active Workspace — received almost no attention this week.** STATUS lists devpulse as active for M1.1 re-verify, but session-report shows only 0.3 active hours / 11 human messages on devpulse over 7 days, vs 25.1 active hours in the architecture-review repo. Re-verify cannot have started.
- **The user has repeatedly invoked the exact pattern this skill was built to detect.** Cache-break clusters are dominated by meta-direction prompts: `"Can you analyze all my prompts and check the docs/GOAL.md and think if our GOAL is fully aligned"` (2026-05-20T11:56, 141K), `"are you following same pattern like it was done earlier you can check docs/PROGRESS.md"` (2026-05-20T16:38, 107K), `"its time for the migration of our existing goal system"` (2026-05-21T07:21, 432K). 5 of 9 cache-breaks > 100K are direction-check questions, not execution prompts.
- **Top prompts by token weight confirm two threads: planning ceremony and direction-check.** #1 `"Can you create a plan for it first"` (39M tokens), #2 `/resume-session` (24M), #3 `"Please continue with the plan in docs/PLAN.md"` (20M), #6 `"You are the expert here , do you think something else needs to be done?"` (14M), #11 `"are you checking the run through builder cli?"` (11M). The pattern is "plan → resume → check" — not implementation.
- **The framework is now in place — STATUS.md just needs to acknowledge it.** Two `2026-05-21` Recent Decisions entries already record the framework migration and IMP-007/IMP-009 closure, so the historical record is correct. The `Current Item In Flight` and `Last Update` fields are the lagging surface.

**Alignment verdict:** **drifting** — substantive intent (build the management framework) does not match the named Current Item (devpulse re-verify). Framework work was the right thing to do; STATUS just didn't track it.

**Suggested STATUS.md change:** Update `Current Item In Flight` to reflect that framework migration + goal-audit skill are now live and the next concrete action is the actual devpulse re-verify (M1.1 final step). Add a Recent Decisions line: `"2026-05-21 — Direction-audit infrastructure live: docs/goal/INSIGHTS.md + .claude/skills/goal-audit/ (self-contained, bundled analyzer). First run produced this entry."`

**Suggested ROADMAP.md change:** None. M1.1 remains valid and the framework work was infrastructure FOR the roadmap, not a roadmap item. Once devpulse re-verify completes, M1.1 → done as planned.

### Autoresearch focus candidates

| Driver | Sessions in scope | OPTIMIZE_IDEAS map |
| --- | --- | --- |
| *(none — `aggregated_drivers.top_cost_drivers` is empty)* | 0 | — |

`aggregated_drivers.recommended_next_change` is `{maintain_current_flow: 6}` across all 6 analyzed Builder-runtime sessions (3 devpulse + 3 todo-app). The Builder side is operating cleanly — no chunk pressure, no avoidable cost flags, no recurring driver. **No autoresearch action this run; system stable.**

Two side-notes from session-report data (not Builder-runtime, so not autoresearch action items):

- **`general-purpose` Claude Code subagent averages 3.45M tokens / call** (`by_subagent_type` data). This is above the 2M threshold the SKILL.md mentions. However, this maps to Claude Code's `general-purpose` subagent scoping, not Builder's `code-gen` subagent. The mapping is *not* OPTIMIZE_IDEAS idea 8.
- **Cache-break locations show prefix is stable**: the `here` prompt on each cache-break is operator-typed text, not a large tool result reinjection. That rules out idea 6 (tool-output reinjection cap) — the breaks are user-prompt-driven, not tool-driven.

**OPTIMIZE_IDEAS.md actions taken:** none. No driver met the `≥3 sessions` threshold because the empirical `top_cost_drivers` shape returned by `builder logs analyze` differs from what the SKILL.md mapping table assumes (see Recommended Actions #3).

### Recommended actions

1. **Update STATUS.md `Current Item In Flight` and add a Recent Decisions line** as drafted under "Suggested STATUS.md change" above. Without this, future agents landing on the framework will read a stale claim about devpulse re-verify being in flight.
2. **Run the devpulse re-verify.** It's the last gate before M1.1 → done. The framework can't help the roadmap advance if the next concrete item never gets executed. Allocate one focused session to it.
3. **Fix the goal-audit driver-shape mismatch.** The SKILL.md static driver mapping table assumes `top_cost_drivers` is a list of named driver strings (`large_command_output`, `truncate_tool_output_before_reinjection`, etc.), but `builder logs analyze --full --json` actually returns objects keyed by `agent_name`. Until `collect.py:aggregate_drivers` is updated to handle both shapes (or to extract the *actual* driver signal — likely `recommended_next_change`, `avoidable_cost_flags`, and per-agent `noncached_plus_output_tokens` ratios), the OPTIMIZE_IDEAS reorder logic will never fire. Two-line fix in `aggregate_drivers()`.
4. **No OPTIMIZE_IDEAS.md reorder needed this run.** The system is stable. Re-run the audit after #3 lands to see if any real driver clusters emerge.

---

## 2026-05-21 — Run #2 (since 7d, ~16 min after Run #1, 28 Builder-related sessions analyzed)

### Intent vs current focus

- **Delta since Run #1 is tiny but consistent in direction.** Total input tokens grew from 391M to 403M (+12M), active hours from 13.0 → 13.5, human messages from 210 → 212 in the 16-minute window between Run #1 (collected 08:28:57Z) and this run (08:44:41Z). The two new human prompts produced too little token weight to crack the token-ranked `top_prompts` list — those snapshots are still dominated by the heavy planning/resume prompts from earlier in the week.
- **The work in that 16-minute window was follow-through on Run #1's recommendations** (corroborated from the active conversation thread, since prompt-text evidence is below the token cap):
  - **Run #1 Action #3 (fix driver-shape mismatch) → done.** `aggregate_drivers()` in `collect.py` rewritten to extract three independent streams (`recommended_next_change`, `avoidable_cost_flags` from `optimization_decision`, `agent_names_with_avoidable_tokens` from `top_cost_drivers[*]` where `avoidable_token_estimate > 0`). The SKILL.md mapping table was reorganized into 3 sub-tables matching the streams. Smoke test confirms 4 sub-keys present in the aggregated_drivers structure.
  - **Bug 1 (skill mutating STATUS.md) → fixed in SKILL.md.** Added an ⚠ HARD RULE block at the top of SKILL.md listing the 14 forbidden-to-edit files, plus a Step-7 self-check before reporting.
  - **Bug 3 (skill not invocable via Skill tool) → fixed in frontmatter.** Added `model: sonnet`, `effort: high`, `allowed-tools: Read, Edit, Bash` to match the format the existing project-local skills (`implementation`, `init-project`) use.
  - **Run #1 Action #1 (update STATUS.md) → not done.** This is by design — the new ⚠ HARD RULE blocks the skill from editing STATUS.md. That recommendation is a *user decision*, not a skill action.
  - **Run #1 Action #2 (devpulse re-verify) → not done.** Still the next concrete roadmap action; no time spent on it in this window.
- **No new cache_breaks > 100K and no new direction-pivot prompts in scope.** The 16-minute window was tightly focused (bug-fix loop on the audit tool itself), not direction-changing. That's a healthy signal — direction has been stable since Run #1's verdict.
- **STATUS.md state still reads as it did at Run #1** (`Current Item In Flight = End-to-end re-verify`, Active Workspace = devpulse). This is consistent with the HARD RULE: the skill cannot fix this; the user must.

**Alignment verdict:** **drifting (unchanged from Run #1)** — same gap as before: STATUS lags reality. The framework + skill infrastructure is now hardened (3 bugs fixed); the next move is for the user to either update STATUS.md or run the devpulse re-verify (which would then justify keeping STATUS as-is).

**Suggested STATUS.md change:** unchanged from Run #1. Update `Current Item In Flight` to reflect the framework + audit-infrastructure milestone, OR run the devpulse re-verify so the current item makes sense as in-flight again.

**Suggested ROADMAP.md change:** none.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 6 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Builder-runtime signals identical to Run #1 (same 3 devpulse + 3 todo-app sessions analyzed; same `maintain_current_flow` × 6 verdict). With the fixed aggregator, the reorder logic would now fire if real waste appeared in any stream — but the Builder system has nothing to flag.

Side-data unchanged: Claude Code `general-purpose` subagent still averages 3.46M tokens/call (above the 2M threshold mentioned in SKILL.md gotchas). This is informational only and not mappable to OPTIMIZE_IDEAS idea 8 (which is about Builder's `code-gen` subagent, a different concern).

**OPTIMIZE_IDEAS.md actions taken:** none — same as Run #1.

### Recommended actions

1. **Audit cadence limitation surfaced.** The token-weighted `top_prompts` cap (200) silently excludes short recent activity. After a successful Run #N, subsequent runs within the same day will see the window dominated by older heavy prompts and the newer (small) prompts disappear. This Run #2 saw +12M tokens of new work but 0 new top_prompts because the window was 16 min and individual prompts were small. Consider a future enhancement: add a `since_run` mode where the collector accepts a prior `INSIGHTS.md` timestamp and emits a "deltas since" section. Not blocking; just a known sharpness limit.
2. **Run #1's recommended actions #1 and #2 remain open.** Update STATUS.md OR run the devpulse re-verify. The Builder system is genuinely clean — the bottleneck right now is the unblocking action on M1.1, not any inefficiency.
3. **The skill is now self-correcting.** Run #1 surfaced 3 bugs; this Run #2 confirms all 3 fixed and the system is otherwise stable. Future runs should produce shorter Recommended-actions sections as the framework reaches steady state.
4. **No OPTIMIZE_IDEAS.md reorder needed.** All three driver streams empty for actionable signals; system stable.

---

## 2026-05-21 — Run #4 (since 7d, 40 Builder-related sessions analyzed)

### Intent vs current focus

- **M1.2 is genuinely in flight for the first time.** The 40-session window now includes 12 sessions under `/tmp/aab-workspaces/128e02f6-...` (scaffold + code-gen for the first devpulse task, completed at ~11:25) and 1 session under `/tmp/aab-workspaces/a3c4511b-...` (a second code-gen task, currently running as task `brae6l70h` at time of this audit). By-project: devpulse=7, source repo=14, tmp-workspaces=13. This is the first run where devpulse + workspace sessions together exceed source-repo sessions — execution has caught up with framework-building.
- **The brief context7 / automation-recommender detour (09:18–09:32) does not indicate drift.** Recent prompts `"Provide top 4 recommendation which i should definitely implement"` (09:26), `"/claude-code-setup:claude-automation-recommender"` (09:18), `"i cant install mcp, but will install context7 plugin"` (09:28), `"this is managed environment hooks are disabled here"` (09:27) — these 15 minutes of infrastructure exploration preceded the actively running M1.2 dispatch. They did not displace it.
- **CLAUDE.md placement clarification was M1.2-adjacent work, not drift.** Prompts `"not project local .claude"` (09:39) and `"its the opposite i want project local .claude/CLAUDE..md updated"` (09:39) indicate a brief correction on where generated-app CLAUDE.md should land — directly relevant to the scaffold + builder-init flow being tested in M1.2.
- **STATUS Evidence Pointers are one task behind.** STATUS records task `128e02f6` as the latest Agent session (done, 11:25). The currently active task `brae6l70h` (board state: pending=3, active=1) is not yet reflected. This is expected during in-flight work, not a lie — but should be updated when the task completes. Evidence: monitor event `11:27:52 board: pending=3 active=1` (task-notification in current session).
- **User is reading the docs/goal/ framework while monitoring the running agent.** Prompts `"can you read through docs/goal/README.md"` (11:28:07), `"yes please continue, some monitors are already in place and running"` (11:28:38), `"in meantime can you run goal audit skill"` (11:29:38) — this is informed operator oversight while execution proceeds, not redirection away from M1.2.

**Alignment verdict:** **aligned** — first aligned verdict across 4 audit runs. STATUS claims M1.2 in flight; actual sessions confirm M1.2 is executing. Evidence Pointers are slightly stale (expected; task in progress). No structural STATUS or ROADMAP edits needed.

**Suggested STATUS.md change:** After task `brae6l70h` completes, update Evidence Pointers: `Latest agent session id (Claude lane)` → new session ID, board state → post-completion snapshot.

**Suggested ROADMAP.md change:** None.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 6 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Builder-runtime evidence unchanged across all 4 audit runs: same 3 devpulse + 3 todo-app session IDs (deduplicated), all reporting `maintain_current_flow`, no avoidable cost flags, no expensive agents. The autoresearch loop cannot fire without a ≥3-session single-item-mapped driver — none exists.

**OPTIMIZE_IDEAS.md actions taken:** none.

### Recommended actions

1. **After task `brae6l70h` completes, update STATUS.md Evidence Pointers.** Run `builder logs analyze --session <new-id> --json` and `builder board show --json` from `/home/gurusharangupta/Builder-Workspace/devpulse`; capture session ID, cost, board state. This closes the one-task lag identified above.
2. **Run Tier 1 verification as the next gate.** Per EVALUATION.md §1.1: `builder logs analyze --session <id> --json` (cache_ratio > 5x?), `builder metrics show --json --full --limit 8` (chunk_pressure_risk, avoidable_cost_flags, recent_risky_runs). M1.2 cannot be closed without this evidence.
3. **No OPTIMIZE_IDEAS.md reorder needed.** All three driver streams are empty for actionable signals across all 4 audit runs. Builder system is operating cleanly.

---

## 2026-05-21 — Run #3 (since 7d, 28 Builder-related sessions analyzed; first run with `recent_prompts` as primary intent signal)

### Intent vs current focus

- **STATUS.md was updated by the user between Run #2 and this run** — closing Run #1/#2 Recommended Action #1. Current Position now reads M1.1 closed (all 8 IMPs resolved with regression tests), M1.2 in flight, IMP-010 opened as the M1.2 blocker. `Last Update: 2026-05-21 — M1.1 closed by Claude Sonnet 4.6 session; IMP-010 opened`. The framework lag identified in Runs #1 and #2 is no longer a STATUS-vs-reality gap on the roadmap side; STATUS now reflects what the M1.1 work actually accomplished.
- **However, recent activity is not on the named in-flight item.** STATUS says `Current Item In Flight = M1.2 first item — fresh devpulse builder init + readiness gate green`. Recent intent (newly visible because `recent_prompts` is now recency-ranked, not token-weighted) shows the past ~90 minutes in this repo focused entirely on goal-audit skill maturation, not on M1.2/IMP-010 work. Evidence from `recent_prompts` (newest first, all in this project):
  - `08:53` `"what you said in honest finding, then everything will always be clouted by the first planning prompt"` — first-principles critique of the skill itself
  - `08:44` `"Yes i want you to rerun the audit again, i have a session which has been running for quite some time now"`
  - `08:35` `"can you first fix teh bugs"`
  - `08:28` `"shall we test?"`
  - `08:09` `"sure go ahead"` (api_calls=145 — heaviest recent prompt, driving the bug-fix and self-containment work)
  - `08:06` `"the skill should be self contained if anything referenced from outside like the session report copy the desired file into the skill itself and tailor it as per your requirement"`
  - `07:54` `"does it provide any signal that will tell agent to update autoresearch as well?"`
  - `07:50` `"can you check the docs/goal/README.md and continue"`
  - `07:47` `"can you first use the /session-report:session-report skill to see how it could be used to tailor the skill"`
  - `07:45` `"I want to create a skill using skill creator skill which manages my goal folder and autoresearch folder"`
- **Project attention distribution unchanged.** `by_project` still shows ~14h active in this architecture-review repo (now 14.2h vs Run #2's 13.5h, so +0.7h since Run #2) vs 0.3h on devpulse over the full 7-day window. Devpulse work has not started.
- **This is the *intended* drift: framework before fieldwork.** The recent_prompts make clear that the work pattern is `build the audit tool that will help validate M1.2` rather than `do M1.2 directly`. That's a deliberate sequencing choice, not unconscious drift. The skill development is infrastructure for the roadmap, not a roadmap item itself — exactly the same pattern as Run #1's verdict on the docs/goal/ framework build.
- **Run #3 closes the visibility gap that Run #2 raised as Recommended Action #1.** Run #2 noted that `top_prompts` (token-ranked) silently buried short recent prompts. This Run #3 is the first run with `recent_prompts` (recency-ranked) as the primary intent signal, and the past 90 minutes of activity are now visible at the top of the list instead of behind week-old planning prompts. Confirms the fix works.

**Alignment verdict:** **drifting (acknowledged-and-intentional)** — Current Item In Flight per STATUS is M1.2/IMP-010; current actual work is goal-audit skill maturation. The work is justified (better audit tooling helps validate M1.2), but it's not a roadmap item, so STATUS cannot reflect it without adding either (a) a new roadmap milestone for self-auditing infrastructure, or (b) a Recent Decisions line acknowledging the parallel infrastructure thread.

**Suggested STATUS.md change:** Optional. Either add a Recent Decisions line: `"2026-05-21 — goal-audit skill matured (3 audit runs, first-principles cleanup, top_prompts → recent_prompts swap). Audit infrastructure now ready to validate M1.2 reverse-flow."` OR pivot focus to M1.2 / IMP-010 so the skill development thread naturally winds down. Skill leaves this choice to the user (HARD RULE).

**Suggested ROADMAP.md change:** None. Consider whether the meta-framework / audit-infrastructure work deserves an explicit roadmap callout (e.g., as part of M2.x), but this is a strategic question for the user, not an audit action.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 3 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Builder-runtime evidence unchanged in substance from Runs #1 and #2: the same devpulse + todo-app sessions analyzed; all report `maintain_current_flow`. The count moved from `{maintain_current_flow: 6}` (Runs #1/#2) to `{maintain_current_flow: 3}` (Run #3) because the cleaned aggregator now deduplicates by session_id across workspaces — the same 3 Builder-runtime session IDs appeared in both `Builder-Workspace/devpulse` and `Workspace/todo-app` probes, and earlier they were double-counted. The verdict is unchanged either way.

**OPTIMIZE_IDEAS.md actions taken:** none — same as Runs #1 and #2.

### Recommended actions

1. **The audit-tool maturation thread can wind down.** Three audit runs (#1, #2, #3) plus first-principles cleanup and self-containment fixes constitute a complete iteration. The skill now produces correct evidence-grounded entries, can detect direction drift visibly, and respects the HARD RULE. Further refinement should be driven by new findings during real use, not pre-emptive polishing.
2. **The next concrete action per STATUS is M1.2 → IMP-010 fix.** `agent_run_lifecycle.py` `monitor_workspace_diff` not-stopped-on-exception path. Once IMP-010 closes, M1.2 first item (fresh devpulse `builder init` + readiness gate green) can run.
3. **The cleaned aggregator + recent_prompts changes from this session should be reflected as a goal-audit memory entry.** Per [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable), the durable learning is: *"prefer recency-ranked intent over token-weighted intent — token weight silently buries recent short prompts behind heavy old ones"*. Suggested memory write: `builder memory add --type pattern --tag goal-audit,intent-extraction ...` from the Builder source repo, not from this architecture-review repo.
4. **No OPTIMIZE_IDEAS.md reorder needed.** All three driver streams empty for actionable signals; Builder system continues to operate cleanly.

---

## 2026-05-21 — Run #5 (since 7d, 50 Builder-related sessions analyzed)

### Intent vs current focus

- **A strategic-direction lane opened in the most recent sessions that the prior 4 runs didn't see.** The user pulled an external best-practices artifact (`"now can you read the … how-openai-uses-codex.pdf … its codex related but think in general for any agent harness"`, 2026-05-21T15:46:53, session `c281c387`), proposed a new product surface (`"I had been thinking of two feature one is autopilot mode, where in if you turn on the autonpilot the orchestrator agent takes the responsibility of approving and moving the task forward or recover…"`, 2026-05-21T15:22:19, session `c281c387`), and repeatedly asked for harness-level recommendations (`"what is you recommendation which we should implement in our autonomous builder?"` 2026-05-21T15:50:04; `"Give you recommendation , what do you think about it"` T15:25:26). This is intake-and-direction work, not execution.
- **STATUS.md `Current Item In Flight` still reads `M1.2 first item — devpulse sprint in progress; 2 tasks done, 3 pending`, but session distribution shows the named work has barely started.** Source repo drew 17 sessions / 15.1 active hours / 213 human messages this week; the named devpulse workspace drew 7 sessions / 0.3 active hours / 11 human messages. The Active Workspace got <2% of human attention. Same drift shape as Runs #1–#4 — unchanged.
- **Generated-app activity is happening on disposable `aab-workspaces-*` paths, not on canonical devpulse.** `ab-workspaces-ced2f6f3` ran feature-verifier scaffolds (T15:32:37, T15:42:28, T15:46:46, session `c281c387`); `ab-workspaces-128e02f6` ran scaffold-agent prompts throughout (T06:22 → T09:49). The STATUS-listed devpulse workspace is not where Builder runs landed this week.
- **Builder-runtime side is stable across every analyzed session.** `aggregated_drivers.recommended_next_change` is `{maintain_current_flow: 6}` (3 devpulse + 3 todo-app `builder logs analyze` probes); `avoidable_cost_flags` and `agent_names_with_avoidable_tokens` are both empty. Devpulse `cache_ratio = 18,584` — far above the 5× bar. No autoresearch signal to act on.
- **Cache-breaks this window are operator-workflow, not direction-pivot.** 11 breaks total; surrounding `context` arrays are dominated by `/model`, `/plan`, `/resume-session`, and "check docs/goal/README.md" — not the autopilot or harness-recommendation prompts that are the actual direction signal. The genuine pivot (autopilot) did not itself produce a cache_break, confirming the gotcha that cache-breaks ≠ intent shifts.

**Alignment verdict:** **drifting** — same drift as Runs #1–#4 (STATUS claims M1.2 first item is in flight; it isn't). New nuance this run: a strategic intake lane has opened (OpenAI PDF + autopilot proposal + recommendation requests) that is not in ROADMAP or backlog, and will lose signal without capture.

**Suggested STATUS.md change:** Either (a) update `Current Item In Flight` to reflect that M1.2 first-item execution is paused while strategic intake runs, OR (b) close the intake lane and pick up M1.2 execution on devpulse. The current file says M1.2 is in flight; the data says it isn't. (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** Consider an "Autopilot mode — orchestrator owns approval, recovery, and continuation" item in Epoch 2 or a Future Surfaces bucket. The user has proposed it once explicitly with a concrete description; it is a real direction signal, not a passing remark. (HARD RULE: skill does not edit.)

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 6 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Same shape as Runs #1–#4. The OpenAI Codex best-practices reading prompted a "what should we implement" question, but the Builder runtime itself flags nothing avoidable. The 7 PDF principles map cleanly onto existing OPTIMIZE_IDEAS items already in the backlog: "environment learning > prompt iteration" ≈ items 6/7/9; "subagent for code-gen" = item 8; "plan→execute" is already enforced by phase model; "persistent context" is already CLAUDE.md/AGENTS.md/`builder knowledge`; "task queue as backlog" is already `project→item→task`. The PDF reinforces existing direction; it does not introduce a new driver. Best-of-N and "after-fix sibling search" are genuinely new but lack runtime evidence to justify promotion.

**OPTIMIZE_IDEAS.md actions taken:** none. `maintain_current_flow` is explicitly excluded from reorder candidates (HARD RULE check). No other stream populated.

### Recommended actions

1. **Capture the autopilot proposal before it drifts back into chat.** Either append a ROADMAP item under Epoch 2 ("Autopilot mode — orchestrator owns approval/recovery/continuation"), OR run `builder backlog item create --type feature --source validation --title "Autopilot mode: orchestrator owns approval, recovery, continuation" --json` from the source repo. This is the only genuinely new direction signal in the 7-day window, and it has zero durable representation right now.
2. **Do NOT add OpenAI-PDF principles as new framework prose.** Five of the seven principles are already encoded (phase model, CLAUDE.md/AGENTS.md, OPTIMIZE_IDEAS 6/7/8/9, project→item→task backlog). Writing them again as new doctrine would compound the same drift the prior 4 audits flagged: more meta-framework, less M1.2 execution. The two genuinely new principles (Best-of-N, after-fix sibling search) need runtime evidence before promotion.
3. **The honest answer to "what should we implement?" is: finish M1.2 first.** Empirical priority comes from `aggregated_drivers` (empty) and STATUS (M1.2 named but unstarted). Until devpulse actually ships one feature end-to-end through the lane STATUS claims is active, new OpenAI-derived principles cannot be tested against real data — they would be doctrine without measurement.
4. **If the user still wants to bias toward an OpenAI-PDF principle now, the highest-fit existing item is OPTIMIZE_IDEAS #6 (cap tool-output reinjection at 2K with builder artifact pointer).** This is "environment learning > prompt iteration" in practical form. It is at position 6 with `Attempts: none`. The user can manually promote it; the data doesn't authorize auto-reorder.
5. **Add "after-fix sibling search" as OPTIMIZE_IDEAS #11 (new entry)** if the user wants to record it as a hypothesis. Status: `Attempts: none`; SDK basis: bounded `repo-researcher` subagent invoked after `implementation` closes on a bug-fix item. Skill cannot add new ideas; flagging as a user action.

---

## 2026-05-21 — Run #6 (since 7d, 51 Builder-related sessions analyzed)
<!-- collected_at: 2026-05-21T16:27:09.587Z -->

### Intent vs current focus

- **For the first time across 6 audit runs, STATUS.md accurately reflects reality.** STATUS reads "M1.2 Claude lane complete; Codex SDK lane pending." The data agrees: devpulse had 7 sessions / 0.3 active hours; M1.2 Claude lane is done (5/5 tasks, $2.08). There is no stale "in flight" claim this run.
- **This session was dedicated to framework governance, not product advancement.** The 16 most recent prompts cluster entirely around: commit-and-push requirement for `[x]` items (Hard Rule 13), CHANGELOG requirement before committing (Hard Rule 14), `.gitignore` for runtime artifacts, `docs/goal/` self-containment audit, and the INSIGHTS→ROADMAP completed-item lifecycle. Evidence: `"When checklist is marked completed, the changes have to be committed and pushed to remote"` (T16:14, session `ab11d3d`), `"can you also update the docs/goal/README.md on updating the CHANGELOG.md before commit"` (T16:26), `"is our docs/goal self contained and properly wired?"` (T16:09). None of these prompts advanced the Codex SDK lane.
- **Two Run #5 recommended actions were fully executed this session.** (1) Autopilot mode added to ROADMAP.md as M2.6 with 5 concrete items — Run #5 action #1 is done. (2) After-fix sibling search added to ROADMAP.md M3.5 as a `[ ]` item — Run #5 action #5 is done. This is the INSIGHTS→ROADMAP lifecycle working as designed: recommendations from an audit entry became `[x]`-trackable roadmap items.
- **Source repo attention remains dominant.** 17 sessions / 15.8 active hours in source repo vs 7 sessions / 0.3 active hours in devpulse. This is consistent with a framework-governance session. The framework work is durable and now committed + pushed (per the Hard Rules just established).
- **M1.2 has two open `[ ]` items that require execution, not governance.** Codex SDK lane (same operator wording, same devpulse workspace) and Tier-1 verification (`cache_ratio > 5x`, `chunk_pressure_risk: false`, `avoidable_cost_flags: []`, gate-pass rate `1.0`). Neither moved this session.

**Alignment verdict:** **aligned** — STATUS is accurate; this session's governance work is consistent with the framework. No stale claims. The open gap is execution-only: run the Codex lane and verify Tier-1 bars.

**Suggested STATUS.md change:** Add a Recent Decisions line: `"2026-05-21 — Framework governance: Hard Rules 13 & 14 (commit+push, CHANGELOG-before-commit) added to README.md; .gitignore updated; docs/goal/ self-containment confirmed; INSIGHTS→ROADMAP lifecycle documented."` The Current Position and Next Action fields are already accurate.

**Suggested ROADMAP.md change:** None. M2.6 (autopilot) and M3.5 after-fix sibling search were already added this session. No new items surfaced in this audit.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 6 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Sixth consecutive run with `maintain_current_flow` dominating all Builder-runtime sessions. devpulse `cache_ratio = 18,530` (far above 5× bar); `avoidable_token_estimate = 0` across all analyzed sessions. The Builder runtime is operating cleanly; there is nothing to optimize yet.

**OPTIMIZE_IDEAS.md actions taken:** none.

### Recommended actions

ROADMAP.md cross-check results (new rule applied retroactively to this entry):

- Action "Run Codex SDK lane" → already tracked as ROADMAP.md M1.2 `[ ]` item (line 44). No new action needed.
- Action "Run Tier-1 verification and archive evidence" → already tracked as ROADMAP.md M1.2 `[ ]` items (lines 45-46). No new action needed.
- Action "Update STATUS.md" → standard protocol in ROADMAP.md § How To Pick The Next Item (steps 6-7). No new action needed.

**No net-new recommended actions this run.** All three candidate actions are already on ROADMAP.md. The framework is self-consistent. The only thing needed is execution: dispatch the Codex SDK lane per the existing M1.2 `[ ]` items.

---

## 2026-05-22 — Run #7 (since 30d, 106 Builder-related sessions analyzed; coding-agent retrospective + SDK-grounded prevention)
<!-- collected_at: 2026-05-22T06:27:58.314974+00:00 -->

### Intent vs current focus

- **Today's intent is a retrospective + readiness pass between M1.2 close and M1.4 start.** Recent prompts: `"Can you go through the docs/goal/README.md and AGENTS.md"` (2026-05-22T06:17:45), `"Can you use the goal audit skill to check what issues in codebase had to be fixed, cause of those issues and what should be done so that similar issues don't arise again"` (T06:27:06), `"this is for you the coding agent so that you don't code similar issues into the code and stay on the best practice lane from the get-go"` (T06:27:06, same prompt continued). No Codex-SDK-lane work landed in the past 24h.
- **The M1.4 thread is already open from last night.** Prompt `"sure go ahead with two workspace validation rotation"` (2026-05-21T22:21:44) signals readiness to start M1.4 once this retrospective lands.
- **STATUS-vs-reality alignment unchanged from Run #6.** M1.2 Claude lane done; M1.3 god-file decomposition closed (commit `f6e96b4`); M2.6 autopilot + M3.5 after-fix-sibling-search added to ROADMAP in commits `0eed513`/`457613a`. Run #6's `aligned` verdict still holds.
- **Managed-environment constraint applies to the dev session, not the product code.** Prompt: `"keep in mind we are in managed environment so hooks and mcp servers are out of scope"` (T06:27) was clarified mid-write as `"the hooks and mcps and subagent etc can run inside the autonomous builder which is built on claude agent sdk and codex sdk, i meant in this environment for you itself"` (T06:35). Translation: the Claude Code dev session running audits/reviews cannot install new hooks/MCPs *for itself*, but the autonomous-builder product code absolutely uses hooks, MCP servers, and subagents — they are first-class prevention mechanisms for the patterns in Section D.
- **Managed-app codebase remains read-only for Builder fixes.** Prompt: `"I want to make it very clear, we should never touch the managed app codebase, think about realworld scenario..."` (T06:20:18). Reinforces existing `.memory/corrections/do-not-mutate-managed-app-workspaces-during-builder-validati.md`.

**Alignment verdict:** **aligned** — STATUS reflects reality; retrospective is a deliberate, narrow infrastructure pass.

**Suggested STATUS.md change:** Add a Recent Decisions line: `"2026-05-22 — Coding-agent retrospective + SDK-grounded prevention guidance landed in INSIGHTS.md Run #7. Five priority patterns from IMP-001..IMP-013 + recent gate-remediator fixes mapped to ClaudeAgentOptions / can_use_tool / ClaudeSDKClient / include_partial_messages affordances. Managed-environment scope: no hooks/MCP additions; prevention is code-level only."` (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** None. M1.2 final items, M1.4, M2.3, M2.6, M3.5 already cover what this retrospective serves.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 7 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Seventh consecutive run with `maintain_current_flow` dominating Builder-runtime evidence across 7 analyzed sessions (3 devpulse + 3 todo-app + 1 todo-app-validation). No avoidable cost flags, no expensive agents, no chunk pressure.

**OPTIMIZE_IDEAS.md actions taken:** none.

### Recommended actions

**Status (2026-05-22):** All 10 prevention items from this run were incorporated into ROADMAP.md the same day. Open actions list closed.

| ROADMAP milestone | New items added |
| --- | --- |
| M1.4 (two-workspace validation) | Per-phase `allowed_tools` allowlists; deterministic CLI preflight probes |
| M1.5 (voice parity) | Migrate `query()` → `ClaudeSDKClient` async context manager |
| M2.1 (lifecycle completeness) | Audit early `break` in `receive_response()` |
| M2.3 (cost-aware execution) | First-class `RateLimitEvent` surface |
| M2.5 (architecture rubric) | Short-lived-session pattern; empty-response envelope convention; per-subagent `AgentDefinition.maxTurns` |
| M2.6 (autopilot) | `can_use_tool` callback (precondition); retry/cycle from typed SDK signals (precondition) |

Already-tracked cross-check items (unchanged on ROADMAP):

- `include_partial_messages=True` for in-flight telemetry → M2.3 line 108.
- Codex SDK lane → M1.2 line 46.
- Two-workspace validation rotation → M1.4 (the milestone itself).

Section D below is preserved as durable coding-agent reference (the *why* + *which SDK lever*); ROADMAP carries the trackable `[ ]` items.

### Coding-agent priority issues + SDK-grounded prevention

> This section is the durable answer to "what should the coding agent do so similar issues don't arise again". Read it on every new session before touching agent dispatch, session management, telemetry, or quality-gate code. Five priority patterns, each grounded in the official Claude Agent SDK Python reference (https://code.claude.com/docs/en/agent-sdk/python) and the Claude Cookbook (https://platform.claude.com/cookbook).
>
> **Scope:** prevention applies to the autonomous-builder *product* code (Claude Agent SDK + Codex SDK lanes). Hooks, MCP servers, subagents, and runtime callbacks are all valid product-side mechanisms — the product already uses them (workspace-boundary enforcement hook visible in IMP-006; `mcp__builder__*` tool surface; scaffold / code-gen / gate-remediator subagents). The "managed environment" caveat applies only to the Claude Code dev session running this audit — not to the product code being audited.

#### P0-1 — Agent picks wrong tool / fires multi-tool turns / loses prior-turn context

**Past bugs:** IMP-001 (context drop on intake follow-up), IMP-006 (scaffold shell heredoc instead of Write tool), IMP-007 (4 `task_dispatch` calls in one turn → pool exhaustion), IMP-009 (dispatch before scaffold completed), commit `cd05a09` (scaffold Write/Edit tools + `dontAsk` clarification, 2026-05-22).

**Recurrence:** 5 separate occurrences in past week; one in last 24h.

**Root cause:** Prompts described intent but did not pin SDK affordances. Model followed path of least resistance: shell over Write, parallel over serial, fresh state over threaded state.

**SDK-grounded fix:**
- **`can_use_tool: CanUseTool` callback** in `ClaudeAgentOptions`. Return `PermissionResultDeny(message="...", interrupt=False)` to block a tool call at the SDK boundary. Enforces: only one dispatch tool active at a time; no shell when Write is the right answer; preconditions met (scaffold complete) before dispatch tool fires. Stronger than prompt — the model literally cannot execute a denied tool.
- **`allowed_tools: list[str]`** scoped per phase in `ClaudeAgentOptions`. Scaffold: `["Write", "Read", "Bash"]`. Code-gen: `["Edit", "Bash", "Read"]`. Gate-remediator: `["Edit", "Bash", "Read", "Grep"]`. Never union across phases.
- **`AgentDefinition.maxTurns: int`** per subagent (camelCase in `AgentDefinition`). Caps runaway loops at the SDK boundary.
- **`ClaudeSDKClient` (not `query()`) for multi-turn flows.** Per SDK docs, `ClaudeSDKClient` retains conversation context automatically across `client.query()` calls in the same session — solves the IMP-001 class without manual `recent_context` threading. If `query()` is required, pass `continue_conversation=True` or `resume=<session_id>`.
- **`PermissionMode = "dontAsk"`** already in use per commit `cd05a09`. Keep the agent on this path.
- **Cookbook: Programmatic Tool Calling (PTC)** for orchestrations where tool ordering matters — Claude writes code that calls tools sequentially in the execution environment.

**Coding-agent rule:** Before adding a new subagent, write its `allowed_tools`, `maxTurns`, and (where serialization matters) a `can_use_tool` callback. The prompt is the soft constraint; these three are the hard constraints.

#### P0-2 — Long-lived DB sessions + streaming callbacks = pool exhaustion

**Past bugs:** IMP-010 (monitor task kept writing to rolled-back session), IMP-011 (SSE `Depends(get_db)` held pool connections), IMP-012 (dispatch session invalid after ~90s under sustained load).

**Recurrence:** 3 cascading bugs in same area (`agent_run_lifecycle.py` + `dashboard_api.py`).

**Root cause:** One SQLAlchemy session held across the full `runtime.run()` (4+ minutes), with background callbacks calling `flush()` on it. FastAPI `Depends(get_db)` kept connections alive for SSE client lifetime.

**SDK-grounded fix:**
- **`async with ClaudeSDKClient(options=...) as client:`** — `__aexit__` calls `disconnect()` and cancels background tasks deterministically. Replaces manual `try/finally` + `stop_monitor.set()` that IMP-010 fixed by hand.
- **SDK cleanup gotcha (official docs warning):** *"avoid using `break` to exit early when iterating messages — this can cause asyncio cleanup issues."* Audit every `async for message in client.receive_response():` site for early `break`; use a flag and drain.
- **Short-lived session per chunk/StreamEvent.** Open `async with get_session_factory()() as db:` inside the callback, flush+commit+close. Don't hold the dispatch session. (Already encoded in `.memory/patterns/` as `project_long_lived_session_pattern.md`; SDK docs validate.)
- **`include_partial_messages=True` → `StreamEvent`.** Each event carries `session_id`, `uuid`, raw stream data. Persist via short-lived sessions; never pipe through the dispatch session.
- **SSE endpoints: never `Depends(get_db)`.** Scope a session to the initial snapshot only; release before the long-lived `async for` loop. (Done in IMP-011; codified here as a rule.)

**Coding-agent rule:** Any DB write that happens during `runtime.run()` (i.e., inside an `on_chunk`/`receive_response` loop) uses a fresh short-lived session. The dispatch session stays idle during the run and is used only for the final result write after `runtime.run()` returns.

#### P1-3 — Lifecycle preconditions not enforced at phase boundaries

**Past bugs:** IMP-002 (code-gen dispatched into workspace with no ruff/pytest), IMP-004 (Recover button shown for non-recoverable states), IMP-008 (`git worktree add` against unborn HEAD), IMP-013 (orphan branch refused fast-forward merge — `unrelated histories`).

**Recurrence:** 4 bugs across 4 different phase boundaries.

**Root cause:** Each stage assumed prior stages set up state correctly. Failures happened deep in the call stack, not at the boundary.

**SDK-grounded fix:**
- **Deterministic CLI probes before `client.query()`** — `subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True)`, `shutil.which("ruff")`, `(workspace / "pyproject.toml").exists()`. Raise before dispatch; never let the agent attempt and fail.
- **Match `allowed_tools` to verified capability.** If ruff is missing, exclude `Bash(ruff:*)` from the allowlist. The model can't call what it can't see.
- **UI affordances gated on backend `can_X` signal.** Backend returns `{"can_recover": bool, "reason": str}`; frontend renders only when `can_recover=True`. Pattern already applied in IMP-004 commit `8799f1b`; generalize to every recoverable state.
- **`can_use_tool` callback** for runtime precondition gates. If the agent tries to use a tool against a path the workspace can't support (e.g., `Edit` against a path outside the workspace), deny with a specific reason.

**Coding-agent rule:** Every state transition has a precondition check at the entry. Cheap precondition check > expensive deep-stack failure recovery. UI affordances mirror backend `can_X` signals; never render a control whose backend would 4xx.

#### P1-4 — Telemetry without diagnostic context

**Past bugs:** IMP-003 (`metrics show` returns 0 tokens during in-progress runs), IMP-005 (`memory list` empty doesn't distinguish scope mismatch from genuinely-empty).

**Root cause:** Aggregation endpoints returned data without enough context for callers to interpret `0`/`[]`.

**SDK-grounded fix:**
- **`include_partial_messages=True`** in `ClaudeAgentOptions` to receive `StreamEvent` during `runtime.run()`. Extract token counts and POST to metrics endpoint as the run proceeds, not only at `ResultMessage`.
- **Persist `AssistantMessage.usage`** per turn — docs: each AssistantMessage carries `usage = {input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`.
- **`ResultMessage.model_usage`** for per-model breakdown: `{model_name: {inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow, maxOutputTokens}}`. Surface on the Metrics page in both lanes.
- **`RateLimitEvent`** is first-class in the SDK — `status: "allowed" | "allowed_warning" | "rejected"`, `resets_at`, `utilization`, `rate_limit_type` (`"five_hour" | "seven_day" | ...`). Surface to the dashboard so provider-limit blocked states have first-class telemetry, not stale-gate-failure noise. Maps to the CLAUDE.md provider-limit rule.
- **Empty-response convention:** every aggregation endpoint that can return empty/zero returns a `state` field (`"running" | "no_data" | "scope_mismatch"`) plus a `note` string. IMP-003 already added `active_runs` + `active_runs_note`; codify as a rule.

**Coding-agent rule:** Every endpoint that aggregates over time-bounded state has to answer "why is this empty/zero?" in the response envelope. Never return `{"data": []}` alone.

#### P2-5 — Quality-gate retry/cycle state machine

**Past bugs:** Commit `1153ec6` (`increment retry_count after remediation to avoid cycle detection`), commit `a0e8ca7` (gate-remediator agent + `remediation_possible` fixes).

**Why P2:** Single known instance, but blast radius is M2.6 autopilot — auto-recovery loops must be safe before autopilot ships.

**Root cause:** Cycle detection fired before the retry counter incremented; the first retry looked identical to the second.

**SDK-grounded fix (partial — pure state-machine logic, but typed SDK signals feed it):**
- Feed retry-vs-cycle decisions from typed SDK error signals, not string parsing:
  - **`ResultMessage.is_error: bool`**, `ResultMessage.errors: list[str] | None`, `ResultMessage.api_error_status: int | None`, `ResultMessage.subtype: str` (e.g. `"error_during_execution"`).
  - **`AssistantMessageError`** literal type: `"authentication_failed" | "billing_error" | "rate_limit" | "invalid_request" | "server_error" | "max_output_tokens" | "unknown"`.
- Increment the cycle-detection counter on the transition itself, never on the next transition.
- Add a synthetic-state test for every retry path before M2.6 autopilot ships.

**Coding-agent rule:** State machines that need cycle detection increment the counter on the transition; never on the next one. Decide retry-vs-cycle from typed SDK error signals.

#### Coding-agent prevention checklist (read this before writing new agent code)

1. **Tool affordances are SDK-pinned.** Every subagent has explicit `allowed_tools`, `maxTurns`, and (where serialization matters) a `can_use_tool` callback. Prompts are soft constraints; these are hard.
2. **`ClaudeSDKClient` over `query()` for multi-turn flows.** Async context manager handles cleanup deterministically. Never `break` mid-iteration.
3. **One short-lived session per DB write during agent runs.** Dispatch session stays idle during `runtime.run()`; result writes happen after it returns.
4. **Precondition check at every state-transition entry.** Probe deterministically (subprocess, `shutil.which`, `Path.exists()`) before `client.query()`. Match `allowed_tools` to verified capability.
5. **Aggregation endpoints carry diagnostic state in the envelope.** `state` + `note` on every endpoint that can return empty/zero.
6. **Typed SDK error signals over string parsing.** `ResultMessage.is_error`, `AssistantMessageError`, `RateLimitEvent`. Feed state machines from these.
7. **Increment cycle-detection counters on the transition itself.** Never on the next.
8. **No managed-app codebase mutations.** All Builder fixes land in the `autonomous-agent-builder` source repo; never in `/home/gurusharangupta/Builder-Workspace/*` or `/tmp/aab-workspaces/*`.
9. **Prevention is product-side.** The autonomous-builder uses hooks (`ClaudeAgentOptions.hooks: dict[HookEvent, list[HookMatcher]]`), MCP servers (`mcp_servers`), and subagents (`agents: dict[str, AgentDefinition]`) — these are stronger than prompt constraints because they enforce at the SDK boundary. A `PreToolUse` hook that blocks disallowed tools is a hard guarantee; a prompt asking the agent not to use them is a soft constraint. The "managed environment" caveat in the original prompt applies only to the Claude Code dev session running audits — not to the product code being audited.
10. **Cite the exact SDK option name when proposing a fix.** "Add a callback" is too vague; "add a `can_use_tool` callback that denies `Bash` when `Write` is the right tool, returning `PermissionResultDeny(message=...)`" is right.

#### Cross-reference: ROADMAP items each priority pattern protects

| Pattern | Roadmap items that will regress this if uncaught |
|---|---|
| P0-1 (tool / turn / context) | M1.2 Codex lane, M1.4 reverse-flow, M2.6 autopilot, M3.4 benchmarks |
| P0-2 (sessions / streaming) | M1.5 voice realtime, M2.1 resumability, M3.2 long-horizon, M3.3 multi-operator |
| P1-3 (preconditions) | M1.4, M2.1, M2.6 |
| P1-4 (telemetry context) | M2.3, M3.4 |
| P2-5 (retry state machine) | M2.6 autopilot — **blocking prerequisite** |

