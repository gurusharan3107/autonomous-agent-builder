# Realtime Voice Integration

## Overview

OpenAI Realtime voice operator layer on the builder Agent page. The operator speaks to the builder via WebRTC; the voice model runs server-side tools against the existing Agent-page chat lane.

## Architecture

- **Frontend** — `frontend/src/hooks/use-realtime-voice.tsx` owns the app-level
  voice controller with start/stop, microphone permission, RTCPeerConnection
  offer/answer, and the `oai-events` data channel. `frontend/src/components/SamanthaVoiceOrb.tsx`
  owns the single bottom-right Samantha voice entrypoint: the clickable orb,
  hover label, error/retry state, start/stop action, and ambient radial glow.
  Audio amplitude is measured in real-time via
  Web Audio API `AnalyserNode` on the remote WebRTC `MediaStream` and exposed as
  `remoteAudioLevel` (0–1) through context so the orb pulse and ambient glow stay
  synchronized inside that one component.
  When the data channel opens, Samantha should say exactly `Hi there!` as an activation
  cue. The frontend must send this as a constrained `response.create` activation
  greeting, not as a synthetic operator `conversation.item.create`; after that
  greeting, Samantha must wait for non-empty speech or typed Realtime input.
  `frontend/src/pages/AgentPage.tsx` renders the detailed Agent-page
  voice panel from that shared controller. If browser microphone capture fails
  because no audio device is present or permission is blocked, the controller
  must not strand the operator at a raw browser error. It should create a
  Realtime data-channel session when possible and show typed Realtime input in
  the Agent page `Voice` tab so the operator can still communicate with
  Samantha, the Realtime voice AI. Direct Realtime turns stay in `Voice`; Realtime-to-Builder
  delegations and SDK-backed Agent results are mirrored in `Conversation`.
  When a Realtime tool call delegates to a fresh Agent-page session, the backend
  must bind the active Realtime call to that delegated session, publish a
  `voice_control_action` carrying the new `session_id` and route, and let the
  frontend switch the visible Agent page to that Conversation thread. The
  operator must not be left on an empty Voice session after Samantha says she is
  checking with Builder.
  While voice is connected, the Agent
  page also runs a narrow transcript sync fallback so a voice-created or
  voice-switched Agent session becomes visible before browser refresh. The
  fallback must only adopt histories containing voice transcript evidence, only
  update React state when the transcript changed, and leave the per-session SSE
  stream as the primary live lane. Voice navigation requests must be applied
  from direct SSE/custom events only. Persisted timeline items are audit
  evidence, not imperative commands; the Agent page must not replay historical
  `voice_navigation_request` or `voice_control_action` rows when loading chat
  history or syncing a voice transcript.
- **Backend** — `src/autonomous_agent_builder/embedded/server/routes/realtime.py`
  exposes `POST /api/realtime/session`. It is transport glue: it proxies SDP to
  OpenAI `/v1/realtime/calls`, returns the answer, starts a WebSocket sideband,
  and delegates voice behavior to `services/voice_operator.py`. It also exposes
  `POST /api/realtime/text-control` for deterministic typed Realtime controls
  that should not depend on the Realtime model choosing a tool call.
- **Model** — `gpt-realtime-mini` with `marin` voice. `gpt-realtime-mini` is
  the default because it is the documented cost-efficient Realtime model.
- **Sideband** — A persistent WebSocket reads tool calls from the Realtime
  session and dispatches them through `VoiceOperatorService`
  (`get_builder_agent_update`, `delegate_to_builder_agent`,
  `answer_pending_builder_question`, `recover_blocked_run`,
  `switch_builder_runtime`, `prepare_high_risk_decision`, `confirm_high_risk_action`,
  `wait_for_user`). `AgentOperatorService` owns the Agent-page bridge, so
  voice-initiated work produces visible transcript content without route-local
  calls into private Agent helpers.
- **Runtime switching** — `switch_builder_runtime` persists the same
  future-runs-only runtime selection as the dashboard Settings API. It accepts
  Codex SDK and Claude Agent SDK selections, writes `runtime_settings_updated`,
  updates repo-local runtime env, and preserves historical task, run, metrics,
  observability, memory, knowledge, and backlog attribution.
- **Provider-limit status** — `get_builder_agent_update` includes recent
  model-backed Agent runs that stopped with `provider_limit`, so voice can tell
  the operator when the SDK lane hit a provider limit even after a Board task is
  recovered for a future retry.
