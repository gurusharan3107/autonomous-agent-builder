# Agent Quality Tuning Loop

## Overview

This workflow is the repo-owned loop for improving the quality and context
efficiency of work produced by `autonomous-agent-builder`.

Use it when the tuning target is builder behavior itself rather than only a
single user-visible bug. Typical targets include:

- wrong or wasteful tool selection
- poor model selection
- repeated context overload
- weak prompt or instruction shaping
- bad phase routing
- unnecessary subagent use
- weak or missing runtime evidence

The workflow stays aligned to ~~MISSION.md~~:
the user should not need to manage workflow, tools, models, or context by hand.

Use [system-improvement-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/system-improvement-loop.md)
instead when the primary problem is a concrete product defect, stale UI,
backend/orchestrator regression, or other user-visible failure that must first
be reproduced through the live product surface.

## Core Principle

Tune from evidence, not from instinct.

Start with a real builder session, reduce it to the smallest useful quality
signals, find the smallest correct owner surface, change that surface, then
rerun the same style of work to prove the behavior improved.

## When To Use

- the builder produces low-quality or wasteful outputs
- the agent uses the wrong tools or too many tools
- the model choice is too weak or too expensive for the task
- prompts or `CLAUDE.md` guidance look bloated, duplicated, or mis-scoped
- a phase agent or subagent is doing work that should belong to the main lane
- `builder logs analyze` shows context-efficiency warnings or suspicious tool
  patterns
- OTEL or builder telemetry needs to be used to understand agent behavior

## Workflow

### 1. Choose A Concrete Tuning Subject

Use one bounded subject:

- one builder session
- one builder run
- one task flow
- one repeated workflow such as planning, design, implementation, verification,
  or reverse engineering

Do not start with "make the agent smarter" as an unbounded ask.

## 2. Collect Builder-Owned Evidence First

Inspect the repo-local evidence before changing prompts or agent definitions.

Use:

- `builder agent sessions --json`
- `builder agent history --session <id> --json`
- `builder agent runtime show --json`
- `builder agent runtime probe --json`
- `builder logs analyze --session <id-or-prefix> --json`
  - add `--full` only after the compact summary identifies a specific prompt,
    tool, or telemetry gap that needs raw detail
- `builder metrics show --json`
- `builder logs --error`
- `builder logs --info --compact --json`

Use `builder metrics show --json` to choose the current active optimization
target. Historical raw, cached, non-cached-plus-output, and top-driver totals
remain audit evidence, but `recommended_next_change` must follow active recent
avoidable flags and active top drivers. Use `builder logs analyze --session
<id-or-prefix> --json` to explain a specific prompt or run. If metrics and
session analysis disagree, treat metrics as the product-wide active ranking and
the session analysis as diagnostic evidence for that lane.

For forward-engineering and reverse-engineering optimization, first verify the
run was driven through the dashboard-first contract. If lifecycle actions were
performed through mutating CLI commands, the evidence does not prove product
quality; rerun through the Agent page before tuning prompts or models.

Look for:

- model used
- effort and thinking budget used
- tools used and in what order
- repeated or broad retrieval
- duration, cost, and stop reason
- delegated subagent usage
- context-efficiency warnings
- explicit observability gaps
- selected runtime, provider, model, effort, telemetry source, runtime-native
  telemetry health, and builder-product telemetry health
- deterministic recommendation codes, evidence, severity, and next action

If OTEL export is enabled, use it as a strengthening lane for traces and span
timings. Do not skip the builder-owned evidence lane.

## 3. Use Vendor Docs Only As Bounded Runtime-Advisory Input

When the tuning question is specifically about a runtime SDK or harness
contract, use the matching vendor documentation as bounded advisory guidance.
Use Claude docs for Claude Code or Claude Agent SDK behavior, and official
OpenAI/Codex docs for Codex runtime behavior.

Good questions:

- which SDK feature best fits this runtime need
- which permission or approval pattern matches the SDK contract
- whether a session, subagent, hook, or tool pattern is aligned with the SDK
- whether a telemetry or observability pattern matches documented usage
- whether Codex subscription auth, app-server events, or request-user-input
  behavior supports the desired product integration

Guardrails:

- treat vendor docs as docs-grounded advisory only
- require an exact docs page or section for every accepted claim
- use it for SDK-pattern questions, not for general architecture or product
  design
- do not accept it as proof of what this repo currently does
- if the question is about builder runtime behavior or implementation truth,
  escalate back to repo evidence, code review, and tests

Do not use vendor docs for:

- runtime validation of this repo
- code generation
- repo-specific architecture ownership decisions
- broad product quality judgments that are not specific to the selected runtime

Codex SDK / OpenAI token tuning must use the official OpenAI docs as the
bounded advisory lane before changing prompt, tool, cache, state, or telemetry
behavior:

