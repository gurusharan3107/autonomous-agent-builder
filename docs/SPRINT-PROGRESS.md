# Feature Creation Cycle Sprint Progress

Goal source: active thread goal. Execution instructions: [PLAN.md](PLAN.md).

## Checklist

- [x] Load repo and global operating instructions, active goal, progress, and lifecycle/system-improvement docs.
- [x] Inspect current uncommitted route/test diff before changing files.
- [x] Replace the exact `start shipping` delivery-start trigger with context-driven model-backed delivery context for ready Board work.
- [x] Add a regression test using non-magic operator wording: `I'm ready for the next safe step.`
- [x] Run focused route tests for saved-feature delivery, existing continuation dispatch, and model-backed ready delivery.
- [x] Run broader changed-surface tests and static checks.
- [x] Test the feature creation cycle through the live Agent page in the managed `todo-app` workspace.
- [x] Capture Builder-owned Board, logs, metrics, token, and browser-visible evidence for the Agent run-trace loading issue.
- [x] Capture Builder-owned Board, logs, metrics, token, and browser-visible evidence for the live due-date shipping run.
- [x] Fix the Agent-page recovered-thread ready-state header found during the live run.
- [x] Document the initial memory boundary, then add the relevant memory after the explicit user request.
- [x] Fix `truncate_tool_output_before_reinjection`, pair it with bounded
  retrieval guidance, and validate the same managed `todo-app` metrics lane.
- [x] Clarify Agent-page current-session token accounting so cached raw tokens
  are separated from non-cached-plus-output spend.
- [x] Fix the Agent-page transcript refresh path so the current timeline UI does
  not revert to the older card renderer after reload.
- [x] Fix active SDK-backed Agent polling so the Conversation timeline stays
  mounted while a chat/task run is live.
- [x] Align the Voice tab transcript with the Conversation timeline and place
  the Realtime input below transcript content.
- [x] Stop Realtime Voice from producing unsolicited Samantha turns before the
  operator speaks or types.
- [x] Fix Agent-page New Thread so it detaches stale voice/session history,
  clears URL state, and opens a real empty thread.
- [x] Fix the Conversation composer so pending questions and visible approvals
  can be answered inline instead of forcing the operator to know card controls.
- [x] Fix timeline-mode approval controls so inline questions/approvals stay
  actionable in the current Conversation timeline.
- [x] Fix approved delivery handoff so Agent-page approval starts the first
  generated task directly.
- [x] Prove serial task completion dispatches the next task automatically in
  the managed `todo-app` live run.
- [x] Fix current-sprint generated-task status drift in Board summaries.
- [x] Ship `High-priority todo marking` through a second live Agent-page feature
  cycle in the managed `todo-app` workspace.
- [x] Verify high-priority marking browser-visibly in Chrome, including
  persistence after refresh.
- [x] Browser-retest the Board recovery action through the visible Board UI and
  confirm it uses the shared task recovery service.
- [x] Clean up Agent, Voice, Board, Backlog, and approval happy-path copy so
  operators are not required to understand internal lifecycle terms.
- [x] Patch generated-app post-ship optimization routing so Builder-owned
  residual token-policy work is deferred to Builder source instead of launching
  an owner-mismatched model-backed optimization-agent run.
- [x] Normalize Agent-page chat status token usage so Metrics keeps cached
  input separate from output/non-cached spend.
- [x] Fix Realtime text-mode input so plain Enter submits typed Samantha
  requests during browser-visible Voice validation.
- [x] Fix Realtime text-only fallback so typed work requests open the delegated
  SDK-backed Agent thread and keep the operator's exact wording visible.
- [x] Ship `Collapsible completed todos section` through another live Agent-page
  cycle and verify the Conversation timeline reports final shipped evidence.
- [x] Fix the shipped-closeout recovery bug found during that live cycle by
  resolving real sprint plan document ids instead of the display `sprint-plan-*`
  id directly.
- [x] Keep metrics recommendations active-evidence based so historical
  agent-chat raw totals do not keep driving stale follow-up work after clean
  deterministic runs.
- [x] Replace visible approval/start copy that exposed plan ids, task titles, or
  sprint-task wording with operator-friendly next-action language.
- [x] Fix forward-engineering Agent chat so new-app typed prompts enter the
  general model-backed `chat` lane first instead of being pre-routed into
  `init-project-chat` by project state.
- [x] Ship `Add compact Clear completed action` through a live Agent-page cycle
  and capture Board recovery, shipped closeout, token evidence, and browser
  phase-drawer proof.
- [x] Fix Board phase timeline and drawer regressions found in Sprint 13:
  Review and Build no longer appear skipped before Done, Build opens its own
  drawer, and each phase drawer shows phase-specific agents/evidence instead of
  repeating the same sprint metadata.
- [x] Update frontend/backend architecture rubrics with the target
  decomposition patterns, one-owner rule, and 500-line file-size standard.
- [x] Continue the top god-file decomposition by extracting Agent chat-turn
  terminal publication into a focused owner module with regression coverage.
- [x] Split the largest Agent route test file into focused owner modules for
  operator-safe content, runtime resume safety, forward-engineering behavior,
  and shared Agent-route history support.
- [x] Deep-split the remaining embedded Agent route tests into focused
  sub-500-line owner modules and remove the stale complexity baseline for
  `tests/test_embedded_agent_routes.py`.
- [x] Split the Board frontend route adapter into sub-500-line feature owners
  for selectors, phase strip, lane cards, sprint drawer, and task drawer.
- [x] Re-test the patched Board through the Chrome Computer Use plugin: shipped
  board rendered, `Start work` stayed disabled, and Plan/Gates/Review/Build/Done
  opened phase-specific drawers.
- [x] Extract Agent chat-turn direct actions into a focused backend owner and
  ratchet the Agent route/function complexity baseline down after verification.
- [x] Update [PROGRESS.md](PROGRESS.md) with final evidence and commit the implementation with progress docs.

