---
title: "Realtime voice Agent page agent rubric"
tags: ["agent-page", "realtime", "voice", "rubric"]
doc_type: "rubric"
created: "2026-05-11"
---

# Realtime Voice Agent Page Agent Rubric

## Purpose

Use this rubric to decide what Samantha, the Realtime voice agent, can do directly, what it
must delegate to the SDK-backed Agent page agent, and what it must not do.

This rubric is the product contract. Code evidence below is implementation
traceability, not the source of truth. If current Realtime behavior disagrees
with the rubric, classify the mismatch as a bug or explicit product decision.

Realtime voice is a low-latency operator interface for the Agent page. It is not
the worker lane. Its direct powers are intentionally small, deterministic, and
auditable. Durable Builder work goes through the SDK-backed Agent page chat lane.
When Samantha delegates work, she must preserve the operator's exact work
request in the Agent-page message. She may use `routing_reason` for compact
classification, but she must not rewrite "I want to improve/add/ship..." into a
narrower investigation unless the operator actually asked only for an
investigation.

## Architecture Scope

The frontend starts a WebRTC voice session from the Agent page. The backend
proxies the SDP offer to OpenAI Realtime, returns the SDP answer, starts a
sideband WebSocket, and dispatches Realtime tool calls through Builder-owned
voice services.

The model policy uses `gpt-realtime-mini` with the `marin` voice. It requires
`OPENAI_API_KEY` in the Builder source environment to start a voice session.
That key is for the Realtime voice lane, not for Codex SDK subscription access
or Claude Agent SDK auth.

## Can Do Directly

| Capability | Rubric | Code evidence |
| --- | --- | --- |
| Start and stop a voice session | Use microphone audio, `RTCPeerConnection`, SDP offer/answer, and the `oai-events` data channel. | [`use-realtime-voice.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/hooks/use-realtime-voice.tsx), [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) |
| Continue without microphone input | When the browser has no microphone device or permission is blocked, keep the Voice tab usable by opening a Realtime data-channel session and accepting typed Realtime input. | [`use-realtime-voice.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/hooks/use-realtime-voice.tsx), [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) |
| Wait silently after handled turns | Do not keep chatting after deterministic controls, side conversation, silence, or background audio. VAD may detect audio turns, but response creation must be explicit after non-empty operator input; `wait_for_user` tool outputs must not create a spoken response. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py), [`use-realtime-voice.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/hooks/use-realtime-voice.tsx), [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) |
| Render Voice turns as transcript rows | The Voice tab should use the same timeline component as Conversation, but normal Samantha responses are speaker turns labeled `Samantha`, not `thinking · Samantha`. Reserve `thinking` labels for actual reasoning/run-trace activity between responses. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx), [`agent-native.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/components/agent-native.tsx) |
| Separate Realtime talk from Builder chat | Direct operator-to-Samantha and Samantha-to-operator turns belong in the Agent page `Voice` tab. If Samantha delegates to Builder, the `Conversation` tab must show the `Samantha -> Agent` turn and SDK-backed Agent result. Plain typed Agent chat must remain an `Operator` bubble. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) |
| Bind to an Agent page session | Start fresh or attach to the current Agent page session via `X-Agent-Session-Mode` and `X-Agent-Session-Id`. | [`use-realtime-voice.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/hooks/use-realtime-voice.tsx) session headers |
| Read compact Builder state | Read current runtime, active run, pending operator items, Board task counts, backlog completion, sprint counts, blocked tasks, provider-limit status, and voice usage. Natural status phrasings such as "what's left in the backlog?" should call Builder state directly and answer in the Voice tab without creating SDK-backed Agent work. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `get_builder_agent_update` |
| Navigate Builder dashboard | Open simple dashboard destinations from natural language such as "show me the board", "show me the backlog", "go to settings", "open metrics", "go back to Voice", or "show Conversation". Typed Realtime text-control must return the target route and the frontend must apply it directly, while live Realtime tool calls can still navigate through the event stream. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `navigate_dashboard`, [`use-realtime-voice.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/hooks/use-realtime-voice.tsx) voice navigation event listener |
| Open run trace evidence | Resolve natural language such as "last task run", "last optimization run", or "run that led to blocked state" to an existing task-owned run trace and navigate the Agent page to `Run trace`. If the operator also asks for analysis, Samantha must open the trace first and then delegate the analysis to the SDK-backed Agent with the resolved run id and task id. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `open_run_trace`, [`voice_operator.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/voice_operator.py) `open_run_trace` |
| Delegate normal work | Send operator messages into the SDK-backed Agent page chat lane and wait for an auditable Builder answer. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `delegate_to_builder_agent`, [`voice_operator.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/voice_operator.py) `send_message` |
| Answer pending questions | Answer a visible Agent page question card, including resolving recommended options like "use the recommended one." | [`voice_operator.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/voice_operator.py) `answer_pending_question` |
| Handle approval flow safely | Stage a high-risk allow/deny decision, ask for explicit confirmation, and only then confirm the prepared action. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `prepare_high_risk_decision`, `confirm_high_risk_action` |
| Recover blocked runs | Recover a blocked Board task through Builder recovery when the operator explicitly asks to recover or resume blocked work. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `recover_board_task`, [`voice_operator.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/voice_operator.py) |
| Dispatch recovered or current task | Dispatch the current dispatchable Board task through the same Builder dispatch path as the Board UI when the operator asks to start, continue, run, or dispatch it. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `dispatch_board_task`, [`tasks.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/tasks.py) `_run_dispatch` |
| Switch runtime for future work | Switch future Builder runs between Codex SDK and Claude Agent SDK while preserving historical attribution. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) `switch_builder_runtime`, [`runtime_settings.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/runtime_settings.py) |
| Wait silently | Record a no-op wait only for silence, keyboard noise, music, room disturbance, side conversation, or speech clearly not addressed to Builder. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py) `VOICE_OPERATOR_INSTRUCTIONS` |
| Show transcript evidence | Surface voice operator messages, delegated SDK-backed work, and final summaries in the Agent page transcript. | [`AgentPage.tsx`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/frontend/src/pages/AgentPage.tsx) voice timeline entries |

