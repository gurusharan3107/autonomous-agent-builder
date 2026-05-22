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

**All actions closed.** 10 prevention items absorbed across [ROADMAP](ROADMAP.md) M1.4 / M1.5 / M2.1 / M2.3 / M2.5 / M2.6. Durable SDK-grounded rationale (P0-1…P2-5 patterns) extracted to [`docs/references/coding-agent-prevention.md`](../references/coding-agent-prevention.md).

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

