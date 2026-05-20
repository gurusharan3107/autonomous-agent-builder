---
title: "SDK-backed Agent page agent rubric"
tags: ["agent-page", "runtime", "sdk-backed", "rubric"]
doc_type: "rubric"
created: "2026-05-11"
---

# SDK-Backed Agent Page Agent Rubric

## Purpose

Use this rubric to decide what the SDK-backed Agent page agent can do, what it
must ask for, and what it must not own.

This rubric is the product contract. Code evidence below is implementation
traceability, not the source of truth. If the current implementation disagrees
with the rubric, classify the mismatch as a bug or explicit product decision.

The SDK-backed Agent page agent is the durable worker lane behind the Agent page.
It runs through the selected runtime harness, records the auditable transcript,
and publishes Builder-owned run evidence. It is not a second owner for Builder
product semantics.

## Runtime Scope

The Agent page chat route resolves the active runtime for each turn, builds the
prompt, runs the selected runtime, streams assistant output, records tool events,
and writes a final `run_status` event with runtime, token, cost, SDK session, and
observability evidence.

Streaming must still respect the user-visible transcript boundary. Runtime-native
progress events, tool events, and run status can appear while a run is active,
but draft transport text that is not yet the settled assistant answer must not be
rendered as operator-facing transcript content. This matters most for
`codex_sdk`, where app-server deltas can contain draft planning text before the
final assistant message is complete.

Active-run history refresh must preserve the already-mounted Conversation
timeline. Recovery polling for missed SSE events may update items, status,
runtime, and token rails, but it must not clear the transcript into a loading
state on every interval while the SDK-backed run is still active.

Only one run may be active for a chat session. The run slot must be reserved
before a new user message is persisted so a rejected concurrent request cannot
leave an operator-visible prompt that no runtime will answer.

Runtime selection is future-run-only. Switching from Claude Agent SDK to Codex
SDK, or back, controls the next Agent turn and dispatch target. It must not
rewrite historical task, run, metric, observability, memory, knowledge, backlog,
or approval attribution.

## Can Do