- **Capability decision** — `VoiceCapabilityDecisionService` runs before
  Agent-page delegation. It returns the structured agreement required by
  The structured agreement: `decision`, `voice_action`, `builder_route`,
  `can_execute_now`, `blocker`, `operator_message`, and `evidence_refs`.
  Blocked runtime/provider-limit states and unsupported operator requests are
  reported to the operator without appending Agent-page chat events or starting
  an SDK-backed run.
- **Pending questions** — `PendingOperatorItemService` exposes pending Agent
  questions with their options, `recommended_index`, and recommended option so
  Realtime can ask the operator a normal spoken question. Voice-submitted
  answers are persisted as the Agent page's canonical `answer_value`; natural
  answers like "use the recommended one" are resolved to the recommended option
  label before the existing Agent response lifecycle continues.
- **Pending approval reminders** — Realtime voice must not poll for pending
  approvals and speak reminders without new operator input. When the operator
  asks about pending approvals or answers a visible approval/question, Builder
  may read the pending item, record auditable voice evidence, and ask for the
  needed approve, deny, confirm, cancel, or more-details decision.
- **Sideband shutdown** — Browser navigation, Stop voice, or remote Realtime
  call teardown can close the sideband WebSocket without a close frame. Treat
  that as normal session shutdown and return cleanly; it must not produce
  unhandled task exceptions in the dashboard server logs.
- **Ledger** — `VoiceCostLedger` records Realtime response usage and usefulness
  classification. `realtime_voice_ledger.py` builds the dashboard-visible voice
  ledger from ChatEvent records: usage, useful vs wasted turns, delegation
  messages, prepared actions, and no-op waits. Rendered on the Metrics page.
- **Completion notifier** — `VoiceCompletionNotifier` registers a task-done
  callback for delegated SDK-backed Agent work. The callback persists a
  structured `voice_final_summary` and a `voice_completion_notification`, so
  long-running work can complete after the synchronous Realtime tool-call wait
  expires.
- **High-risk actions** — `HighRiskVoiceActionService` prepares durable action
  records for approvals and blocked Board-task recovery. Mutating recovery is
  not executed until `confirm_high_risk_action` confirms the prepared action id.
- **Voice digests** — `AgentVoiceDigestService` creates structured
  `voice_final_summary` payloads with `spoken_summary`, `outcome`,
  `recommended_next_action`, and `evidence_refs`. Realtime should read the
  digest fields, not raw Agent output or tool logs.
- **Policy** — `realtime_voice_policy.py` owns the canonical model constant (`gpt-realtime-mini`), operator instructions, tool definitions, and routing rules (e.g. quick factual status reads route to `get_builder_agent_update`; "check with Builder," log/metric verification, or disputed Board/sprint/blocked-task checks route to `delegate_to_builder_agent` for Agent-page audit; normal instructions route to `delegate_to_builder_agent`). Addressed Builder requests must never be answered from Realtime memory alone: voice should acknowledge and delegate, ask one concise clarification, or use Builder status. Token savings must come from bounded tools and compact evidence, not from replacing Agent judgment with generic deterministic answers. `wait_for_user` is only for silence, noise, side conversation, or speech clearly not addressed to Builder.
- **Agent chat retrieval** — `src/autonomous_agent_builder/embedded/server/routes/agent.py` builds the Agent-page chat prompt. When the operator references prior discussion, memory, recommendations, backlog, sprint, board state, or project history, the SDK-backed Agent must perform bounded retrieval through Builder/repo surfaces before asking for missing context. It must not say it will check memory, backlog, board, or project state unless it actually uses the corresponding tool in that turn.
- **Env boundary** — `codex_subscription_env.py` strips `OPENAI_API_KEY` from Codex SDK child processes to enforce that ChatGPT subscription (not API key) powers SDK lanes.

## Voice Tools

