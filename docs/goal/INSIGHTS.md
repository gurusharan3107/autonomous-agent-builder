# Insights — Direction Audit Log

> Output surface for the `goal-audit` skill. Read [README.md](README.md) first.

Each entry is appended by `goal-audit` (project-local at [`.claude/skills/goal-audit/`](../../.claude/skills/goal-audit/SKILL.md)) and contains: **intent vs current focus** (alignment between recent sessions and STATUS/ROADMAP), **autoresearch focus candidates** (Builder CLI evidence mapped to [OPTIMIZE_IDEAS.md](../autoresearch/OPTIMIZE_IDEAS.md)), and **recommended actions**.

Invocation, edit scope, and the auto-trim of closed prior-entry actions live in the skill itself — see [SKILL.md](../../.claude/skills/goal-audit/SKILL.md). Closed recommendations are absorbed by [ROADMAP.md](ROADMAP.md) as `[x]` items; this file is the audit trail, not the completed-work checklist.

## Entries

## Closed audit runs (2026-05-21 → 2026-05-22 morning)

Earlier audit runs are summarized below; their full prose was removed once all recommendations either shipped or were tracked on [ROADMAP.md](ROADMAP.md). The audit trail (intent observations, autoresearch tables) lived in Git history before this compression.

| Run | Date | Verdict | Outcome |
| --- | --- | --- | --- |
| #1 | 2026-05-21 | drifting | Framework migration + goal-audit skill landed; M1.1 closed; driver-shape fix shipped (verified Run #2). |
| #2 | 2026-05-21 | drifting | `--since-run` mode shipped; HARD RULE block + frontmatter fixes; aggregator rewritten for 3-stream extraction. |
| #3 | 2026-05-21 | drifting (intentional) | `recent_prompts` (recency-ranked) replaced `top_prompts` (token-weighted); IMP-010 closed; pattern memory entry recorded. |
| #4 | 2026-05-21 | aligned | First aligned verdict; M1.2 in flight; Evidence Pointers updated through M1.2 closeout (cache_ratio = 18,530). |
| #5 | 2026-05-21 | drifting | Autopilot proposal captured → ROADMAP M2.6; after-fix sibling search → OPTIMIZE_IDEAS #11 + ROADMAP M3.5. |
| #6 | 2026-05-21 | aligned | Framework governance: Hard Rules 13 & 14 added to README; INSIGHTS→ROADMAP lifecycle documented. |

Builder-runtime evidence across all six runs: `maintain_current_flow` dominated; no avoidable cost flags; no expensive agents; cache_ratio consistently >5× bar. No OPTIMIZE_IDEAS reorder fired in any run — system stable.

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

**All actions closed.** 10 prevention items absorbed across [ROADMAP](ROADMAP.md) M1.4 / M1.5 / M2.1 / M2.3 / M2.5 / M2.6. Durable SDK-grounded rationale lives in ROADMAP items + git log.

---

## 2026-05-22 — Run #8 (since 7d, 72 Builder-related sessions analyzed)
<!-- collected_at: 2026-05-22T08:08:53.169396+00:00 -->

### Intent vs current focus

- **M1.4 is the active execution thread.** Session `f5adb72c` (T07:18:44): `"skip the codex lane for now, what next can we tackle"` → `"Can you continue with ROADMAP.md"` (T07:18:09) → `"sure go ahead"` (T07:21:41, 9.6M tokens, 78 api calls). Git status shows `post_ship_optimization.py` and `quality_gate_runner.py` modified (unstaged) — corroborates active M1.4 implementation work. STATUS.md reads "M1.4 in progress — per-phase allowlists + preflight probes ✓; forward/reverse workspace validation pending." This is accurate.
- **KB/context tooling is a new intent thread, adjacent to M2.2.** Session `b4395188` (T07:12:59): `"I think claude code, claude agents sdk, claude managed agents has a lot to provide, and we only use 10%, you use only those things that comes into your context..."` (217K tokens). Follow-up at T07:53: `"can we create a knowledge skill around this which keeps our workflow knowledge updated and maintained with the latest, like you had mentioned earlier SDK's get updated faster than KB's get created..."` (3.4M tokens, 24 api calls). Result: `kb-refresh` skill created at `.claude/skills/kb-refresh/` (untracked in git). A `hallmark` skill was also created at `.claude/skills/hallmark/`. Neither is a tracked roadmap item; both are dev-session tooling adjacent to M2.2's KB freshness objective.
- **Session opened with the docs/goal bootstrap protocol.** First substantive prompt: `"can you first check the AGENTS.md and docs/goal/README.md"` (session `4a6c8d4a`, T08:08:11), followed immediately by goal-audit invocation. Consistent with README.md Rule 1 (read-in-order). No stale claims at session start.
- **Managed app runs (todo-app) show Builder operating cleanly.** Approximately 20 sessions across `/tmp/aab-workspaces/*` workspaces with gate-remediator active (T07:01 in workspace `87e5c6bf`, T06:54 in workspace `87e5c6bf`). No avoidable cost flags in any session.

**Alignment verdict:** **aligned** — STATUS is accurate; M1.4 execution is the stated and observed focus; KB tooling work is consistent with M2.2 spirit.