| Capability | Rubric | Code evidence |
| --- | --- | --- |
| Chat from the Agent page | Accept a user message, append it to the canonical chat session, start one active run, and stream output back to the Agent page without leaking SDK-specific draft reasoning into the visible transcript. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `agent_chat`, `_run_chat_turn`, `chat_stream` |
| Keep active runs visible | While a chat or delegated SDK-backed run is active, the Conversation timeline stays mounted and the operator sees the existing thread plus running state. Missed-event polling is quiet; it must not flash `Loading agent transcript...` between polls. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) `loadHistory`, active-run polling effect |
| Answer visible blocking cards inline | Pending structured questions and visible approvals stay inline in the Conversation timeline, not in a modal dialog. The operator should not need to know the card's internal event type, but every visible control on the card must resolve through the canonical `/agent/chat/respond` path. The bottom composer may submit text responses, and structured choice rows must submit directly when clicked. Structured choices should render readable operator labels, such as `Start now` and `Hold`, not internal payload objects or lifecycle terms. If a model-backed assistant answer asks whether Builder should start, proceed, or hold delivery work, the Agent page must convert that permission request into the same inline question/approval surface. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) `pendingBlockingItem`, `pendingQuestionOptions`, `submitQuestion`, `submitApproval`; [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_append_assistant_requested_question_if_needed`, `_serialize_event` |
| Start a clean thread | `New thread` clears session, task, and run URL state, detaches stale voice transcript bindings, stops active voice refresh, and opens an empty transcript. A later refresh must not rehydrate the detached session unless the operator explicitly opens it. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) `clearSession`, `detachedVoiceSessionIdsRef` |
| Resume sessions | Continue a persisted SDK session when `sdk_session_id` exists, while keeping the Agent page transcript as the visible user surface. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `ChatHistoryResponse`, `_run_chat_turn` |
| Use repo retrieval | Read project files and use `Read`, `Glob`, `Grep`, and repo-safe `Bash` when direct evidence is needed. | [`definitions.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/definitions.py) `AGENT_DEFINITIONS["chat"]` |
| Use Builder product tools | Use Builder MCP tools for Board, task, backlog, KB, and memory access through canonical surfaces. | [`definitions.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/definitions.py) chat tool list |
| Navigate Builder dashboard | Treat explicit UI navigation controls as dashboard events. Typed operator prompts that ask to inspect or navigate should still enter the selected SDK runtime so the model can interpret intent and choose the appropriate product action or ask a structured question when unclear. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_run_chat_turn` |
| Continue current Board work | Dispatch the current dispatchable Board task through Builder's normal task-dispatch path when the operator asks to start, continue, run, or finish the remaining sprint task. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) continuation guards and `_first_dispatchable_task`, [`tasks.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/tasks.py) `_run_dispatch` |
| Interpret ready-delivery follow-ups | When ready Board work exists and the operator uses natural wording that is not a read-only status, documentation, feature-spec, or explicit sprint-planning request, keep the turn model-backed. The selected runtime must inspect Builder state, decide the next tool chain, and may dispatch the exact ready task through Builder tools without requiring the operator to use magic phrases such as backlog, sprint, task id, or dispatch. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_general_chat_prompt`, `_run_chat_turn`, `mcp__builder__task_dispatch` permission branch |
| Ask structured questions | Use `AskUserQuestion` for bounded operator choices and persist answer cards in the Agent page timeline. Runtime-native question text is operator-facing UI, so persisted cards must render plain product wording even if the runtime supplied internal terms such as backlog, sprint, lifecycle, bounded, raw/full logs, chunk, or token pressure. | [`definitions.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/definitions.py) chat and init-project tools; [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_operator_safe_question_payload` |
| Report status through the model | Let the selected SDK runtime interpret read-only Board, sprint, backlog, blocked-task, recovery, approval, and task-count prompts, then answer from bounded Builder state. Natural operator phrasings such as "what's left in the backlog?" and "is anything actually blocked?" must stay model-backed; the model can use compact Builder tools/context and ask a structured question if the status target is unclear. When backlog features are done but Board verification/recovery tasks remain, say both facts instead of calling queued Board work open backlog work. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_message_requests_read_only_status`, `_general_chat_prompt`, read-only Builder tool permission |
| Plan and spec features | Run requirements/bootstrap and feature-spec flows, including structured backlog-ready output when scope is ready. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `_init_project_chat_prompt`, `_feature_spec_chat_prompt` |
| Dispatch explicit continuation | Dispatch through Builder task tools only when the user clearly requests autonomous continuation and the request is not ambiguous. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `mcp__builder__task_dispatch` permission branch |
| Produce run evidence | Emit final status with turns, max turns, tokens, cost, SDK session id, duration, stop reason, and observability. Agent Run trace should preserve runtime/provider attribution for historical rows and may collapse adjacent uninformative tool-use events into one counted timeline entry while leaving raw events available in the full trace lane. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) final `run_status` payload; [`task_activity.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/task_activity.py) activity timeline metadata |

## Requires Approval Or Operator Input

| Situation | Required behavior | Code evidence |
| --- | --- | --- |
| Non-read-only tool use | Create a visible `tool_approval_request`, wait for allow/deny, and continue only with the approved input. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `can_use_tool`, `respond_to_chat_event` |
| Pending requirement decision | Create an `ask_user_question` card instead of burying choices in prose. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `AskUserQuestion` handling |
| Ambiguous continuation | Ask for the missing decision or present the deterministic next step; do not silently dispatch. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) continuation guards |
| Bulk backlog/Board mutation request | Let the selected runtime judge intent from bounded Builder state, and let approved product/tool paths execute clear operator intent. The model must inspect broad bulk targets first and cannot claim mark, clear, delete, approve, deny, dispatch, or ship effects until an allowed tool and visible approval/prepared-action path confirms the exact target and consequence. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) chat prompt and `tool_approval_request` branch |
| Tool approval answer | Persist the operator answer and resolve the pending run if the run is still waiting. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `respond_to_chat_event` |

## Cannot Do

| Prohibited behavior | Reason | Code or contract evidence |
| --- | --- | --- |
| Redefine Builder lifecycle semantics | Backlog, Board, task states, approvals, gates, recovery, memory, knowledge, metrics, and observability are Builder-owned product contracts. | [`claude-agent-sdk.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md) expectations and fail signals |
| Mutate repo-local KB or memory by direct file or database writes | Durable knowledge and memory writes must go through Builder publish surfaces. | [`claude-agent-sdk.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md), [`definitions.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/definitions.py) chat prompt |
| Treat runtime switch as data migration | Runtime switch only selects the harness for future work. Historical attribution must remain visible. | [`runtime-settings.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md), [`runtime-switch-dashboard-contract.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-switch-dashboard-contract.md) |
| Bypass visible approval cards for risky tool use | The Agent page is the audit surface for operator decisions. | [`agent.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/agent.py) `tool_approval_request` branch |
| Invent a "don't-ask mode" or treat broad operator wording as approval | Runtime judgment decides how to interpret intent, but it cannot create product authority that Builder did not grant through tools and visible approvals. | [`definitions.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/definitions.py) chat prompt |
| Infer Board completion from repository evidence alone | Builder Board state is the source of truth for task status; tests or git state can support verification but cannot replace Board state. | [`realtime-voice-integration.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/realtime-voice-integration.md) Key Constraints |
| Make the user reason about runtime mechanics to use product features | Runtime mechanics must stay behind Builder-owned UI and product surfaces. | [`claude-agent-sdk.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md) pass and fail signals |

## Claude Agent SDK Capability Profile

When the selected runtime is `claude`, `ClaudeRuntime.capabilities()` reports:

| Capability | Native |
| --- | --- |
| chat | yes |
| streaming | yes |
| tools | yes |
| MCP | yes |
| subagents | yes |
| workspace access | yes |
| shell | yes |
| sandboxing | yes |
| approvals | yes |
| session resume | yes |
| subscription auth | yes |
| API-key auth | no |
| model listing | no |
| provider-limit detection | yes |
| tracing | yes |