## 2026-05-18 Sprint 13 Clear Completed And Phase Drawer Proof

- Live Agent-page cycle: session `b5d27111-bff5-45c7-8ced-fba5c9da8831`
  shipped feature `B29D9D70`, `Add compact Clear completed action`, with final
  transcript closeout and token evidence of `185,398` raw, `180,864` cached,
  and `4,534` non-cached-plus-output tokens across 13 runs.
- Board recovery: task `09CD521A` initially blocked after a dispatch failure;
  the visible Board `Recover` action moved it back to queued, `Continue work`
  resumed the task, and Sprint 13 reached shipped with 3 done tasks and
  0 blocked tasks.
- Phase timeline fix: backend and embedded dashboard summaries now expose
  `verify`, `pr_review`, `build`, and `shipped` statuses; the Build dot opens
  the Build drawer; Done is not visually complete while Review or Build remain
  pending.
- Phase drawer fix: Gates shows persisted gate results, Review shows
  `evidence-collector` runs and file diffs, Build shows build-verifier plus
  feature-acceptance runs, and Shipped shows shipping/optimization evidence.
- Verification: focused phase/drawer tests passed, `ruff` passed for touched
  backend/test files, `npm run lint` passed, and the managed `todo-app`
  dashboard rebuilt through `uv run builder start --port 9876 --force`.

## 2026-05-18 Approval Handoff Live Proof

- Agent-page issue: approved feature requests could leave the operator stuck at
  an inline control or require a follow-up such as `start` because the approval
  response was not tied to direct delivery dispatch.
- Source fix: pending question/approval events now update through the active
  request DB session, approved delivery scope schedules the first generated task
  immediately, and embedded dispatch continues to the next serial task when the
  previous task integrates.
- UI fix: the current Conversation timeline renders pending question and
  approval actions inline with the design-system controls instead of falling
  back to hidden card-only controls or text-command handoffs.
- Live managed proof: fresh `todo-app` Agent-page session
  `1d65ce61-b421-485f-bb69-e836d87bd4af` captured `Show Enter Key Hint Beside
  Add Button`, accepted inline `Start now`, accepted inline approval, returned
  `POST /api/agent/chat/respond` 200, dispatched
  `a83e3383-d521-4900-980d-ffbb15e90a59`, and then auto-selected
  `97d57af5-5048-4cd9-abba-a7ef5f96381f` with reason `next_serial_task`.
- Closeout proof: `builder board show --json` ended with latest Sprint 12
  `shipped`, no pending/active/review work for the feature, and all three
  generated tasks `done`; `builder metrics show --json` reported no active raw
  tokens, no active non-cached-plus-output spend, no avoidable-cost flags, no
  recent risky runs, and no recent large-output runs.
- Follow-up regression cleanup: the broad Agent-route plus embedded-server
  test group that previously failed after route tests now passes because
  app-local chat hubs are drained before the test DB engine is disposed.

## Evidence

- Focused regression command passed: `uv run pytest tests/test_embedded_agent_routes.py::test_ready_delivery_followup_stays_model_backed_and_allows_model_dispatch tests/test_embedded_agent_routes.py::test_continue_building_auto_approves_builder_task_dispatch tests/test_embedded_agent_routes.py::test_chat_saved_feature_delivery_followup_routes_through_sprint_backlog_and_queue_approval -q`.
- Root cause found for the live Agent-page run-trace failure: the embedded dashboard route used by `builder start` streamed unbounded historical Board payloads, including large completed-task `agent_runs[*].diff_summary` and sprint execution implementation metadata. The adjacent API route had partial compaction, but the live embedded route had drifted.
- Fixed the root cause by sharing bounded dashboard payload serializers and sprint execution compaction across API and embedded routes, limiting board task run history, and keeping the Agent page on the board SSE contract rather than a task-specific polling fallback.
- Live `todo-app` proof after restart: `/api/dashboard/board` dropped from `11801990` bytes to `835662` bytes, and `/api/dashboard/board/stream` dropped from `12703880` bytes over two seconds to `879995` bytes. Chrome-visible Run trace loaded the selected task-owned run, event timeline, Run explorer, and Agent runs instead of `Could not load task runs`.
- Broader verification passed: `uv run pytest tests/test_dashboard_api.py tests/test_embedded_dashboard_streams.py tests/test_dashboard_streams.py tests/test_dashboard_design_system_contract.py tests/test_embedded_agent_routes.py -q` (`159 passed`), `npm run lint`, `npm run build`, `python scripts/pre_commit_checks.py`, `git diff --check`, and `builder verify --changed --execute --json` executable checks.
- Live due-date shipping test: in managed `todo-app`, the Agent page accepted
  `I'm ready for the next safe step.` and recovery prompts, dispatched the due
  date improvement, and the lifecycle finished with Board counts
  `pending: 0`, `active: 0`, `review: 0`, `done: 26`, `blocked: 0`.
- The run was not clean enough to call the full goal complete: a server restart
  left the Agent page showing stale `Active 0 RUNNING`, and final verification
  had to be recovered/dispatched through the visible Board path. The frontend
  ready-state rule was patched so non-running, unblocked Agent sessions render
  `Ready` and use `AGENT · READY` instead of the global shell running label.
- Final task evidence: `builder backlog task status
  6e1333a4-fc20-4e98-a11b-e5043d55311b --json` returned `status: done`;
  `feature-acceptance-tests` completed in `164ms` with `0` tokens and
  `build-verifier` completed in `2202ms` with `0` tokens.
- Generated app proof: `npm test` passed `55` tests, `npm run lint` passed, and
  `npm run build` passed after `npm ci` restored Vite. Chrome also loaded the
  rebuilt Agent page with `Ready`, `AGENT · READY`, selected shipped
  verification task, and recent deterministic run evidence visible.
- Token evidence: `builder metrics show --json` reported `raw_token_total:
  2035506`, `noncached_plus_output_tokens: 508877`, `cache_ratio: 5.895`,
  `large_command_output: 12`, `redundant_scan: 11`, `chunk_pressure_risk:
  false`, and recommended `truncate_tool_output_before_reinjection`.