| Tool | Purpose |
|------|---------|
| `get_builder_agent_update` | Read Agent-page status and pending operator items |
| `navigate_dashboard` | Move the visible dashboard to a simple destination such as Board, Conversation, Voice, Run trace, Metrics, Observability, Backlog, or Settings |
| `open_run_trace` | Resolve natural language such as last task run, last optimization run, or blocked-state run to an existing Agent page Run trace. With `intent=open_only`, it only navigates. With `intent=open_then_analyze`, it opens the trace first, publishes a navigation event that includes the full `analysis_request`, then delegates analysis to the SDK-backed Agent with the resolved run id and task id. Repeated analysis prompts still emit a fresh navigation event so the visible page can reopen Run trace even when the route is unchanged. |
| `delegate_to_builder_agent` | Send an operator message into the Agent-page chat lane |
| `answer_pending_builder_question` | Answer a pending question card |
| `recover_board_task` | Recover a clear blocked, failed, or capability-limited Board task through Builder's task recovery service; if no recoverable Board task exists, report that recovery is unavailable and use run-trace diagnosis instead |
| `dispatch_board_task` | Dispatch the current dispatchable or recovered Board task through Builder's normal Board dispatch path |
| `recover_blocked_run` | Compatibility alias for Board-backed recovery only; it must not turn historical Agent-page chat failures into a recovery approval or retry |
| `switch_builder_runtime` | Switch future Builder runs between Codex SDK and Claude Agent SDK |
| `prepare_high_risk_decision` | Stage an allow/deny decision without executing |
| `confirm_high_risk_action` | Execute a staged approval decision after confirmation |
| `wait_for_user` | Persist a no-op wait event for silence, noise, side conversation, or speech clearly not addressed to Builder |

## Direct vs Agent-Page Work

Realtime voice has direct tool access only for cheap, deterministic,
control-plane actions:

- Read compact status: current runtime, active run, pending operator items,
  Board counts, blocked tasks, recent provider-limit run status, and voice usage.
- Navigate simple dashboard destinations from ordinary speech.
- Open existing task-owned run trace evidence from natural language. This is
  evidence navigation, not analysis.
- Answer a visible pending Agent question.
- Recover a clear blocked Board task and dispatch a dispatchable Board task
  through Builder-owned lifecycle APIs.
- Stage and confirm a visible pending approval or ambiguous/high-risk recovery.
- Switch future runs between Codex SDK and Claude Agent SDK.
- Record an intentional no-op wait for silence, noise, side conversation, or
  speech not addressed to Builder.

Everything else goes through `delegate_to_builder_agent`, including:

- Run trace interpretation after Samantha has loaded the requested trace.
- Log, metric, or observability interpretation.
- Failure diagnosis or "why did this happen?" analysis.
- Repo, generated-app, docs, tests, build, browser validation, or implementation
  work.
- Planning, requirements, design review, or backlog creation beyond simple
  navigation, direct Board recovery, direct Board dispatch, runtime switching,
  or answering a visible question card.
- Any disputed, ambiguous, fresh-verification, or multi-step request.

Realtime voice is a low-latency operator interface, not the worker. The selected
runtime SDK-backed Agent owns heavy reasoning and durable work so the Agent page
has the auditable transcript and Builder state does not fork into a hidden
voice-only lane.

## Capability Agreement

Every `delegate_to_builder_agent` call must pass through the builder-owned
capability decision service before Agent-page chat events are appended or
`_run_chat_turn` is scheduled.

The service may return:

- `voice_direct` for compact status answers that Realtime can speak from
  Builder state.
- `sdk_chat` for normal Agent-page chat work.
- `lifecycle_dispatch`, with `builder_route` such as `code_gen`,
  `sprint_dispatch`, `build_verifier`, or `feature_verifier`, when the request
  maps to Builder delivery work.
- `requires_approval` or `requires_question` when the next valid action is a
  visible operator confirmation or pending Agent question answer.
- `blocked` when the selected runtime or recent provider-limit state means an
  SDK-backed run would fail before doing useful work.
- `unsupported` when neither Realtime tools nor Builder lifecycle routes can do
  the requested work.

For `blocked` and `unsupported`, Realtime must speak the `operator_message` and
must not create `voice_operator_message` / `user_message` Agent-page events.
Those outcomes are not hidden failures; they are deliberate operator-facing
capability results.

## Status Projection Contract

Realtime direct status answers and SDK-backed Agent read-only status shortcuts
must project Board and backlog state with the same semantics. Backlog feature
completion and Board task state are separate facts: if all backlog features are
done but a verification or recovery task remains on the Board, both lanes must
say the backlog features are complete and the Board still has queued or active
work. Do not describe queued Board work as open backlog work, and do not reuse a
prior provider-limit summary as a current block unless current run evidence
still proves it.

## Dashboard Navigation Contract

Simple dashboard navigation intents are direct product controls only when they
arrive through the Realtime text-control/direct-action path. SDK-backed Agent
chat still sends typed prompts through the selected model so the runtime can
interpret intent and decide whether navigation, a status answer, or a follow-up
question is the right action.

- Realtime typed text-control must return the resolved route in the direct
  response so the frontend can navigate immediately. The SSE/custom-event path
  remains valid for live Realtime tool calls, but successful text-control
  navigation must not depend on a later event replay.
