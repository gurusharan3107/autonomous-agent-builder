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