- Token-efficiency fix: Codex SDK observability now scores compacted runtime
  events after full command output is stored as a Builder artifact, so large
  command output is not re-counted as active reinjection context. The chunk-limit
  retry prompt and Agent-page observability context now include the concrete
  bounded retrieval shortcut.
- Token after evidence: Chrome-visible Agent-page validation created session
  `4ac92212-f60e-4153-8185-22a1163038a5`; after that run,
  `builder metrics show --json --full --limit 8` reported
  `active_avoidable_cost_flags: []`, `recent_large_output_runs: 0`, and
  `recommended_next_change: reduce_agent-chat_raw_tokens`, with the remaining
  decision targeting `bounded_retrieval_shortcut`.
- Agent-page token display fix: the validated session's raw `35,126` tokens
  included `33,152` cached input tokens and `1,974` non-cached-plus-output
  tokens. The Session rail now shows non-cached-plus-output, raw, and cached
  tokens separately, grounded in OpenAI prompt-caching/conversation-state
  guidance that cached input must be monitored explicitly.
- Agent-page refresh fix: screenshots showed the current timeline conversation
  UI before refresh and the old card renderer after refresh while the Session
  rail stayed updated. Root cause was the persisted/default
  `transcriptLayout: "cards"` preference. The default now uses timeline, stored
  old card preferences migrate once, Settings lists Timeline first, and a static
  regression locks this path.
- Voice-tab alignment: Realtime Voice messages now render through
  `AgentTimeline`, operator text is labeled `Operator`, Samantha responses are
  labeled `Samantha` rather than `thinking · Samantha`, the old
  `Operator to Samantha` label is blocked by regression coverage, and the
  Realtime input is below the transcript like the Conversation composer.
- Realtime activation fix: starting a Voice session now sends a constrained
  Samantha activation greeting, `Hi there!`, without creating a synthetic operator
  message, and the sideband no longer emits pending-approval reminders without
  operator input.
- Forward-engineering Agent-page root-cause fix: managed `sample-app` evidence
  showed a one-word `hi` prompt in a new app was being handled by
  `init-project-chat` because project readiness state selected the
  requirements interviewer before the model processed the user prompt. The
  route now always sends typed Agent-page prompts through the selected
  model-backed `chat` lane, adds forward-engineering context inside that prompt,
  and stops auto-creating a bootstrap requirements session from chat history.
- Regression proof: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_typed_operator_prompt_contract_stays_model_backed
  tests/test_embedded_agent_routes.py::test_forward_engineering_greeting_uses_general_model_backed_chat
  tests/test_embedded_agent_routes.py::test_forward_engineering_chat_marks_provider_limit_blocked
  tests/test_embedded_agent_routes.py::test_built_project_does_not_bootstrap_init_project_chat
  tests/test_embedded_agent_routes.py::test_forward_engineering_new_thread_does_not_reuse_bootstrap_session
  -q` passed `5 passed`.
- Owner-doc direction: the model-backed/deterministic rubric, agent-quality
  tuning workflow, runtime telemetry reference, and agent-quality gate now point
  future SDK-backed optimization at cache-friendly prompt shape, bounded
  evidence, deferred tools where supported, compaction, and clear
  raw/cached/effective token reporting rather than deterministic intent
  shortcuts.
- Claude SDK doc pass: official Claude Agent SDK docs were checked for the
  agent loop, context/caching, permissions, `AskUserQuestion`, hooks, subagents,
  tool search, cost/cache tracking, OpenTelemetry, and sessions. The Claude
  telemetry reference, Claude SDK quality gate, SDK-backed Agent rubric, and
  agent-quality workflow now include the same model-backed optimization
  direction for the `claude` runtime lane.
- Code alignment scan: Claude runner paths already use SDK controls for
  tool scope, permissions, hooks, subagents, turn/budget limits, compaction
  settings, and result usage; Codex SDK already stores large command output as
  Builder artifacts and blocks resume from large-output contexts. Remaining
  alignment work is usage telemetry shape: Claude cache-creation/subtype/error
  fields and OpenAI Agents runtime usage/cost/session extraction.
- Browser proof: `builder start --port 9876` in the managed `todo-app`
  workspace rebuilt/published the dashboard. Chrome visibly loaded `/board`
  with Sprint 4 lanes and shipped due-date task cards, then loaded the Agent
  page with separate `Non-cached + output`, `Raw tokens`, and `Cached tokens`
  Session rows. A later Chrome refresh showed the Voice tab using the
  Conversation-style timeline with the Realtime input below the transcript and
  `SAMANTHA ... Hi there!` as the bounded activation cue. The temporary server
  was stopped afterward.
- Memory update: after the explicit memory request, added repo correction
  `.memory/corrections/keep-agent-page-intent-model-backed-while-optimizing-token-a.md`
  and global ad-hoc note
  `extensions/ad_hoc/notes/20260515T212958+0530-builder-sdk-token-optimization.md`;
  `builder memory lint --json` passed.
- High-priority live run: Agent session
  `b961bffd-a89a-46fe-827d-a53c0e07b2c7` shipped Sprint 5
  `High-priority todo marking` to `pending: 0`, `active: 0`, `review: 0`,
  `done: 29`, `blocked: 0`. Chrome proof at `http://127.0.0.1:5173/`
  added `Pay taxes`, toggled `Mark high` to `High priority`, showed the
  high-contrast priority treatment, and preserved it after refresh.
- High-priority token evidence: scoping used `39,808` raw tokens with `33,152`
  cached; implementation, persistence/tests, and verification used `60,062`,
  `63,383`, and `52,673` raw tokens respectively. Final metrics reported
  `raw_token_total: 2328520`, `noncached_plus_output_tokens: 527715`,
  `cache_ratio: 5.2114`, `recent_risky_runs: 0`, and
  `recent_large_output_runs: 0`.