- SDK-backed Agent chat must not use a zero-token navigation shortcut for typed
  prompts. If the selected model chooses to navigate, the resulting event should
  use the same navigation event shape as Realtime with a source that identifies
  the Agent lane.
- Persisted navigation events are audit evidence. They must not be replayed from
  history or transcript sync when the operator later returns to the Agent page.

Unless the operator explicitly asks about older sprints, previous sprints, or
all-sprint history, the default status scope is the current sprint selected by
the dashboard contract. Realtime and SDK-backed Agent read-only summaries must
match that current-sprint default instead of widening to older sprint tasks on
their own.

Natural operator variants such as "what is left on the board?" and "what is
remaining?" are status reads, not implicit delivery dispatches. The SDK-backed
Agent read-only shortcut and Realtime direct status path must classify those
phrases through the same current-sprint Board projection.

Natural navigation requests such as "take me to backlog" or "show me the
board" are not status reads even when they mention Board or backlog. Typed
Realtime text control must route those one-step intents through the same
`navigate_dashboard` event path that model-backed Realtime tool calls use, so
the visible dashboard moves without requiring a memorized prompt.

Typed Realtime status prompts must pass through `/api/realtime/text-control`
before the frontend sends them to the Realtime data channel. If the text matches
a simple Board, backlog, sprint, blocked-task, or approval status intent, the
endpoint calls Builder-owned status logic directly, records
`voice_tool_call`/`voice_tool_output`/`voice_digest` evidence, and returns the
Samantha response for the Voice tab. Only unhandled text continues to the
Realtime model over `conversation.item.create` plus `response.create`.
Those handled status replies should reuse the same core Board projection lines
as the SDK-backed Agent read-only shortcut so current-sprint counts, backlog
completion, and shipped-state narration do not drift between lanes.

## Key Constraints

- Voice does not bypass approvals or directly mutate generated code.
- High-risk actions require two-phase confirmation (prepare then confirm).
- `OPENAI_API_KEY` must be set in the Builder source environment and is scoped
  to the Realtime voice path only. Do not copy it into generated app `.env`
  files. Codex SDK remains subscription-authenticated, and its `RUNTIME_*` /
  `AAB_CODEX_*` Builder configuration also belongs in the autonomous-builder
  source `.env`, not in generated app `.env` files.
- Voice lives on the existing Agent page in a separate `Voice` tab, not in a
  separate product route.
- Microphone unavailability is a degraded input mode, not a dead end. The
  Voice tab should show the microphone problem, keep Agent chat usable in
  `Conversation`, and offer typed Realtime input over the `oai-events` data
  channel when the Realtime backend session can still connect.
- Live microphone sessions use Realtime `server_vad` turn detection with
  automatic response creation after a short silence. Samantha must answer normal
  spoken turns without requiring a transcript-completed event or a browser-side
  manual `response.create`. Typed Realtime input still sends
  `conversation.item.create` plus `response.create` from the browser because it
  does not pass through audio VAD.
- The WebRTC voice session must outlive dashboard route changes. The fixed
  bottom-right AI widget is always available as a collapsed round Samantha
  control, expands on click, collapses when clicked again, and collapses after
  short inactivity. The operator can drag the round control to a convenient
  screen position, and that position persists locally so the widget does not
  keep covering important dashboard data. The pulse animation is reserved for
  Realtime assistant output that is actively streaming/speaking, not merely for
  a connected session. Deactivating Samantha stops the current Realtime session
  but must not remove the widget; clicking the collapsed control starts
  Samantha again. Navigation to Board, Metrics, Observability, Knowledge,
  Memory, Backlog, Inbox, or Compare does not turn voice off.
- Starting voice must preserve the operator's Agent-page session intent. If the
  operator clicked New thread, the Realtime session must bind to a fresh Agent
  chat session and transcript sync must not fall back to the latest persisted
  session. If an Agent session is active, the Realtime call should bind to that
  explicit session id.
- Voice must not leave the operator guessing whether it heard a Builder-directed request. For normal work, it should acknowledge the handoff before delegating and then summarize the SDK-backed Agent result.
- Board, sprint, blocked-task, and pending-approval status cannot be answered
  from Realtime memory alone. `get_builder_agent_update` must include
  `board_status`, including sprint counts and compact sprint summaries, and its
  digest must not say "Builder is idle" when any Board task is blocked,
  capability-limited, failed, or has a recent model-backed provider-limit run.
  Repeated Board/status questions are fresh reads; Samantha must use the
  current Board lane names exactly (`queued`, `in progress`, `needs review`,
  `shipped`, `blocked`) and must not call a task active only because its task
  status is `implementation` or its sprint verification status is blocked.
  Explicit dashboard refreshes may use deterministic status reads, but typed or
  spoken operator prompts should remain model/tool mediated so Samantha can
  interpret intent and call the right Builder tool.