## Must Delegate To SDK-Backed Agent

Realtime voice must call `delegate_to_builder_agent` when the operator asks for:

- logs, metrics, observability, or failure diagnosis
- repo work, generated-app work, docs, tests, build, browser validation, or
  implementation
- planning, requirements, design review, or backlog creation beyond simple
  dashboard navigation, direct Board recovery, direct Board dispatch, runtime
  switching, or answering a visible question card
- disputed correctness, ambiguous status, fresh verification, or multi-step work
- product corrections, normal work instructions, feature requests, bug reports,
  validation requests, or implementation requests

The voice agent may briefly say that it is checking with Builder, but the actual
work and final auditable answer must come from the SDK-backed Agent page lane.

## Cannot Do

| Prohibited behavior | Reason | Evidence |
| --- | --- | --- |
| Do heavy lifting directly | Direct Realtime tools are only for cheap, deterministic, auditable control-plane actions. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py) routing rules |
| Mutate generated code directly | Voice is an operator surface, not an implementation runtime. | [`realtime-voice-integration.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/realtime-voice-integration.md) Direct vs Agent-Page Work |
| Bypass approvals | High-risk decisions must be prepared and explicitly confirmed before execution. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) high-risk tools |
| Diagnose failures from its own assumptions | Failure diagnosis must be delegated so the Agent page records the question and SDK-backed answer. | [`realtime.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/embedded/server/routes/realtime.py) tool descriptions |
| Treat old voice summary as current state | For fresh factual status, call `get_builder_agent_update` again. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py) latest summary rule |
| Rename Board lanes from memory | Use the current `board_status` lane names and counts exactly; queued implementation work is not active unless the latest run is running. | [`voice_operator.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/voice_operator.py) Board lane counts |
| Answer addressed Builder requests from memory | It must call the right Builder tool, ask one short clarification, or state it is checking with Builder before the tool call. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py) operator instructions |
| Use wait-for-user on low-confidence Builder-directed speech | Low-confidence Builder-directed requests require clarification, not silent waiting. | [`realtime_voice_policy.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/services/realtime_voice_policy.py) wait policy |
| Fork Builder state into a voice-only lane | Durable transcript and work evidence belong in the Agent page SDK-backed lane. | [`realtime-voice-integration.md`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/realtime-voice-integration.md) Direct vs Agent-Page Work |