- Post-ship optimization defect: the live lane exposed an owner mismatch where
  generated-app shipment launched `optimization-agent` for Builder-owned
  token-policy residuals. Source now defers Builder-owned generated-app
  residuals; focused sprint-execution regression tests passed. The stale live
  row `122a3d82-210a-49ee-8062-ba616e704f91` was cleared by startup
  reconciliation after server restart.
- Agent-chat metrics normalization: the remaining token-efficiency pass found
  that model-backed Agent-page chat statuses collapsed SDK usage into
  `tokens_used`, causing Metrics to read the total as output tokens. Source now
  persists and reads separate input, output, cached, raw, and
  non-cached-plus-output fields for chat status events, preserving the
  model-backed prompt path while making spend analysis cache-aware.
- Realtime text-mode finding: Chrome validation on the refreshed managed
  dashboard showed `Hi there!` and accepted a plain typed improvement request,
  but the request did not submit through the visible text path. Source now sends
  Realtime text on plain Enter and reserves Shift+Enter for multiline editing.
- Realtime handoff finding: after the text path submitted, Samantha delegated
  to Builder but Conversation stayed on the empty Voice session. Source now
  makes voice delegation event-driven by default, rebinds the active Realtime
  call to the delegated Agent session, emits a session-switch control event, and
  follows that session in the visible timeline.
- Live handoff proof: fresh Voice session `BCDE6F97` accepted
  `I want to improve the todo app so I can search tasks by text.` and
  navigated to Conversation session `b48fc8cf-59b7-4dea-97e3-59b717eea602`
  with visible `USER · OPERATOR` and `TOOL · SAMANTHA` entries. Logs recorded
  `delegate_to_builder_agent ok (running)`, `realtime_tool_exchange`
  `estimated_tokens=247`, SDK prompt assembly `estimated_tokens=900`, and the
  completed Agent run at `50,081` raw tokens.
- Realtime parity closeout: the first restart pass proved the SDK-backed Agent
  now preserves exact feature wording, but the Voice tab stayed on the voice
  shell session and a later text-mode pass let Samantha claim delegation without
  a Builder tool call. Source now treats text-only Realtime as a direct
  `delegate_to_builder_agent` fallback, derives the delegated session from the
  returned route, and loads that Conversation thread.
- Live Realtime text fallback proof after rebuild: Playwright browser loaded
  `http://127.0.0.1:9876/?mode=voice&v=voice-direct-fallback-proof`, started
  text-mode Realtime, submitted `I want to improve the todo app so overdue
  tasks stand out clearly.`, and navigated to
  `/?session=17572d99-54cb-4593-9432-68b0a53e5516&mode=chat`. The Conversation
  view showed the exact `USER · OPERATOR` wording, `TOOL · SAMANTHA`, the
  agreement for `Make overdue todos stand out`, and the pending shipping
  question.
- Realtime token/evidence closeout: `builder logs --info --compact --json`
  recorded `delegate_to_builder_agent ok (running)`, Realtime exchange context
  budget `estimated_tokens=265`, SDK Agent prompt assembly
  `estimated_tokens=699`, and final run completion with `40,339` raw tokens,
  `38,272` cached tokens, `2,067` non-cached-plus-output tokens, duration
  `48,303ms`, and stop reason `completed`.

## 2026-05-16 Full Agent-Page Shipping Proof

- Live session: Chrome-visible Agent page at
  `http://127.0.0.1:9876/?session=ec2d5ffd-8f0d-400e-9456-d517191da072&mode=chat`
  captured `I want to improve the todo app so completed tasks can be collapsed
  into a compact section.`, asked one product question, requested approval,
  created the internal delivery plan, and dispatched implementation from the
  operator's `start` message.
- Board evidence: `builder board show --json` in managed `todo-app` reported
  `pending: 0`, `active: 0`, `review: 0`, `done: 35`, `blocked: 0`; Sprint 7
  `e8765572-e495-4205-9660-99a215ee92a5` was `shipped`, and all three
  generated tasks for `Collapsible completed todos section` were `done`.
- Closeout bug and fix: refresh initially showed the shipped task but no final
  Agent message. The route now maps the display `sprint-plan-*` id in chat back
  through the persisted `sprint_plan` design document content before checking
  the owning Sprint. After rebuild, Computer Use refresh of the same Chrome
  session showed `Builder shipped ... Evidence ... Token evidence ...` inline
  in the Conversation timeline.