- Runtime switch requests are direct voice actions when the operator explicitly
  asks to switch to Codex SDK or Claude Agent SDK. The voice response must say
  that the switch applies to future runs only and does not rewrite historical
  runtime attribution.
- Realtime voice must not inspect logs, metrics, observability, files, app
  source, tests, browser proof, or repo history by itself. Those requests are
  delegated to the Agent-page chat lane.
- Realtime should use bounded judgment within this boundary. Compact factual
  Board/sprint/blocked-task/pending-approval reads can use direct Realtime tools.
  Interpretation, disputed answers, failure diagnosis, logs/metrics,
  observability, repo work, or generated-app work should go to the Agent page. A
  `latest_voice_summary` is context about the last Agent result, not proof of
  current Builder state.
- Agent-page chat follows the same boundary: typed prompts stay model-backed,
  while deterministic status shortcuts are only for explicit UI/system refresh
  actions. Verification, shippability,
  failure-diagnosis, owner-classification, recovery-planning, and
  evidence-seeking prompts must use the SDK-backed Agent with Builder tools so
  it can reason from logs, metrics, Board state, command evidence, and repo
  files.
- If the SDK-backed Agent ends with a plain-language delivery permission prompt
  such as "Would you like me to proceed with the implementation?" Builder must
  persist that as a normal `ask_user_question` card. Realtime answers like
  "yes, proceed" should then use `answer_pending_builder_question` instead of
  being treated as unrelated current-thread work.
- The SDK-backed Agent must do bounded retrieval before claiming missing context for prior recommendations, backlog, sprint, board, memory, or project-history references.
- If Realtime voice mistakenly calls an approval-preparation tool for a normal
  Builder work request and the target event is not a pending
  `tool_approval_request`, Builder should treat it as a voice-routing mistake:
  delegate the usable operator reason/message through `delegate_to_builder_agent`
  and reserve prepare-then-confirm behavior for real pending approvals.
- Agent-page status checks are read-only unless the operator gives an explicit
  delivery command. Recovery, approval, blocked-task, sprint, or Board status
  phrases must not trigger autonomous sprint continuation merely because the
  utterance includes a task title with words like "build" or "ship".
- Read-only Board/status prompts must be answered from Builder's persisted
  Board/task state before invoking the SDK runtime. Do not let the SDK infer
  Board completion from `git`, `npm`, or test evidence; command success can
  support a separate verification answer, but Builder Board state remains the
  source of truth for whether a task is blocked or done.
- Blocked-task diagnosis, verification, and shippability prompts are not
  read-only Board/status shortcuts when they ask to investigate, find the exact
  failing command or gate, cite verifier evidence, name the likely owner or
  owning surface, or recommend the next safe recovery step. Those prompts must
  go through the SDK-backed Agent page lane so the answer can use Builder tools,
  logs, commands, and file/test evidence beyond Board counts.
- Realtime costs are not estimated without a configured local rate card. The
  dashboard shows captured Realtime token usage with
  `usage_without_realtime_rate_card`, a delegation ratio, and useful vs wasted
  turn counts so operators can see whether paid voice turns advance the Builder
  lifecycle.

## Testing

- `tests/test_realtime_voice_operator.py` — backend tool dispatch, service
  ownership wrappers, sideband, Agent delegation streaming, structured voice
  digests, provider-limit run status, direct-status delegation guards, sprint
  count status, runtime switching, event-driven completion notification, pending
  question option and recommended-answer handling, high-risk action
  confirmation, useful vs wasted Realtime usage, error handling,
  acknowledgement/wait policy, and wait-for-user.
- `tests/test_dashboard_api.py` — dashboard metrics response includes voice
  cost, delegation, wait, and prepared-action totals.
- `tests/test_realtime_voice_frontend_static.py` — frontend static structure,
  SDP post, voice panel rendering, Metrics voice ledger copy, delegation
  indicator, Realtime navigation event dispatch, timeline-item navigation
  application, transcript sync fallback wiring, bounded activation greeting
  without a synthetic operator message, and Voice tab timeline labeling.
- `tests/test_embedded_agent_routes.py` — Agent-page chat prompt requirements,
  including bounded retrieval before missing-context clarification and persisted
  pending-question cards for plain delivery-permission prompts.
- `tests/test_start_env.py` — Codex subscription env boundary isolates `OPENAI_API_KEY` from SDK child processes.