The runtime probe requires Claude Agent SDK availability and local Claude auth.
If unavailable, the remediation is to run Claude auth or set
`CLAUDE_CODE_OAUTH_TOKEN` for local SDK auth.

## Codex SDK Contrast

The Agent page can also run through `codex_sdk`. That runtime remains the same
Builder-owned Agent page lane, but its adapter capability profile differs:
Codex SDK uses Codex subscription login, app-server events, native user-input
requests, MCP elicitations, request permissions, token usage stream evidence,
and project-local Codex telemetry. It must not be documented as inheriting
Claude hooks, Claude OTEL, or Claude Agent SDK auth.

When the selected runtime is `claude`, the Agent page uses the Claude Agent SDK
agent loop: Claude interprets the prompt, decides whether to call tools, receives
tool results, and repeats until a final `ResultMessage` or a limit/error subtype.
Builder owns the product semantics around that loop. Claude-specific tuning
should use SDK knobs such as tool allowlists/denylists, permission mode,
approval callbacks, hooks, subagents, tool search, max turns, budget, effort,
session resume/fork, compaction evidence, and OTEL export policy. It must not
replace broad operator judgment prompts with deterministic shortcuts just to
save tokens.

## Tool-Call Signal Rubric

The SDK-backed Agent page must receive the same high-signal default shape across
all three tool-call surfaces:

- Claude Agent SDK MCP tools: compact Builder product-service outputs, explicit
  `allowedTools`, bounded workspace reads such as `read_file(start_line,
  max_lines)`, `AskUserQuestion` for needed clarification, permission callback
  evidence for approvals, cache creation/read token accounting, and
  post-mutation proof for writes.
- Codex SDK app-server tools and command events: compact event previews, native
  `item/*` command-output accounting, request-user-input card mapping, and
  optimization telemetry that flags `large_command_output`.
- Builder CLI commands used from shell/Bash/Codex command tools: `--json`
  defaults that expose counts, IDs, status enums, compact evidence summaries,
  `token_estimate`, and exact next commands, with raw or wider output behind
  bounded `--full`, `--limit`, or focused read commands.

`builder board show --json` is the canonical pipeline-state example: default
output keeps complete counts and compact rows, while `--full --limit <n>`
expands bounded board task fields without dumping raw sprint, observability, or
timeline blobs. Any SDK or CLI surface that needs more than this default must
follow a focused command such as `builder backlog task status <task-id> --json`.

## Rubric Checks

Use this checklist when reviewing Agent page behavior:

- Does the request require heavy reasoning, repo work, failure diagnosis, or
  validation? It belongs in the SDK-backed Agent lane.
- Is the action read-only Builder state retrieval? It can be auto-approved when
  the tool is in the chat agent read-only allowlist.
- Is the action mutating, high-risk, or ambiguous? It needs a visible question or
  approval card.
- Does the behavior touch Board, backlog, approvals, memory, knowledge, metrics,
  or observability semantics? The SDK-backed agent must consume Builder surfaces,
  not redefine them.
- For `claude` runs, does evidence include result subtype/stop reason, usage,
  cache creation/read tokens, turn/budget limit state, approval or
  `AskUserQuestion` pauses, and any compaction boundary?
- During an active `codex_sdk` run, does the Conversation tab avoid draft
  planning text and wait for the settled assistant message while still showing
  running state and tool evidence?
- During any active SDK-backed run, does the Conversation tab keep the visible
  timeline mounted across recovery polling instead of flashing or remounting a
  loading transcript?
- Do pending questions and approvals render as readable timeline entries and
  inline response controls, not raw objects, SDK event names, or lifecycle
  ceremony?
- If a runtime-native question contains internal nouns such as backlog, sprint,
  task id, lifecycle, bounded, raw/full logs, chunk, or token pressure, does the
  Agent page sanitize the persisted card into plain product wording before it
  reaches the operator?
- If a model-backed assistant answer asks whether Builder should start,
  proceed, or hold delivery work, does the Agent page turn that into an inline
  question/approval with readable controls instead of leaving it as plain prose?
- For status prompts, does the answer distinguish backlog feature completion
  from Board task state using the same wording contract as Realtime Voice, and
  default to the current sprint unless the operator explicitly asks about older
  sprint history?
- Do natural backlog/blocked status questions stay model-backed while using
  bounded Builder state, and ask a structured question when the target is
  unclear?
- Did the final answer or run produce retrieveable Agent page evidence?

## Validation

Useful checks:

```bash
builder quality-gate claude-agent-sdk --json
builder quality-gate modular-runtime --json
builder quality-gate product-lifecycle --json
PYTHONPATH=src pytest tests/test_runtime_interface.py tests/test_embedded_agent_routes.py -q
```

## Related Docs

- [Deterministic vs model-backed Agent behavior](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/rubric/deterministic-vs-model-backed-agent-behavior.md)
- [Claude Agent SDK architecture gate](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md)
- [Modular runtime quality gate](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [Runtime settings](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [Runtime switch dashboard contract](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-switch-dashboard-contract.md)
- [Agent page hierarchy](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/agent-page-hierarchy.md)