- Token evidence from the shipped closeout: `176,481` raw, `171,136` cached,
  and `5,345` non-cached-plus-output tokens across `12` completed run records.
  The first Agent prompt also showed the expected cache-heavy pattern:
  `31,558` raw, `31,104` cached, and `454` non-cached-plus-output tokens.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_chat_history_appends_shipped_delivery_closeout_once
  -q` passed after updating the test fixture to use the real persisted sprint
  plan document shape.
- Active metrics cleanup: the same managed `todo-app` metrics lane now reports
  `recommended_next_change: maintain_current_flow` with empty
  `active_avoidable_cost_flags`; historical `agent-chat` and `code-gen` totals
  remain visible for audit but no longer drive stale next-action guidance after
  clean active evidence.
- Operator-copy cleanup: the visible post-approval response now says Builder
  prepared the work and makes the next action obvious without requiring a magic
  word; the internal plan id is stored in a non-visible
  `delivery_plan_created` event for closeout recovery.

## 2026-05-16 Inline Decision Submit And Trace Cleanup

- [x] Removed the remaining dialog-backed question/approval path from the
  Agent page. Questions and approvals now stay inline in the timeline and use
  Builder status pills, token-backed review surfaces, readable labels, option
  rows, and inline approval actions.
- [x] Fixed the root cause of the option-click stall: the visible inline
  question-choice button now posts directly to `/api/agent/chat/respond`
  instead of only selecting local draft state.
- [x] Verified the fix with Computer Use on managed `todo-app` session
  `bf352c22-e6be-424d-9fae-bcedfa8477df`: clicking `Due reminders
  (Recommended)` produced a `POST /api/agent/chat/respond`, exact-session
  history reloads, an inline assistant response, `Question Answered`, and a
  `Ready` session rail.
- [x] Preserved the separate refresh/session fix: new chats, session opens,
  question responses, and approval responses continue to sync the selected
  `session=<id>` into the URL before reload.
- [x] Reduced run-trace noise by collapsing adjacent uninformative tool-use
  rows into one counted timeline entry and carrying runtime/provider metadata
  through board activity APIs so Codex, Claude, and Samantha rows can render the
  correct glyph.
- [x] Regression proof: focused frontend/static/API tests passed (`7 passed`),
  `npm run lint` passed, `frontend` `npm run build` passed with the existing
  Vite chunk warning, `git diff --check` passed, and
  `builder quality-gate dashboard-ux --json` returned `ok`.

## 2026-05-16 Agent-Page Start Root Fix And Overdue Shipping Proof

- [x] Fixed the root Agent-page bootstrap path that left a fresh
  `/` Agent route on `Loading agent transcript...` with a disabled composer
  when no `session=` URL parameter and no repo-scoped stored chat session
  existed. The bootstrap now clears the legacy global `chat_session_id`,
  loads an empty fresh transcript, and enables the composer.
- [x] Verified the bootstrap fix with Computer Use in the visible Chrome
  dashboard for managed `todo-app`: after rebuild, the root Agent page showed
  `No active transcript`, kept the selected task visible, and accepted a
  typed operator message.
- [x] Found and fixed the deeper `start` inefficiency: the previous delivery
  continuation branch deterministically dispatched work from prompt wording
  and produced a zero-token `agent-chat` turn. Natural operator prompts such
  as `Start` and `Continue building my app.` now run through the selected
  runtime prompt with Builder delivery context; the model chooses whether to
  inspect Board/task state, dispatch, recover, or ask a bounded question.
- [x] Removed the remaining prompt-handling wording and code paths that treated
  natural typed status/recovery/spec prompts as deterministic shortcuts:
  `CLAUDE.md`, SDK-backed Agent docs, runtime-switch docs, and the
  deterministic-vs-model-backed rubric now reserve deterministic behavior for
  explicit UI controls/system refreshes/exact persisted-state reads. If the
  model is unclear after bounded evidence, it must ask through `AskUserQuestion`
  or the Agent page's equivalent structured question.
- [x] Replaced placeholder runtime timeline labels with design-system-aligned
  SVG marks: Codex rows use a terminal-in-circle glyph, Claude rows use a
  radial burst glyph with status-token color, and Samantha/OpenAI rows use an
  OpenAI-style knot mark. Regression coverage blocks the old `CX` and plain
  `C` placeholders.
- [x] Live shipping evidence for `Make overdue todos stand out`: using the
  Agent page and managed `todo-app`, Builder completed Sprint 9
  `20f459bf-acd2-4668-abad-1c03aaa02462`; `builder board show --json`
  reported `pending: 0`, `active: 0`, `review: 0`, `blocked: 0`, and the
  feature plus all 3 generated tasks in `done` with `verification_status:
  shipped`.
- [x] Token and chunk monitoring for the same lane: Realtime/Agent scoping
  session `17572d99-54cb-4593-9432-68b0a53e5516` used `40,339` raw tokens,
  `38,272` cached, and `2,067` non-cached-plus-output. Implementation,
  persistence/test, and verification runs used `52,835`, `65,782`, and
  `60,195` raw tokens respectively, with cached-token counts `50,560`,
  `63,360`, and `59,264`. Final `builder metrics show --json` reported
  `active_raw_token_total: 0`, `active_noncached_plus_output_tokens: 0`,
  `active_cached_tokens: 0`, empty `active_avoidable_cost_flags`, no recent
  risky/large-output runs, and `chunk_pressure_risk: false`.
- [x] Follow-up efficiency issue: the live server log still showed stale-tab
  polling for an older session while the current session was active. Treat this
  as a session-noise/product robustness issue after the current model-backed
  start and icon fixes are committed.
- [x] Live prompt-path validation after the model-backed start fix exposed a
  root runtime stall instead of deterministic prompt handling: fresh managed
  `todo-app` session `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` showed the
  typed prompt running under `codex_sdk` with context budget `681`, but
  `builder agent history`, `builder logs --compact --json`, and
  `builder logs analyze --session ... --json` showed `sdk_session_id: null`,
  `turns: 0`, `tokens_used: 0`, and no runtime error while the UI stayed
  `running`.
- [x] Fixed that root cause in the Codex app-server runtime: response waits for
  `initialize`, `thread/start` or `thread/resume`, and `turn/start` now have a
  bounded timeout, so a stalled SDK process is converted into a recorded run
  error and the process is shut down instead of leaving an indefinite session.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_codex_app_server_runtime.py -q` passed `14 passed`, including
  coverage for timeout before `thread/start`, timeout before `turn/start`, and
  the existing idle-after-turn timeout.
- [x] Memory closeout: added
  `.memory/patterns/timeout-codex-app-server-pre-response-waits.md`, then
  verified `builder memory lint --json` passed and `builder memory search
  "sdk_session_id null zero turns Agent page running" --tag runtime --limit 5`
  retrieves the new pattern.
- [x] Operator-abstraction follow-up from the same live session: reloading
  managed `todo-app` session `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` proved the
  timeout hole now resolves to a visible inline question, but the model-supplied
  card leaked internal wording (`bounded`, `approval/status recovery`,
  `backlog item`, `large logs`). The Agent route now gives runtimes explicit
  plain-product question guidance and sanitizes persisted `ask_user_question`
  payloads before serialization, including historical cards.