**Suggested STATUS.md change:** Add a Recent Decisions line: `"2026-05-22 — kb-refresh skill (`.claude/skills/kb-refresh/`) and hallmark skill (`.claude/skills/hallmark/`) created in dev session. kb-refresh keeps global Claude tooling knowledge current against SDK changelogs; adjacent to M2.2 KB freshness objective. Dev-session tooling scope only."` (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** None. M1.4 and M2.2 already cover the active work threads.

### Autoresearch focus candidates

| Driver | Sessions in scope | OPTIMIZE_IDEAS map |
| --- | --- | --- |
| `maintain_current_flow` | 7 | no action |
| avoidable_cost_flags | 0 | — |
| agent_names_with_avoidable_tokens | 0 | — |

**No autoresearch action — system stable.** Eighth consecutive run with `maintain_current_flow` dominating all Builder-runtime sessions. No avoidable cost flags, no expensive agents, no chunk pressure across any analyzed session.

**OPTIMIZE_IDEAS.md actions taken:** none.

### Recommended actions

1. **Document kb-refresh and hallmark skill creation in STATUS.md Recent Decisions.** Both skills are untracked in git and not yet captured anywhere in the goal framework. Not a ROADMAP item (dev-session tooling); a STATUS.md Recent Decisions one-liner is sufficient. *Not yet on ROADMAP — genuine documentation gap.*
2. **Commit the uncommitted M1.4 changes before claiming `[x]` items.** `post_ship_optimization.py` and `quality_gate_runner.py` are modified but unstaged. Per Hard Rule 14, CHANGELOG update + commit must land before any M1.4 item is ticked `[x]`. *Already tracked as M1.4 `[ ]` items — no new ROADMAP item; confirming execution is in progress, not yet closeable.*
3. **No new ROADMAP items needed this audit.** M1.4 forward/reverse workspace validation (`[ ]` items) is the concrete next execution step. M2.2 already tracks KB freshness as a `[ ]` item. Nothing from this session falls outside existing roadmap coverage.

---

## 2026-05-22 — Architecture review against Claude Agent SDK rubric (ad-hoc, runtime-explainer-driven)
<!-- collected_at: 2026-05-22 (manual entry; not from goal-audit collector) -->

Source: review of [`autonomous-agent-builder-runtime-explainer.html`](../../autonomous-agent-builder-runtime-explainer.html) cross-referenced against KB article `2026-05-22-claude-agent-sdk-rubric` (SDK `0.2.85`). Manual entry — written outside `goal-audit` skill. Run #7 already mapped lifecycle/retry/max_turns/allowlists/`can_use_tool` to ROADMAP; this pass surfaces the **next layer**: cost telemetry, durable session, output normalization, deferred permissions.

### Gaps already covered by ROADMAP (no action)

| SDK lever | Roadmap item |
| --- | --- |
| `async with ClaudeSDKClient` context manager | M1.5 |
| `receive_response()` early-`break` drain audit | M2.1 |
| `can_use_tool` callback (block parallel/wrong-tool/precondition) | M2.6 |
| Typed retry (`AssistantMessageError`, `api_error_status`, `RateLimitEvent`) | M2.6 + M2.3 |
| `AgentDefinition.maxTurns` per subagent | M1.4 ✓ / M2.5 |
| Per-phase `allowed_tools` allowlists (never union) | M1.4 ✓ |
| Preflight probes before dispatch | M1.4 ✓ |

### New gaps not yet on ROADMAP

| # | SDK lever | Current state | Payoff |
| --- | --- | --- | --- |
| G1 | `include_partial_messages=True` → `StreamEvent` per-turn telemetry | Claude lane batches usage from `ResultMessage` at run end (explainer § Observability) | Closes Claude-vs-Codex parity on Agent Page Session rail; M2.3 prerequisite |
| G2 | `exclude_dynamic_sections=True` on `SystemPromptPreset` | Uses `preset:"claude_code"` + project setting_sources; dynamic cwd/memory/git in system prompt | Direct unlock for Tier-1 `cache_ratio > 5x` bar (pending) |
| G3 | `SessionStore` adapter (Python parity 0.1.64) + conformance harness | Local JSONL + `Task.session_id`; resume requires same `cwd` | Prerequisite for M3.2 (30+ day resume) and M3.3 (multi-operator) |
| G4 | File checkpointing (`/agent-sdk/file-checkpointing`) | Workspace isolation + git rebase only; `gate-remediator` "never delete files" enforced by prompt | Replaces prompt rule with SDK guarantee; cheaper auto-recovery |
| G5 | `permissionDecision="defer"` + `DeferredToolUse` | BLOCKED state halts whole task | Cleaner mid-run approval gates; pairs with M2.6 autopilot |
| G6 | `include_hook_events=True` → `HookEventMessage` stream | Hook events (workspace boundary, bash validation) logged out-of-band | Operator-visible block reasons in Agent Page; M2.4 contributor |
| G7 | `strict_mcp_config=True` | In-process `mcp__builder` + `mcp__workspace` registered without floor | Hardens M1.4 per-phase allowlist boundary against MCP drift |
| G8 | Claude lane `AskUserQuestion` adoption audit | Explainer lists Codex `item/tool/requestUserInput` but not Claude `AskUserQuestion` — asymmetric | Verify both lanes use native structured Q&A |
| G9/G10 | `skills` option + `disable_mode` | Prompt-shaped scaffolding instead of loadable skills | Compounding-knowledge story (M2.2); cuts skill description token cost |
| G11 | `thinking_display` per-phase | Adaptive thinking set; display control unclear | Agent Page UX polish |
| G12 | `PostToolUseHookSpecificOutput.updatedToolOutput` (replace tool output before model sees it) | PostToolUse logs only; noisy pytest/ruff/diff output reaches model in full | **Highest cost ROI**; feeds Tier-1 `avoidable_cost_flags: []` |
| G13 | `effort:"xhigh"` (Opus 4.7 deep reasoning) | `execution_policy.py` resolves low/medium/high | Carve-out for planner/designer on high-complexity items |
| G14 | Per-tool MCP permission policy (TS only) | N/A on Claude lane today | Track for TS port |
| G15 | Typed SDK error catch (`CLINotFoundError`/`ProcessError`/`CLIJSONDecodeError`) | `failure_diagnosis.py` exists; typed catch surface unclear | Tighter `FAILED` vs `CAPABILITY_LIMIT` discrimination |
| G16 | Bash permission hardening audit (SDK 0.2.85) | `validate_bash_argv` hook present | Re-audit allow rules against recent SDK tightening |

### Recommended actions (priority)

**P0 — Insert into Epoch 1 (M1.4 / M2.3 scope; low risk, immediate measurable payoff):**

1. **G2 — `exclude_dynamic_sections=True`**: single config flip; verifiable via `builder logs analyze` cache_ratio delta. Add as M2.3 item.
2. **G12 — `updatedToolOutput` truncation/normalization** for noisy tools (pytest, ruff, git diff). Highest cost ROI for Tier-1 `avoidable_cost_flags: []`. Add as M2.3 item.
3. **G1 — `include_partial_messages=True`** on Claude lane. Direct unblock of M2.3 "per-turn tokens visible in Agent page Session rail in both lanes" (currently Claude-lane-blocked).
4. **G7 — `strict_mcp_config=True`** alongside M1.4 per-phase allowlists. Same boundary; deterministic MCP set per phase.

**Proposed grouping:** new sub-milestone **M2.3.1 — SDK-native cost & telemetry levers** to hold G1/G2/G7/G12 together so they ride with cost-aware-execution work rather than waiting.

**P1 — Epoch 2 differentiators (front-load before M3.2/M3.3 attempts):**

5. **G3 — `SessionStore` adapter (Postgres-backed)** with conformance harness validation. **Hard prerequisite** for M3.2 and M3.3; resume-by-cwd brittleness blocks both today.
6. **G4 — File checkpointing** for `gate-remediator` and other scope-limited agents. Replaces prompt rule from `project_gate_remediator.md` memory with SDK guarantee.
7. **G5 — `permissionDecision="defer"` + `DeferredToolUse`** for risky mid-run actions. M2.6 autopilot precondition for security-flagged calls.
8. **G6 — `include_hook_events=True`** streaming on Agent Page. M2.4 "no internals leakage" contributor.

**P2 — Polish / capacity (Epoch 2-3):**

9. **G9/G10 — `skills` + `disable_mode`** for generated-app per-project skills; optimization-agent can encode reusable patterns as loadable skills.
10. **G8 — Audit Claude lane `AskUserQuestion` adoption** for parity with Codex `requestUserInput`. Update explainer table.
11. **G13 — `effort:"xhigh"`** policy carve-out in `execution_policy.py` for planner/designer on high-complexity items.
12. **G15 — Typed SDK error catch surface** in `failure_diagnosis.py`.
13. **G11 — `thinking_display`** per-phase policy.
14. **G16 — Bash permission hardening audit** against SDK 0.2.85.

### Verification gate

Before implementing any of G1–G16: `ctx7 docs /anthropics/claude-agent-sdk-python "<feature>"` against pinned SDK `0.2.85` — signatures move between minor releases.

### Suggested ROADMAP.md change

Add **M2.3.1 — SDK-native cost & telemetry levers** (or fold G1/G2/G7/G12 as four `[ ]` items under existing M2.3). Add **G3 SessionStore adapter** as an explicit `[ ]` prerequisite under M3.2 to prevent that milestone from being attempted on local-JSONL resume. HARD RULE: this skill does not edit ROADMAP.

---

## 2026-05-22 — Codebase-grounded revalidation of the ad-hoc rubric pass
<!-- collected_at: 2026-05-22 (manual entry; codebase-grounded follow-up to the ad-hoc rubric review above) -->

Source: `workflow knowledge read 2026-05-22-claude-agent-sdk-rubric` cross-referenced against `grep -rn <lever> src/`. Closes the verification gap in the prior ad-hoc entry: G1–G16 were mapped from the runtime-explainer + rubric only, without confirming codebase state. This pass validates each candidate before ROADMAP commitment.

### Validation table

| Gap | Codebase state | Action |
|---|---|---|
| G1 `include_partial_messages` | absent | Added to M2.3 (P0) — commit prior |
| G2 `exclude_dynamic_sections` | absent; `claude_runtime.py:247-248` confirms `preset:"claude_code"` + `setting_sources=["project"]` without the flag | Added to M2.3 (P0) — commit prior |
| G3 `SessionStore` adapter | absent; resume is local-JSONL + cwd-bound | Added as **HARD prerequisite** under M3.2 + dependency note on M3.3 |
| G4 file checkpointing | absent; gate-remediator relies on `.memory/project_gate_remediator.md` prompt rule | Added to M2.5 architecture rubric |
| G5 `permissionDecision="defer"` + `DeferredToolUse` | absent | Added to M2.6 |
| G6 `include_hook_events` → `HookEventMessage` | absent | Added to M2.4 |
| G7 `strict_mcp_config` | absent | Added to M2.3 (P0) — commit prior |
| G8 `AskUserQuestion` Claude-lane audit | **already adopted**: extensive use across `agent_tool_policy.py`, `agents/definitions.py` (7+ instructional sites + `allowed_tools` entries) | **No ROADMAP action**; prior recommendation withdrawn |
| G9/G10 `skills` + `disable_mode` | not searched this pass | Defer — P2 |
| G11 `thinking_display` | not searched this pass | Defer — P2 |
| G12 `updatedToolOutput` | absent | Added to M2.3 (P0) — commit prior |
| G13 `effort:"xhigh"` | `effort` plumbed via `execution_policy.py` and `orchestrator/agent_run_lifecycle.py:192,310` but only `low/medium/high/none` resolved; `xhigh` absent | Added to M2.5 with a complexity-threshold gate |
| G14 per-tool MCP permission (TS) | N/A on Python lane | No action |
| G15 typed SDK error catch | **partial**: `agents/runner.py:818-845` catches `CLINotFoundError`/`ProcessError`/`CLIJSONDecodeError`; `AssistantMessageError` literal + `api_error_status` absent | Narrowed scope of existing M2.6 typed-retry item to reference the gap explicitly; no new bullet |
| G16 bash permission hardening | `validate_bash_argv` hook present; re-audit deferred | Defer — P2 |
| `StopFailure` hook (rubric § Hooks) | mentioned only in a docstring in `services/provider_limits.py`; no hook registration | Augmented existing M2.3 `RateLimitEvent` item to require the hook |
| `can_use_tool` / `PermissionResultDeny` | absent | Already correctly listed `[ ]` in M2.6 |
| `async with ClaudeSDKClient` | `ClaudeSDKClient` referenced across runtime + agents; full `async with`-as-context-manager pattern needs follow-up grep | Already correctly listed `[ ]` in M1.5 |

### Completed-item SDK-debt audit (no new ROADMAP entries needed)

The following closed IMPs would be cleaner under SDK-native levers, but each is already covered by a pending ROADMAP item — no new entries required:

| Closed item | Current implementation | SDK-native version | Covered by |
|---|---|---|---|
| IMP-003 | `dashboard_metrics.py` diagnostic note for zero tokens | `include_partial_messages=True` → `StreamEvent` token deltas | M2.3 § G1 |
| IMP-006 | Prompt constraint in `agents/definitions.py` against Bash heredoc | `can_use_tool` callback returning `PermissionResultDeny` | M2.6 `can_use_tool` item |
| IMP-007 | `dispatch_lock.py` backend guard | `can_use_tool` callback at SDK boundary | M2.6 `can_use_tool` item |
| IMP-009 | HTTP timeout + pre-dispatch scaffold-running guard | `can_use_tool` precondition deny | M2.6 `can_use_tool` item |
| IMP-010 | `try/finally` + flush-error structlog in `agent_run_lifecycle.py` | `async with ClaudeSDKClient` `__aexit__` | M1.5 `ClaudeSDKClient` migration item |

### Verdict

Codebase validation **reduced** the open SDK-lever surface from 14 candidates (G1–G14 net of TS-only) to ~10 net additions (G1, G2, G3, G4, G5, G6, G7, G12, G13, `StopFailure` hook), and **withdrew** the standalone G8 recommendation. No completed work needs to be re-opened.

### Suggested ROADMAP.md change

All validated additions landed in ROADMAP this session (M2.3 × 4 P0 + StopFailure augmentation, M2.4 × 1, M2.5 × 2, M2.6 × 1 + typed-retry refinement, M3.2 × 1 + M3.3 dependency note). No further ROADMAP changes pending from this revalidation. HARD RULE: this entry is manual; no skill ran.

---

## 2026-05-23 — Run #9 (since 30d, 130 Builder-related sessions analyzed)
<!-- collected_at: 2026-05-23T06:49:29.445183+00:00 -->

### Intent vs current focus

- **Past 30 hours: the operating thread is `.claude/skills/` as the executable discipline layer, not direct ROADMAP execution.** The autoresearch skill was conceived ("now is the right time to create the autoresearch skill in project local .claude/skills using skill creator skill" — 2026-05-22T17:52:20 sess=`d05a2998`), iterated to a single entry + 3 lanes ("my entry point should be the skill only" — 2026-05-23T04:20:13 sess=`bbb15796`; "add ask use question first all the lane to choose, each lane should have its preflight and close out" — T04:22:35; "there can be at max 4 lanes, which holds true everytime not sometimes" — T04:24:36; "Inspect lane is not required" — T04:27:31), and bound to `docs/autoresearch/` freshness ("autoresearch skill is responsible of the docs/autoresearch folder is fully updaated and nothing is stale at all times as part of any lane" — T04:37:04). Project-local save/resume-session rebuilt after the user-global versions broke ("I have you to create project local save-session and resume-session command, save-session basically saves to .claude/session-data/ what we were working on" — 2026-05-23T05:10:58 sess=`bbb15796`).
- **A cache-break at 2026-05-22T17:43:39 sess=`d05a2998` is a deliberate pivot from M2.3 P0 cluster Tier B execution to autoresearch skill creation.** Surrounding context: `/plan` loaded `can-you-create-a-mighty-spark.md` ("Tier B (M2.3 P0 Cluster): SDK-Grounded Cost + Telemetry Fixes") at T16:14, then T17:52 "before that, i think now is the right time to create the autoresearch skill". When forced to choose, the operator picks durable governance before more shipped code.
- **Every skill encodes a workflow the user had to drive by hand once.** `knowledge-base`: "I think claude code, claude agents sdk, claude managed agents has a lot to provide, and we only use 10%, you use only those things that comes into your context, i think we need to have solution for [this]" (2026-05-22T07:12:59 sess=`b4395188`) → "can we create a knowledge skill around this which keeps our workflow knowledge updated and maintained with the latest" (T07:53:15). `roadmap-audit`: "the analysis you just did of analyzing the roadmap gaps against the workflow knowledge and validating that against the codebase to provide recommendation and adding new ones to insight" (2026-05-22T10:03:05 sess=`a21043fe`) → "use skill creator skill" (T10:04:09). Pattern: skills crystallize the second time a manual workflow proves valuable; the failure being prevented is context-blindness regression on the next pass.
- **STATUS Recent Decisions is in honest agreement with the past 24 hours for the *core* execution work.** All three major work items (autoresearch single-entry restructure, freshness sweep bundled script, save/resume-session project-local rebirth) and the M1.3 re-closure (commit `5e05b62`) have entries. No silent drift on shipped code.
- **M1.4 forward/reverse workspace validation has had no execution activity in 24–48 hours; the operating focus is M3.5 D1 Baseline substrate prep.** No `recent_prompt` in the past 36h names "forward-engineering on fresh workspace" or "reverse-engineering on existing workspace" or M1.4 explicitly; conversely ~20 prompts cluster on autoresearch skill restructure, freshness sweep, extraction debt, `iterations.html` sample-data cleanup, and save/resume-session. STATUS `Current Item In Flight` still reads "M1.4 in progress"; STATUS `Last Update` correctly says "Next: kick off Baseline lane" — the latter is the truer read of the operating lane.

**Alignment verdict:** aligned — STATUS is honest about shipped code; the operating-focus shift from M1.4 to M3.5 substrate prep is implicit in STATUS `Last Update` and explicit in `Recent Decisions`.

**Suggested STATUS.md change:** Update `Current Item In Flight` to: `"M3.5 D1 (N=5 baseline) substrate prep complete — autoresearch single-entry + 3 lanes + freshness sweep + M1.3 re-closure shipped 2026-05-23. M1.4 forward/reverse workspace validation paused pending M3.5 D1 kickoff."` (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** None. M1.4 and M3.5 are both already correctly tracked; the priority signal is a STATUS-level concern, not a ROADMAP restructure.

### Autoresearch focus candidates

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 8 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Ninth consecutive run with `maintain_current_flow` dominating Builder-runtime evidence across 8 analyzed sessions (5 `devpulse` + 1 `todo-app-validation` + 2 `todo-app`). No avoidable cost flags, no expensive agents, no chunk pressure. Per autoresearch Hard Rule 8 (`runtime_aggregates.session_scoped` must be `true`), the post-2026-05-23 telemetry-honesty fix (commit `a3354c2`) means these readings are genuinely session-scoped, not the pre-fix global-aggregate bleed — the `maintain_current_flow` signal is trustworthy in a way it was not before 2026-05-23.

**OPTIMIZE_IDEAS.md actions taken:** none.

**Prior-entry trim:** Run #8 Recommended Action #1 ("Document kb-refresh and hallmark skill creation in STATUS.md Recent Decisions") is partly open — the autoresearch/save-session work landed in Recent Decisions on 2026-05-23, but `knowledge-base` (the renamed successor to `kb-refresh`) and `hallmark` still have no Recent Decisions entry. Prior entry still has open actions; section left unchanged.

### Recommended actions

1. **Surface `.claude/skills/` as a first-class control surface in `docs/goal/`.** None of NORTH-STAR.md / ROADMAP.md / README.md / INDEX.md describe the skill suite as part of the goal framework. Future agents (and the user post-30-day gap) will not know that `autoresearch` / `goal-audit` / `roadmap-audit` / `knowledge-base` / `save-session` / `resume-session` *are* executable governance, not optional tooling. Recommended: one bullet under NORTH-STAR § Differentiators ("Executable governance via project-local skills") + an INDEX.md row pointing to `.claude/skills/`. *Not yet on ROADMAP — genuine documentation gap.*
2. **Add a 2026-05-23 STATUS Recent Decisions line covering `knowledge-base` + `hallmark` provenance.** Closes the open action from Run #8 #1. One sentence: `knowledge-base` supersedes the `kb-refresh` prototype as the global Claude-tooling KB owner; `hallmark` is a sibling design skill used to build `docs/autoresearch/iterations.html` and the runtime-explainer page. *Not on ROADMAP — STATUS-level documentation closure.*
3. **Resolve `.claude/skills/autoresearch-workspace/iteration-1/`.** Untracked artifact directory adjacent to the autoresearch skill; not surfaced in any `docs/autoresearch/*` index, not gitignored, no `SKILL.md`. Operator decision needed: track, ignore, or migrate under `docs/autoresearch/`. *Not on ROADMAP — small hygiene gap.*
4. **No autoresearch action.** Ninth `maintain_current_flow` run on now-session-scoped telemetry. Baseline / Iterate lane choice is the operator's next move, not this audit's. STATUS already says "Next: kick off Baseline lane."

---

## 2026-05-24 — Run #11 (since 30d; doc-gap retrospective — which mistakes were avoidable with better AGENTS.md / SKILL.md rules)
<!-- collected_at: 2026-05-24T06:45:00.000000+00:00 -->

### Intent vs current focus

- **Operator request is a doc-gap audit: "analyze session using goal audit, to know which mistakes happened were avoidable only if AGENTS.md or any other doc were updated with certain items."** (2026-05-24, current session). This is the second retrospective pass — Run #10 taxonomized failures by *recovery type* (deterministic vs model-backed); Run #11 taxonomizes by *prevention surface* (which doc was missing what rule that would have blocked the mistake pre-execution).
- **STATUS alignment: M3.5 substrate repair thread active; preflight/self-heal/seed-verify shipped.** Run #10 Action #2 (seed git-history check) is CLOSED — `seed_verify.py` implements `forbidden_commit_subject_patterns` via `git log --format=%s --all`, and `preflight.py:recipe 1` calls `seed_verify.py`. Run #10 Action #3 (contract regression tests) is HALF-CLOSED — `test_harness_contracts.py` exists (12 734 bytes) but is untracked (not committed). Actions 1, 4, 5 remain OPEN.
- **No new execution work since Run #10.** No new git commits beyond the P18 fix (commit `35a3ae4`). Operator is in a deliberate governance pass before re-starting the B–E baseline.

**Alignment verdict:** **aligned** — STATUS reflects reality; doc-gap retrospective is deliberate governance, not misdirection.

**Suggested STATUS.md change:** Add Recent Decisions line: `"2026-05-24 — Doc-gap retrospective (Run #11) landed in INSIGHTS.md. 5 prevention gaps identified: AGENTS.md missing harness-contract-first trigger + subprocess-capture rule; autoresearch SKILL.md missing composite-metric Hard Rule + analyze.json attribution warning; Run #10 Action #2 now confirmed closed (seed_verify.py). test_harness_contracts.py untracked — commit needed."` (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** none — the doc fixes are AGENTS.md/SKILL.md hygiene; not ROADMAP-scope feature work.

### Autoresearch focus candidates

761 sessions, 83h active, cache 98.2% across 30d. 15 Builder-related sessions in driver scope.

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 15 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

**No autoresearch action — system stable.** Eleventh consecutive run with `maintain_current_flow` dominating. Builder runtime unaffected by the autoresearch harness repairs (correct: harness tests *Builder behavior*, not Builder's own cost pattern).

**OPTIMIZE_IDEAS.md actions taken:** none.

**Prior-entry trim (Run #10):** Actions 1, 4, 5 still open per above — prior entry left unchanged.

### Doc-gap taxonomy — mistakes avoidable with better rules

Cross-map of P1–P18 + CURRENT blocker against docs that existed at incident time.

| Gap | Doc that was missing | Failures caused | Now remediated? |
|---|---|---|---|
| No "harness-contract-first" Required Trigger | AGENTS.md § Required Triggers | P1–P15 (8 patches, Class C) | Partially — `test_harness_contracts.py` exists but not wired into AGENTS.md as a trigger |
| No "subprocess stderr capture" coding rule | AGENTS.md § Codex Productivity Rules | Class B silent failures (3+ iters invisible) | Code fixed (`feature_check.log`); NO doc encodes the rule |
| No "per-iter abort on gate failure" Hard Rule in SKILL.md | autoresearch SKILL.md | 3 doomed iters $5/1.5h (Class E) | YES — Hard Rule 11 |
| No "seed capture protocol" checklist | autoresearch SKILL.md | P17 (missing deps), P18 (stale DB), CURRENT (git history) | YES — Hard Rules 12/13 + seed_manifest.json |
| No "composite metric single-dimension" principle | autoresearch SKILL.md | P16 CV=77.5% (Class D) | Code fixed (P16); NO Hard Rule encodes it |
| No "analyze.json attribution limit" warning | autoresearch SKILL.md Dead Ends / AGENTS.md | Ongoing telemetry blind spot (OPEN gap) | NO — only in memory as OPEN |
| No "in-flight process check at skill entry" rule | autoresearch SKILL.md | Operator had to manually kill loop (Class B) | YES — SKILL.md "Before anything" section |

**Two gaps remain completely un-encoded in any doc**: subprocess stderr capture rule (AGENTS.md) and the composite-metric single-dimension principle (SKILL.md). Every future agent on this repo can repeat both mistakes.

### Recommended actions

1. **Add subprocess stderr capture rule to AGENTS.md § Codex Productivity Rules.** Exact text: "Subprocess calls in harness, CI, and scripts: always use `capture_output=True`; write combined stdout+stderr to a named evidence file (`evidence_dir/feature_check.log` pattern). Never rely on `-q` flags or inherited fds on external tools called from non-interactive contexts." — caused Class B silent failures across multiple iters. Not on ROADMAP — genuine AGENTS.md gap. *Protects Differentiator #6 (cost-aware execution — silent failures are invisible cost drivers).*
2. **Add composite-metric Hard Rule to autoresearch SKILL.md § Hard Rules.** "Hard Rule 15: Composite must be a single uncorrelated dimension. Never multiply time × count × rate — correlated products amplify CV and produce negative/useless σ-floors. When in doubt: single metric is correct." Caused P16 (CV=77.5%, 2σ-floor=-3.19e9). Currently only in PROGRESS.md. Not on ROADMAP — genuine SKILL.md gap. *Protects Differentiator #6.*
3. **Add analyze.json attribution warning to autoresearch SKILL.md Dead Ends.** "analyze.json for sessions spawned by the autoresearch harness shows `prompt_count=1, agent_name=unknown` — this is a known Builder product gap (chat_session_id not threaded from harness into Builder DB). Do not use these fields for per-session cost attribution until the gap is fixed (tracked in memory as OPEN)." Not on ROADMAP — genuine SKILL.md gap. *Protects Differentiator #6.*
4. **Add "harness-contract-first" Required Trigger to AGENTS.md.** "Before writing any external script/harness that calls `builder` CLI: run the command live once, verify output shape, add field assertions to `.claude/skills/autoresearch/scripts/test_harness_contracts.py`. Never write extraction code against CLI output without a shape assertion that runs in `preflight.py --recipe 1`." Caused P1–P15 (8 of 18 patches; whole Class C). Not on ROADMAP. *Protects Differentiator #6.*
5. **Commit `test_harness_contracts.py` (untracked).** Run #10 Action #3 half-complete — file exists but git shows `?? .claude/skills/autoresearch/scripts/test_harness_contracts.py`. A file that prevents the whole P1–P15 class should be committed before re-baseline. *Already tracked as M3.5; commit closes it.*

---

## 2026-05-24 — Run #10 (since 30d, 760 sessions, 18 autoresearch patches analyzed; mistake-class audit + deterministic-vs-model-backed recovery taxonomy)
<!-- collected_at: 2026-05-24T05:46:06.096018+00:00 -->

### Intent vs current focus

- **Operator request is an explicit meta-audit: "where were mistakes made in autoresearch, what is the best way to recover, what type of issue requires deterministic script vs model-backed intelligence."** Prompt (2026-05-24T05:43:27, sess=`current`). This is a deliberate pause to categorize failure modes before restarting the B–E baseline, not a routine goal check.
- **Past 48 hours: entirely autoresearch substrate repair.** Session arc on 2026-05-23: `"what happened with the autoresearch baseline?"` (T13:56) → `"then what happened as part of baseline (B1-5)"` (T16:47) → `"i only cancelled since some fix was applied, can we run the baseline from fixture B?"` (T19:03) → `"yes cancel the inflight baseline, fix the issues"` (T21:03). Operator had to manually kill poll loops (T17:37–17:50) and cancel the run after it became clear the substrate was still polluted. ~$5 / 1.5h burned on 3 doomed iters before P17–P18 surfaced.
- **Process-awareness gap surfaced explicitly.** Operator: `"why were you not aware of this run?"` (T17:40) and `"i dont think start and save session requires process awareness, its the autoresearch skill"` (T17:42). Result: `lane_status.py` + `check_no_inflight_lane` preflight shipped to give the skill eyes on the OS. But the current blocker (seed git history pollution) still requires an operator-led re-snapshot decision that no script can make.
- **STATUS accurately reflects M3.5 substrate-prep focus.** Alignment confirmed by STATUS `Current Item In Flight` + `Last Update`. No quiet drift.
- **Blocker not yet on ROADMAP as a concrete `[ ]` item.** Seed git history pollution (7+ `feat: Add current time button` commits baked into HEAD) is described in CURRENT.md and PROGRESS.md but has no ROADMAP line or explicit decision record in STATUS Recent Decisions.

**Alignment verdict:** **aligned** — STATUS reflects reality; operator's audit request is deliberate governance, not misdirection.

**Suggested STATUS.md change:** Add Recent Decisions line: `"2026-05-24 — Autoresearch mistake-class audit landed (Run #10). Seed git history pollution identified as current structural blocker; requires operator-led re-snapshot decision (recapture from ~/Builder-Workspace/devpulse upstream vs hard-reset seed to pristine revision). 18 patches in 2 days confirmed the harness self-heals known gaps but cannot recover from substrate-identity failures — those need operator decision."` (HARD RULE: skill does not edit.)

**Suggested ROADMAP.md change:** Add one `[ ]` item under M3.5: `"Seed re-snapshot: verify seed git HEAD is pristine (0 past-agent commits in log) before any B–E baseline run. Decision: recapture from ~/Builder-Workspace/devpulse vs hard-reset seed to pre-agent revision."` Not yet on roadmap — genuine gap.

### Autoresearch focus candidates

Builder telemetry (60 sessions analyzed across 11 workspaces):

| Stream | Value | Sessions | OPTIMIZE_IDEAS map |
| --- | --- | --- | --- |
| recommended_next_change | `maintain_current_flow` | 60 | no action |
| avoidable_cost_flags | *(empty)* | 0 | — |
| agent_names_with_avoidable_tokens | *(empty)* | 0 | — |

Builder runtime is stable. The autoresearch harness (not Builder itself) was the source of all 18 patches. Builder `maintain_current_flow` continues because the autoresearch loop tests Builder's *behavior*, not its cost pattern — those are separate concerns.

**OPTIMIZE_IDEAS.md actions taken:** none — no driver met reorder threshold.

**Prior-entry trim:** Run #9 Recommended Actions: #1 (`.claude/skills/` as first-class surface in docs/goal/) — open; #2 (STATUS Recent Decisions for knowledge-base + hallmark) — open; #3 (autoresearch-workspace/iteration-1/ orphan) — open. Prior entry has open actions; section left unchanged.

### Mistake-class taxonomy + recovery routing

This run's primary output is a classification of the 18 autoresearch patches by failure type and recovery mechanism. Source: `docs/autoresearch/PROGRESS.md` patches P1–P18 + CURRENT.md blocker.

#### Class A — Environment / Substrate Identity (highest cost class: $5+/1.5h on 3 doomed iters)

| Patch | Root cause | Recovery type |
|---|---|---|
| P17: pytest-asyncio in working-tree but not HEAD | Seed captured after manual dep tweak; git clean didn't check | **Deterministic** — `check_seed_git_clean` preflight (now shipped) |
| P17: seed .venv missing jinja2 | Seed .venv not pre-populated; pip install ran but workspace was later overwritten | **Deterministic** — `check_seed_pytest_collect` preflight (now shipped) |
| P18: seed DB carries stale Builder state | `restore_seed` copied DB without wiping 11 tables | **Deterministic** — SQL DELETE on 11 tables (now shipped); schema-level, no judgment needed |
| **CURRENT: seed git history carries past-agent commits** | Seed captured AFTER prior fixture-A runs, not from pristine upstream | **Model-backed** — no script can determine "which revision is pristine"; requires operator to decide: hard-reset to pre-agent sha vs recapture from `~/Builder-Workspace/devpulse` |

**Rule:** if the check is "does file/dep/row X exist?" → deterministic. If the check is "is this the right version of reality?" → model-backed (requires intent + history reasoning).

#### Class B — Observability Blindness (caused silent failures to go undetected for multiple iters)

| Patch | Root cause | Recovery type |
|---|---|---|
| Silent stderr from subprocess | `subprocess.check_output` + `-q` flag; stderr inherited parent's fd | **Deterministic** — `run.py:run_feature_check` now writes `feature_check.log` with explicit stdout+stderr capture |
| No per-phase forensic trail | Evidence dirs not created until P-fix iteration | **Deterministic** — `evidence_dir/` per iter + `feature_check.log` pattern |
| In-flight lane not visible to skill | `ps -ef` not checked at session entry | **Deterministic** — `lane_status.py` + `check_no_inflight_lane` preflight (now shipped) |
| analyze.json: prompt_count=1, agent_name=unknown for autoresearch-spawned sessions | Builder's session attribution doesn't scope by spawn context | **Model-backed** — requires tracing how `chat_session_id` flows from autoresearch harness into Builder; can't be a grep |

**Rule:** if the fix is "capture this output surface" → deterministic. If the fix is "understand why this attribution is missing" → model-backed.

#### Class C — Data Contract Drift (caused 0-composite results or wrong gate verdicts)

| Patch | Root cause | Recovery type |
|---|---|---|
| P12: gate_pass_rate used wrong Builder CLI command | `builder board show` vs `builder task list`; different output shape | **Deterministic** — contract test asserting CLI output field exists |
| P15: metrics key `metrics["optimization"]` not `metrics["optimization_summary"]` | P12 fix missed a parallel site in run.py | **Deterministic** — unit test asserting key name at extraction point |
| P11: multiple similar schema mismatches (P1–P10) | Builder API/CLI contract drifted across versions with no harness-side tests | **Deterministic** — integration contract test suite against real Builder output; these all had binary assertions |

**Rule:** if the failure is "key X exists in JSON" or "CLI output has field Y" → deterministic. The whole class is detectable with `assert` or `jq`.

#### Class D — Statistical Measurement Error (caused useless 2σ-floor)

| Patch | Root cause | Recovery type |
|---|---|---|
| P16: composite = noncached × operator_turns × wallclock → CV=77.5%, 2σ-floor negative | Correlated dimensions multiply noise; product of 3 metrics amplifies variance | **Model-backed** — required statistical reasoning: "what am I trying to minimize?" and "which dimensions are correlated?". Answer (single metric: `noncached_plus_output_tokens`) was not derivable from a test or script. |

**Rule:** formula selection is a judgment call about measurement intent → always model-backed.

#### Class E — Autonomy Gap (caused 3 doomed iters + manual operator cancellation)

| Patch | Root cause | Recovery type |
|---|---|---|
| Per-iter abort missing | baseline.py ran all N iters even when feature_correct=False | **Deterministic** — strict per-iter gate in `baseline.py` (now shipped); threshold is binary (feature_correct ≠ True → abort) |
| Self-heal for known patterns (missing-module, uncommitted-working-tree) | These patterns are mechanical; safe to auto-fix | **Deterministic** — `self_heal.py` pattern catalog with pip-install + git-commit remediations (now shipped) |
| Self-heal for unknown patterns | New pattern, no catalog entry → `applied=False`, operator investigates | **Model-backed** — "is this pattern safe to auto-heal?" requires model judgment; false fixes are worse than no fix (stated explicitly in `self_heal.py` docstring) |
| Seed re-snapshot policy | Seed identity question cannot be delegated to a script | **Model-backed** — requires operator + model to inspect git history, pick pristine revision, and re-snapshot |

**Rule for autonomy boundary:** if the remediation has a known-good mechanical path (install X, delete Y rows, abort at threshold T) → deterministic. If the remediation requires "is this situation one I know how to fix safely?" → the model decides whether to apply or escalate.

### The meta-rule (applies across all classes)

**Deterministic script** = the predicate is enumerable at write-time (value exists, count ≥ N, key present, command exits 0). Safe to run headlessly for $0. False positives are caught by the next check; false negatives from a broken script are bounded.

**Model-backed intelligence** = the predicate requires understanding *intent* or *context* (which revision is pristine, is this pattern safe to auto-heal, what should the composite measure). No script can express "what was the intended baseline state before any agent touched it." False negatives here mean the agent applies a plausible-looking but wrong fix — cost is unbounded.

**When in doubt, don't auto-fix.** `self_heal.py`'s `applied=False` path is correct behavior, not a bug. The operator loop exists precisely for situations where the predicate isn't deterministic.

### Recommended actions

1. **Operator decision: seed re-snapshot path.** Either `cd ~/.seed/devpulse && git log --oneline` to find the last clean sha → `git reset --hard <sha>` → re-capture, OR recopy from `~/Builder-Workspace/devpulse` if that workspace is pristine. This is a model-backed decision (Class A, CURRENT blocker). *Not on ROADMAP — add as explicit `[ ]` item under M3.5 per Suggested ROADMAP.md change above.*
2. **Add seed git-history preflight to Recipe 1.** `check_seed_git_clean` catches working-tree dirtiness but not *history* pollution (past-agent commits in git log). Add a companion `check_seed_git_log_clean` probe: `git log --oneline | grep -c "^[a-f0-9]* feat:"` — if count > expected (0 for fixture B/C/D/E), warn and block. Deterministic; $0. *Not yet in preflight.py — genuine gap.*
3. **Add contract regression tests for harness-to-Builder API shape.** Classes B and C (8 of 18 patches) were all binary assertion failures against Builder CLI/API output. A `test_harness_contracts.py` that runs `builder task list`, `builder logs analyze`, `builder board show` against the live seed and asserts key shapes catches the whole class before any iter burns tokens. Deterministic; should run as part of `preflight.py:Recipe 1`. *Not yet tracked on ROADMAP.*
4. **Surface analyze.json attribution gap to Builder maintainers.** `prompt_count=1, agent_name=unknown` for autoresearch-spawned sessions blocks per-agent cost attribution (original telemetry gap from NEXT-SESSION.md). This is model-backed diagnosis — needs a traced investigation of `chat_session_id` flow from harness into Builder DB. *Not yet on ROADMAP; was noted in memory as OPEN.*
5. **Run `baseline.py --fixtures A --n 1` as autonomy-stack sanity check before re-snapshot.** Confirms self-heal + per-iter gate + preflight stack works end-to-end on fixture A (already stable). $1 / ~5min. If it completes clean, that's evidence the substrate tooling is correct and only the seed identity is wrong. *Next concrete action per CURRENT.md.*



## 2026-05-29 — Codebase-grounded ROADMAP revalidation (roadmap-audit, devpulse-validation-driven)

Trigger: operator request to bring `docs/goal/` up to date after a hermes-chrome-driven devpulse validation session. Each candidate was grepped against `src/` (adoption ≠ docstring mention). Skill edited `ROADMAP.md` + this file only; STATUS sync is recommended below (skill is forbidden from editing STATUS).

### Validation table

| ROADMAP item | Bucket | Evidence (`path:line`) | Action |
| --- | --- | --- | --- |
| M2.5 `AgentDefinition.maxTurns` per subagent | **already-present** | `agents/definitions.py` `max_turns=20` per subagent; `agents/runner_options.py:61` forwards `maxTurns` | ticked `[x]` (duplicate of M1.4 closure) |
| M1.5 migrate `query()` → `ClaudeSDKClient` ctx mgr | **partial** | migrated: `agents/runner.py:690` `async with ClaudeSDKClient(...)`; gap: `claude_runtime.py:265` bare `sdk_query()` (chat path) | narrowed to the `claude_runtime.py` chat path |
| M2.1 audit `receive_response()` early `break` | **already-safe** | single site `agents/runner.py:692`, no early `break` | downgraded P0 → hardening (codify-as-rule only) |
| M2.6 `can_use_tool` enforces subagent boundaries | **partial** | deny exists for chat tools `agent_tool_policy.py:52` (via `routes/agent.py:702`); subagent path `claude_runtime.py:236 _auto_approve` always allows | narrowed to "extend deny to subagent path" |
| M3.2 G3 `SessionStore` adapter | **confirmed-missing** | `grep SessionStore src/` → 0 hits | kept `[ ]`; revalidated genuinely absent (HARD prereq for M3.2 + M3.3) |
| M1.1 IMP-014/015/016/017 | **confirmed-missing (new)** | devpulse validation this session (observability stale-error rec; `type=feature` shown as IMPROVEMENT; chat mis-routes builder asks to app backlog; no item remove/cancel) | added earlier this session |
| M2.1 +2 lifecycle features (auto-complete feature / backlog-item) | **confirmed mis-filed** | were `type=feature` in the devpulse backlog; builder-lifecycle behavior | added earlier this session |

### Net effect

- Two phantom-work items retired from the active backlog: `maxTurns` (done) closed; the async-break audit downgraded from P0 to preventive hardening.
- Two P0 items narrowed to the actual remaining gap (chat-path `query()` migration; subagent-path `can_use_tool` deny) — saves re-implementing already-shipped halves.
- The genuinely-open extreme-priority set is now honest: **G3 `SessionStore`** (biggest unlock; HARD prereq), the **subagent `can_use_tool` deny extension** (cheap; deny mechanism already exists), and the **M1.1 IMP-014/016/017** operator-trust/integrity defects.

### Recommended actions (STATUS — operator-owned, skill cannot edit)

1. STATUS Recent Decisions: add a 2026-05-29 line recording this revalidation (maxTurns closed; query-migration + can_use_tool narrowed to partial; async-break downgraded; SessionStore revalidated absent).
2. STATUS `Last Update`: refresh to 2026-05-29.
3. No EVALUATION.md change required — no tier bar moved.