## Routing Rubric

| Operator utterance | Correct Realtime behavior |
| --- | --- |
| "What is the board status?" | Call `get_builder_agent_update`; answer from the compact current-state digest. |
| "How many sprints are there?" | Call `get_builder_agent_update`; answer from sprint counts. |
| "Check the logs and tell me why it failed." | Say it will check with Builder; call `delegate_to_builder_agent`. |
| "Fix the generated app." | Call `delegate_to_builder_agent`; SDK-backed Agent owns the work. |
| "Use the recommended option." | If a pending question card exists, call `answer_pending_builder_question` with the resolved recommended option. |
| "Approve the pending action." | Call `prepare_high_risk_decision`, ask for explicit confirmation, then call `confirm_high_risk_action` only after confirmation. |
| "Recover the blocked task from provider limit." | Call `recover_board_task`; summarize the recovered task and next step. |
| "Recover the last failed run." with no blocked Board task | Report that no blocked, failed, or capability-limited Board task is recoverable; offer to open or diagnose the run trace instead of preparing approval. |
| "Dispatch the recovered task." | Call `dispatch_board_task`; summarize whether Builder dispatched it or what blocked dispatch. |
| "I want to see the board." | Call `navigate_dashboard` with `board`; the dashboard should move to Board. |
| "Show me the last optimization run." | Call `open_run_trace` with `intent=open_only`; the Agent page should open the matching Run trace. |
| "Analyze the current agent run and tell me if it was efficient." | Call `open_run_trace` with `intent=open_then_analyze` and `analysis_request`; Samantha opens the matching Run trace, then delegates analysis to the SDK-backed Agent. |
| "Switch to Codex SDK." | Call `switch_builder_runtime` with `codex_sdk`; explain future-runs-only attribution. |
| Side conversation or room noise | Call `wait_for_user` silently. |
| Unclear but probably Builder-directed speech | Ask one short clarification question. |

## Evidence And Ledger Requirements

Realtime voice activity must remain visible and auditable:

- Realtime session setup failures should return actionable API-key or SDP errors.
- Browser microphone failures should be actionable and should fall back to
  Realtime text mode in the Voice tab when the Realtime backend can still
  connect.
- Tool calls and outputs should be recorded as voice tool events.
- Direct navigation/run-trace/recovery/dispatch controls should emit `voice_navigation_request`
  or `voice_control_action` events and remain visible in logs/metrics.
- After a deterministic navigation/control result such as "Opening Board.",
  Samantha should stop and wait for the next operator turn. Extra clarification
  or readiness messages without new operator input are Realtime eagerness bugs.
- Delegated work should create `voice_operator_message`, normal Agent-page
  `user_message`, SDK-backed Agent output, and `voice_final_summary`.
- Delegated work should return to Realtime as event-driven `running` work by
  default. Realtime must not hold the voice response open waiting for the full
  SDK-backed Agent run. The visible Agent page should switch from the voice
  session to the delegated Conversation session immediately.
- Usage, useful versus wasted turns, delegation messages, prepared actions, and
  waits should be available through the voice ledger and Metrics page.
- Pending approval reminders should be event-driven and should not create
  unhandled sideband task failures.

## Validation

Useful checks:

```bash
PYTHONPATH=src pytest tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py -q
PYTHONPATH=src pytest tests/test_dashboard_api.py::TestMetricsEndpoint::test_metrics_include_voice_cost_and_delegation_ledger -q
```

## Related Docs

- [Deterministic vs model-backed Agent behavior](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/rubric/deterministic-vs-model-backed-agent-behavior.md)
- [Realtime voice integration](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/realtime-voice-integration.md)
- [Runtime settings](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [Runtime switch dashboard contract](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-switch-dashboard-contract.md)
- [Agent page hierarchy](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/agent-page-hierarchy.md)