- [x] Browser proof: after rebuilding `todo-app` with the patched Builder
  source and hard-refreshing Chrome, the same pending question rendered as
  plain product wording, with option labels `Yes, define it (Recommended)` and
  `Different improvement`; `backlog`, `bounded`, `approval/status`, and
  `large logs` no longer appeared in the visible card.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_operator_question_payload_removes_internal_lifecycle_terms
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_existing_question_payloads
  tests/test_embedded_agent_routes.py::test_chat_feature_spec_can_use_ask_user_question_and_resume_to_feature_save
  -q` passed `3 passed`; `PYTHONPATH=src pytest
  tests/test_codex_app_server_runtime.py::test_codex_app_server_runtime_maps_request_user_input
  -q` passed `1 passed`.

## 2026-05-16 Inline Start Permission Follow-Up

- [x] Re-tested managed `todo-app` session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` after the operator-safe question
  card fix by clicking the visible inline `Yes, define it (Recommended)`
  option. The button submitted, the question moved to `Answered`, and a
  model-backed Codex SDK follow-up completed instead of using a deterministic
  prompt shortcut.
- [x] Captured live token evidence for that follow-up: `builder logs analyze
  --session 4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175 --json` reported
  `run_status completed`, SDK session
  `019e3028-4790-7a01-9b48-df0b0ac3f03f`, `32,322` raw tokens, `2,432`
  cached tokens, `29,890` non-cached-plus-output tokens, prompt
  `context_budget` estimate `796`, no missing telemetry signals, and
  `recommended_next_change: maintain_current_flow`.
- [x] Logged the follow-up UX finding as a product robustness issue: the
  model-backed answer still contained the internal phrase
  `approval/status recovery` and asked `Ready for Builder to start now, or
  should I hold?` as prose instead of a timeline-native approval/question card.
- [x] Fixed the root Agent serialization path for this class of issue. Existing
  assistant messages that contain delivery-permission wording or internal
  lifecycle terms are normalized before they are rendered, and future
  model-backed delivery-permission phrasing such as `Ready for Builder to start
  now, or should I hold?` is recognized as a pending inline question so the
  operator sees structured `Start now` / `Hold` controls.
- [x] Post-fix rendering evidence: with the managed `todo-app` dashboard
  restarted from the current Builder source, `/api/agent/chat/history` for
  session `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` returned the historical
  question as `clear approval flow for blocked work`, removed the `a an`
  artifact, and returned the assistant text as `approval flow improvement` with
  `Approval and Recovery Panel` instead of the raw `approval/status` wording.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_operator_question_payload_removes_internal_lifecycle_terms
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_existing_question_payloads
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_delivery_permission_assistant_content
  tests/test_embedded_agent_routes.py::test_assistant_delivery_permission_prompt_becomes_pending_question
  -q` passed `4 passed`.

## 2026-05-16 Model-Backed Typed Prompt Cleanup

- [x] Removed the remaining SDK-backed Agent chat deterministic early returns
  for typed dashboard navigation, recovery preflight, and observability
  explanation prompts. These natural operator prompts now enter the selected
  runtime/model lane, preserving the `docs/PLAN.md` contract that the model
  interprets user intent and chooses the appropriate tool chain.
- [x] Updated the active progress checklist and runtime/Realtime owner docs to
  reserve deterministic behavior for explicit UI controls or system refreshes,
  not typed SDK-backed Agent prompts.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_agent_chat_simple_dashboard_navigation_is_model_backed
  tests/test_embedded_agent_routes.py::test_agent_chat_observability_question_is_model_backed
  tests/test_embedded_agent_routes.py::test_agent_chat_recovery_request_without_board_target_is_model_backed
  tests/test_embedded_agent_routes.py::test_board_status_uses_dashboard_lane_counts_for_waiting_implementation_task
  tests/test_embedded_agent_routes.py::test_board_status_names_running_task_as_in_progress
  tests/test_embedded_agent_routes.py::test_board_status_defaults_to_current_sprint_scope
  tests/test_embedded_agent_routes.py::test_board_remaining_prompt_uses_model_backed_status_lane
  tests/test_embedded_agent_routes.py::test_assistant_delivery_permission_prompt_becomes_pending_question
  -q` passed `10 passed`.

## 2026-05-17 Fresh App First-Product Intake

- [x] Started a fresh managed app workspace at
  `/private/tmp/habit-lab-model-app` and validated through the visible Agent
  page on `localhost:9876` using Computer Use.
- [x] Verified clean-slate chat state no longer auto-creates the old
  assistant-only bootstrap thread: `/api/agent/chat/sessions` was empty after
  onboarding, and the visible fresh Agent page rendered the empty transcript
  instead of a loading loop.
- [x] Submitted real Agent-page prompts in Chrome. `hi` and
  `have we built any app?` were processed by the selected Codex SDK model in
  the `chat` lane, not by deterministic `init-project-chat` dispatch.
- [x] Fixed `builder logs analyze --session ... --json` so prompt summaries
  include per-turn `tokens_input`, `tokens_output`, `tokens_cached`,
  `raw_tokens`, `noncached_plus_output_tokens`, and `cache_ratio`.
- [x] Captured live token evidence for session
  `fa7cfd9c-06a9-4d94-ae91-bd2934659821`: `hi` was `30,623` raw /
  `28,703` non-cached-plus-output; `have we built any app?` was `34,162`
  raw / `1,010` non-cached-plus-output with `33,152` cached; the Habit Lab
  prompt was `36,631` raw / `5,527` non-cached-plus-output with `31,104`
  cached.
- [x] Identified a requirements-lane product issue: a broad first-product
  prompt for a Habit Lab app jumped to approval before gathering enough
  user-specific requirements for a tailored first backlog.
- [x] Updated the forward-engineering prompt contract and owner docs so broad
  first-product prompts use model-backed judgment to ask as many
  product-shaping questions or follow-up rounds as the specification needs
  before backlog capture, while still allowing the model to answer directly or
  emit `FEATURE_SPEC_JSON:` when the prompt is already specific enough.