- GPT-5.5 / reasoning guidance: keep model-backed tool orchestration, use
  `previous_response_id` or returned output items for state, set reasoning
  effort deliberately, put most tool-specific guidance in tool descriptions, and
  use compaction intentionally for long-running agents.
- Prompt caching: put stable repeated content at the beginning of the request,
  dynamic user/project evidence at the end, use a consistent cache key where
  the SDK surface supports it, and monitor cached-token counts.
- Tool search / deferred tools: for large tool catalogs, prefer deferred tool
  loading where supported so the model sees only the high-level namespace first
  and cache preservation is not destroyed by loading every function schema.
- Conversation state: raw prior input can still appear in token accounting when
  chaining responses, so product telemetry must separate raw input, cached
  input, output, and non-cached-plus-output totals.
- Compaction: compact at meaningful workflow boundaries, not after every turn,
  and preserve completed actions, active assumptions, IDs, tool outcomes,
  blockers, and the next concrete goal.

Current optimization direction for the SDK-backed Agent page:

1. Do not make natural judgment prompts deterministic to save tokens.
2. Keep operator intent and tool choice model-backed.
3. Reduce actual prompt/tool waste first: duplicate context, raw command output
   reinjection, broad retrieval, and over-eager tool catalogs.
4. Keep bounded Builder metrics/logs/observability evidence available as compact
   context or tools the model can choose.
5. Show raw tokens, cached tokens, cache ratio, and non-cached-plus-output tokens
   in the dashboard before judging whether a turn was expensive.
6. Re-run the same live Agent-page lane and compare raw, cached,
   non-cached-plus-output, chunk pressure, repeated retrieval, blockers, and
   visible operator burden.
7. Persist Agent-page chat `run_status` token usage as separate input, output,
   cached, raw, and non-cached-plus-output fields; do not collapse SDK usage
   into a single output bucket before Metrics or Observability consume it.

Claude Agent SDK tuning must use the official Claude Agent SDK docs as the
bounded advisory lane before changing `sdk=claude` prompts, tools, permissions,
context, sessions, or telemetry:

- Agent loop: Claude evaluates the prompt, decides which tools to call, receives
  tool results, and repeats until completion. Keep operator intent/tool choice
  model-backed for judgment work; tune `max_turns`, `max_budget_usd`, model, and
  effort rather than replacing the loop with deterministic routing.
- Context and caching: system prompt, tool definitions, conversation history,
  tool inputs, and tool outputs all consume context. Stable repeated content is
  prompt-cached; large tool outputs and long sessions still create context
  pressure. Persistent rules belong in `CLAUDE.md` / project settings, not in
  one-off prompts that compaction may summarize away.
- Tool surface: use narrow `allowed_tools`, `disallowed_tools`, and
  `permission_mode`; prefer tool search for large MCP/custom tool catalogs, but
  load small tool sets directly when that is simpler and faster.
- Approvals and questions: for interactive products, use the SDK approval/user
  input flow (`canUseTool` and `AskUserQuestion`) so the model asks necessary
  product questions and the dashboard renders the user's choices. If a `tools`
  array restricts capabilities, include `AskUserQuestion` when clarifications
  are allowed.
- Permissions and hooks: hooks run before permission callbacks and can block,
  transform, or add context around tool calls. Use hooks for deterministic safety
  policy; use the model loop for intent, diagnosis, synthesis, and tool choice.
- Subagents: use subagents for focused isolated subtasks, parallel evidence, or
  specialist instructions. Restrict their tools; rely on their final summary to
  keep the parent context lean.
- Cost and telemetry: read usage and cost from result messages, including error
  results. Track input, output, cache creation, and cache read tokens
  separately. Treat SDK `total_cost_usd` as an estimate; use Builder metrics and
  authoritative provider usage for final accounting.
- OpenTelemetry: export structural spans/metrics/logs for model requests, tool
  calls, token counts, duration, failures, and approval decisions. Keep raw
  prompts, tool arguments, tool output bodies, and raw API bodies off by default
  unless a narrow debugging case explicitly requires them.

Official Claude docs to check for this lane:

- `https://code.claude.com/docs/en/agent-sdk/agent-loop`
- `https://code.claude.com/docs/en/agent-sdk/claude-code-features`
- `https://code.claude.com/docs/en/agent-sdk/user-input`
- `https://code.claude.com/docs/en/agent-sdk/permissions`
- `https://code.claude.com/docs/en/hooks`
- `https://code.claude.com/docs/en/agent-sdk/tool-search`
- `https://code.claude.com/docs/en/agent-sdk/subagents`
- `https://code.claude.com/docs/en/agent-sdk/cost-tracking`
- `https://code.claude.com/docs/en/agent-sdk/observability`