- [x] Browser proof: after restarting the managed
  `/private/tmp/habit-lab-model-app` dashboard from patched source, Chrome
  session `4f4e754e-dc88-4207-9430-cd899caafec1` turned the same Habit Lab
  prompt into an inline product question with `Track Streaks`, `Run
  Experiments`, and `Plan Routine` choices instead of a stale delivery approval.
  Clicking `Track Streaks` advanced the inline question to `Answered` and then
  produced the delivery-start question.
- [x] Updated the inline question UX so product-shaping questions expose three
  model-suggested options, recommended first, plus an inline custom-answer text
  box for anything else the operator has in mind. Existing answered question
  cards now keep the submitted answer visible for later review.
- [x] Browser proof: after restarting the same managed dashboard from patched
  source, Chrome session `4f4e754e-dc88-4207-9430-cd899caafec1` rendered the
  answered question with `ANSWERED WITH Track Streaks (Recommended)` in the
  timeline, and the pending delivery approval remained inline below chat
  content rather than becoming a modal.
- [x] Updated the Agent-page wait state so tool calls after a user prompt show
  as one design-system activity row with an increasing count and latest tool
  label until the agent response arrives, instead of flashing empty tool boxes.
- [x] Follow-up validation on the managed `todo-app` Agent page confirmed the
  active wait state now shows the Agent design-system row with `Running` and
  the current tool-use count instead of the previous dot-loading indicator.
- [x] Token proof for that session: `builder logs analyze --session 4f4e754e
  --json` reported `32,444` raw tokens, `31,616` cached tokens, `828`
  non-cached-plus-output tokens, zero tools, and a `941` token prompt assembly
  estimate.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_forward_engineering_first_product_prompt_requires_user_specific_intake
  tests/test_embedded_agent_routes.py::test_first_product_prompt_is_not_delivery_continuation
  tests/test_embedded_agent_routes.py::test_forward_engineering_first_product_prompt_ignores_stale_delivery_feature
  -q` passed `3 passed`.
- [x] Final focused regression proof: `PYTHONPATH=src pytest
  tests/test_onboarding_api.py tests/test_builder_cli_surfaces.py
  tests/test_embedded_agent_routes.py tests/test_realtime_voice_frontend_static.py
  -q` passed `288 passed`; `npm run lint`, `npm run build`, and
  `git diff --check` passed. The Vite build still reports the existing
  chunk-size warning.

## 2026-05-17 Realtime Auth And Model Boundary

- [x] Grounded the expected Realtime lane in current official OpenAI docs:
  Realtime WebRTC sessions are created server-side through
  `/v1/realtime/calls` with a standard API key, and `gpt-realtime-mini` is the
  cost-efficient GPT Realtime model for audio/text over WebRTC, WebSocket, or
  SIP.
- [x] Verified the implementation boundary: Realtime session creation and
  sideband WebSocket auth use only `OPENAI_API_KEY`; selected runtime
  `RUNTIME_API_KEY_ENV` values are ignored by Realtime; Codex SDK subscription
  runs strip OpenAI API credentials.
- [x] Regression proof: `PYTHONPATH=src pytest
  tests/test_realtime_voice_operator.py::test_realtime_session_requires_openai_api_key
  tests/test_realtime_voice_operator.py::test_realtime_session_does_not_use_selected_runtime_api_key
  tests/test_realtime_voice_operator.py::test_realtime_session_posts_sdp_and_session_as_multipart_fields
  tests/test_realtime_voice_operator.py::test_sideband_registers_tools_and_returns_function_output
  -q` passed `4 passed`; `PYTHONPATH=src pytest
  tests/test_runtime_interface.py::TestNonClaudeRuntimes::test_codex_subscription_env_strips_openai_api_key
  tests/test_realtime_voice_frontend_static.py -q` passed `20 passed`.

## 2026-05-17 Backlog Surface Retest

- [x] Confirmed root `PROGRESS.md` and `GOAL.md` are absent; the active
  objective/progress lane stays under `docs/PLAN.md` and `docs/PROGRESS.md`.
- [x] Browser-tested the managed `todo-app` Backlog page on
  `http://127.0.0.1:9876/backlog` with Chrome/Computer Use after rebuilding the
  dashboard from patched source.
- [x] Verified the visible Backlog happy path uses operator-facing language for
  plain requests, ready work, and shipped work: `Planned improvements`, `Work
  list`, `Ideas`, `Queued`, `Improvement`, `Success checks`, and
  `Prerequisites`.
- [x] Added regression coverage that Backlog metadata continues to use design
  system primitives and displays generated `feature-*` IDs as `item-*`.
- [x] Focused proof passed: `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_dashboard_design_system_contract.py -q` (`19 passed`),
  `builder quality-gate dashboard-ux --json`, `npm run lint`, and
  `npm run build`. The build still reports the existing Vite chunk-size warning.

## 2026-05-17 Agent Active Work Indicator

- [x] Replaced the Agent-page active wait indicator with a design-system
  activity card that shows `Agent`, `Running`, the current tool-use call count,
  and the latest tool name when available.
- [x] Browser proof: after rebuilding and opening a cache-busted Chrome window
  against the managed `todo-app` dashboard, session
  `1d65ce61-b421-485f-bb69-e836d87bd4af` showed
  `Agent working with 0 active tool use calls` and `0 TOOL USE CALLS` while the
  agent was running, instead of the previous dot-loading row.
- [x] Evidence: `builder logs analyze --session
  1d65ce61-b421-485f-bb69-e836d87bd4af --json` reported one prompt, zero tool
  calls, `38,276` raw tokens, `36,224` cached tokens, and `2,052`
  non-cached-plus-output tokens. `builder board show --json` showed the
  remaining blocked item is the prior shipping verification restart, not this
  Agent-page UI behavior.
- [x] Regression proof: `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_embedded_agent_routes.py tests/test_realtime_voice_frontend_static.py
  -q` passed `134 passed`; `npm run build` passed with the existing Vite
  chunk-size warning; `git diff --check` passed.

## 2026-05-18 Completion Validation Sprint