## 4. Classify The Failure

Classify the tuning need before editing anything:

- prompt shaping problem
- owner-surface duplication problem
- tool allowlist or permission problem
- phase routing problem
- intent-routing or feature-chat convergence problem
- subagent boundary problem
- model selection problem
- knowledge or retrieval placement problem
- observability gap
- target-app environment or diagnostic-script gap

One session may show multiple symptoms, but choose one primary failure first.

## 5. Map To The Correct Owner Surface

Fix the narrowest correct surface:

- `CLAUDE.md` for runtime contract and repo-specific invariants
- `docs/references/phase-model.md` or phase docs for phase/tool boundary rules
- agent definitions or runner wiring for model/tool/subagent behavior
- `src/autonomous_agent_builder/agents/execution_policy.py` for model, effort,
  subagent, budget, or context strategy changes
- builder-owned knowledge docs for durable retrieval guidance
- target-app scripts or CLIs when the app under construction needs a
  deterministic `dev`, `test`, `lint`, `build`, `doctor`, or `smoke` command
  for builder-owned verification
- quality-gate docs when the failure should become a standing review rule
- logs/observability surfaces when the real blocker is missing evidence

Do not spread one tuning decision across prompts, docs, and code if one owner
surface is enough.

For post-ship optimization, preserve the owner lane from Metrics and
Observability recommendations. A generated-app shipment may refresh app-local
SDK guidance or run deterministic app verification, but it must not launch a
model-backed optimization-agent run to handle Builder-owned residuals such as
agent-chat token budget, bounded retrieval, telemetry instrumentation, or
runtime error trends. Defer those residuals to Builder source work so the
generated-app lane stays seamless and does not show fake or owner-mismatched
active work after the feature ships.

Treat higher model effort as a last-mile knob. Check the prompt contract,
tool boundary, compact evidence, and verification loop before increasing
effort or moving a lane to a stronger model.

## 6. Keep The Tuning Change Bounded

Prefer small, testable changes such as:

- tightening an allowlist
- reducing or restructuring loaded instructions
- moving repeated guidance out of the prompt and into the right retrieval doc
- changing the model for one agent lane
- removing an unjustified subagent
- adding one explicit decision rule for a phase
- exposing one more compact signal in builder-owned telemetry

Avoid broad "rewrite the agent prompt" edits without a precise failure claim.

## 7. Re-run The Same Kind Of Work

Re-run the same task class or session flow and compare:

- output quality
- tool count and relevance
- context-efficiency signals
- cost and duration
- need for subagents
- user-facing burden
- whether Metrics and Observability now expose one clear next optimization
  decision without raw database inspection

The goal is not only "did it still work?" but "did it work with less wasted
context and less operator burden?"

## 8. Promote Durable Rules

If the tuning lesson is likely to recur:

- update a quality gate
- update a workflow
- update `CLAUDE.md`
- update a repo knowledge doc

If the lesson is session-specific only, keep it out of the durable owner docs.

## 9. Record Remaining Gaps Honestly

If the evidence is incomplete, say so explicitly.

Examples:

- builder history is sufficient but OTEL traces are still unavailable
- tool events are visible but prompt content export is intentionally disabled
- model choice improved but phase-level permissions still need follow-up

Do not pretend the lane is tuned if the missing evidence still hides the real
failure mode.

## Default Checklist

- [ ] Chose one bounded tuning subject
- [ ] Captured builder-owned session/log evidence
- [ ] Captured metrics and observability JSON when optimizing runtime behavior
- [ ] Used the Claude docs assistant only when the question was SDK-specific and docs-citable
- [ ] Classified the primary failure mode
- [ ] Mapped the issue to the correct owner surface
- [ ] Applied the smallest correct tuning change
- [ ] Re-ran the same task class or flow
- [ ] Compared quality, cost, context, and tool behavior
- [ ] Confirmed deterministic recommendations stayed rule-backed and visible in
      one tabbed Recommendations panel
- [ ] Promoted only the durable lesson into docs or gates
- [ ] Reported remaining observability or evidence gaps

## Common Anti-Patterns

- tuning from prompt taste instead of real session evidence
- mixing several failure categories into one large speculative edit
- assuming a subagent improves quality without proving net context savings
- adding more instructions when the real problem is wrong tool permissions
- treating telemetry export as complete product understanding
- treating the Claude docs assistant as implementation truth for this repo
- fixing one bad session with an oversized permanent prompt
- fixing natural Agent-page feature requests by adding more broad keywords to
  the intent matcher before checking live SDK behavior, session continuity,
  tool context, and ResultMessage/run telemetry

## Related Docs

- ~~MISSION.md~~
- [agent-quality.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/agent-quality.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md)
- [system-improvement-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/system-improvement-loop.md)