- [x] Rebuild and open the managed `todo-app` dashboard from the current
  Builder checkout in Chrome. Evidence: `builder start --port 9876 --force`
  rebuilt and published the dashboard from this checkout; `builder server
  status --port 9876 --json` reported owned live PID `23482` on
  `http://127.0.0.1:9876`.
- [x] Verify neighboring surfaces before feature creation: Agent, Voice, Board,
  Backlog, Metrics, Settings voice controls, and Inbox. Chrome evidence:
  Agent conversation and Voice tab rendered; Board showed 0 in-progress,
  0 queued, 3 shipped, 0 blocked; Backlog showed `todo-app` with 21 total,
  9 queued, 12 done; Metrics showed 631 runs, 95% pass rate, 4,225,092
  tokens, and `$7.0988`; Observability showed `codex_sdk`, missing signals 0,
  and 4.2M raw tokens; Settings showed Realtime mini, Alloy, push-to-talk hold,
  inline transcript on, bind current session on, and destructive confirmation
  required; Inbox showed 0 pending approval gates.
- [x] Create the frontend/backend review rubrics before further optimization:
  `docs/rubric/frontend-react-architecture.md` owns React architecture,
  performance, context management, and design-system compliance; and
  `docs/rubric/backend-service-architecture.md` owns service boundaries,
  runtime isolation, state ownership, and backend performance.
- [x] Create one feature end to end through the Agent page from a fresh thread,
  including clarification, inline answer/approval, delivery start, Board
  movement, shipped closeout, and Builder-owned log/metric evidence.
- [x] Create one feature end to end through Voice/Samantha from the Voice tab or
  floating control, including visible voice transcript, Agent-page handoff,
  inline answer/approval, Board movement, shipped closeout, and voice/log/metric
  evidence.
- [x] Re-run the source quality gates after browser validation and record
  final evidence in `docs/PROGRESS.md`.
- [x] Fix the approval-regression control owner: the Agent page now exposes the
  actionable `Start now`/`Hold` decision only in the composer/footer pending
  response surface, while the timeline keeps the recorded decision as evidence.
  The shared timeline no longer has a generic action slot that can become a
  second owner.
- [x] Fix the voice handoff duplicate-source regression: voice final summaries,
  completion notifications, persisted delivery permission questions, and sprint
  delivery scope approvals now reconcile to the persisted question when it owns
  the decision. Historic duplicates are marked `superseded`; new handoffs do
  not create another approval while a pending owner exists.
- [x] Replace the Samantha floating control mark with the black/white knot-style
  icon requested by the operator, while preserving the existing `Activate
  Samantha` accessible label and visual active/error states.
- [x] Validate phase rail and drawer semantics in Chrome: Sprint 14 finished
  with all phase dots green only after shipment; Gates, Review, Build, and
  Done opened distinct phase-specific drawers instead of repeating plan/design
  metadata.
- [x] Validate Board start-state behavior in Chrome: after Sprint 14 shipped
  through visible Board continuation, the Board showed no queued/current work
  for that sprint and the `Start work` control was disabled.
- [x] Validate generated-app behavior for the voice-created feature:
  completing `Pay taxes` changed the footer to
  `1 total - 0 active - 1 completed`, reload preserved that count, and
  `Clear 1 completed todo` returned the app to
  `0 total - 0 active - 0 completed` without changing add, filter,
  persistence, or completion behavior.
- [x] Final evidence recorded in `docs/PROGRESS.md`: Sprint 14 board state,
  Agent session `0bc7f16a-0ce9-45e3-8930-bc448483922e`, backend/frontend
  source gates, generated-app gates, workflow owner checks, and
  `git diff --check`. The final post-doc focused regression run passed
  `27 passed`, and `git diff --check` remained clean.
- [x] Decompose the current god-file growth instead of expanding complexity
  baselines: Agent API models, Agent control-owner reconciliation, Realtime
  voice completion digest, voice handoff routing helpers, and focused
  regression tests were moved into named owner modules. `builder lint
  --complexity-report --json` now reports 0 ratchet violations.
- [x] Deep Agent route test decomposition: the previous
  `tests/test_embedded_agent_routes.py` god file is now a 101-line contract
  file; focused route modules cover chat navigation/context, tool events,
  pending questions, tool approvals, feature-spec prompts/capture/backlog,
  sprint start/planning, delivery dispatch/status, recovery, board status,
  documentation routing/tool approval, runtime settings, chat sessions, and
  timeline closeout. Focused split proof passed `127 passed`, and complexity
  report now shows 54 historical over-500 files with 0 violations.
- [x] Production Agent route decomposition continued by moving
  documentation-specialist intent, action resolution, continuation matching, and
  generic specialist route selection to
  `embedded/server/documentation_routing.py`. The new owner is 321 lines,
  `routes/agent.py` dropped to 5,609 lines, and the complexity baseline was
  ratcheted down accordingly. Post-split proof passed the full decomposed Agent
  route suite with `127 passed`, `builder lint --json`, and `git diff --check`.
- [x] Additional route cleanup removed unreachable deterministic Board
  status/recovery handlers and moved active observability context plus
  generated-app surface detection into focused owner modules. `routes/agent.py`
  is now 5,085 lines, and focused route proofs passed for observability,
  forward-engineering bootstrap, Board status, Board questions, and recovery
  status. Full decomposed Agent route proof still passed `127 passed`, and
  complexity passed with 0 violations.
- [x] Continued backend owner extraction by moving Agent transcript projection
  and repo-scoped chat-session lookup out of `routes/agent.py` into
  `embedded/server/agent_chat_transcript.py` and
  `embedded/server/agent_chat_sessions.py`. Realtime Voice now uses those
  owners directly instead of private route helpers. `routes/agent.py` is now
  4,716 lines; the new modules are 228 and 164 lines; the Realtime Voice
  operator test hotspot dropped to 3,090 lines; broad Agent/Realtime proof
  passed `186 passed`, focused post-support proof passed `80 passed`, and
  `builder lint --json` passed with 0 complexity ratchet violations.
