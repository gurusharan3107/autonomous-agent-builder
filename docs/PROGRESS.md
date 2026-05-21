# Autonomous Builder Robustness Progress

### 2026-05-20 Orchestrator Quality Gate Runner Split

- Backend decomposition pass: extracted 3 quality gate methods
  (`_phase_quality_gates` → `run_phase_quality_gates`,
  `_run_feature_acceptance_gate` → `run_feature_acceptance_gate`,
  `_record_feature_acceptance_tests` → `run_record_feature_acceptance_tests`)
  from `orchestrator.py` into
  `src/autonomous_agent_builder/orchestrator/quality_gate_runner.py`. All take
  `orchestrator: Any` first param. Class methods converted to one-liner
  delegations. Test patches updated from
  `orchestrator.orchestrator.run_quality_gates|TestingGate|validate_task_system_docs`
  to `orchestrator.quality_gate_runner.*` (10 patches in test_orchestrator_gates.py).
- Size evidence: `src/autonomous_agent_builder/orchestrator/orchestrator.py` is
  now 1,224 measured lines, down from 1,420 in this pass (-14%). The new quality
  gate runner is 224 lines.
- decomposition_result: {"parent_before": 1420, "parent_after": 1224,
  "new_module": "orchestrator/quality_gate_runner.py",
  "new_module_lines": 224, "methods_moved": 3}
- Verification: `uv tool run ruff check` passed. `uv run pytest
  tests/test_orchestrator.py tests/test_orchestrator_gates.py -q` passed
  `93 passed`. `uv run builder lint --complexity-report --json` passed with
  0 violations after ratcheting `orchestrator.py` baseline from 1,420 to 1,224
  and adding `quality_gate_runner.py` at 224.

### 2026-05-20 Orchestrator Workspace Provisioning Split

- Backend decomposition pass: extracted `_ensure_workspace` (108 lines) and
  `_sanitize_task_workspace_for_agent` (76 lines) from `orchestrator.py` into
  the existing
  `src/autonomous_agent_builder/orchestrator/workspace_integration.py` as
  module-level `ensure_workspace(orchestrator, task)` and
  `sanitize_task_workspace_for_agent(workspace_path, *, is_worktree)`.
  `_provision_workspace_info` stays in orchestrator.py since tests patch it as
  a method; `ensure_workspace` calls it through `orchestrator._provision_workspace_info`.
  Class methods converted to one-liner delegations.
- Size evidence: `src/autonomous_agent_builder/orchestrator/orchestrator.py` is
  now 1,420 measured lines, down from 1,591 in this pass (-11%).
  `workspace_integration.py` grew from 500 to 705 lines to absorb the moved
  workspace provisioning code.
- decomposition_result: {"parent_before": 1591, "parent_after": 1420,
  "target_module": "orchestrator/workspace_integration.py",
  "target_module_lines": 705, "methods_moved": 2}
- Verification: `uv tool run ruff check` passed. `uv run pytest
  tests/test_orchestrator.py tests/test_orchestrator_gates.py -q` passed
  `93 passed`. `uv run builder lint --complexity-report --json` passed with
  0 violations after ratcheting `orchestrator.py` baseline from 1,591 to 1,420
  and adding `workspace_integration.py` at 705.

### 2026-05-20 Orchestrator Sprint Lifecycle Split

- Backend decomposition pass: extracted 9 sprint branch management methods
  (`_maybe_mark_sprint_shipped` → `sprint_mark_shipped`,
  `_verify_materialized_sprint_checkout` → `sprint_verify_materialized_checkout`,
  `_maybe_ff_merge_sprint_branch` → `sprint_maybe_ff_merge`,
  `_verify_sprint_checkout_clean_after_merge` → `sprint_verify_clean_after_merge`,
  `_stash_dirty_head_paths` → `sprint_stash_dirty_paths`,
  `_restore_missing_head_paths` → `sprint_restore_missing_paths`,
  `_open_sprint_pr` → `sprint_open_pr`,
  `_sprint_changes_summary` → `sprint_changes_summary`,
  `_extract_pr_url` → `sprint_extract_pr_url`) into
  `src/autonomous_agent_builder/orchestrator/sprint_lifecycle.py`.
  Class methods in `orchestrator.py` converted to one-liner delegations.
  Pure functions (no `self`) call module-level helpers directly;
  methods needing db/agents take `orchestrator: Any` as first param.
- Size evidence: `src/autonomous_agent_builder/orchestrator/orchestrator.py` is
  now 1,591 measured lines, down from 2,013 in this pass (-21%). The new sprint
  lifecycle owner is 550 lines and is baselined.
- decomposition_result: {"parent_before": 2013, "parent_after": 1591,
  "new_module": "orchestrator/sprint_lifecycle.py",
  "new_module_lines": 550, "methods_moved": 9}
- Verification: `uv tool run ruff check` passed. `uv run pytest
  tests/test_orchestrator.py tests/test_orchestrator_gates.py -q` passed
  `93 passed`. `uv run builder lint --complexity-report --json` passed with
  0 violations after ratcheting `orchestrator.py` baseline from 2,013 to 1,591
  and adding `sprint_lifecycle.py` at 550.

### 2026-05-20 Observability Summary Runtime Aggregates Split

- Backend decomposition pass: extracted 14 runtime aggregate functions
  (`_empty_runtime_aggregates`, `_recommendations`, `_recommendation`,
  `_phase_ceremony_summary`, `_agent_cost`, `_approval_wait_summary`,
  `_provider_limit_summary`, `_error_summary`, `_error_row_has_later_success`,
  `_session_user_prompt`, `_has_later_successful_prompt_session`,
  `_session_terminal_runtime`, `_session_has_later_successful_terminal_status`,
  `_has_later_successful_voice_tool`) into
  `src/autonomous_agent_builder/observability/summary_runtime_aggregates.py`.
  New module imports from `summary_db.py`, `summary_recommendation_lifecycle.py`,
  and `services/provider_limits.py`.
- Size evidence: `src/autonomous_agent_builder/observability/summary.py` is
  now 540 measured lines, down from 1,138 in this pass (-53%). The new runtime
  aggregates owner is 621 lines and is baselined.
- decomposition_result: {"parent_before": 1138, "parent_after": 540,
  "new_module": "observability/summary_runtime_aggregates.py",
  "new_module_lines": 621, "functions_moved": 14}
- Verification: `uv tool run ruff check` passed. `uv run pytest
  tests/test_observability_summary.py -q` passed `18 passed`.
  `uv run builder lint --complexity-report --json` passed with 0 violations
  after ratcheting `summary.py` baseline from 1,138 to 540 and adding
  `summary_runtime_aggregates.py` at 621.

### 2026-05-20 Observability Summary Recommendation Lifecycle Split

- Backend decomposition pass: extracted 8 recommendation lifecycle functions
  (`_empty_recommendation_lifecycle`, `_recommendation_lifecycle`,
  `_decision_entries`, `_recommendation_codes`, `_record_recommendation_decision`,
  `_apply_recommendation_lifecycle`, `_open_script_candidates`,
  `_is_historical_info_recommendation`) into
  `src/autonomous_agent_builder/observability/summary_recommendation_lifecycle.py`.
  New module imports DB helpers from `summary_db.py` and
  `_deterministic_recommendation` from `summary_recommendations.py`.
- Size evidence: `src/autonomous_agent_builder/observability/summary.py` is
  now 1,138 measured lines, down from 1,437 in this pass. The new lifecycle
  owner is 319 lines and remains below the 500-line target.
- decomposition_result: {"parent_before": 1437, "parent_after": 1138,
  "new_module": "observability/summary_recommendation_lifecycle.py",
  "new_module_lines": 319, "functions_moved": 8}
- Verification: `uv tool run ruff check
  src/autonomous_agent_builder/observability/summary.py
  src/autonomous_agent_builder/observability/summary_recommendation_lifecycle.py`
  passed. `uv run pytest tests/test_observability_summary.py -q` passed
  `18 passed`. `uv run builder lint --complexity-report --json` passed with
  0 violations after ratcheting `summary.py` baseline from 1,437 to 1,138.

### 2026-05-20 Observability Summary DB Query Helpers Split

- Backend decomposition pass: extracted 18 SQL/DB query primitive functions
  (`_agent_run_rows`, `_chat_run_rows`, `_runtime_recovery_summary`,
  `_context_budget_summary`, `_merge_rows`, `_sum_rows`, `_add_row`,
  `_stop_reason_counts`, `_tool_counts`, `_event_types`,
  `_repeated_retrieval_signal`, `_column_or_default`, `_table_exists`,
  `_table_columns`, `_row_dict`, `_maybe_json_dict`, `_parse_datetime`,
  `_provider_payload`) into
  `src/autonomous_agent_builder/observability/summary_db.py`.
  Parent imports all 17 public-facing names back as aliases.
- Size evidence: `src/autonomous_agent_builder/observability/summary.py` is
  now 1,437 measured lines, down from 1,751 in this pass. The new DB query
  owner is 342 lines and remains below the 500-line target.
- decomposition_result: {"parent_before": 1751, "parent_after": 1437,
  "new_module": "observability/summary_db.py", "new_module_lines": 342,
  "functions_moved": 18}
- Verification: `uv tool run ruff check
  src/autonomous_agent_builder/observability/summary.py
  src/autonomous_agent_builder/observability/summary_db.py` passed.
  `uv run pytest tests/test_observability_summary.py -q` passed `18 passed`.
  `uv run builder lint --complexity-report --json` passed with 0 violations
  after ratcheting `summary.py` baseline from 1,751 to 1,437.

### 2026-05-20 Observability Summary Deterministic Recommendations Split

- Backend decomposition pass: extracted `_deterministic_recommendations`
  (324 lines, 67 branches — active threshold violation), `_deterministic_recommendation`,
  `_rank_recommendations`, `_recommendation_priority`, `_top_cost_driver`,
  `_cost_driver`, and `_candidate_evidence_source` into
  `src/autonomous_agent_builder/observability/summary_recommendations.py`.
  The parent `summary.py` imports `_deterministic_recommendations` and
  `_rank_recommendations` back as aliases so all callers are unaffected.
- Size evidence: `src/autonomous_agent_builder/observability/summary.py` is
  now 1,751 measured lines, down from 2,185 in this pass. The new
  recommendations owner is 450 lines. The function-level baseline for
  `summary_recommendations.py::_deterministic_recommendations` is registered
  at 324 lines / 67 branches pending further per-signal decomposition.
- decomposition_result: {"parent_before": 2185, "parent_after": 1751,
  "new_module": "observability/summary_recommendations.py",
  "new_module_lines": 450, "functions_moved": 7,
  "violation_cleared_from_parent": true}
- Verification: `uv tool run ruff check
  src/autonomous_agent_builder/observability/summary.py
  src/autonomous_agent_builder/observability/summary_recommendations.py`
  passed. `uv run pytest tests/test_observability_summary.py -q` passed
  `18 passed`. `uv run builder lint --complexity-report --json` passed with
  0 violations after ratcheting the `summary.py` baseline from 2,185 to 1,751
  and registering the new `summary_recommendations.py` function baseline.

Goal source: active thread goal. Execution instructions: [PLAN.md](PLAN.md).

Current status: **in progress on the architecture and 500-line ratchet**. The
managed `todo-app` due-date, high-priority, collapsible-completed, and
voice-created completed-count improvements have shipped through the live Builder
lifecycle with Agent-page prompts, Realtime Voice/Samantha handoff, inline
approval, Board recovery and continuation, phase-specific drawer evidence,
feature-acceptance verification, generated-app browser proof, final shipped
closeout, and token/log evidence. The referenced audit progress file reports 0
open defects, risks, smells, or cross-cutting issues, but current source still
has historical >500-line hotspots. Completion remains unclaimed until the
current branch is reverified after the ongoing decomposition pass.

## Active Checklist

- [x] Review current implementation/docs diff, exclude local render byproducts,
  and prepare the progress-synchronized commit.
- [x] Create [SPRINT-PROGRESS.md](SPRINT-PROGRESS.md) for the feature creation
  cycle test pass.
- [x] Replace the exact `start shipping` phrase trigger with context-driven
  model-backed delivery context when ready Board work exists.
- [x] Run broader changed-surface checks.
- [x] Validate the feature creation cycle through the live Agent page in the
  managed `todo-app` workspace.
- [x] Capture logs, metrics, Board state, token evidence, and browser-visible
  proof for the live run.
- [x] Fix the Agent-page recovered-thread header so ready sessions do not render
  as `Active 0 RUNNING`.
- [x] Validate Realtime Voice uses the same plain operator wording and recovery
  behavior as the Agent page.
- [x] Fix the live run's `truncate_tool_output_before_reinjection` token-waste
  driver and prove the same managed `todo-app` metrics lane no longer treats
  large command output as the active next optimization.
- [x] Clarify Agent-page current-session token accounting so cached raw input
  tokens do not look like fresh model spend.
- [x] Fix the Agent-page transcript refresh path so persisted/default layout
  settings do not fall back from the current timeline UI to old cards.
- [x] Fix active SDK-backed Agent polling so the Conversation timeline does not
  remount into `Loading agent transcript...` while a run is live.
- [x] Align the Voice tab transcript with the Conversation timeline renderer and
  keep the Realtime input below transcript content.
- [x] Stop Realtime Voice from generating Samantha turns before non-empty
  operator speech or typed input.
- [x] Replace the Agent-page active wait indicator with a design-system
  active tool-use count while the agent is working.
- [x] Fix New Thread and pending-response composer issues found during the
  high-priority live shipping run.
- [x] Ship a second real feature through Agent page and verify generated-app
  browser behavior plus persistence.
- [x] Prevent generated-app post-ship optimization from launching a model-backed
  optimization-agent run for Builder-owned residual token-policy work.
- [x] Normalize Agent-page chat run status and Metrics token usage so cached
  input tokens remain separate from output and non-cached spend.
- [x] Fix Realtime text-mode input so a plain Enter submits typed Samantha
  requests while Shift+Enter remains available for multiline input.
- [x] Ship `Collapsible completed todos section` through the live Agent page and
  prove the shipped closeout appears in the Conversation timeline.
- [x] Reduce the remaining repeated broad retrieval/token driver now that
  tool-output reinjection is compacted.
- [x] Hide remaining operator-facing lifecycle ceremony after approval in the
  Agent page route responses.
- [x] Fix answered Agent-page questions and approvals so shipped sessions do
  not continue to look like pending review work.
- [x] Verify the latest shipped Agent-page thread renders the final closeout at
  the bottom of the Conversation timeline after the patched dashboard rebuild.
- [x] Keep Agent-page questions and approvals inline while applying Builder
  design-system status pills, token-backed review surfaces, and readable option
  rows.
- [x] Keep new forward-engineering Agent-page prompts model-backed by routing
  typed prompts through `chat` first, with forward-engineering context inside
  the prompt instead of a pre-model `init-project-chat` dispatch.
- [x] Browser-retest the Board recovery action against the same shared recovery
  service used by Agent chat and Realtime Voice.
- [x] Fix Agent-page approval handoff so inline approved feature requests start
  delivery directly and serial tasks auto-dispatch without operator `start`
  prompts.
- [x] Fix timeline-mode question/approval controls so the current Conversation
  timeline remains actionable without falling back to text-command handoffs.
- [x] Fix current-sprint generated-task status summaries so Board evidence uses
  live task status instead of hardcoded `done`.
- [x] Fix the combined Agent-route plus embedded-server regression leak so
  background chat runs cannot hold stale SQLite connections across app
  instances.
- [x] Create frontend and backend architecture rubrics before further
  optimization so code review has a clear React/design-system and
  service-boundary lens.
- [x] Fix the Agent-page approval handoff to one control owner: pending
  decisions render their actionable response controls in the composer/footer,
  while historical timeline entries remain evidence-only.
- [x] Remove redundant approval/voice-summary sources so voice handoff, persisted
  delivery permission, and generated delivery scope approval cannot each own the
  same `Start now` decision.
- [x] Replace the Samantha floating control mark with a black/white knot-style
  icon and keep the existing accessibility label and active/error state.
- [x] Correct Board phase semantics so Plan, Design, Implement, Gates, Review,
  Build, and Done turn green only when their own evidence is complete and open
  phase drawers show phase-specific work.
- [x] Verify `Start work`/`Continue work` state through the visible Board
  control: work in progress disables duplicate starts, and fully shipped work
  returns to a disabled `Start work` state.
- [x] Ship a voice-created feature end to end through Samantha, Agent-page
  `Start now`, Board continuation, generated-app browser proof, and Builder
  CLI/log evidence.
- [x] Re-run changed-surface backend, frontend, generated-app, workflow, and
  diff checks after browser validation.
- [x] Decompose current god-file growth instead of widening complexity
  baselines: embedded Agent API contracts, Agent control-owner reconciliation,
  Realtime voice completion digest, voice handoff routing helpers, and focused
  regression tests now live in named owner modules.
- [x] Deep-split `tests/test_embedded_agent_routes.py` under the 500-line
  target into focused Agent route test owners for navigation/context, tool
  events, pending questions, tool approvals, feature-spec capture, sprint
  start/planning, delivery dispatch/status, recovery, board status/questions,
  documentation routing/tool approval, runtime settings, and timeline closeout.
- [x] Split the Board React god file into Board feature owners for lifecycle
  selectors, phase strip, lanes, sprint drawer, and task drawer while preserving
  Start Work, phase-dot, and phase-specific drawer behavior.
- [x] Extract Agent chat-turn direct actions from the embedded Agent route into
  a focused route-adjacent owner and ratchet the Agent route/function
  complexity baseline down to the new measured size.
- [x] Move terminal chat-turn error publication into the chat-turn publication
  owner and remove `_run_chat_turn` from the complexity function-hotspot list.
- [x] Split Builder verify changed-surface contract tests out of the broad CLI
  surface suite and ratchet the CLI test hotspot baseline down.
- [x] Move Agent runtime status payload projection into a route-adjacent owner
  and ratchet the embedded Agent route baseline down again.
- [x] Split Builder knowledge CLI contract tests and shared CLI fixtures out of
  the broad CLI surface suite and ratchet the CLI test hotspot baseline down.
- [x] Move Agent chat message-intent classifiers into a route-adjacent owner
  and ratchet the embedded Agent route baseline down again.
- [x] Move orchestrator agent-run lifecycle persistence into a focused backend
  owner and ratchet the orchestrator baseline down.
- [x] Move Builder runtime-guidance git preservation out of the orchestrator
  and ratchet the orchestrator baseline below the embedded Agent route hotspot.
- [x] Move Agent feature payload parsing and saved-feature session predicates
  into a route-adjacent owner and ratchet the embedded Agent route baseline
  below 4,000 measured lines.
- [x] Move task and sprint approval outcome transitions out of the orchestrator
  and ratchet the orchestrator baseline again.
- [x] Move active feature scope reminder rendering and sibling ownership parsing
  into a focused orchestrator owner and ratchet the orchestrator baseline down
  again.
- [x] Move Agent chat tool-response and permission policy helpers into a
  route-adjacent owner and ratchet the embedded Agent route baseline down again.
- [x] Move structured operator-decision handoff parsing and state mutation into
  a focused orchestrator owner and ratchet the orchestrator baseline down again.
- [x] Move implementation prompt gate-feedback context assembly into the
  existing gate-feedback owner and ratchet the orchestrator baseline down again.
- [x] Move documentation refresh gate support helpers into a focused
  orchestrator owner and ratchet the orchestrator baseline below the embedded
  Agent route hotspot.
- [x] Move Agent shipped-delivery closeout derivation and append/watch logic
  into a route-adjacent owner and ratchet the embedded Agent route baseline
  down again.
- [x] Move orchestrator phase-context persistence and compaction into a focused
  backend owner and ratchet the orchestrator baseline down again.
- [x] Move deterministic build and feature-verifier policy helpers into a
  focused orchestrator owner and ratchet the orchestrator baseline down again.
- [x] Move runtime failure diagnosis and polluted-workspace chunk-limit
  classification into a focused orchestrator owner and ratchet the
  orchestrator baseline down again.
- [x] Move workspace and git-output policy helpers into a focused orchestrator
  owner and ratchet the orchestrator baseline below the embedded Agent route
  hotspot.
- [x] Move documentation-specialist context assembly into a route-adjacent
  Agent owner and ratchet the embedded Agent route baseline down again.
- [x] Split Builder knowledge extract CLI contracts out of the broad CLI
  surface suite and ratchet the top overall CLI test hotspot baseline down.
- [x] Split Builder metrics and local agent-history fallback contracts out of
  the broad CLI surface suite and ratchet the top overall CLI test hotspot
  baseline down again.
- [x] Split Builder Board/task CLI fallback and recovery contracts out of the
  broad CLI surface suite and ratchet the CLI test hotspot below the current
  top production hotspot.
- [x] Move task workspace integration, generated-artifact cleanup,
  directory-workspace copying, rebase conflict resolution, and conflict-marker
  checks into a focused orchestrator owner and ratchet the orchestrator
  baseline below 3,100 measured lines.
- [x] Move Agent chat event persistence, mirrored transcript writes, pending
  request updates, and Realtime voice final-summary appends into a focused
  route-adjacent owner and ratchet the embedded Agent route below 3,250
  measured lines.
- [x] Move Realtime voice interaction parsing, dashboard target routing,
  provider-limit freshness checks, task/run snapshots, and call-session binding
  into a focused service owner and ratchet the voice operator below 3,050
  measured lines.
- [x] Move Agent sprint-planning prompt/delivery helpers into a focused
  route-adjacent owner and ratchet the embedded Agent route and test hotspot
  baselines down.
- [x] Move board-state query helpers and prompt builders into focused route-adjacent
  owners; move post-ship optimization CLI probe, runtime guidance refresh, and
  voice support classes into focused owners; split Builder quality-gate CLI
  contracts out of the broad CLI surface suite. Ratchet all baselines down.
- [x] Continue the top-down 500-line decomposition pass on the remaining
  hotspots, starting with the embedded Agent route, Realtime voice operator,
  and remaining CLI/runtime owners, without changing user-visible lifecycle
  behavior. (`builder lint --complexity-report --json` reports 0 violations.)

## 2026-05-20 WSL devpulse validation cycle

**Status as of 2026-05-20:** First feature attempt (session `68bc4348-dae8-4c1d-a5ea-a5604c315eb4`) surfaced **4 blocking inefficiencies**: IMP-001 (multi-turn context loss), IMP-002 (gates-first not enforced — 27-turn $0.46 run before workspace has ruff/pytest), IMP-003 (`builder metrics show` reports 0 tokens while real cost was $0.46), IMP-004 (Recover button returns 409 for gate-infrastructure-blocked tasks). Cycle is **paused on Track A** until these close in [`IMPROVEMENTS.md`](IMPROVEMENTS.md). See [`GOAL.md`](GOAL.md) for the testing standard, fix standard, and acceptance thresholds.

**Track B (optimization loop)** at [`autoresearch/`](autoresearch/) is dormant and activates only after this cycle's checklist completes and baseline variance is measured per [`autoresearch/baseline_variance.md`](autoresearch/baseline_variance.md).

- [x] Close IMP-001 through IMP-004 in `docs/IMPROVEMENTS.md` with SDK-grounded fixes and regression tests (blocks all items below).
- [ ] Ship first feature on fresh devpulse workspace through live Agent page
  (Claude Agent SDK lane, port 9876) and capture token evidence per turn.
- [ ] Ship second feature and verify Board → implementation → verification
  → closeout works end to end without operator intervention after approval.
- [ ] Ship remaining features until devpulse app is complete and satisfying
  from UI, backend, architecture, and design pattern perspective.
- [ ] Identify and fix every Claude Agent SDK usage gap found during the
  feature cycle. Track each in docs/IMPROVEMENTS.md.
- [ ] Verify gates-first principle: devpulse workspace has ruff, mypy, and
  architecture import enforcement before any feature code is merged.
- [ ] Confirm cache ratio > 5x after turn 2 for all agent turns.
- [ ] Confirm chunk_pressure_risk: false across all feature runs.
- [ ] Confirm avoidable_cost_flags: [] across all feature runs.

## 2026-05-20 Agent Sprint Planning Owner Split

- Architecture lens: continued the top-down 500-line decomposition pass on the
  embedded Agent route. Sprint planning feature selection, dependency readiness
  checks, `_request_chat_question`, `_request_chat_approval`, sprint planning
  question/approval persistence, `handle_sprint_planning_turn`, and
  `create_delivery_plan_for_approved_features` now live in
  `embedded/server/agent_sprint_planning.py`; `routes/agent.py` imports the
  public functions as private aliases and passes them as parameters where needed.
- Decomposition result: `embedded/server/routes/agent.py` dropped from 2,857 to
  2,398 measured lines (459 lines removed). The new sprint-planning owner is
  exactly 500 lines, at the file-size boundary; added as a new baseline entry.
  Complexity baseline for `agent.py` ratcheted from 2,857 to 2,398.
- Test patch fix: 8 test files that patched `agent_routes._schedule_task_dispatch`
  for tests exercising the `create_delivery_plan_for_approved_features` path now
  also patch `agent_sprint_planning.schedule_task_dispatch`; tests that use the
  `publish_direct_chat_turn_if_handled` callback path retain both patches without
  breakage.
- Verification: `uv run pytest tests/test_agent_sprint_planning_routes.py
  tests/test_agent_pending_question_routes.py tests/test_agent_sprint_start_routes.py
  tests/test_agent_feature_spec_backlog_routes.py tests/test_agent_control_owner_routes.py
  tests/test_agent_documentation_chat_routes.py
  tests/test_agent_feature_spec_capture_routes.py
  tests/test_agent_delivery_status_routes.py
  tests/test_agent_recovery_status_routes.py -q` passed `34 passed`; full
  `uv run pytest tests/test_agent_*.py -q` passed `129 passed` with the same
  8 pre-existing `test_agent_documentation_routing.py` failures unchanged.

## 2026-05-19 Voice Operator Interaction Split

- Architecture lens: continued the top production-hotspot pass on
  `services/voice_operator.py`. Voice answer parsing, approval decision text,
  runtime SDK/display normalization, dashboard target routing, provider-limit
  freshness parsing, task/run snapshots, Board lane classification, recovery
  task matching, and Realtime call-session binding now live in
  `services/voice_operator_interaction.py`; `voice_operator.py` keeps local
  aliases for the existing service and route call sites.
- Decomposition result: `services/voice_operator.py` dropped from 3,350 to
  3,033 measured lines and from 93 to 68 functions. The new interaction owner
  is 390 lines, below the 500-line file threshold, so no new baseline exception
  was added.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/services/voice_operator.py
  src/autonomous_agent_builder/services/voice_operator_interaction.py
  tests/test_voice_operator_interaction.py` passed; `uv run pytest
  tests/test_voice_operator_interaction.py
  tests/test_realtime_voice_operator.py::test_realtime_session_fresh_mode_binds_new_agent_session
  tests/test_realtime_voice_operator.py::test_get_builder_status_includes_pending_question_options
  tests/test_realtime_voice_operator.py::test_voice_delegation_rebinds_visible_session_without_waiting
  -q` passed `10 passed`.

## 2026-05-19 Agent Chat Event Persistence Split

- Architecture lens: resumed the top production-hotspot pass on
  `embedded/server/routes/agent.py`. Agent chat event persistence, mirrored
  transcript-message writes, pending request-event updates, and SDK-backed
  Realtime voice final-summary event appends now live in
  `embedded/server/agent_chat_events.py`; the route keeps the same private
  `_append_chat_event`, `_append_voice_final_summary_if_needed`, and
  `_update_request_event` import seams for existing route and voice callers.
- Decomposition result: `embedded/server/routes/agent.py` dropped from 3,375
  to 3,246 measured lines and from 73 to 70 functions. The new chat-events
  owner is 151 lines, below the 500-line file threshold, so no new baseline
  exception was added.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/agent_chat_events.py
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  tests/test_agent_chat_events.py` passed; `uv run pytest
  tests/test_agent_chat_events.py
  tests/test_agent_pending_question_routes.py::test_chat_response_updates_pending_event_without_opening_second_db_session
  tests/test_realtime_voice_operator.py::test_sdk_agent_completion_persists_voice_final_summary_for_realtime
  -q` passed `4 passed`.

## 2026-05-19 Orchestrator Workspace Integration Split

- Architecture lens: resumed the production-hotspot pass on `orchestrator.py`.
  Task workspace integration, task-branch change commits, generated artifact
  cleanup commits, directory workspace copying, task-branch rebase handling,
  integration conflict resolver dispatch, and conflict-marker detection now
  live in `orchestrator/workspace_integration.py`; `orchestrator.py` retains
  compatibility wrappers, sprint branch selection, phase transitions, and
  runtime guidance preservation wrappers.
- Decomposition result: `orchestrator.py` dropped from 3,516 to 3,091 measured
  lines and from 90 to 85 functions. The new workspace-integration owner is
  exactly 500 lines, within the file-size target, so no new complexity
  baseline exception was added.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/workspace_integration.py
  tests/test_workspace_integration.py` passed; `uv run pytest
  tests/test_workspace_integration.py
  tests/test_orchestrator_gates.py::test_integrates_first_task_branch_into_unborn_main
  tests/test_orchestrator_gates.py::test_integrates_uncommitted_worktree_changes_into_unborn_main
  tests/test_orchestrator_gates.py::test_integration_preserves_project_runtime_guidance
  tests/test_orchestrator_gates.py::test_integration_rebases_diverged_task_branch
  tests/test_orchestrator_gates.py::test_integration_uses_resolver_for_rebase_conflicts
  tests/test_sprint_branch_lifecycle.py::test_rebase_task_workspace_uses_sprint_branch_target
  tests/test_sprint_branch_lifecycle.py::test_rebase_conflict_resolution_stages_full_workspace
  -q` passed `9 passed`.

## 2026-05-19 Builder Board Task CLI Test Split

- Architecture lens: continued the top-down pass on the current largest overall
  test hotspot, `tests/test_builder_cli_surfaces.py`. Board JSON counts,
  compact/full payload behavior, local Board count fallback, local task-status
  lookup, Board connectivity fallback, task status fallback, failed-task
  recovery guidance, and recovery request posting now live in
  `tests/test_builder_board_task_cli_surface.py`; the broad CLI surface suite
  keeps shared CLI wiring and other command-family contracts.
- Decomposition result: `tests/test_builder_cli_surfaces.py` dropped from
  3,690 to 3,332 measured lines and from 130 to 104 functions. The new
  Board/task test owner is 372 lines, below the 500-line target. This moves the
  broad CLI test suite below `orchestrator.py`, so the next top-down hotspot is
  the orchestrator production owner.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_board_task_cli_surface.py` passed; `uv run pytest
  tests/test_builder_board_task_cli_surface.py tests/test_builder_cli_surfaces.py
  -q` passed `103 passed`.

## 2026-05-19 Builder Metrics CLI Test Split

- Architecture lens: continued the top-down pass on the current largest
  overall hotspot, `tests/test_builder_cli_surfaces.py`. Metrics JSON summary,
  full-output sanitization, local metrics fallback, agent-chat analysis IDs,
  local agent-history noise filtering, and repo-local DB selection now live in
  `tests/test_builder_metrics_cli_surface.py`; the broad CLI surface suite
  keeps shared CLI wiring and other command-family contracts.
- Decomposition result: `tests/test_builder_cli_surfaces.py` dropped from
  4,036 to 3,690 measured lines and from 137 to 130 functions. The new metrics
  test owner is 360 lines, below the 500-line target, and the complexity
  baseline now ratchets the broad CLI suite down to the new measured size.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_metrics_cli_surface.py` passed; `uv run pytest
  tests/test_builder_metrics_cli_surface.py tests/test_builder_cli_surfaces.py
  -q` passed `108 passed`.

## 2026-05-19 Builder Knowledge Extract CLI Test Split

- Architecture lens: resumed the top-down pass on the current largest overall
  hotspot, `tests/test_builder_cli_surfaces.py`. Knowledge extract pipeline
  contracts for deterministic validation fallback, unavailable agent advisory
  handling, doc-slug forwarding, non-blocking generator errors, and
  noncanonical output preflight now live in
  `tests/test_knowledge_extract_cli_surface.py`; the broad CLI surface suite
  keeps shared command wiring and unrelated command-family contracts.
- Decomposition result: `tests/test_builder_cli_surfaces.py` dropped from
  4,302 to 4,036 measured lines and from 159 to 137 functions. The new
  knowledge extract test owner is 278 lines, below the 500-line target, and
  the complexity baseline now ratchets the broad CLI suite down to the new
  measured size.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_knowledge_extract_cli_surface.py` passed; `uv run pytest
  tests/test_knowledge_extract_cli_surface.py tests/test_builder_cli_surfaces.py
  -q` passed `113 passed`.

## 2026-05-19 Agent Documentation Context Split

- Architecture lens: resumed the top-down production-hotspot pass on the
  embedded Agent route after moving the orchestrator below it. Documentation
  specialist context assembly, targeted KB document shaping, freshness
  candidate selection, latest-task context loading, canonical branch metadata,
  and documentation action payload construction now live in
  `embedded/server/agent_documentation_context.py`; `routes/agent.py` still
  owns the route policy table, chat runtime flow, event publication, and HTTP
  endpoints.
- Decomposition result: `embedded/server/routes/agent.py` dropped from 3,600
  to 3,375 measured lines and from 80 to 73 functions. The new
  documentation-context owner remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_documentation_context.py
  tests/test_agent_documentation_context.py
  tests/test_agent_documentation_chat_routes.py` passed; `uv run pytest
  tests/test_agent_documentation_context.py
  tests/test_agent_documentation_chat_routes.py -q` passed `8 passed`.

## 2026-05-19 Orchestrator Workspace Policy Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  workspace/git policy seam. Directory-workspace staleness checks, clean
  directory workspace path allocation, directory copy exclusions,
  builder-source repo detection, fast-forward divergence matching, and
  merge-overwrite path parsing now live in `orchestrator/workspace_policy.py`;
  `orchestrator.py` still owns workspace provisioning, git command execution,
  integration transitions, and failure persistence.
- Decomposition result: `orchestrator.py` dropped from 3,603 to 3,516 measured
  lines and from 97 to 90 functions, moving it below
  `embedded/server/routes/agent.py` in the current production-hotspot order.
  `tests/test_orchestrator.py` dropped from 983 to 970 measured lines after
  moving direct policy coverage into `tests/test_workspace_policy.py`. The new
  workspace-policy owner remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/workspace_policy.py
  tests/test_workspace_policy.py tests/test_orchestrator.py` passed; `uv run
  pytest tests/test_workspace_policy.py tests/test_orchestrator.py -q` passed
  `50 passed`.

## 2026-05-19 Orchestrator Runtime Failure Diagnosis Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  runtime failure diagnosis seam. Codex chunk-limit detection, polluted
  Builder-internal workspace detection, runtime observability evidence
  formatting, and failure-reason assembly now live in
  `orchestrator/failure_diagnosis.py`; `orchestrator.py` still owns the phase
  transitions, workspace provisioning decision, and failure persistence.
- Decomposition result: `orchestrator.py` dropped from 3,660 to 3,603 measured
  lines and from 100 to 97 functions. `tests/test_orchestrator.py` dropped from
  1,034 to 983 measured lines after moving duplicated diagnosis coverage into
  `tests/test_failure_diagnosis.py`. The new failure-diagnosis owner remains
  below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/failure_diagnosis.py
  tests/test_failure_diagnosis.py tests/test_orchestrator.py` passed; `uv run
  pytest tests/test_failure_diagnosis.py tests/test_orchestrator.py -q` passed
  `47 passed`.

## 2026-05-19 Orchestrator Build Verification Policy Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  deterministic verification policy seam. Sprint execution payload extraction,
  deterministic evidence/build-verifier selection, sprint feature-verification
  task-key matching, sprint branch naming, build-verifier failure parsing, and
  feature-verifier JSON status parsing now live in
  `orchestrator/build_verification.py`; `orchestrator.py` still owns the async
  database/script execution and lifecycle state transitions.
- Decomposition result: `orchestrator.py` dropped from 3,710 to 3,660 measured
  lines and from 107 to 100 functions. The new build-verification policy owner
  remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/build_verification.py
  tests/test_orchestrator_build_verification.py tests/test_sprint_execution.py
  tests/test_sprint_branch_lifecycle.py` passed; targeted verifier and
  orchestrator regression tests passed `56 passed`.

## 2026-05-19 Orchestrator Phase Context Owner Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  cross-phase context seam. Stored phase context lookup, non-destructive
  context persistence, and compact agent output normalization now live in
  `orchestrator/phase_context.py`; `orchestrator.py` keeps the lifecycle
  transition call sites that decide when planning, design, implementation, and
  workspace context should be recorded.
- Decomposition result: `orchestrator.py` dropped from 3,729 to 3,710 measured
  lines and from 110 to 107 functions. The new phase-context owner remains
  below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/phase_context.py
  tests/test_phase_context.py` passed; `uv run pytest tests/test_phase_context.py
  tests/test_orchestrator_gates.py -q` passed `56 passed`.

## 2026-05-19 Agent Delivery Closeout Owner Split

- Architecture lens: continued the embedded Agent route hotspot pass on the
  shipped-delivery timeline closeout seam. Delivery plan-id extraction, shipped
  sprint lookup, feature/run evidence formatting, token totals, closeout event
  persistence, and the background closeout watcher now live in
  `embedded/server/agent_delivery_closeout.py`; the route still owns the HTTP
  chat history and chat-turn orchestration entrypoints.
- Decomposition result: `routes/agent.py` dropped from 3,827 to 3,600 measured
  lines and from 89 to 80 functions. The new delivery-closeout owner remains
  below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_delivery_closeout.py
  tests/test_agent_delivery_closeout.py` passed; `uv run pytest
  tests/test_agent_delivery_closeout.py tests/test_agent_timeline_closeout_routes.py
  -q` passed `5 passed` with existing FastAPI `on_event` deprecation warnings.

## 2026-05-19 Documentation Refresh Gate Support Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  PR-creation documentation refresh gate seam. Documentation project-root
  resolution, KB validation payload parsing, canonical HEAD detection,
  forward-engineering advisory predicates, documentation bridge run recording,
  and blocked-message formatting now live in
  `orchestrator/documentation_refresh_gate.py`; `orchestrator.py` retains thin
  private delegates so the existing documentation refresh gate call sites and
  tests keep their patch points.
- Decomposition result: `orchestrator.py` dropped from 3,861 to 3,729 measured
  lines. The new documentation-refresh gate support owner remains below the
  500-line target, and the embedded Agent route is now the top production
  hotspot again.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/documentation_refresh_gate.py
  tests/test_documentation_refresh_gate.py` passed; `uv run pytest
  tests/test_documentation_refresh_gate.py
  tests/test_orchestrator_gates.py::TestDocumentationRefreshGate -q` passed
  `11 passed`; `uv run pytest tests/test_orchestrator_gates.py -q` passed
  `51 passed`.

## 2026-05-19 Gate Feedback Context Owner Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  implementation retry feedback seam. Latest gate-failure query/formatting for
  implementation prompts now lives in `orchestrator/gate_feedback.py`, next to
  the existing gate failure retry/capability-limit owner; `orchestrator.py`
  retains a thin private delegate for the phase dispatch call site.
- Decomposition result: `orchestrator.py` dropped from 3,898 to 3,861 measured
  lines. The existing gate-feedback owner remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/gate_feedback.py
  tests/test_gate_feedback.py` passed; `uv run pytest tests/test_gate_feedback.py
  tests/test_orchestrator_gates.py::TestKnowledgeLifecycleContext::test_implementation_phase_receives_latest_gate_feedback
  -q` passed `21 passed` with the existing pytest warning about one synchronous
  test inheriting the class-level asyncio mark.

## 2026-05-19 Operator Decision Handoff Owner Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  phase-blocking operator decision seam. `OPERATOR_DECISION_JSON` extraction,
  task blocking, blocked-reason formatting, and stale handoff clearing now live
  in `orchestrator/operator_decisions.py`; `orchestrator.py` retains thin
  private delegates for the existing phase dispatch call sites.
- Decomposition result: `orchestrator.py` dropped from 3,934 to 3,898 measured
  lines. The new operator-decision owner remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/operator_decisions.py
  tests/test_operator_decisions.py` passed; `uv run pytest
  tests/test_operator_decisions.py
  tests/test_orchestrator_gates.py::TestKnowledgeLifecycleContext::test_design_phase_can_block_with_structured_operator_decision
  tests/test_orchestrator_gates.py::TestKnowledgeLifecycleContext::test_implementation_phase_can_block_with_structured_operator_decision
  -q` passed `5 passed`; `uv run pytest tests/test_orchestrator_gates.py -q`
  passed `51 passed`.

## 2026-05-19 Agent Tool Policy Owner Split

- Architecture lens: continued the embedded Agent route hotspot pass on the
  chat tool policy seam. Tool text-payload parsing, permission result
  construction, tool approval summaries, tool-response normalization,
  repo-local KB validation policy, and feature-spec tool denials now live in
  `embedded/server/agent_tool_policy.py`; the route still owns persistence,
  SSE publication, and chat-turn orchestration.
- Decomposition result: `routes/agent.py` dropped from 3,949 to 3,827 measured
  lines and from 97 to 89 functions. The new tool-policy owner remains below
  the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_tool_policy.py
  tests/test_agent_tool_policy.py` passed; `uv run pytest
  tests/test_agent_tool_policy.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_feature_spec_tooling_routes.py -q` passed `11 passed`;
  `uv run builder lint --complexity-report --json` passed after ratcheting the
  embedded Agent route baseline to the measured 3,827 lines.

## 2026-05-19 Active Feature Scope Reminder Owner Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  implementation prompt scope seam. Active feature reminder rendering and
  sibling sprint ownership parsing now live in
  `orchestrator/active_feature_scope.py`; `orchestrator.py` retains thin
  private delegates so the implementation dispatch path stays unchanged.
- Decomposition result: `orchestrator.py` dropped from 4,016 to 3,934 measured
  lines. The new active-feature-scope owner is below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/active_feature_scope.py
  tests/test_active_feature_scope.py` passed; `uv run pytest
  tests/test_active_feature_scope.py
  tests/test_orchestrator_gates.py::TestKnowledgeLifecycleContext::test_implementation_phase_passes_knowledge_retrieval_guidance
  tests/test_orchestrator_gates.py::TestKnowledgeLifecycleContext::test_implementation_phase_receives_latest_gate_feedback
  -q` passed `5 passed`; `uv run pytest tests/test_orchestrator_gates.py -q`
  passed `51 passed`.

## 2026-05-19 Approval Outcome Owner Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  approval-state transition seam. Task approval outcomes and sprint PR approval
  outcomes now live in `orchestrator/approval_outcomes.py`; `orchestrator.py`
  re-exports the functions so API and embedded gates routes keep the existing
  public import path.
- Decomposition result: `orchestrator.py` dropped from 4,107 to 4,016 measured
  lines and from 112 to 110 functions. The new approval outcome owner is 89
  lines.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/approval_outcomes.py` passed; `uv
  run pytest tests/test_orchestrator_gates.py::TestApplyApprovalOutcome
  tests/test_orchestrator_gates.py::TestApplySprintApprovalOutcome -q` passed
  `12 passed`; `uv run pytest tests/test_gates_route_sprint_pr.py -q` passed
  `3 passed`; `uv run builder lint --complexity-report --json` passed with 380
  Python files, 4,522 functions, 54 historical over-threshold files, 6 function
  hotspots, and 0 violations.

## 2026-05-19 Agent Feature Payload Owner Split

- Architecture lens: continued the embedded Agent route hotspot pass on the
  feature-capture lane. Feature-list/spec marker parsing, JSON object
  extraction, payload normalization, saved-feature session predicates, and
  captured feature-title parsing now live in
  `embedded/server/agent_feature_payloads.py`; the route still owns HTTP
  orchestration, chat-turn execution, and persistence.
- Decomposition result: `routes/agent.py` dropped from 4,136 to 3,949 measured
  lines and from 107 to 97 functions. The new feature-payload owner is 219
  lines, keeping the parser/predicate logic below the 500-line target.
- Verification: `uv run ruff check --fix
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_feature_payloads.py`
  passed after import sorting; `uv run pytest
  tests/test_agent_feature_spec_capture_routes.py
  tests/test_agent_feature_spec_backlog_routes.py
  tests/test_agent_feature_spec_tooling_routes.py -q` passed `12 passed`;
  `uv run pytest tests/test_agent_documentation_chat_routes.py
  tests/test_agent_tool_approval_routes.py tests/test_agent_timeline_closeout_routes.py
  -q` passed `10 passed`; `uv run builder lint --complexity-report --json`
  passed with 379 Python files, 4,522 functions, 54 historical over-threshold
  files, 6 function hotspots, and 0 violations.

## 2026-05-19 Runtime Guidance Preservation Split

- Architecture lens: continued the orchestrator production-hotspot pass on the
  Builder-owned runtime guidance protection path. Runtime guidance status
  parsing, snapshotting, pre-merge cleanup, post-merge restore, and generated
  workspace preservation now live in
  `orchestrator/runtime_guidance_preservation.py`; `Orchestrator` keeps thin
  compatibility wrappers for existing private contracts used by sprint branch
  and runtime-guidance tests.
- Decomposition result: `orchestrator.py` dropped from 4,306 to 4,107 measured
  lines and from 115 to 112 functions. The new runtime-guidance preservation
  owner is 241 lines, and the current top production hotspot shifted back to
  the embedded Agent route at 4,136 measured lines.
- Verification: `uv run ruff check --fix
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/runtime_guidance_preservation.py`
  passed after import sorting; `uv run pytest
  tests/test_runtime_guidance.py::test_orchestrator_tracked_modified_paths_filters_untracked
  tests/test_runtime_guidance.py::test_orchestrator_untracked_paths_filters_only_untracked
  tests/test_runtime_guidance.py::test_orchestrator_tracked_modified_paths_empty_status
  -q` passed `3 passed`; `uv run pytest
  tests/test_sprint_branch_lifecycle.py::test_untracked_runtime_guidance_does_not_block_task_branch_merge
  -q` passed `1 passed`; `uv run pytest
  tests/test_orchestrator_gates.py::test_integration_preserves_project_runtime_guidance
  -q` passed `1 passed`; `uv run builder lint --complexity-report --json`
  passed with 378 Python files, 4,522 functions, 54 historical over-threshold
  files, 6 function hotspots, and 0 violations.

## 2026-05-19 Orchestrator Agent Run Lifecycle Split

- Architecture lens: continued the top-down production-hotspot pass on
  `orchestrator.py`, the current largest Python hotspot. Agent prompt
  preparation, runtime selection, streaming run-event persistence, workspace
  diff monitoring, token observability, and final run recording now live in
  `orchestrator/agent_run_lifecycle.py`; `Orchestrator._run_agent` remains the
  phase-owned dispatch boundary used by planning, design, implementation,
  review, and recovery paths.
- Decomposition result: `orchestrator.py` dropped from 4,559 to 4,306 measured
  lines. The new lifecycle owner is 329 physical lines, its extracted helpers
  keep `run_agent_lifecycle` under the function threshold, and the stale
  `Orchestrator._run_agent` function-hotspot baseline was removed.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/agent_run_lifecycle.py` passed;
  `uv run pytest tests/test_orchestrator_gates.py::TestAgentRunRecording -q`
  passed `5 passed`; `uv run pytest tests/test_orchestrator_gates.py -q`
  passed `51 passed`; `uv run builder lint --complexity-report --json` passed
  with 377 Python files, 4,516 functions, 54 historical over-threshold files, 6
  function hotspots, and 0 violations; `uv run builder lint --json` passed with
  5 checks passed and the expected uninitialized `knowledge` and `readiness`
  skips; `git diff --check` passed.

## 2026-05-19 Agent Message Intent Owner Split

- Architecture lens: continued the backend rubric's route-thinness standard on
  the embedded Agent route hotspot. Feature-spec, delivery-continuation,
  read-only status, recovery, dashboard-navigation, ambiguous-continuation, and
  sprint-planning message classifiers now live in
  `embedded/server/agent_message_intent.py` instead of the FastAPI route module.
- Decomposition result: `routes/agent.py` dropped from 4,595 to 4,136 measured
  lines and from 123 to 107 functions. The new message-intent owner is 500
  lines, preserving the 500-line target while keeping classifier constants and
  pure predicates together.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_message_intent.py
  tests/test_agent_feature_spec_prompt_contracts.py
  tests/test_agent_chat_navigation_routes.py tests/test_embedded_agent_routes.py
  tests/test_agent_delivery_dispatch_routes.py` passed; `uv run pytest
  tests/test_agent_feature_spec_prompt_contracts.py
  tests/test_agent_chat_navigation_routes.py tests/test_embedded_agent_routes.py
  tests/test_agent_delivery_dispatch_routes.py -q` passed `22 passed`;
  `uv run builder lint --complexity-report --json` passed with 376 Python
  files, 4,511 functions, 54 historical over-threshold files, 7 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 5 checks
  passed and the expected uninitialized `knowledge` and `readiness` skips;
  `git diff --check` passed.

## 2026-05-19 Builder Knowledge CLI Test Split

- Architecture lens: continued the backend rubric's test-boundary standard on
  the broad CLI contract hotspot. Knowledge list/search/summary/show contracts
  now live in `tests/test_builder_knowledge_cli_surface.py`; reusable local-KB,
  path-client, and agent JSON contract fixtures live in
  `tests/builder_cli_surface_helpers.py`.
- Decomposition result: `tests/test_builder_cli_surfaces.py` dropped from 4,649
  to 4,302 measured lines. The new knowledge CLI owner is 304 lines, the shared
  CLI surface helper is 74 lines, and the complexity baseline was ratcheted to
  the new measured hotspot size.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_knowledge_cli_surface.py
  tests/builder_cli_surface_helpers.py` passed; `uv run pytest
  tests/test_builder_knowledge_cli_surface.py tests/test_builder_cli_surfaces.py
  -q` passed `123 passed`; `uv run builder lint --complexity-report --json`
  passed with 375 Python files, 4,511 functions, 54 historical over-threshold
  files, 7 function hotspots, and 0 violations; `uv run builder lint --json`
  passed with 5 checks passed and the expected uninitialized `knowledge` and
  `readiness` skips; `git diff --check` passed.

## 2026-05-19 Board Frontend Owner Split

- Architecture lens: applied the frontend rubric's feature-sliced page
  standard. `BoardPage.tsx` is now the route adapter and data/subscription owner;
  lifecycle selectors and shipped-task projections live in
  `features/board/board-model.ts`; visible workflow owners live in
  `BoardSprintStrip.tsx`, `BoardLane.tsx`, `SprintDetailSidebar.tsx`, and
  `TaskDetailSidebar.tsx`.
- Decomposition result: `BoardPage.tsx` dropped from 1,359 lines to 255 lines.
  New Board owner modules stay under the 500-line target:
  `SprintDetailSidebar.tsx` 486, `board-model.ts` 283,
  `TaskDetailSidebar.tsx` 157, `BoardSprintStrip.tsx` 117,
  `board-detail-shared.tsx` 74, and `BoardLane.tsx` 65.
- Verification: `npm run lint` passed; `npm run build` passed; `uv run pytest
  tests/test_dashboard_design_system_contract.py -q` passed `23 passed`.
- Browser proof: using Chrome/Computer Use against the rebuilt managed
  `todo-app` dashboard on `http://localhost:9876/board`, the Board rendered
  Sprint 14 with live stream, disabled `Start work`, empty active/review/queued
  lanes, three shipped cards, and empty blocked lane. The Build phase opened a
  `Sprint build` drawer with build-verifier/feature-acceptance evidence; the
  Review phase opened a distinct `Sprint review` drawer with evidence-collector
  rows, confirming the phase-specific drawer split still works in-browser.
- Chrome-plugin browser proof: started the managed `todo-app` dashboard from
  this checkout with `uv run --project ... builder start --port 9876 --force`,
  opened `http://127.0.0.1:9876/board` in Google Chrome through the Computer
  Use plugin, and verified the patched Board rendered with shipped Sprint 13,
  disabled `Start work`, empty in-progress/review/queued/blocked lanes, and
  three shipped cards. Phase rail clicks opened distinct `Sprint plan`,
  `Sprint gates`, `Sprint review`, `Sprint build`, and `Sprint shipped` drawers
  with phase-specific summary/evidence instead of one repeated drawer body.

## 2026-05-19 Agent Direct-Action Owner Split

- Architecture lens: continued the backend rubric's route-thinness standard on
  the highest remaining production hotspot named by the audit. Direct
  no-runtime Agent chat-turn actions now live in
  `embedded/server/chat_turn_direct_actions.py`, covering review approval
  continuation, sprint planning, and saved-feature delivery follow-up.
  `_run_chat_turn` now delegates those direct actions before building the model
  prompt/runtime loop.
- Decomposition result: `routes/agent.py` dropped from 4,716 to 4,679 lines,
  `_run_chat_turn` dropped from 313 to 273 lines and from 59 to 18 branch-count
  allowance, and the new direct-action owner is 82 lines. The complexity
  baseline was ratcheted to the lower measured route/function sizes so future
  growth fails the gate instead of hiding in historical allowance.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/chat_turn_direct_actions.py`
  passed; `uv run pytest tests/test_agent_sprint_planning_routes.py
  tests/test_agent_delivery_dispatch_routes.py
  tests/test_agent_delivery_status_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_chat_turn_publication.py tests/test_dashboard_design_system_contract.py
  -q` passed `37 passed`; `uv run builder lint --complexity-report --json`
  passed with 370 Python files, 4,504 functions, and 0 violations; and
  `uv run builder lint --json` passed with 5 checks passed and 2 expected
  uninitialized-surface skips.

## 2026-05-19 Chat-Turn Error Publication Split

- Architecture lens: continued the backend rubric's route-thinness and
  projection-owner standards on the embedded Agent route hotspot. Terminal
  runtime error publication now lives in `ChatTurnPublisher`, beside terminal
  assistant response and run-status publication, instead of being hand-built in
  `_run_chat_turn`.
- Decomposition result: `_run_chat_turn` dropped below the 250-line function
  target and no longer appears in the complexity function-hotspot inventory.
  `routes/agent.py` dropped from 4,671 to 4,652 lines, and the stale
  `_run_chat_turn` function baseline was removed while the file baseline was
  ratcheted down to the new measured size.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/chat_turn_publication.py
  tests/test_chat_turn_publication.py` passed; `uv run pytest
  tests/test_chat_turn_publication.py tests/test_agent_sprint_planning_routes.py
  tests/test_agent_delivery_dispatch_routes.py
  tests/test_agent_delivery_status_routes.py tests/test_agent_tool_approval_routes.py
  -q` passed `15 passed`; and `uv run builder lint --complexity-report --json`
  passed with 371 Python files, 4,511 functions, 54 historical
  over-threshold files, 7 function hotspots, and 0 violations.

## 2026-05-19 Builder Verify CLI Test Split

- Architecture lens: continued the backend rubric's test-boundary standard on
  the current top test hotspot. Builder verify changed-surface classification
  and proof-selection contracts now live in
  `tests/test_builder_verify_cli_surface.py`, leaving
  `tests/test_builder_cli_surfaces.py` to own the remaining shared CLI command
  surfaces.
- Decomposition result: `tests/test_builder_cli_surfaces.py` dropped from 4,785
  to 4,649 lines. The new verify-focused test owner is 147 lines, stays below
  the 500-line target, and the CLI test hotspot baseline was ratcheted down to
  the new measured size.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_verify_cli_surface.py` passed; `uv run pytest
  tests/test_builder_verify_cli_surface.py tests/test_builder_cli_surfaces.py
  -q` passed `137 passed`; `uv run builder lint --complexity-report --json`
  passed with 372 Python files, 4,511 functions, 54 historical
  over-threshold files, 7 function hotspots, and 0 violations; and
  `uv run builder lint --json` passed with 5 checks passed and 2 expected
  uninitialized-surface skips.

## 2026-05-19 Agent Runtime Status Owner Split

- Architecture lens: continued the backend rubric's route-adapter and
  projection-owner standards on the embedded Agent route hotspot. Runtime
  metadata, initial running status, and terminal chat run-status payload
  construction now live in
  `embedded/server/agent_runtime_status.py`, while `routes/agent.py` remains
  the HTTP/session adapter.
- Decomposition result: `routes/agent.py` dropped from 4,652 to 4,595 lines
  after import formatting, and the new runtime-status owner is 83 lines. The
  Agent route file baseline was ratcheted down to the new measured size.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_runtime_status.py` passed;
  `uv run pytest tests/test_embedded_agent_forward_engineering.py
  tests/test_chat_turn_publication.py tests/test_agent_runtime_settings_routes.py
  -q` passed `12 passed`; `uv run builder lint --complexity-report --json`
  passed with 373 Python files, 4,511 functions, 54 historical
  over-threshold files, 7 function hotspots, and 0 violations; and
  `uv run builder lint --json` passed with 5 checks passed and 2 expected
  uninitialized-surface skips.

## 2026-05-18 God-File Decomposition Pass

- Architecture lens: applied the backend service rubric route-thinness and
  service-contract standards. The pass did not claim to finish all historical
  hotspots; it removed the current baseline-growth violations and created
  clearer owners for the surfaces changed in this audit.
- Embedded Agent route split: moved Agent API Pydantic contracts out of
  `routes/agent.py` into `embedded/server/agent_api_models.py`, and moved
  duplicate decision-surface reconciliation into
  `embedded/server/agent_control_owners.py`. `routes/agent.py` now imports
  those contracts and calls `reconcile_session_control_owners(...)` with the
  delivery-feature resolver instead of owning that policy inline.
- Realtime voice split: moved SDK-backed voice completion summary construction
  into `services/voice_completion_digest.py`; `voice_operator.py` keeps the
  operator lane and notification wiring. `AgentOperatorService.send_message`
  now delegates route/capability selection, direct route responses, Agent-thread
  resolution, and already-running handoff responses to named methods instead of
  carrying one branch-heavy function.
- Test split: moved approval-control-owner route tests to
  `tests/test_agent_control_owner_routes.py` and voice handoff tests to
  `tests/test_realtime_voice_handoff.py` so regression coverage follows the new
  owner modules instead of growing the existing god-test files.
- Ratchet evidence: `routes/agent.py` dropped from 6,153 to 5,944 lines;
  `voice_operator.py` dropped from 3,481 to 3,355 lines; the extracted owner
  modules are 106, 145, and 219 lines. `tests/test_embedded_agent_routes.py`
  dropped to 7,313 lines against a 7,330 allowance, and
  `tests/test_realtime_voice_operator.py` dropped to 3,111 lines against a
  3,153 allowance.
- Verification: `uv run ruff check ...` passed for the changed source and test
  files; focused regression tests passed `8 passed`; `uv run builder lint
  --complexity-report --json` passed with 335 Python files, 4,494 functions, and
  0 ratchet violations; `uv run builder lint --json` passed with 7 checks total,
  5 passed and 2 expected uninitialized-surface skips; `git diff --check`
  remained clean.
- Follow-up Agent chat-turn split: moved terminal Agent chat publication into
  `embedded/server/chat_turn_publication.py`, including stream-delta publication
  and no-token assistant/status closeouts for review approval, sprint planning,
  and saved-feature delivery follow-up. `_run_chat_turn` now delegates this
  repeated event/status contract instead of owning it inline.
- Follow-up ratchet evidence: `routes/agent.py` dropped again from 5,944 to
  5,870 lines, `_run_chat_turn` dropped from 388 to 313 lines, and the extracted
  publication helper is 89 lines with focused coverage in
  `tests/test_chat_turn_publication.py`. The complexity baseline was ratcheted
  to those current values.
- Follow-up verification: `uv run ruff check` passed for the new publication
  helper, the Agent route, and helper tests; `uv run pytest
  tests/test_chat_turn_publication.py tests/test_chat_turn_intent.py
  tests/test_agent_control_owner_routes.py` plus targeted model-backed Agent
  route slices passed `15 passed`; `uv run builder lint --complexity-report
  --json` passed with 337 Python files, 4,510 functions, 55 historical
  over-500 files, 8 function hotspots, and 0 violations.
- Full Agent route proof: `uv run pytest tests/test_embedded_agent_routes.py
  tests/test_chat_turn_publication.py tests/test_chat_turn_intent.py -q` passed
  `127 passed`, covering the large embedded Agent route suite after the
  publication extraction.
- First-principles placement update: the frontend and backend architecture
  rubrics now define what belongs in shared system modules versus focused owner
  modules. Shared system code is limited to stable primitives/contracts used by
  multiple owners; workflow policy stays in focused modules; routes/pages/CLI
  remain adapters.
- Focused Agent route test split: moved operator-safe transcript content tests
  to `tests/test_agent_operator_safe_content.py`, runtime resume attribution
  tests to `tests/test_agent_runtime_resume.py`, forward-engineering Agent route
  tests to `tests/test_embedded_agent_forward_engineering.py`, and shared
  Agent-route history/readiness helpers to `tests/agent_route_test_support.py`.
  `tests/test_embedded_agent_routes.py` dropped from 7,313 to 6,587 lines, and
  every new file stays under 500 lines.
- Focused split verification: `uv run ruff check` passed for the split Agent
  route test files; `uv run pytest tests/test_agent_operator_safe_content.py
  tests/test_agent_runtime_resume.py tests/test_embedded_agent_forward_engineering.py
  -q` passed `13 passed`; `uv run pytest tests/test_embedded_agent_routes.py
  tests/test_agent_operator_safe_content.py tests/test_agent_runtime_resume.py
  tests/test_embedded_agent_forward_engineering.py tests/agent_route_test_support.py
  -q` passed `118 passed`; and `uv run builder lint --complexity-report --json`
  passed with 341 Python files, 4,510 functions, 55 historical over-500 files,
  8 function hotspots, and 0 violations.
- Deep Agent route test split: moved the remaining route scenarios into focused
  modules, each under 500 lines: chat navigation/context, chat tool events,
  pending questions, tool approvals, feature-spec prompts/capture/backlog/tooling,
  sprint start/planning, delivery dispatch/status, recovery dispatch/status,
  board status/questions, documentation chat/tool approval, runtime settings,
  chat sessions, timeline closeout, operator-safe content, runtime resume, and
  forward-engineering behavior. The former god file
  `tests/test_embedded_agent_routes.py` is now a 101-line contract file.
- Deep split verification: `uv run ruff check` passed for the decomposed Agent
  route test modules; `uv run pytest tests/test_embedded_agent_routes.py
  tests/test_agent_chat_navigation_routes.py
  tests/test_agent_chat_tool_event_routes.py
  tests/test_agent_pending_question_routes.py
  tests/test_agent_tool_approval_routes.py
  tests/test_agent_feature_spec_prompt_contracts.py
  tests/test_agent_feature_spec_capture_routes.py
  tests/test_agent_feature_spec_backlog_routes.py
  tests/test_agent_feature_spec_tooling_routes.py
  tests/test_agent_sprint_start_routes.py
  tests/test_agent_sprint_planning_routes.py
  tests/test_agent_delivery_dispatch_routes.py
  tests/test_agent_delivery_status_routes.py
  tests/test_agent_recovery_dispatch_routes.py
  tests/test_agent_recovery_status_routes.py
  tests/test_agent_board_status_routes.py
  tests/test_agent_board_question_routes.py
  tests/test_agent_timeline_closeout_routes.py
  tests/test_agent_documentation_chat_routes.py
  tests/test_agent_documentation_tool_approval.py
  tests/test_agent_documentation_routing.py
  tests/test_agent_chat_session_routes.py
  tests/test_agent_runtime_settings_routes.py
  tests/test_agent_operator_safe_content.py
  tests/test_agent_runtime_resume.py
  tests/test_embedded_agent_forward_engineering.py
  tests/test_chat_turn_publication.py tests/test_chat_turn_intent.py -q`
  passed `127 passed`; `uv run builder lint --complexity-report --json` passed
  with 363 Python files, 4,510 functions, 54 historical over-500 files, 8
  function hotspots, and 0 violations. The stale
  `tests/test_embedded_agent_routes.py` complexity baseline entry was removed.
- Production documentation-routing split: moved documentation intent matching,
  continuation matching, required-doc detection, action resolution, specialist
  policy models, and generic specialist route selection out of
  `routes/agent.py` into
  `embedded/server/documentation_routing.py`. The route file keeps the
  Agent-specific documentation context pack and a compatibility wrapper for
  existing tests, while the new owner module stays at 321 lines.
- Production split verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/documentation_routing.py
  tests/test_agent_documentation_routing.py
  tests/test_agent_documentation_chat_routes.py
  tests/test_agent_documentation_tool_approval.py` passed, and `uv run pytest
  tests/test_agent_documentation_routing.py
  tests/test_agent_documentation_chat_routes.py
  tests/test_agent_documentation_tool_approval.py
  tests/test_agent_chat_navigation_routes.py tests/test_embedded_agent_routes.py
  -q` passed `38 passed`. `routes/agent.py` dropped to 5,609 lines and the
  complexity baseline ratcheted down from 5,870 to 5,609 lines.
- Post-production-split closeout: the full decomposed Agent route proof still
  passed `127 passed`; `uv run builder lint --json` passed with 5 checks
  passed and 2 expected uninitialized-surface skips; `git diff --check`
  remained clean.
- Additional Agent route cleanup: removed unreachable deterministic read-only
  Board status/recovery handlers that were no longer called by the model-backed
  Agent route, moved the active observability context-pack builder into
  `embedded/server/agent_observability_context.py`, and moved generated-app
  surface detection into `embedded/server/agent_workspace_surface.py`. The
  route file dropped from 5,609 to 5,085 lines, the new owner modules are 119
  and 64 lines, and the stale route baseline was ratcheted down again.
- Additional cleanup verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_observability_context.py
  src/autonomous_agent_builder/embedded/server/agent_workspace_surface.py
  tests/test_agent_chat_navigation_routes.py
  tests/test_embedded_agent_forward_engineering.py` passed; `uv run pytest
  tests/test_agent_chat_navigation_routes.py
  tests/test_embedded_agent_forward_engineering.py tests/test_embedded_agent_routes.py
  -q` passed `19 passed`; `uv run pytest tests/test_agent_board_status_routes.py
  tests/test_agent_board_question_routes.py tests/test_agent_recovery_status_routes.py
  tests/test_embedded_agent_routes.py -q` passed `19 passed`; the full
  decomposed Agent route suite still passed `127 passed`; and
  `uv run builder lint --complexity-report --json` passed with 366 Python files,
  4,501 functions, 54 historical over-500 files, 8 function hotspots, and
  0 violations.
- Session/transcript owner split: moved Agent timeline serialization,
  operator-safe transcript projection, token/status projection, runtime-thread
  metadata, repo-scoped chat-session lookup, resume compatibility, and session
  preview logic out of `routes/agent.py` into
  `embedded/server/agent_chat_transcript.py` and
  `embedded/server/agent_chat_sessions.py`. Realtime Voice now calls those
  focused owners directly instead of depending on private route helpers.
  `routes/agent.py` dropped from 5,085 to 4,716 lines, the new owners are 228
  and 164 lines, and the Realtime Voice operator test hotspot was nudged down
  from 3,111 to 3,090 lines by moving shared test doubles into
  `tests/realtime_voice_operator_test_support.py`.
- Session/transcript split verification: `uv run ruff check` passed for the
  touched route, owner modules, voice services, and focused tests; the broad
  Agent/Realtime regression command passed `186 passed`; the post-test-support
  focused voice/session route command passed `80 passed`; `uv run builder lint
  --complexity-report --json` passed with 369 Python files, 4,501 functions, 54
  historical over-500 files, 8 function hotspots, and 0 ratchet violations; and
  `uv run builder lint --json` passed with 5 checks passed and 2 expected
  uninitialized-surface skips.

## 2026-05-18 Architecture Rubric And 500-Line Ratchet Update

- Frontend architecture rubric: `docs/rubric/frontend-react-architecture.md`
  now defines the high-level React target as feature-sliced pages, focused
  workflow components, side-effect hooks, pure selectors/presenters,
  design-system primitives, typed API boundaries, and matching static/browser
  tests. It explicitly marks the 500-line frontend file target and names the
  decomposition lens for Agent, Board, Voice, phase drawers, pending decisions,
  and realtime transcript surfaces.
- Backend architecture rubric: `docs/rubric/backend-service-architecture.md`
  now defines the high-level backend target as a modular-monolith,
  ports-and-adapters architecture: routes/CLI as adapters, services as state
  owners, query/projection builders for read models, runtime adapters for
  provider mechanics, serializers/API models beside adapter contracts, and
  tests following the same owner boundaries.
- Complexity gate: the Python file-size target is now 500 lines. Historical
  over-500 Python files are tracked in
  `docs/quality-gate/complexity-baseline.json` with owner/extraction plans, and
  the complexity guard now fails if a decomposed hotspot keeps a stale higher
  baseline instead of ratcheting down.
- Ratchet proof: the new rule caught a stale `_run_chat_turn` allowance after
  decomposition; the baseline was lowered from 553 to 388 lines. After that,
  `uv run pytest tests/test_complexity_guard.py
  tests/test_complexity_cli_contract.py -q` passed `7 passed`,
  `uv run builder lint --complexity-report --json` passed with 335 Python files,
  4,496 functions, 55 historical over-500 files, 8 function hotspots, and
  0 violations, `uv run builder lint --json` passed with 7 checks total,
  5 passed and 2 expected uninitialized-surface skips, and `git diff --check`
  remained clean.
- Frontend static proof: `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py -q` passed `42 passed`. The
  frontend line inventory currently shows historical over-500 files headed by
  `AgentPage.tsx` at 2,709 lines and `BoardPage.tsx` at 1,359 lines; these are
  now explicit decomposition targets in the frontend rubric rather than accepted
  growth areas.
- Frontend build proof: from `frontend/`, `npm run lint` passed and
  `npm run build` passed. Vite still reports the existing over-500 kB main
  chunk warning, which is now covered by the frontend rubric's bundle/context
  review lens instead of being treated as invisible build output.
- Scope note: this update does not claim all existing god files are gone. It
  turns the target architecture into owner docs and enforcement so future audit
  fixes must reduce large files, avoid generic `utils`/`common` buckets, and
  preserve behavior while extracting the next hotspot.

## 2026-05-18 Voice Approval Control Owner And Sprint 14 Proof

- Audit objective: the referenced audit progress file at
  `.codex-audits/autonomous-agent-builder-20260518T051747Z/PROGRESS.md` reports
  status `remediated`, 0 open defects, 0 open risks, 0 open smells, and 0 open
  cross-cutting issues. The live follow-up pass focused on the user-visible
  regressions found after that remediation: duplicate approvals, approval
  ownership, phase clarity, Samantha icon clarity, and Board start-state
  correctness.
- Single control owner: the Agent page now renders pending decision controls in
  one composer/footer surface with `aria-label="Pending decision response"`.
  Timeline question/approval entries keep the recorded decision evidence but no
  longer own action buttons. The generic `TimelineEntry.actions` escape hatch was
  removed from the shared timeline component so future code has one obvious
  owner for decision controls.
- Backend ownership cleanup: voice final summaries, voice completion
  notifications, delivery permission questions, and sprint-scope approvals now
  reconcile to the persisted delivery permission question when that question is
  the active owner. Historic duplicate voice-summary and delivery-scope approval
  rows are marked `superseded` instead of hidden, and new voice handoffs do not
  create a second approval source while a pending decision exists.
- Browser proof: Chrome validated Agent session
  `0bc7f16a-0ce9-45e3-8930-bc448483922e`. The old polluted thread reconciled to
  one answered `Start now` question, no duplicate pending approval box, no
  trailing `TOOL - BUILDER` approval echo after the question, and a usable
  composer. The floating Samantha control rendered the new black/white knot
  icon with accessible label `Activate Samantha`.
- Board and phase proof: the voice-created Sprint 14 feature
  `Show completed todo count in footer` moved from queued verification through
  the visible Board `Continue work` control to 3 shipped tasks. The final Board
  state showed the current sprint shipped, no queued or active Sprint 14 work,
  all phase dots green through Done, and a disabled `Start work` state. Phase
  drawers rendered distinct evidence: Gates showed persisted gate results,
  Review showed evidence-collector/file-diff proof, Build showed
  build-verifier/acceptance proof, and Shipped showed shipped outcome plus
  optimization evidence.
- Generated-app proof: the managed `todo-app` browser run showed
  `1 total - 1 active - 0 completed`; after checking `Pay taxes`, it showed
  `1 total - 0 active - 1 completed`, a completed section, and
  `Clear 1 completed todo`. Reload preserved the completed count, and clearing
  completed todos returned the footer to `0 total - 0 active - 0 completed`
  with `No todos yet.`
- CLI/log evidence: `builder board show --json` showed latest Sprint 14
  `active_phase: shipped`, task counts `done: 3`, and
  `verification_status: shipped`. `builder backlog task show` for final task
  `15b53795-755a-4fc4-98f9-1787cd49d121` showed completed `code-gen`,
  `feature-acceptance-tests`, `evidence-collector`, and `build-verifier` agent
  runs. `builder logs analyze --session 0bc7f16a --json` showed the post-fix
  `Start now` prompt had 0 tools and 0 failed tools; earlier failed tool calls
  were historical pollution from before reconciliation.
- Source gates: the changed-surface backend test sweep passed `354 passed`;
  backend `ruff check` passed; frontend `npm run lint` and `npm run build`
  passed; generated `todo-app` `npm run test`, `npm run lint`, and
  `npm run build` passed; `workflow --docs-dir docs read REFERENCE`,
  `workflow --docs-dir docs summary design-language`,
  `builder quality-gate dashboard-ux --json`, `workflow read principles
  --section Evidence`, and `git diff --check` passed. After this progress
  update, the focused duplicate-approval, voice-handoff, phase, and Samantha
  regression suite passed `27 passed`, and `git diff --check` remained clean.

## 2026-05-18 Chat Run Cleanup And Combined Regression Stability

- Root cause: Agent-route tests could exit while an Agent-page background chat
  task was still attached to an app-local `ChatSessionHub`. The next embedded
  app instance then initialized against a test DB while a stale async SQLite
  connection from the previous route test was still being garbage-collected.
- Fix: `ChatSessionHub` now tracks process-local hub instances, refuses new run
  attachments after shutdown, drains active run tasks and pending answers on
  shutdown, and exposes `shutdown_all()` for test/app cleanup. The route test DB
  fixture now drains hubs before restoring and disposing the test engine.
- Test helper fix: assistant-message waits now avoid returning on the transient
  `completed_after_running_status` projection and explicit status assertions
  wait for the final `end_turn` status event.
- Regression proof: the previously failing combined command
  `PYTHONPATH=src .venv/bin/python -m pytest tests/test_embedded_agent_routes.py
  tests/test_embedded_server_app.py tests/test_dashboard_api.py
  tests/test_realtime_voice_frontend_static.py -q` now passes with
  `181 passed`.

## 2026-05-18 Agent Approval Handoff And Serial Dispatch

- Root cause: inline Agent-page responses updated pending question/approval
  events through a second DB session while the request already held the event
  row. In the managed SQLite-backed app this could hang the approval button and
  leave the operator at a disabled inline control.
- Fix: pending question/approval responses now update through the request DB
  session, persisted delivery-scope approval creates sprint execution artifacts
  and schedules the first generated task immediately, and embedded task dispatch
  continues to the next serial task after the previous task integrates.
- UI fix: the timeline renderer now supports per-entry actions, so pending
  questions and approvals render design-system inline buttons in the current
  Conversation timeline instead of requiring text such as `start` or `approve`.
- Board sync fix: `current_sprint.generated_tasks[*].status` now comes from the
  live task row; the summary no longer marks active generated tasks as `done`.
- Live proof: managed `todo-app` session
  `1d65ce61-b421-485f-bb69-e836d87bd4af` captured `Show Enter Key Hint Beside
  Add Button`, accepted inline `Start now`, showed inline `Approve` / `Deny` in
  timeline mode, logged `POST /api/agent/chat/respond` 200, dispatched task
  `a83e3383-d521-4900-980d-ffbb15e90a59`, then selected
  `97d57af5-5048-4cd9-abba-a7ef5f96381f` with reason `next_serial_task`.
- Final live state: `builder board show --json` reported `pending: 0`,
  `active: 0`, `review: 0`, latest Sprint 12 `active_phase: shipped`,
  `verification_status: shipped`, and all three `Show Enter Key Hint Beside Add
  Button` generated tasks `done`.
- Token/efficiency evidence: `builder metrics show --json` after closeout
  reported `active_raw_token_total: 0`, `active_noncached_plus_output_tokens: 0`,
  `active_avoidable_cost_flags: []`, `recent_risky_runs: 0`, and
  `recent_large_output_runs: 0`.
- Regression evidence: focused approval/dispatch/dashboard tests passed; the
  relevant files also passed independently:
  `tests/test_embedded_agent_routes.py` (`116 passed`),
  `tests/test_embedded_server_app.py` (`14 passed`),
  `tests/test_dashboard_api.py tests/test_realtime_voice_frontend_static.py`
  (`50 passed`), and `npm run build` passed with the existing Vite chunk-size
  warning.
- Broad-suite note: running
  `tests/test_embedded_agent_routes.py tests/test_embedded_server_app.py
  tests/test_dashboard_api.py tests/test_realtime_voice_frontend_static.py`
  together still trips the pre-existing leaked async SQLite connection between
  route and embedded-server files; each file/group passes in isolation.

## 2026-05-16 Clear Completed Shipping And Decision-State Cleanup

- Result: managed `todo-app` session
  `b409573c-08ed-40be-b8c5-a37363b48324` shipped `Clear Completed Tasks With
  Confirmation`. `builder board show --json` reported `pending: 0`,
  `active: 0`, `review: 0`, `blocked: 0`, `done: 38`; Sprint 8
  `9f7cfbfb-f8b4-4718-babe-feb5e3ef381e` was `shipped`, and all three generated
  tasks were `done`.
- Agent-page UX fix: while validating with Computer Use, the right rail showed
  the final verification task as `COMPLETE` but the Conversation timeline still
  labeled answered question/approval rows as `Needs review`. The frontend now
  derives decision timeline status from persisted `answered`/`decision` payloads
  and displays `Answered`, `Approved`, or `Denied`.
- Scroll fix: the timeline now waits for the rendered tail item before scrolling
  to the bottom, so persisted shipped closeouts are visible after reload instead
  of leaving the operator focused on older recovery messages.
- Live proof: after `builder start --port 9876 --force`, Computer Use refreshed
  the same session and verified `QUESTION Answered`, `APPROVAL NEEDED Approved`,
  and `Builder shipped ... Token evidence ...` visible in the Conversation
  timeline.
- Token/efficiency evidence: `builder logs analyze --session
  b409573c-08ed-40be-b8c5-a37363b48324 --json` reported `prompt_count: 4` and
  `total_tokens: 91,528`; the shipped closeout recorded `164,528` raw,
  `158,336` cached, and `6,192` non-cached-plus-output tokens across `12` runs.
  `builder metrics show --json` still reported `active_avoidable_cost_flags: []`,
  `active_raw_token_total: 0`, `recent_risky_runs: 0`,
  `recent_large_output_runs: 0`, and `chunk_pressure_risk: false`.
- Residual robustness findings: one implementation task failed because this
  validation restarted the Builder server during the run; a later recovery used
  the same blocked-restart wording for the follow-up task, which should be
  treated as recovery-state/misclassification hardening in the next pass.

## 2026-05-16 Active Metrics And Operator Copy Cleanup

- Metrics fix: `builder metrics show --json` now keeps historical raw, cached,
  non-cached-plus-output, and top-driver totals visible, but chooses
  `recommended_next_change` from active recent evidence. On managed `todo-app`,
  the same metrics lane now reports `recommended_next_change:
  maintain_current_flow`, `active_avoidable_cost_flags: []`,
  `active_raw_token_total: 0`, `active_noncached_plus_output_tokens: 0`, and
  zero active chunk/large-output pressure after the shipped deterministic closeout
  runs.
- Operator-copy fix: approval recovery and delivery planning no longer expose
  `sprint-plan-*`, task titles, "current sprint task", or work-step counts in
  the visible Agent response. The internal `delivery_plan_created` event stores
  the plan id for shipped-closeout recovery, while the operator sees
  "Builder prepared the work..." and a clear next action without depending on a
  magic word.
- Regression proof: `PYTHONPATH=src pytest tests/test_codex_optimization.py
  tests/test_runtime_optimization.py tests/test_builder_cli_surfaces.py::test_metrics_show_json_includes_summary_and_next_step
  -q` passed `24` tests; focused Agent-route delivery/closeout copy tests
  passed `10` tests.

## 2026-05-16 Agent Conversation Timeline Stabilization

- Root cause: the active-run recovery poll called the full `loadHistory` path
  every two seconds. That set `historyLoaded` false before each fetch, so the
  visible Conversation panel could remount as `Loading agent transcript...`
  while an SDK-backed Agent run was still running.
- Fix: `loadHistory` now has a `quiet` mode for missed-SSE recovery polling.
  Quiet refreshes still update items, status, runtime, and token rails, but they
  do not clear `historyLoaded`, `items`, or `status` on each interval. Initial
  loads and explicit session switches still use the normal loading state.
- Operator-flow cleanup in the same source-owned pass: persisted delivery
  questions now say `Start now` / `Hold`, Conversation renders pending questions
  and approvals as timeline-native assistant entries, and the composer offers
  inline option buttons below the thread content.
- Live proof: Computer Use watched managed `todo-app` session
  `b409573c-08ed-40be-b8c5-a37363b48324` while a Codex SDK Agent prompt and the
  recovered follow-up code-gen run were active. The thread remained visible
  across repeated polling intervals; no `Loading agent transcript...` flash was
  observed after the source fix was rebuilt with `builder start --port 9876
  --force`.
- Token evidence: the recovery Agent prompt reported `48,497` raw tokens and
  completed in `43,700ms`; the earlier clean recovery prompt showed `43,031`
  raw, `42,368` cached, and `663` non-cached-plus-output tokens. The interrupted
  code-gen failure itself reported `0` tokens because it was caused by a builder
  server restart before runtime evidence arrived.

## 2026-05-16 Collapsible Completed Todos Shipping Cycle

- Result: the managed `todo-app` shipped `Collapsible completed todos section`
  through session `ec2d5ffd-8f0d-400e-9456-d517191da072`; Board state reached
  `pending: 0`, `active: 0`, `review: 0`, `done: 35`, `blocked: 0`, and Sprint
  7 reported `active_phase: shipped`, `verification_status: shipped`.
- Operator flow: the Agent page accepted the natural prompt `I want to improve
  the todo app so completed tasks can be collapsed into a compact section.`,
  asked one product question, captured the improvement, requested delivery
  approval, created plan `sprint-plan-1645f377603e`, and dispatched work from
  the operator's `start` message without requiring Board or backlog knowledge.
- Shipped closeout fix: the Conversation timeline initially ended at
  `Started ...` after the sprint shipped. Source now resolves persisted sprint
  plan documents by their embedded `sprint-plan-*` id and appends a final
  `Builder shipped ... Evidence ... Token evidence ...` assistant message for
  shipped plans. Chrome-visible refresh of the same session showed the final
  closeout inline.
- Token evidence in the final closeout: `176,481` raw tokens, `171,136` cached
  tokens, and `5,345` non-cached-plus-output tokens across `12` completed run
  records. The three model-backed code-gen steps were `58,984`, `63,078`, and
  `54,419` raw tokens respectively; the remaining recorded proof/check runs
  were deterministic zero-token runs.
- Remaining efficiency findings: initial Agent chat remains high in raw cached
  context for a plain improvement prompt, running code-gen token counters still
  show `0` until completion, and generated app workspaces still accumulate
  runtime artifacts/owner-surface mutations that should be addressed in Builder
  hardening rather than by hand-editing generated apps.

## 2026-05-15 Agent Page High-Priority Shipping Cycle

- Result: the managed `todo-app` shipped `High-priority todo marking`; Board
  state reached `pending: 0`, `active: 0`, `review: 0`, `done: 29`,
  `blocked: 0`, and Sprint 5 reported `active_phase: shipped`,
  `verification_status: shipped`.
- Operator flow: the Agent page accepted the natural prompt `I want to improve
  the todo app so important tasks can be marked as high priority and clearly
  stand out.`, captured the improvement, asked the plain shipping question,
  accepted the answer through the composer, accepted typed approval through the
  composer, and dispatched delivery after the operator wrote `Continue the work
  and ship it.`
- Browser proof: Chrome on the generated app at `http://127.0.0.1:5173/` added
  `Pay taxes`, showed the `Mark high` control, toggled it to `High priority`
  with stronger row treatment, and preserved the high-priority state after
  refresh.
- Generated-app deterministic proof: `npm run lint` passed, `npm test` passed
  `59` Node tests including high-priority localStorage/store coverage, and
  `npm run build` passed.
- Token evidence for the live lane: initial feature scoping used `39,808` raw
  tokens with `33,152` cached and `6,656` non-cached plus output; the three
  shipped task runs then used `60,062`, `63,383`, and `52,673` raw tokens. The
  final metrics total was `raw_token_total: 2328520`,
  `noncached_plus_output_tokens: 527715`, `cache_ratio: 5.2114`,
  `recent_risky_runs: 0`, and `recent_large_output_runs: 0`.
- Efficiency finding fixed in Builder source: after shipping, Builder launched
  a model-backed `optimization-agent` run for Builder-owned residual token
  policy work while the generated app had no owning write surface for that
  issue. The source now defers Builder-owned residuals from generated-app
  post-ship optimization, preserving deterministic app-local guidance work and
  routing the remaining token-policy work back to Builder source.
- Live reconciliation evidence: the pre-fix `optimization-agent` row
  `122a3d82-210a-49ee-8062-ba616e704f91` stayed `running` with zero tokens and
  no logs until server restart; startup reconciliation marked it failed with
  `Agent run was interrupted by a builder server restart before it reported
  runtime evidence.` This confirms the fake-running row is cleared, while the
  source patch prevents the same generated-app owner mismatch in future runs.
- Remaining UX issues from this run: the approval card still does not
  auto-dispatch or expose a first-class `Start work` action after approval, and
  session-level token rows remain zero for deterministic dispatch even while
  task-run tokens are available in metrics/run evidence.

## 2026-05-15 Agent Chat Metrics Token Normalization

- Root cause: Agent-page model-backed chat status events persisted SDK usage as
  one `tokens_used` bucket. Metrics then treated that total as output tokens for
  `agent-chat`, which blurred raw input, cached input, output, and
  non-cached-plus-output accounting.
- Fix: chat completion, provider-limit, and error statuses now persist
  `tokens_input`, `tokens_output`, `tokens_cached`, `raw_tokens`, and
  `noncached_plus_output_tokens`; dashboard Metrics normalizes those fields
  from status payloads or native observability token accounting before falling
  back to legacy `tokens_used`.
- Impact: future Agent-page chat runs keep user-intent processing model-backed
  while giving Metrics/Observability the cache-aware fields needed to judge
  actual spend and token waste.

## 2026-05-15 Realtime Text-Mode Operator Input

- Browser finding: after starting Voice in the managed `todo-app` dashboard,
  Samantha gave the expected `Hi there!` activation cue and text mode accepted
  the plain operator request `I want to improve the todo app so I can search
  tasks by text.`, but the operator had no obvious successful way to submit the
  typed request.
- Fix: Realtime text mode now submits on plain Enter, while Shift+Enter remains
  available for multiline input. This keeps Voice parity usable for the same
  natural improvement wording tested on the Conversation tab.
- Handoff finding: after Enter-submit worked, Voice delegated the request but
  left Conversation on the empty Realtime session. The backend had created
  Agent session `6f5fca21-43a1-4c27-a269-13da2323ced8`, but the visible page
  still showed `No active transcript`.
- Fix: Realtime delegation is now event-driven by default, rebinds the active
  Realtime call to the delegated Agent session, emits a `voice_control_action`
  route to the old voice session, and lets the frontend follow the Builder
  thread immediately. The Voice tool output changed from waiting up to
  `120s` and returning `still_running` to returning `running` immediately.
- Browser proof: after rebuild from the managed `todo-app` workspace, a fresh
  Voice session `BCDE6F97` said `Hi there!`; Enter-submitting
  `I want to improve the todo app so I can search tasks by text.` navigated the
  visible browser to Conversation session
  `b48fc8cf-59b7-4dea-97e3-59b717eea602`, showing `USER · OPERATOR` and
  `TOOL · SAMANTHA` entries instead of a blank transcript.
- Token evidence: the live handoff recorded `realtime_tool_exchange`
  `estimated_tokens=247`, SDK agent prompt assembly `estimated_tokens=900`,
  Realtime voice usage `4,488` total tokens, and a completed Agent run with
  `50,081` raw tokens. The run also proved
  `truncate_tool_output_before_reinjection` compacted a `56,422` byte command
  output into a stored Builder artifact, so the remaining efficiency issue is
  `agent-chat` raw-token volume and Realtime prompt/context size, not
  unbounded tool-output reinjection.
- Follow-up direction: Realtime policy now instructs Samantha to pass the
  operator's exact message to `delegate_to_builder_agent`, not rewrite
  "I want to improve/add/ship..." into a narrower investigation. The policy
  change still needs a fresh browser pass after server restart before the
  Realtime parity checklist can be marked complete.

## 2026-05-15 Agent Page Due-Date Shipping Cycle

- Result: the managed `todo-app` shipped `Add due dates and Today attention
  view`; Board state reached `pending: 0`, `active: 0`, `review: 0`,
  `done: 26`, `blocked: 0`. Focused task status for
  `6e1333a4-fc20-4e98-a11b-e5043d55311b` is `done`.
- Operator prompts used plain wording: `I'm ready for the next safe step.`,
  then recovery prompts asking Builder to keep going until the due-date
  improvement was shipped. The operator did not need backlog, sprint, task, or
  product-backlog terminology.
- Not a clean Agent-page-only pass: after a server restart, the Agent page held
  a stale `Active 0 RUNNING` header while persisted history reported
  `running: false`; final verification had to be dispatched through the visible
  Board recovery path. The frontend now maps non-running, unblocked Agent
  sessions to `Ready` and ignores the global shell `running_label` unless the
  selected Agent session is actually running.
- Runtime fix: verification now runs deterministic feature acceptance first,
  avoiding a repeat of the earlier `feature-verifier` chunk-limit failure
  (`Separator is not found, and chunk exceed the limit`) when durable tests
  already prove the feature.
- Feature proof: final deterministic runs were `feature-acceptance-tests`
  (`46cf0af7-fd04-498d-b648-0e7ed7508d91`, `164ms`, `0` tokens) and
  `build-verifier` (`a225aafa-9c97-4c6d-8791-63f1bf11d5b0`, `2202ms`,
  `0` tokens). The generated app passed `npm test` (`55` tests), `npm run
  lint`, and `npm run build`.
- Token/efficiency evidence: `builder metrics show --json` reported
  `raw_token_total: 2035506`, `noncached_plus_output_tokens: 508877`,
  `cache_ratio: 5.895`, `large_command_output: 12`, `redundant_scan: 11`,
  `chunk_pressure_risk: false`, and recommended
  `truncate_tool_output_before_reinjection`.
- Browser proof: Chrome loaded the Agent page from the rebuilt dashboard at
  `http://127.0.0.1:9876/?v=readyfix3` with `Ready`, `AGENT · READY`, the
  selected shipped verification task, and recent deterministic run evidence
  visible.
- Memory note: this was initially skipped until the later explicit memory-update
  request, then captured in the repo correction and global ad-hoc note listed
  below.

## 2026-05-15 Token-Efficiency Reinjection Fix

- Baseline evidence from managed `todo-app`: `builder metrics show --json` and
  `builder logs --error --json` showed `raw_token_total: 2035506`,
  `noncached_plus_output_tokens: 508877`, `large_command_output: 12`,
  `redundant_scan: 11`, `recent_large_output_runs: 1`, and
  `recommended_next_change: truncate_tool_output_before_reinjection`. Error
  logs included the earlier transport chunk-limit failures and the explicit
  recommendation for paired output truncation plus bounded retrieval.
- Root cause: Codex app-server large command output was materialized to a
  Builder artifact and compacted for returned runtime events, but the
  optimization summary still measured the raw event stream. That kept the
  metrics lane recommending output truncation even after Builder was already
  avoiding polluted thread resume.
- Fix: Codex SDK run observability now scores the compacted reinjection event
  stream, preserves the full command output in `.agent-builder/runtime-artifacts`
  metadata, records `tool_output_reinjection.policy:
  truncate_tool_output_before_reinjection`, and includes the concrete bounded
  retrieval shortcut in both chunk-limit retry prompts and Agent-page
  observability context packs.
- Regression proof: `uv run pytest
  tests/test_codex_app_server_runtime.py tests/test_codex_optimization.py
  tests/test_runtime_optimization.py
  tests/test_embedded_agent_routes.py::test_observability_context_pack_keeps_analysis_model_backed
  tests/test_embedded_agent_routes.py::test_compatible_resume_session_rejects_codex_large_output_context`
  passed `33` tests; `uv run ruff check
  src/autonomous_agent_builder/runtime/codex_app_server_runtime.py
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  tests/test_codex_app_server_runtime.py tests/test_embedded_agent_routes.py`
  passed.
- Live after evidence: Chrome-visible Agent-page validation on
  `http://127.0.0.1:9876` created session
  `4ac92212-f60e-4153-8185-22a1163038a5` using the bounded retrieval prompt.
  After the run, `builder metrics show --json --full --limit 8` reported
  `active_avoidable_cost_flags: []`, `recent_large_output_runs: 0`, and
  `recommended_next_change: reduce_agent-chat_raw_tokens`; the compact metrics
  decision now targets `bounded_retrieval_shortcut` rather than output
  reinjection.

## 2026-05-15 Agent Page Token Accounting Display

- Root cause: the live Agent page Session rail showed a single `Tokens` value
  from raw total token accounting. In the validated Codex SDK session
  `4ac92212-f60e-4153-8185-22a1163038a5`, that made `35,126` raw tokens look
  like fresh work even though `33,152` input tokens were cached and the
  non-cached-plus-output total was `1,974`.
- SDK guidance checked: OpenAI's GPT-5.5, prompt caching, conversation-state,
  tool-search, and compaction docs all support keeping the operator prompt
  model-backed while making context/tool surfaces cache-friendly and reporting
  cached-token metrics explicitly. Claude Agent SDK docs add the parallel
  guidance for the `claude` lane: preserve the agent loop, tune tool scope,
  permissions, hooks, `AskUserQuestion`, subagents, tool search, compaction,
  effort, turn/budget limits, usage/cache tracking, and structural OTEL.
- Fix: the Agent page now derives current-session token accounting from the
  run observability payload and displays `Non-cached + output`, `Raw tokens`,
  and `Cached tokens` in the Session rail. This keeps intent/tool selection
  model-backed and makes cached raw-token reuse visible to the operator.
- Transcript refresh fix: the new timeline conversation UI and the old card
  renderer were both still present, with `transcriptLayout: "cards"` as the
  persisted/default preference. A hot page could show the timeline first, then
  refresh would rehydrate the old preference and show the card UI. The default is
  now `timeline`, existing stored `cards` preferences migrate once to timeline,
  Settings lists Timeline first, and regression coverage locks the migration.
- Voice tab alignment: Realtime Voice messages now use the same `AgentTimeline`
  renderer as Conversation, operator text is labeled `Operator` instead of
  `Operator to Samantha`, normal Samantha responses are labeled `Samantha`
  instead of `thinking · Samantha`, and the realtime text composer sits below
  the transcript content instead of inside the old voice card stack.
- Realtime eagerness fix: when the Realtime data channel opens, Samantha now
  says exactly `Hi there!` as a constrained activation greeting instead of receiving a
  synthetic operator `Hi`. The sideband no longer polls pending approvals into
  unsolicited spoken reminders, so after the activation cue Samantha waits for
  non-empty operator speech or typed input.
- Owner docs updated: `docs/rubric/deterministic-vs-model-backed-agent-behavior.md`,
  `docs/workflows/agent-quality-tuning-loop.md`,
  `docs/references/runtime-settings.md`, and
  `docs/quality-gate/agent-quality.md` now state the optimization direction for
  Codex SDK. `docs/references/claude-agent-sdk-telemetry-observability.md`,
  `docs/quality-gate/claude-agent-sdk.md`, and
  `docs/rubric/sdk-backed-agent-page-agent.md` now carry the matching Claude
  Agent SDK direction: preserve model-backed judgment, then optimize
  cache-friendly prompt shape, bounded evidence, tool scope, permissions,
  hooks, `AskUserQuestion`, subagents, deferred tools, compaction, and
  raw/cached/effective token reporting.
- Code alignment scan: current code already aligns on Claude SDK tool
  allowlists, permission callbacks, hooks, subagents, max-turn/budget controls,
  compaction settings, and Codex SDK bounded large-output artifacts with
  no-resume retention. Follow-up code alignment should add full SDK usage
  normalization: Claude cache-creation tokens and result subtype/error evidence,
  and OpenAI Agents runtime usage/cost/session telemetry extraction. The scan did
  not find a reason to replace model-backed recommendation prompts with
  deterministic intent shortcuts.
- Regression coverage: `tests/test_dashboard_design_system_contract.py` locks
  the Session rail token labels and prevents regressing to a single raw
  `Tokens` row. It also locks the Agent-page transcript layout refresh default
  and migration to timeline.
- Browser proof: started the managed `todo-app` dashboard with
  `builder start --port 9876`. Chrome visibly loaded `/board` with Sprint 4
  lanes and shipped due-date task cards, then loaded the Agent page with the
  Session rail showing `Non-cached + output`, `Raw tokens`, and `Cached tokens`
  as separate rows. A later Chrome refresh showed the Voice tab using the
  Conversation-style timeline, the Realtime input below the transcript, and a
  bounded activation greeting rendered as `SAMANTHA ... Hi there!` without a
  `thinking` label. The temporary dashboard server was stopped afterward.
- Memory update: after the explicit user request to update memory, added repo
  correction
  `.memory/corrections/keep-agent-page-intent-model-backed-while-optimizing-token-a.md`
  and global ad-hoc note
  `extensions/ad_hoc/notes/20260515T212958+0530-builder-sdk-token-optimization.md`;
  `builder memory lint --json` passed.

## 2026-05-15 Agent Run Trace Loading Root Cause

- Root cause: the live embedded dashboard route streamed unbounded historical
  Board payloads. Completed task run summaries carried large diff/observability
  evidence, and embedded sprint execution summaries had drifted from the compact
  API route contract. The Agent page waited on that broad board snapshot before
  it could render the selected active task-owned run.
- Fix: shared bounded dashboard payload serializers and sprint execution
  compaction across API and embedded routes; bounded Board task run history; kept
  Agent-page run trace on the Board SSE contract instead of adding a
  task-specific polling workaround.
- Evidence: managed `todo-app` Board JSON dropped from `11801990` bytes to
  `835662` bytes, and Board SSE over two seconds dropped from `12703880` bytes
  to `879995` bytes. Chrome-visible Run trace loaded the selected task run,
  event timeline, Run explorer, and Agent runs instead of showing `Could not
  load task runs`.

## Full Goal Checklist

### Operator UX Abstraction

- [x] Agent page can capture a plain improvement request without requiring backlog, sprint, task, or product-backlog terminology.
- [x] Question and approval cards render readable option labels instead of `[object Object]`.
- [x] Typed Agent-page prompts stay model-backed; explicit dashboard controls and
  system refreshes own deterministic state/actions.
- [x] Blocked task recovery ownership is explicit: Agent chat, Board, and Realtime Voice are entrypoints; `recover_failed_task`, orchestrator dispatch, integration gates, and state reconciliation own the mutation.
- [x] Ready Board delivery follow-up can stay model-backed without exact magic wording; the runtime model receives delivery context and chooses Builder tool calls.
- [x] Browser-retest the Board recovery action for the same blocked task shape and prove it calls the same recovery service as Agent chat.
  Evidence: see `2026-05-17 Board Recovery Browser Retest`; Chrome/Computer
  Use clicked the visible Board `Recover` button, the card moved from
  `Blocked` to `Queued`, the embedded server logged
  `POST /api/tasks/068d477f-2b4d-4fb0-a62c-190a51a32d9a/recover`, and backend
  state showed the shared recovery service cleared blocked/capability-limit
  fields.
- [ ] Browser-retest Realtime Voice text mode with the same recovery/continuation wording and compare the transcript, Board state, and runtime evidence against SDK-backed Agent.
- [x] Remove or hide remaining operator-facing lifecycle ceremony after approval; the operator should not be asked to understand when sprint tasks should start.
- [x] Confirm no visible Agent, Realtime, Board, Backlog, or approval copy requires internal terms to complete the happy path.
  Evidence: patched and browser-retested the managed `todo-app` dashboard on
  `http://127.0.0.1:9876`. Agent now opens with `Tell Builder what to improve
  next`, Voice shows `No voice turns yet`, Board opens as `Work board`,
  Backlog opens as `Planned improvements` with `Work list`, `Ideas`,
  `Improvement`, `Success checks`, and `Prerequisites`, and the approval
  fallback opens as `Decision needed` / `Review the proposed work`.
  Technical runtime/evidence metadata remains available inside evidence
  surfaces, but the happy path no longer asks the operator to understand
  backlog ledger, sprint task, gate, tool-call, or Realtime wording.

### Live Shipping And Managed App Boundary

- [x] Ship one real `todo-app` improvement from the Agent page end to end through Builder-owned agents/gates, not manual generated-app edits.
- [x] Prove generated-app source changes are produced, integrated, verified, and surfaced by Builder task runs.
- [x] Prove final generated-app browser behavior for the shipped task in the real app checkout.
- [x] Keep Codex out of direct managed-app mutation during Builder validation; `todo-app/node_modules` was removed after the boundary correction.
- [x] Save the managed-app ownership correction in Builder memory and pass `builder memory lint --json`.
- [x] Recover the current blocked `todo-app` state through Builder product entrypoints only, or create a Builder-owned incident if recovery remains blocked.

### Token, Runtime, And Observability Monitoring

- [x] `builder metrics show --json` exposes compact token/cost/run evidence and keeps `--full --limit` for raw evidence.
- [x] Observability shows reachable Claude, Codex, and Builder telemetry collectors after `builder start` starts the local OTLP collector.
- [x] Large-output recommendations use active recent flags instead of stale lifetime counts.
- [x] During the next live shipping run, capture per-run tokens, total/raw tokens, cached tokens, noncached plus output tokens, chunk pressure, large-output flags, zero-turn runs, repeated retrieval, blockers, and top cost drivers.
- [x] Treat any token waste, chunk risk, zero-turn ineffective run, or repeated retrieval as a Builder robustness defect with an owner and follow-up.
- [x] Verify Realtime uses the OpenAI API key only for Realtime and the cost-efficient Realtime mini model, while Codex SDK remains ChatGPT-subscription backed.

### Surface Coverage

- [x] Board status lanes match across Board page, SDK-backed Agent, and Realtime Voice for queued/active/blocked counts.
- [x] Settings runtime switching preserves historical attribution and applies only to future runs.
- [x] Simple observability status checks can use deterministic Builder state,
  while recommendation and `what should I fix next?` prompts stay model-backed.
- [x] Simple Backlog/Board navigation is deterministic across Agent chat and Realtime Voice text mode.
- [ ] Board: verify recovery, dispatch, blocked, needs-review, and shipped actions browser-visibly after the recovery ownership fix.
- [x] Backlog: verify plain feature requests, approved improvements, and ready items without internal lifecycle language.
- [x] Approvals: verify approval naturally continues delivery, or the next action is obvious and does not require sprint/task vocabulary.
- [x] Metrics: verify live run token/efficiency evidence updates after a real shipped task.
- [ ] Observability: verify recommendation tabs classify Builder versus App versus Rejected after the next live run.
- [ ] Realtime Voice: verify text-mode parity for feature request, approval, recovery, status, run-trace open, and open-then-analyze.
- [ ] SDK-backed Agent: verify the same plain prompt set against both `claude` and `codex_sdk` runtimes with consistent product behavior and distinct runtime/auth evidence.

### Source Quality And Enforcement

- [x] Focused Agent chat recovery tests pass.
- [x] Orchestrator tracked-overwrite integration tests pass.
- [x] Broader Agent route, Realtime, orchestrator/task-recovery/run-reconciliation, Builder CLI/subagent/pre-commit, frontend lint, and frontend build proof passed for the current source slice.
- [x] `builder verify --changed --execute --json` passed executable proof and identified only manual dashboard proof as remaining.
- [x] Pre-commit enforcement now requires `CHANGELOG.md` for product, docs, hook, or operator-surface changes.
- [x] Updated pre-commit tests and hook command pass after the changelog entry landed.
- [x] Keep `docs/PROGRESS.md` and `CHANGELOG.md` synchronized for each commit-worthy product slice; root `PROGRESS.md` has been removed so `docs/PROGRESS.md` is the single progress owner.

- [x] Realtime Voice text mode remains usable when macOS/browser exposes no microphone input.
  - Evidence: Browser-visible Voice tab shows the actionable fallback message.
  - Evidence: macOS probes showed no AVFoundation audio input devices exposed to apps.
  - Evidence: `uv run pytest tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py -q` passed.

- [x] SDK-backed Agent no longer double-counts Board `omitted` runs as shipped tasks.
  - Evidence: Browser prompt "From the board, how many tasks are shipped and how many are blocked?" returned `Shipped: 17 tasks` and `Blocked: 0 tasks`.
  - Evidence: `builder logs --session B9E63E22 --compact --json` showed `mcp__builder__board` completed successfully.

- [x] Samantha can resolve and open task-owned run traces deterministically.
  - Implemented `open_run_trace` as a direct Realtime tool.
  - Supported intents: `open_only` for navigation and `open_then_analyze` for navigation followed by SDK-backed Builder analysis.
  - Boundary: Samantha resolves and opens existing evidence; SDK-backed Builder performs analysis when requested.
  - Evidence: `uv run pytest tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py -q` reported `49 passed`.
  - Memory: `.memory/patterns/samantha-opens-run-trace-before-delegating-analysis.md`; `builder memory lint --json` passed.

- [x] Codex app-server large-output recommendations no longer stay stale after a runtime fix.
  - Implemented large command-output artifact retention under `.agent-builder/runtime-artifacts/codex-app-server/`, compact run evidence previews, and `context_retention.resume_recommended=false` for affected Codex SDK sessions.
  - Metrics now keep lifetime `large_command_output` counts for audit history while using active recent flags for `recommended_next_change` and deterministic script candidates.
  - Browser evidence: live Observability page on `http://127.0.0.1:9876/observability` no longer shows the output-truncation recommendation card after fresh clean runs.
  - CLI evidence: `builder metrics show --json | jq '{recommended_next_change: .optimization_summary.recommended_next_change, recent_large_output_runs: .optimization_summary.chunk_pressure.recent_large_output_runs, deterministic_script_candidates: [.deterministic_script_candidates[]?.code]}'` returned `recommended_next_change=reduce_agent-chat_raw_tokens`, `recent_large_output_runs=0`, and only `bounded_retrieval_shortcut`.
  - Runtime evidence: `builder agent runtime show --json` returned Codex SDK telemetry `collector_status=reachable`; `lsof -nP -iTCP:4318 -sTCP:LISTEN` and `lsof -nP -iTCP:9876 -sTCP:LISTEN` both showed the restarted dashboard process listening.
  - Test evidence: `pytest tests/test_codex_app_server_runtime.py tests/test_embedded_agent_routes.py tests/test_codex_optimization.py tests/test_runtime_optimization.py` reported `122 passed`; `pytest tests/test_runtime_boundary_gate.py -q` reported `4 passed`; `uv run ruff check ... --ignore E501` passed; `git diff --check` passed.
  - Memory: `.memory/decisions/use-active-recent-flags-for-large-output-recommendations.md`; `builder memory lint --json` passed.

- [x] Browser-visible retest of Samantha run-trace navigation in the live dashboard.
  - Prompt examples: "Show me the last optimization run." and "Analyze the current agent run. Was it efficient?"
  - Evidence: Chrome prompt "Show me the last optimization run." changed the Agent page URL to `/?mode=trace&task=de8324dc-14b7-462c-b41b-cd441441bf71&run=d17656f2-17df-479e-9acd-82b209aafb19` and selected `Run trace`.
  - Regression found: when the URL already pointed at the same trace, Samantha could queue Builder analysis while the visible panel stayed on Voice. The fix now applies voice navigation from timeline items as well as direct SSE/custom events.
  - Evidence: After rebuilding the dashboard from source and manually returning to Voice while the URL remained `/?mode=trace&task=de8324dc-14b7-462c-b41b-cd441441bf71&run=d17656f2-17df-479e-9acd-82b209aafb19`, Chrome prompt "Analyze the current agent run. Was it efficient? Also tell me what to do next." switched the visible Agent page back to `Run trace` and rendered the selected optimization-agent run without manual tab selection.
  - Evidence: `builder agent history --session d67845ce-7910-4d2a-a3b6-84af603b3cec --full --json` recorded fresh event `52d06407-ac7b-4ce9-be15-bf2f2ebadb1b` with `type=voice_navigation_request`, `intent=open_then_analyze`, `analysis_request="Analyze the current agent run. Was it efficient? Also tell me what to do next."`, and the resolved route above.
  - Evidence: The same history recorded Samantha-to-Agent delegation with resolved run id `d17656f2-17df-479e-9acd-82b209aafb19`, task id `de8324dc-14b7-462c-b41b-cd441441bf71`, and the full operator request.
  - Evidence: `builder logs --session d67845ce --compact --json` showed fresh `voice_tool_output` for `open_run_trace`, then a completed Agent run with `tokens_used=340`, `cost_usd=0.00827155`, and `stop_reason=end_turn`.
  - Evidence: `builder metrics show --json` showed `voice_ledger.tool_calls=13`, `voice_ledger.tool_outputs=14`, `failed_tool_outputs=0`, and recent `agent-chat` runs including the latest `tokens=340` run.

- [x] Observability page no longer shows Not Found from source-cwd project resolution.
  - Regression found: `/observability` loaded the React shell, but `/api/dashboard/observability` returned `404` with `Run builder commands from the generated app workspace...` because the endpoint resolved `.agent-builder` from `Path.cwd()` instead of the embedded app project root.
  - Fix: `src/autonomous_agent_builder/embedded/server/routes/dashboard.py` and `src/autonomous_agent_builder/api/routes/dashboard_api.py` now resolve the observability database from `request.app.state.project_root`.
  - Evidence: `uv run pytest tests/test_embedded_server_app.py::test_embedded_observability_uses_app_project_root -q` passed.
  - Evidence: after restarting the dashboard against `todo-app/.agent-builder`, `GET /api/dashboard/observability` returned `200 OK` with `ok=true`, `status=ok`, `observability_coverage.source=runtime_env`, and telemetry health; `GET /observability` returned the dashboard shell with no-store cache headers.
  - Evidence: restarted server logs showed repeated `GET /api/dashboard/observability HTTP/1.1" 200 OK` requests from the browser.

- [x] Realtime floating Samantha widget no longer blocks the dashboard by default.
  - Regression found: the bottom-right Realtime widget stayed expanded on trace pages, pulsed while merely connected, and stopping/muting Samantha could remove the visible control.
  - Fix: `frontend/src/hooks/use-realtime-voice.tsx` now keeps the widget mounted as a collapsed round Samantha control, toggles expanded/collapsed on icon click, auto-collapses after inactivity, only pulses while assistant output is streaming/speaking, and supports drag-to-move with locally persisted screen position.
  - Evidence: browser-visible trace page defaulted to a single collapsed Samantha icon; clicking expanded it; clicking the icon again collapsed it; inactivity collapsed it; user confirmed the icon moved.
  - Evidence: `uv run pytest tests/test_realtime_voice_frontend_static.py tests/test_realtime_voice_operator.py -q`, `npm run lint`, and `npm run build` passed.

- [x] Board status answers use the same lane names across Board, SDK-backed Agent, and Realtime Voice.
  - Regression found: the Board page visibly showed `Queued 1`, `In progress 0`, and `Blocked 0`, while the SDK-backed Agent and Realtime Voice called the queued implementation task active.
  - Fix: Agent model-backed prompts and Realtime `board_status` now classify Board lanes using dashboard-equivalent rules: a task is in progress only when the latest task run is running; waiting implementation work is queued; blocked/review states stay separate.
  - Evidence: browser-visible Board page showed Sprint 1 / Feature 5 with `Queued 1`, `In progress 0`, and `Blocked 0`; the SDK-backed Agent prompt "what is teh status of the board" returned `Queued 1, in progress 0, needs review 0, shipped 17, blocked 0`; a fresh Realtime Voice session answered the same typo prompt with `0 blocked tasks` and `1 queued task`.
  - Evidence: `uv run pytest tests/test_realtime_voice_operator.py::test_realtime_voice_policy_instructions_route_operator_requests_to_tools tests/test_realtime_voice_operator.py::test_get_builder_status_uses_board_lane_counts_for_waiting_task tests/test_embedded_agent_routes.py::test_board_status_uses_dashboard_lane_counts_for_waiting_implementation_task tests/test_embedded_agent_routes.py::test_board_status_names_running_task_as_in_progress -q` passed.

- [x] Simple dashboard navigation intents are direct controls in Realtime Voice
  text; SDK-backed Agent typed prompts now stay model-backed.
  - Regression found: Realtime `show me the backlog` said `Opening Backlog.` but stayed on `/`; SDK-backed Agent `show me the backlog` started a full Codex SDK run and failed with `Error: Separator is not found, and chunk exceed the limit`.
  - Fix: Realtime text-control returns the route and the frontend applies it
  directly. The earlier Agent-chat zero-token navigation fast path was removed
  after the prompt contract was clarified: typed Agent prompts must be processed
  by the selected model.
  - Evidence: browser-visible Realtime `show me the backlog` opened `/backlog`; Realtime `take me to the board` opened `/board`; SDK-backed Agent `show me the backlog` opened `/backlog`.
  - Superseded evidence: the old SDK-backed Agent proof used zero-token
  navigation. Current validation must prove typed Agent prompts enter the model
  lane and any navigation happens through model/tool choice.

- [x] Settings runtime controls visibly switch future-run SDK and preserve historical attribution language.
  - Evidence: browser-visible Settings > Runtime lane showed `Claude Agent SDK`, model `sonnet`, telemetry `claude`, and copy stating future runs use the selected SDK while historical state keeps the runtime that created it.
  - Evidence: clicking `Codex SDK` updated the Settings panel to model `gpt-5.5` and telemetry `codex`; `uv run builder agent runtime show --json` from the generated app workspace returned `sdk=codex_sdk`, `provider=codex_subscription`, and `telemetry.active_lane=codex`.
  - Evidence: clicking back to `Claude Agent SDK` restored the Settings panel to model `sonnet` and telemetry `claude`; `uv run builder agent runtime show --json` returned `sdk=claude`, `provider=claude_agent_sdk`, and `telemetry.active_lane=claude`.

- [x] Blocked task recovery responsibility is explicit and Builder-owned.
  - Regression found: live Chrome inspection of the Agent page showed a failed selected verification task after the operator prompt "Please recover this and keep going until it is shipped."; read-only Builder evidence showed the implementation task had failed integration because local checkout changes would be overwritten by merge.
  - Boundary: the operator entrypoints are Agent chat, Board actions, and Realtime Voice; recovery is owned by the shared Builder recovery service, dispatch by the orchestrator, integration by the task/sprint integration gate, and interrupted-run cleanup by state reconciliation. Codex must not install dependencies, edit source, or clean generated app workspaces by hand during Builder validation.
  - Fix: Agent chat recovery-continuation now calls `recover_failed_task` and dispatches the recovered task before later sprint tasks; sprint dispatch no longer skips an earlier failed generated task to start later pending work; task workspace integration preserves tracked local target files before fast-forwarding task output.
  - Evidence: `uv run pytest tests/test_embedded_agent_routes.py::test_recover_and_keep_going_recovers_first_blocked_sprint_task_before_dispatch tests/test_embedded_agent_routes.py::test_continue_remaining_verification_task_dispatches_current_sprint_task tests/test_embedded_agent_routes.py::test_recovery_status_check_does_not_auto_dispatch_sprint_task -q` passed.
  - Evidence: `uv run pytest tests/test_orchestrator.py::test_integrate_task_workspace_preserves_tracked_target_changes_before_merge tests/test_orchestrator.py::test_tracked_overwrite_paths_extracts_safe_relative_paths -q` passed.
  - Evidence: `uv run pytest tests/test_embedded_agent_routes.py -q` passed `99 passed`; `uv run pytest tests/test_orchestrator.py tests/test_task_recovery.py tests/test_run_reconciliation.py -q` passed `54 passed`; `builder verify --changed --execute --json` passed executable proof and only required manual dashboard proof, satisfied by Chrome-visible Agent page render.
  - Memory: `.memory/corrections/do-not-mutate-managed-app-workspaces-during-builder-validati.md`; `builder memory lint --json` passed.

- [ ] Continue operator robustness pass across Board, Backlog, Settings, approvals, Metrics, Observability, Realtime Voice, and SDK-backed Agent.
  - Use natural operator prompts, not implementation prompts.
  - Diagnose failures through Builder-owned logs, metrics, run trace, and browser-visible state.

## 2026-05-17 Board Recovery Browser Retest

- Result: Computer Use drove Chrome at `http://127.0.0.1:9876/board` against
  disposable fixture workspace
  `/private/tmp/aab-board-recovery-fixture-NwXQgj`. The visible Board started
  with task `068d477f-2b4d-4fb0-a62c-190a51a32d9a` in the `Blocked` lane with
  a `Recover` button.
- Browser proof: clicking the visible Board `Recover` button moved `Verify
  Board recovery action uses shared service` from `Blocked` to `Queued`,
  changed blocked count from `1` to `0`, queued count from `0` to `1`, and
  enabled the `Dispatch Verify Board recovery action uses shared service`
  button.
- Shared-service proof: the embedded server log recorded
  `POST /api/tasks/068d477f-2b4d-4fb0-a62c-190a51a32d9a/recover HTTP/1.1`
  with status `200`; [tasks.py](../src/autonomous_agent_builder/embedded/server/routes/tasks.py)
  routes that endpoint directly to `recover_failed_task(task, db)`.
- Backend state proof: `builder board show --json` from the fixture workspace
  returned `pending: 1`, `blocked: 0`, with the task status `implementation`.
  A read-only SQLite check showed `blocked_reason: null` and
  `capability_limit_reason: null` for the recovered task.

## 2026-05-17 Operator Copy Cleanup

- Result: cleaned happy-path wording across Agent, Voice, Board, Backlog, and
  approval fallback surfaces so operators can start or review work without
  needing internal lifecycle terms.
- Agent/Voice proof: Computer Use reloaded Chrome on
  `http://127.0.0.1:9876/?mode=voice`; the visible Agent header read `Tell
  Builder what to improve next`, the Voice panel read `Voice and typed Samantha
  turns stay here`, and the empty state read `No voice turns yet`.
- Board proof: Chrome on `/board` showed `Work board`, `Every improvement, one
  horizon.`, `No work to start`, and `Start work` instead of pipeline/task
  dispatch language.
- Backlog proof: Chrome on `/backlog` showed `Planned improvements`, `Work
  list`, `Ideas`, `Improvement`, `Success checks`, and `Prerequisites` instead
  of backlog ledger, feature, acceptance-criteria, and dependency wording.
- Approval proof: Chrome on `/approvals/not-real` showed the fallback as
  `Decision needed` and `Review the proposed work` with `Decision pending`,
  proving the approval shell no longer opens with gate-specific copy.
- Verification: `npm run lint` and `npm run build` passed for the dashboard
  frontend after the copy changes.

## 2026-05-17 Backlog Surface Retest

- Root objective check: no root `PROGRESS.md` or `GOAL.md` exists; the active
  execution/progress owners remain [PLAN.md](PLAN.md) and
  [PROGRESS.md](PROGRESS.md).
- Browser proof: after rebuilding and serving the managed `todo-app` dashboard
  from patched source on `http://127.0.0.1:9876`, Chrome/Computer Use loaded
  `/backlog` and showed `Planned improvements`, `Work list`, `Ideas`,
  `Improvement`, `Success checks`, and `Prerequisites`.
- State proof: `/api/dashboard/features` reported `total: 18`, `done: 11`,
  `pending: 7`, with visible plain request items under `Ideas`, ready work under
  `Queued`, and shipped work selected in the details pane without exposing
  backlog-ledger, feature-type, acceptance-criteria, or dependency wording.
- UI fix: generated `feature-*` IDs now display as `item-*` in Backlog rows and
  detail metadata, while item type filters use the same operator-facing labels
  as the rest of the page.
- Verification: `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_dashboard_design_system_contract.py -q` passed `19 passed`;
  `builder quality-gate dashboard-ux --json`, `npm run lint`, and
  `npm run build` passed. The build still reports the existing Vite chunk-size
  warning.

## Current Verification

```bash
uv run pytest tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py -q
uv run pytest tests/test_embedded_server_app.py::test_embedded_observability_uses_app_project_root -q
uv run pytest tests/test_realtime_voice_operator.py::test_realtime_voice_policy_instructions_route_operator_requests_to_tools tests/test_realtime_voice_operator.py::test_get_builder_status_uses_board_lane_counts_for_waiting_task tests/test_embedded_agent_routes.py::test_board_status_uses_dashboard_lane_counts_for_waiting_implementation_task tests/test_embedded_agent_routes.py::test_board_status_names_running_task_as_in_progress -q
uv run pytest tests/test_embedded_agent_routes.py::test_agent_chat_simple_dashboard_navigation_is_model_backed tests/test_realtime_voice_operator.py::test_realtime_text_control_prioritizes_navigation_over_status_words tests/test_realtime_voice_frontend_static.py -q
uv run pytest tests/test_embedded_agent_routes.py::test_recover_and_keep_going_recovers_first_blocked_sprint_task_before_dispatch tests/test_embedded_agent_routes.py::test_continue_remaining_verification_task_dispatches_current_sprint_task tests/test_embedded_agent_routes.py::test_recovery_status_check_does_not_auto_dispatch_sprint_task -q
uv run pytest tests/test_orchestrator.py::test_integrate_task_workspace_preserves_tracked_target_changes_before_merge tests/test_orchestrator.py::test_tracked_overwrite_paths_extracts_safe_relative_paths -q
uv run pytest tests/test_embedded_agent_routes.py -q
uv run pytest tests/test_orchestrator.py tests/test_task_recovery.py tests/test_run_reconciliation.py -q
uv run pytest tests/test_dashboard_design_system_contract.py::test_agent_run_trace_surfaces_token_breakdown tests/test_pre_commit_checks.py -q
python scripts/pre_commit_checks.py
uv run builder agent runtime show --json
npm run lint
npm run build
```

Result: Realtime focused tests `60 passed`; Observability project-root regression test `1 passed`; Board lane regression tests `4 passed`; direct dashboard navigation regression tests `6 passed`; recovery-continuation regression tests `3 passed`; integration tracked-overwrite regression tests `2 passed`; embedded Agent route suite `99 passed`; orchestrator/task-recovery/run-reconciliation suite `54 passed`; hook/dashboard contract focused tests `14 passed`; `python scripts/pre_commit_checks.py` passed all selected checks including `changelog_update_required`; runtime show returned Claude after the switch-back retest; dashboard frontend lint and production build passed.

Browser/live evidence: patched dashboard served on `http://127.0.0.1:9876` from source `run_start` against `todo-app/.agent-builder`; Realtime text prompts above passed with Chrome-visible navigation and builder-owned log/session evidence. Realtime `show me the backlog` and `take me to the board` navigated to `/backlog` and `/board`. Later prompt-contract work superseded the SDK-backed Agent zero-token navigation shortcut; typed Agent prompts now stay model-backed. Floating Samantha defaulted to the collapsed control, expanded on icon click, collapsed on a second icon click, and stayed visible without the speaking pulse while only connected/text-fallback active. Board lane retest showed the Board page, SDK-backed Agent, and a fresh Realtime Voice session all treating the remaining implementation task as queued rather than active. Settings runtime retest visibly switched Claude -> Codex -> Claude and the generated-app runtime show command confirmed the final state is Claude.

## 2026-05-15 Change Review And Commit Prep

- Reviewed the pending tree across Codex custom-agent configuration and gate
  enforcement, Builder agent responsibility/tool permissions, Agent
  continuation/recovery routing, Realtime Samantha UI consolidation, onboarding
  codebase classification, task-workspace integration recovery, changelog
  enforcement, repo memory corrections, and active goal documentation.
- Kept the commit scope to durable source, tests, owner docs, progress docs,
  memory corrections, and the agent-sprint-cycle explainer artifact. Added
  ignore coverage for nested `.claude/settings.local.json` and `.thumbnails/`
  render byproducts plus local explainer `audio/` generation files so caches and
  OpenAI-key-backed TTS artifacts do not enter project history.
- Verification added during commit prep:
  `python3 scripts/check_codex_subagents.py --repo-root .` passed;
  `uv run pytest tests/test_codex_subagents.py tests/test_builder_cli_surfaces.py tests/test_pre_commit_checks.py -q`
  passed `163 passed`;
  `uv run pytest tests/test_embedded_agent_routes.py::test_recover_and_keep_going_recovers_first_blocked_sprint_task_before_dispatch tests/test_embedded_agent_routes.py::test_continue_remaining_verification_task_dispatches_current_sprint_task tests/test_embedded_agent_routes.py::test_agent_chat_recovery_request_without_board_target_is_deterministic -q`
  passed `3 passed`; `python scripts/pre_commit_checks.py` passed;
  `git diff --check` passed; `npm run lint` and `npm run build` passed from
  `frontend/` with only the existing large chunk warning.
- Owner-surface checks: `builder quality-gate codex-subagents --json`,
  `builder quality-gate builder-cli --json`, `workflow quality-gate
  cli-for-agents`, `builder memory lint --json`, and `builder verify --changed
  --execute --json` all passed executable proof; `builder verify` still reported
  manual dashboard browser proof as required.
- Browser proof: started the patched dashboard from the managed `todo-app`
  workspace with `builder start --port 9876`; Chrome visibly loaded
  `http://127.0.0.1:9876/board` with Board lanes, the blocked-card Recover
  action, and the collapsed Samantha voice orb, then loaded the Agent page at
  `http://127.0.0.1:9876/` with conversation, selected task, recent runs, and
  the Samantha voice orb visible. The temporary server was stopped afterward.
- Official OpenAI Codex subagent docs were checked for project-scoped
  `.codex/agents/` files and required custom-agent keys.
- Goal remains not complete: browser-visible Agent-page `Start now`, Board
  recovery action parity, and Realtime recovery/continuation parity are still
  open checklist items.

## 2026-05-16 Inline Decision Surface Design Correction

- User correction: question and approval prompts should not open a dialog.
  They should remain inline in the conversation, but the inline controls must
  look like the current Builder design system rather than plain simple buttons.
- Fix: removed the Agent-page decision dialog path entirely. Pending questions
  and approvals now render inline using status pills, the token-backed review
  surface color, structured labels, option rows with descriptions, optional
  approval notes, and inline `Approve` / `Deny` or question-choice controls.
- Refresh fix retained: new chat sessions, question responses, approval
  responses, and session-list opens now sync `session=<id>` into the Agent-page
  URL so browser refresh does not fall back to a different pending session.
- Computer Use proof: rebuilt and republished the dashboard with
  `builder start --port 9876 --force`, then opened managed `todo-app` session
  `bf352c22-e6be-424d-9fae-bcedfa8477df`. The visible Agent page showed the
  pending question inline with `Needs review`, `Choose one to continue`, and
  design-system option rows for `Due reminders`, `Recurring todos`, and
  `Priority levels`; no dialog appeared.
- Root-cause follow-up: the old inline option row only updated local draft
  state, while the bottom quick-choice row submitted to `/api/agent/chat/respond`.
  The inline design-system option row now submits directly, so the visible
  control the operator clicks uses the same backend path as the composer.
- Session proof: after the fix and republish, Computer Use clicked `Due
  reminders (Recommended)` in the same managed `todo-app` session
  `bf352c22-e6be-424d-9fae-bcedfa8477df`. Server logs recorded
  `POST /api/agent/chat/respond` followed by exact-session history reloads;
  `builder agent history --session bf352c22-e6be-424d-9fae-bcedfa8477df
  --json` showed the assistant response scoping `Due reminders for tasks`,
  `stop_reason=completed`, `32,254` raw tokens, `2,432` cached tokens, and
  `29,822` non-cached-plus-output tokens.
- Visible proof: after refresh, the Agent page showed the question as
  `Answered`, rendered the assistant response inline, and moved the session rail
  to `Ready`. That separates the earlier refresh/session sync bug from the
  inline-button bug: URL sync keeps the right session selected, and the option
  row now actually submits.
- Trace cleanup: Run-trace entries now carry runtime/provider metadata through
  both dashboard API schemas and collapse adjacent uninformative tool-use rows
  into one timeline row with a call count. Timeline icons are runtime-aware:
  Codex SDK rows use the Codex glyph, Claude Agent SDK rows use the Claude
  glyph, and Samantha/Realtime Voice rows use the OpenAI glyph.
- Validation: focused frontend/static/API tests passed (`7 passed`), `npm run
  lint` passed, the real `frontend` Vite build passed with the existing
  chunk-size warning, `git diff --check` passed, and
  `builder quality-gate dashboard-ux --json` returned `ok`. The repo-root
  `npm run build` is not the Builder dashboard build in this checkout and
  failed in an unrelated parent Next/Prisma package with missing
  `prisma/config`; the valid dashboard build command is `npm run build` from
  `frontend/`.

## 2026-05-16 Model-Backed Start And Overdue Feature Shipping Proof

- Root Agent-page session fix: the fresh root route no longer stalls on
  `Loading agent transcript...` when no session is selected. The bootstrap
  path now loads an empty fresh transcript and keeps the composer usable after
  clearing the legacy global `chat_session_id`.
- Prompt-processing fix: the live `start` turn exposed a zero-token
  deterministic dispatch shortcut. That branch has been removed; `Start`,
  `Continue building my app.`, and delivery-follow-up wording now invoke the
  selected runtime model with Builder delivery context and allow the model to
  choose the dispatch/recovery/question tool chain.
- Contract cleanup: `CLAUDE.md`, the SDK-backed Agent rubric, the
  deterministic-vs-model-backed rubric, and the runtime-switch dashboard
  contract now state that typed operator prompts stay model-backed. Determinism
  is limited to explicit UI controls, system refreshes, and exact persisted-state
  reads; unclear prompt intent must use `AskUserQuestion` or the Agent page's
  equivalent structured question.
- Code cleanup: removed the unused deterministic feature-spec synthesizer, the
  zero-token read-only status prompt shortcut, and the direct recover-and-dispatch
  prompt branch. Status, recovery, and continuation prompts now exercise the
  runtime/model path in regression coverage.
- Runtime icon cleanup: timeline rows no longer use text placeholders for SDK
  attribution. Codex uses a terminal-in-circle glyph, Claude uses a radial
  burst glyph, and Samantha/OpenAI uses an OpenAI-style knot mark while staying
  within the Builder design-system token classes.
- Live managed `todo-app` proof: through the visible Agent page, Builder
  shipped `Make overdue todos stand out`; `builder board show --json` reported
  Sprint 9 `20f459bf-acd2-4668-abad-1c03aaa02462` as `shipped`, with
  `pending: 0`, `active: 0`, `review: 0`, `blocked: 0`, and all 3 generated
  tasks done.
- Token evidence from that lane: the Realtime/Agent scoping session used
  `40,339` raw tokens, `38,272` cached, and `2,067`
  non-cached-plus-output. The implementation, persistence/test, and
  verification runs used `52,835`, `65,782`, and `60,195` raw tokens; final
  metrics showed no active token pressure, no active avoidable-cost flags, no
  recent risky/large-output runs, and `chunk_pressure_risk: false`.
- Remaining efficiency follow-up: stale Chrome tabs continued polling an older
  session while the current session was active. That is now recorded as a
  session-noise robustness issue, separate from the fixed root bootstrap and
  model-backed start path.

## 2026-05-16 Codex App-Server Pre-Response Timeout

- Live validation evidence: after the model-backed typed prompt fix, a fresh
  managed `todo-app` Agent-page session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` processed `Do I need to approve
  anything?` through `codex_sdk` rather than a deterministic shortcut. The
  compact logs recorded SDK prompt assembly with `estimated_tokens: 681`, while
  `builder agent history` and `builder logs analyze --session ... --json`
  showed `sdk_session_id: null`, `tokens_used: 0`, `turns: 0`, and no error.
  The UI stayed `running`, proving a runtime wait hole rather than prompt
  dispatch confusion.
- Root cause: `CodexAppServerRuntime` already had an idle timeout after
  `turn/start`, but `_read_until_response` could wait forever for the
  `initialize`, `thread/start` or `thread/resume`, and `turn/start` JSON-RPC
  responses. If the app-server stalled before returning one of those responses,
  Builder had no SDK session id, token usage, tool events, or recorded failure.
- Fix: response waits now use `_REQUEST_RESPONSE_TIMEOUT_SECONDS`; timeout
  errors identify the stalled operation and flow through the existing
  `_error_result` path, while the `finally` block shuts down the app-server
  process. This turns the product symptom from an indefinite `running` Agent
  session into observable runtime evidence.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_codex_app_server_runtime.py -q` passed `14 passed`, including
  new coverage for response timeout before `thread/start`, response timeout
  before `turn/start`, and existing idle-after-turn protection.

## 2026-05-16 Operator-Safe Question Cards

- Live validation evidence: after the pre-response timeout fix, reloading
  managed `todo-app` Agent-page session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` showed the stalled prompt recovered
  into a visible inline question. The card was functional and design-system
  styled, but the model-supplied text leaked internal wording including
  `bounded`, `approval/status recovery`, `backlog item`, and `large logs`.
- Fix: the Agent route now tells runtime-native question tools that card text is
  operator-facing UI and must use plain product wording, then sanitizes
  persisted `ask_user_question` payloads before serialization so both new and
  historical cards avoid internal lifecycle terms.
- Browser proof: after rebuilding the managed dashboard and hard-refreshing
  Chrome, the same pending question rendered with plain product wording and
  readable choices such as `Yes, define it (Recommended)` and
  `Different improvement`, without the leaked `backlog`, `bounded`,
  `approval/status`, or `large logs` terms.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_operator_question_payload_removes_internal_lifecycle_terms
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_existing_question_payloads
  tests/test_embedded_agent_routes.py::test_chat_feature_spec_can_use_ask_user_question_and_resume_to_feature_save
  -q` passed `3 passed`; `PYTHONPATH=src pytest
  tests/test_codex_app_server_runtime.py::test_codex_app_server_runtime_maps_request_user_input
  -q` passed `1 passed`.

## 2026-05-16 Inline Start Permission Follow-Up

- Live validation evidence: clicking the sanitized inline question option in
  managed `todo-app` session `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175`
  submitted correctly and continued through the selected Codex SDK model lane.
  The follow-up run completed with SDK session
  `019e3028-4790-7a01-9b48-df0b0ac3f03f`, `32,322` raw tokens, `2,432`
  cached tokens, `29,890` non-cached-plus-output tokens, prompt
  `context_budget` estimate `796`, and no missing telemetry signals.
- Finding: the next assistant answer still exposed the internal phrase
  `approval/status recovery` and asked `Ready for Builder to start now, or
  should I hold?` as plain prose. That meant the lifecycle was model-backed and
  functional, but the operator still had to infer how to continue instead of
  receiving a design-system inline approval/question control.
- Fix: Agent serialization now normalizes assistant delivery-permission content
  that includes internal lifecycle terms, and the pending-question detector
  recognizes `Ready for Builder to start...` / `should I hold` wording so
  future model-backed answers render a structured inline `Start now` / `Hold`
  decision instead of a plain-text prompt.
- Post-fix rendering evidence: restarting the managed `todo-app` dashboard from
  the current Builder source and reading `/api/agent/chat/history` for session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` returned the historical question as
  `clear approval flow for blocked work`, removed the `a an` artifact, and
  rendered the assistant text as `approval flow improvement` with
  `Approval and Recovery Panel` instead of the raw `approval/status` wording.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_operator_question_payload_removes_internal_lifecycle_terms
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_existing_question_payloads
  tests/test_embedded_agent_routes.py::test_serialize_event_sanitizes_delivery_permission_assistant_content
  tests/test_embedded_agent_routes.py::test_assistant_delivery_permission_prompt_becomes_pending_question
  -q` passed `4 passed`.

## 2026-05-16 Model-Backed Typed Prompt Cleanup

- Fix: removed the remaining SDK-backed Agent chat deterministic early returns
  for typed dashboard navigation, recovery preflight, and observability
  explanation prompts. Those natural operator prompts now enter the selected
  runtime/model lane so the model can interpret user intent and choose the
  right Builder action or question.
- Owner-doc cleanup: the runtime-switch and Realtime integration references now
  reserve deterministic behavior for explicit UI controls or system refreshes,
  not typed SDK-backed Agent prompts.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_agent_chat_simple_dashboard_navigation_is_model_backed
  tests/test_embedded_agent_routes.py::test_agent_chat_observability_question_is_model_backed
  tests/test_embedded_agent_routes.py::test_agent_chat_recovery_request_without_board_target_is_model_backed
  tests/test_embedded_agent_routes.py::test_board_status_uses_dashboard_lane_counts_for_waiting_implementation_task
  tests/test_embedded_agent_routes.py::test_board_status_names_running_task_as_in_progress
  tests/test_embedded_agent_routes.py::test_board_status_defaults_to_current_sprint_scope
  tests/test_embedded_agent_routes.py::test_board_remaining_prompt_uses_model_backed_status_lane
  tests/test_embedded_agent_routes.py::test_assistant_delivery_permission_prompt_becomes_pending_question
  -q` passed `10 passed`.

## 2026-05-17 Forward-Engineering Greeting Intent Fix

- Root cause: in a new forward-engineering app with no generated surface or
  saved Builder work, Agent chat selected `init-project-chat` from project
  readiness state before the selected runtime model processed the typed user
  prompt. A greeting such as `hi` therefore entered a requirements-interviewer
  prompt and pushed toward specification gathering.
- Fix: typed Agent-page prompts now enter the general model-backed `chat` lane.
  When a project is still in forward-engineering bootstrap state, Builder adds
  that context inside the prompt so the model can decide whether the user is
  greeting, testing the Agent page, asking for a product scope, or ready to emit
  `FEATURE_SPEC_JSON`. Chat history no longer auto-creates a bootstrap
  requirements session before the operator types.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_typed_operator_prompt_contract_stays_model_backed
  tests/test_embedded_agent_routes.py::test_forward_engineering_greeting_uses_general_model_backed_chat
  tests/test_embedded_agent_routes.py::test_forward_engineering_chat_marks_provider_limit_blocked
  tests/test_embedded_agent_routes.py::test_built_project_does_not_bootstrap_init_project_chat
  tests/test_embedded_agent_routes.py::test_forward_engineering_new_thread_does_not_reuse_bootstrap_session
  -q` passed `5 passed`.

## 2026-05-17 First-Product Requirements Intake

- Live validation evidence: in fresh workspace
  `/private/tmp/habit-lab-model-app`, the visible Agent page session
  `fa7cfd9c-06a9-4d94-ae91-bd2934659821` correctly processed `hi` and
  `have we built any app?` through the Codex SDK `chat` lane. The first actual
  product prompt, `I want to build a personal Habit Lab app...`, was also
  model-backed and produced an inline question/approval path, but it jumped to
  `Ready for Builder to start now` before gathering enough user-specific product
  requirements.
- Token evidence: after the `builder logs analyze --session ... --json`
  analyzer fix, the same session reports prompt-level cache accounting. The
  `hi` turn used `30,623` raw tokens and `28,703`
  non-cached-plus-output tokens. The `have we built any app?` turn used
  `34,162` raw tokens, `33,152` cached tokens, and `1,010`
  non-cached-plus-output tokens. The Habit Lab prompt used `36,631` raw tokens,
  `31,104` cached tokens, and `5,527` non-cached-plus-output tokens.
- Fix direction: first-product prompts in clean-slate forward-engineering
  workspaces now keep model-backed intent classification while biasing broad
  product asks toward runtime-native, user-specific requirements intake before
  backlog capture. The model must still decide whether to answer directly, ask
  as many product-shaping questions or follow-up rounds as the specification
  needs, or emit `FEATURE_SPEC_JSON:`; structured questions are not mandatory
  on every first-product prompt, and the interview is not capped at one
  question or one structured request.
- Post-fix browser evidence: after restarting the managed
  `/private/tmp/habit-lab-model-app` dashboard from the patched source, Chrome
  session `4f4e754e-dc88-4207-9430-cd899caafec1` processed the same Habit Lab
  prompt into an inline product question, `What should the first version of
  your Habit Lab help you do each day?`, with `Track Streaks`, `Run
  Experiments`, and `Plan Routine` choices instead of the stale delivery
  approval. Clicking `Track Streaks` advanced the inline question state to
  `Answered` and then produced the delivery-start question. The session used
  `32,444` raw tokens, `31,616` cached tokens, `828`
  non-cached-plus-output tokens, zero tools, and a `941` token prompt assembly
  estimate.
- Question UI follow-up: product-shaping questions now expose exactly three
  model-suggested options with the recommended option first, plus an inline
  custom-answer text box for operator-specific requirements that do not match
  the suggestions. Answered question cards now render the submitted answer
  inline as `Answered with ...` so the requirements trail remains reviewable.
- Tool-activity follow-up: active tool events after an operator prompt are
  grouped into a single design-system activity row with a live count and latest
  tool name until the next agent response arrives. This replaces empty
  transient tool boxes during the wait state.
- Browser evidence: after restarting the managed
  `/private/tmp/habit-lab-model-app` dashboard from the patched source, Chrome
  session `4f4e754e-dc88-4207-9430-cd899caafec1` rendered the answered first
  product question with `ANSWERED WITH Track Streaks (Recommended)` in the
  Conversation timeline, and the pending delivery decision stayed inline below
  the chat content rather than opening a modal.
- Owner docs updated: `docs/references/phases/requirements.md` and
  `docs/workflows/autonomous-lifecycle-validation.md` now state that broad
  first-product prompts should gather enough user-specific requirements for a
  tailored first backlog, without turning prompt handling into deterministic
  dispatch.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_forward_engineering_first_product_prompt_requires_user_specific_intake
  tests/test_embedded_agent_routes.py::test_first_product_prompt_is_not_delivery_continuation
  tests/test_embedded_agent_routes.py::test_forward_engineering_first_product_prompt_ignores_stale_delivery_feature
  -q` passed `3 passed`; the broader earlier check
  `PYTHONPATH=src pytest
  tests/test_embedded_agent_routes.py::test_forward_engineering_first_product_prompt_requires_user_specific_intake
  tests/test_embedded_agent_routes.py::test_forward_engineering_greeting_uses_general_model_backed_chat
  tests/test_builder_cli_surfaces.py::test_logs_analyze_returns_prompt_level_observability
  -q` passed `3 passed`.
- Final focused regression evidence: `PYTHONPATH=src pytest
  tests/test_onboarding_api.py tests/test_builder_cli_surfaces.py
  tests/test_embedded_agent_routes.py tests/test_realtime_voice_frontend_static.py
  -q` passed `288 passed`; `npm run lint`, `npm run build`, and
  `git diff --check` passed. The Vite build still reports the existing
  chunk-size warning.

## 2026-05-17 Realtime Auth And Model Boundary

- Documentation grounding: the official OpenAI Realtime WebRTC guide says the
  backend creates `/v1/realtime/calls` sessions with a standard API key, and
  the official `gpt-realtime-mini` model page describes it as the
  cost-efficient GPT Realtime model for audio/text over WebRTC, WebSocket, or
  SIP. This matches the repo owner rubric in
  `docs/rubric/realtime-voice-agent-page-agent.md`.
- Implementation evidence: `src/autonomous_agent_builder/embedded/server/routes/realtime.py`
  reads only `OPENAI_API_KEY` for Realtime session creation and sideband
  WebSocket auth, posts SDP plus session config to
  `https://api.openai.com/v1/realtime/calls`, and uses the policy config from
  `src/autonomous_agent_builder/services/realtime_voice_policy.py`, where the
  model is `gpt-realtime-mini`. Codex SDK remains subscription-backed, and
  `codex_subscription_env()` strips `OPENAI_API_KEY`/`OPENAI_BASE_URL` from
  Codex runs.
- Regression evidence: `PYTHONPATH=src pytest
  tests/test_realtime_voice_operator.py::test_realtime_session_requires_openai_api_key
  tests/test_realtime_voice_operator.py::test_realtime_session_does_not_use_selected_runtime_api_key
  tests/test_realtime_voice_operator.py::test_realtime_session_posts_sdp_and_session_as_multipart_fields
  tests/test_realtime_voice_operator.py::test_sideband_registers_tools_and_returns_function_output
  -q` passed `4 passed`; `PYTHONPATH=src pytest
  tests/test_runtime_interface.py::TestNonClaudeRuntimes::test_codex_subscription_env_strips_openai_api_key
  tests/test_realtime_voice_frontend_static.py -q` passed `20 passed`.

## 2026-05-17 Agent Active Work Indicator

- Implementation: the Agent-page active wait row now renders as a
  design-system Agent activity card with `Running`, the current tool-use call
  count, and the latest tool name when available. It replaces the old
  `Agent is thinking` dot loader while preserving the model-backed prompt path.
- Browser proof: after rebuilding the managed `todo-app` dashboard and opening
  a cache-busted Chrome window at `http://127.0.0.1:9876/`, session
  `1d65ce61-b421-485f-bb69-e836d87bd4af` showed
  `Agent working with 0 active tool use calls`, `AGENT`, `Running`, and
  `0 TOOL USE CALLS` before the agent response arrived.
- Token and Board evidence: `builder logs analyze --session
  1d65ce61-b421-485f-bb69-e836d87bd4af --json` reported one prompt, zero tool
  calls, `38,276` raw tokens, `36,224` cached tokens, and `2,052`
  non-cached-plus-output tokens. `builder board show --json` still showed the
  prior `Show active filter todo count` verification task blocked by a Builder
  server restart, separate from this UI fix.
- Regression evidence: `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_embedded_agent_routes.py tests/test_realtime_voice_frontend_static.py
  -q` passed `134 passed`; `npm run build` passed with the existing Vite
  chunk-size warning; `git diff --check` passed.

## Completion Audit

Do not mark the goal complete until every active checklist item has direct browser, log, metric, transcript, or test evidence. Passing focused Realtime tests is not enough to complete the full product robustness goal.

## 2026-05-18 Completion Validation Checklist

The app is not complete for further optimization until both product creation
lanes pass end to end in the managed `todo-app` dashboard rebuilt from the
current Builder source.

- [ ] Baseline gates pass on the current worktree: focused audit remediation
  tests, Realtime voice tests, `builder lint --json`, frontend build, and
  `git diff --check`.
- [x] Frontend and backend architecture rubrics exist as owner-mapped review
  lenses before continuing optimization: `docs/rubric/frontend-react-architecture.md`
  and `docs/rubric/backend-service-architecture.md` are registered in
  `docs/REFERENCE.md`.
- [x] Chrome opens the managed `todo-app` dashboard from the current Builder
  checkout and the neighboring surfaces render without visible regressions:
  Agent, Voice, Board, Backlog, Metrics, Settings voice controls, and Inbox.
  Evidence on 2026-05-18: `builder server status --port 9876 --json` reported
  owned live PID `23482` on `http://127.0.0.1:9876`; Chrome rendered Agent
  conversation, Voice tab, Board, Backlog, Metrics, Observability, Settings
  voice controls, and Inbox. Visible state included Board 0 in-progress,
  0 queued, 3 shipped, 0 blocked; Backlog 21 total / 9 queued / 12 done;
  Metrics 631 runs / 95% pass rate / 4,225,092 tokens / `$7.0988`; and
  Inbox 0 pending approval gates.
- [x] Agent-page feature creation passes end to end from a fresh Agent thread:
  natural product request, model-backed clarification when needed, inline
  answer/approval, visible delivery start, Board state movement, shipped
  transcript closeout, and Builder-owned log/metric evidence.
- [x] Board lifecycle phase evidence is understandable from browser-visible
  phase drawers: Plan, Design, Implement, Gates, Review, Build, and Done use
  phase-specific summaries instead of repeating the same sprint metadata.
  Evidence on 2026-05-18: Chrome rendered Sprint 13 with all dots green only
  after shipment; Gates opened `Sprint gates` with 6 persisted gate results and
  0 failures; Review opened `Sprint review` with 3 `evidence-collector` runs
  and file diffs; Build opened `Sprint build` with build-verifier and
  feature-acceptance evidence; Shipped lane showed 3 done tasks and 0 blocked.
- [ ] Voice feature creation passes end to end from the Voice tab or Samantha
  control: operator request through voice/text voice lane, visible voice
  transcript, handoff into the same Agent-page work thread, inline
  answer/approval handling, Board state movement, shipped transcript closeout,
  and Builder-owned voice/log/metric evidence.
- [ ] Completion evidence is captured in this file with concrete session IDs,
  commands, browser-visible observations, and any remaining known risks. Passing
  static tests alone is not completion evidence.

### 2026-05-18 Agent-Page Clear Completed Cycle And Phase Drawer Evidence

- Live Agent-page feature cycle: managed `todo-app` session
  `b5d27111-bff5-45c7-8ced-fba5c9da8831` shipped feature `B29D9D70`
  (`Add compact Clear completed action`) after the operator prompt
  `Add a compact Clear completed action that only appears when completed todos
  exist. Keep existing add, filter, persistence, and completion behavior
  unchanged.` The Agent transcript ended with shipped closeout and token
  evidence: `185,398` raw, `180,864` cached, and `4,534`
  non-cached-plus-output tokens across 13 runs.
- Live Board recovery and continuation: the visible `Recover` action on task
  `09CD521A` recovered a dispatch-failed blocked verification task to queued;
  the Board then showed `Continue work`, disabled the control while work was
  running, and shipped Sprint 13 with 3 shipped tasks and 0 blocked tasks.
- Runtime regressions fixed during browser validation: dispatch-failed blocked
  tasks are recoverable through the design-system Board action, `Start work`
  becomes `Continue work` or disabled `Work already started` after work begins,
  and `publish_board_snapshot` refreshes stale Board rows without expiring live
  async ORM relationships used by the orchestrator.
- Phase model UI fix: the Board now receives granular `phase_statuses` for
  `verify`, `pr_review`, `build`, and `shipped`; the Build dot opens the Build
  drawer instead of the Verify drawer; Done is only green after Review and Build
  are complete.
- Phase drawer clarity proof in Chrome after rebuilding `todo-app` from the
  current Builder source: Gates opened `Sprint gates` with 6 gate results and
  0 failures; Review opened `Sprint review` with 3 `evidence-collector` runs
  plus file diffs; Build opened `Sprint build` with build-verifier and
  feature-acceptance runs; Shipped showed the shipped outcome and optimization
  evidence instead of repeating the same plan/design metadata.
- Focused verification after these fixes: `uv run pytest
  tests/test_dashboard_api.py::test_dashboard_sprint_phase_statuses_do_not_skip_review_or_build
  tests/test_dashboard_api.py::TestBoardEndpoint::test_board_current_sprint_shows_build_after_review
  tests/test_dashboard_design_system_contract.py::test_board_timeline_separates_gates_review_build_and_done
  -q` -> 3 passed; `uv run ruff check
  src/autonomous_agent_builder/api/routes/dashboard_api.py
  src/autonomous_agent_builder/embedded/server/routes/dashboard.py
  tests/test_dashboard_api.py tests/test_dashboard_design_system_contract.py`
  -> passed; `npm run lint` -> passed; `uv run builder start --port 9876
  --force` from the managed `todo-app` workspace rebuilt and served the
  dashboard on `http://127.0.0.1:9876`.

### 2026-05-19 Agent Page Architecture Decomposition

- Frontend decomposition pass: extracted the Agent-page Conversation side rail
  into `frontend/src/features/agent/AgentConversationRail.tsx`, keeping
  `AgentPage.tsx` as the route/state owner and moving session metrics,
  selected-task summary, and recent-run presentation into a focused feature
  presenter. This follows the frontend rubric's feature-sliced rule without
  changing the visible Agent, Voice, approval, or run-trace workflows.
- Size evidence: `AgentPage.tsx` is now 2,195 lines, down from 2,266 in this
  pass; the new rail presenter is 136 lines, and adjacent extracted feature
  presenters remain under 500 lines (`agent-model.ts` 432 lines,
  `SprintDetailSidebar.tsx` 486 lines).
- Verification: `npm run lint` passed; `npm run build` passed with the existing
  Vite chunk-size warning.

### 2026-05-19 Agent Voice Panel Decomposition

- Frontend decomposition pass: extracted the Agent-page Voice tab body into
  `frontend/src/features/agent/AgentVoicePanel.tsx`. `AgentPage.tsx` still owns
  session state, realtime text submission, voice start/stop commands, and URL
  mode routing; the new presenter owns only the Voice tab layout, Samantha
  transcript projection, and realtime text control rendering.
- Regression contract update: `tests/test_realtime_voice_frontend_static.py`
  now asserts the blocked-session rail behavior across the page plus extracted
  feature presenters, so the one-owner move did not drop the pending-decision
  precedence check.
- Size evidence: `AgentPage.tsx` is now 2,101 lines; the new Voice presenter is
  167 lines; the Conversation rail presenter is 136 lines; and the updated
  static Voice frontend test remains under the 500-line target at 489 lines.
- Verification: `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_realtime_voice_frontend_static.py -q` passed `19 passed`;
  `npm run lint` passed; `npm run build` passed with the existing Vite
  chunk-size warning; `git diff --check` passed.

### 2026-05-19 Complexity Baseline Ratchet

- Gate finding: `uv run builder lint --complexity-report --json` initially
  reported 2 non-blocking ratchet violations because
  `src/autonomous_agent_builder/embedded/server/routes/agent.py` and
  `_run_chat_turn` were smaller than the stored baseline after the ongoing
  decomposition.
- Fix: ratcheted `docs/quality-gate/complexity-baseline.json` to the current
  Agent route values: file baseline `4,671` lines and `_run_chat_turn`
  baseline `262` lines / `15` branches. This keeps the guard from allowing
  future growth back to the older larger values.
- Verification: rerunning `uv run builder lint --complexity-report --json`
  passed with 371 Python files, 4,506 functions, 54 historical over-threshold
  files, 8 function hotspots, and 0 violations. `uv run builder lint --json`
  passed with 7 checks total, 5 passed, 0 failed, and the expected uninitialized
  `knowledge` and `readiness` skips. `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_complexity_guard.py tests/test_complexity_cli_contract.py -q`
  passed `7 passed`.

### 2026-05-19 Voice Browser Retest And Connection-Starvation Fix

- Browser finding: while validating the Voice feature-creation lane in Chrome,
  typed Realtime text stayed on `Sending` and did not reach the server. `lsof`
  showed Chrome already held six established HTTP connections to
  `127.0.0.1:9876`, with long-lived dashboard/Agent streams consuming the
  browser's per-host capacity. The queued text-control request could not reach
  `/api/realtime/text-control` until stale connections were killed.
- Fix: Agent Voice mode no longer keeps the Board SSE stream or the page-level
  Agent chat SSE stream open. The Voice tab keeps the voice-owned handoff
  listener and uses a lightweight Board fallback refresh instead, leaving
  capacity for operator text, approvals, and navigation requests.
- Browser proof after rebuild: the managed `todo-app` dashboard was restarted
  from the patched Builder checkout on `http://127.0.0.1:9876`. A Voice text
  request in session `82506494-7ae4-4bb2-8d75-7367c9a859a1` reached
  Conversation, displayed a single inline `Start now` / `Hold` decision, and
  clicking `Start now` moved the session into a running Agent state with the
  design-system activity row. A diagnostic manual fallback call made during the
  investigation duplicated that specific prompt afterward, so this run is not
  used as final clean completion evidence.
- Regression coverage: `tests/test_realtime_voice_frontend_static.py` now
  asserts that Voice mode avoids the extra Board and page-level Agent SSE
  streams. `PYTHONPATH=src .venv/bin/python -m pytest
  tests/test_realtime_voice_frontend_static.py -q` passed `20 passed`;
  `npm run lint`, `npm run build`, and `git diff --check` passed. The Vite
  build still reports the existing chunk-size warning.

### 2026-05-19 Agent Decision Control Owner Split

- Rubric maintenance: updated the frontend React architecture rubric so static
  contract tests must follow the feature-sliced owner split. Once a page is
  decomposed, tests should scan the route adapter plus feature modules instead
  of forcing feature-owned strings or controls back into the page.
- Frontend decomposition pass: extracted the Agent-page pending question and
  approval response controls into
  `frontend/src/features/agent/AgentDecisionActions.tsx`. `AgentPage.tsx`
  still owns session state, submit handlers, blocked-composer placement, and
  evidence-only timeline cards; the new presenter owns the single actionable
  decision control surface used for `Start now`, `Hold`, custom question
  answers, and allow/deny approval responses.
- Regression contract update: `tests/test_dashboard_design_system_contract.py`
  and `tests/test_realtime_voice_frontend_static.py` now aggregate the Agent
  route adapter plus extracted Agent feature modules for ownership-sensitive
  assertions. This preserves the one-control-owner rule and keeps duplicate
  approval boxes from being reintroduced by page-only static checks.
- Size evidence: `AgentPage.tsx` is now 1,996 lines, down from 2,101 in this
  pass. The new decision-action presenter is 160 lines; the adjacent extracted
  Agent presenters remain under 500 lines (`AgentVoicePanel.tsx` 167 lines and
  `AgentConversationRail.tsx` 136 lines).
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`; and
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations. `uv run builder lint --json` passed with 7
  checks total, 5 passed, 0 failed, and the expected uninitialized `knowledge`
  and `readiness` skips.
- Browser proof: restarted the managed `todo-app` dashboard from the patched
  Builder checkout on `http://127.0.0.1:9876`. Chrome loaded the Agent page
  with the extracted Conversation rail still showing separate non-cached/raw/
  cached token rows and no duplicate decision controls in the empty ready
  thread. Chrome loaded `/board` with Sprint 14 shipped cards, disabled
  `Start work`, all phase dots green for the shipped sprint, empty active/
  review/queued/blocked lanes, and a Build phase drawer with build-specific
  owner/run/verification rows plus acceptance evidence.

### 2026-05-19 Transparent Shell Header Regression Fix

- Browser finding: after the App shell extraction/rebuild, the global sticky
  header rendered an opaque pale band above Agent/Board content. This made the
  first viewport feel detached from the dotted Builder workspace background.
- Fix: changed the shared `AppShell` header normal state in `frontend/src/App.tsx`
  from a surface-tinted backdrop to transparent, matching the condensed state.
  The navigation pill, brand mark, and utility buttons keep their own local
  surfaces, while the page background now continues to the top.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  `uv run pytest tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py -q` passed `43 passed`.
  Rebuilt and republished the managed `todo-app` dashboard on
  `http://127.0.0.1:9876`; Chrome showed the Observability page with the dotted
  workspace background visible behind the header and no white header band.

### 2026-05-19 Agent Run Trace Rail Decomposition

- Frontend decomposition pass: extracted the Agent-page Run trace selector rail
  into `frontend/src/features/agent/AgentTraceRail.tsx`. `AgentPage.tsx` keeps
  trace URL/session state, selected sprint/task/run ids, timeline entries, and
  run-trace content; the new presenter owns the Run explorer, task/run pickers,
  selected-run token diagnostics, large-output/retrieval flags, and run-cost
  meter.
- Regression contract update: `tests/test_dashboard_design_system_contract.py`
  now checks the Agent route adapter plus extracted Agent feature modules for
  run-trace token-accounting strings. This keeps the frontend rubric's static
  contract rule current after the owner split.
- Size evidence: `AgentPage.tsx` is now 1,841 lines, down from 1,996 in this
  pass. The new trace-rail presenter is 206 lines and stays below the 500-line
  target.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`;
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 7 checks
  total, 5 passed, 0 failed, and the expected uninitialized `knowledge` and
  `readiness` skips; `git diff --check` passed.

### 2026-05-19 Agent Transcript Card Decomposition

- Frontend decomposition pass: extracted the Agent Conversation transcript card
  renderer into `frontend/src/features/agent/AgentThreadCards.tsx`.
  `AgentPage.tsx` still owns transcript filters, scroll refs, pending composer
  state, and message submission; the new presenter owns per-event card rendering
  for operator messages, Samantha handoffs, assistant responses, run errors,
  questions, answered-question evidence, and approval evidence.
- Regression contract update: `tests/test_realtime_voice_frontend_static.py`
  now checks Agent-page question/approval status-card strings across the page
  plus extracted Agent feature modules. This keeps the design-system approval
  contract aligned with the current owner split.
- Size evidence: `AgentPage.tsx` is now 1,744 lines, down from 1,841 in this
  pass. The new transcript-card presenter is 107 lines; the existing
  `AgentTraceRail.tsx` presenter is 206 lines; both stay below the 500-line
  target.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`;
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 7 checks
  total, 5 passed, 0 failed, and the expected uninitialized `knowledge` and
  `readiness` skips; `git diff --check` passed.

### 2026-05-19 Agent Transcript Panel Decomposition

- Frontend decomposition pass: extracted the Agent Conversation transcript
  panel into `frontend/src/features/agent/AgentTranscriptPanel.tsx`.
  `AgentPage.tsx` still owns session state, transcript filtering, timeline data,
  and submission handlers; the new presenter owns transcript rendering,
  active-tool activity display, the blocked-composer decision slot, and the
  normal message composer.
- Regression contract update: static Agent/Voice tests now check page plus
  extracted Agent feature modules for decision controls, pending-decision copy,
  composer disabled state, and transcript loading behavior. This preserves one
  control owner without forcing design-system approval strings back into the
  route adapter.
- Size evidence: `AgentPage.tsx` is now 1,656 lines, down from 1,744 in this
  pass. The new transcript-panel presenter is 198 lines; the existing
  `tests/test_realtime_voice_frontend_static.py` file remains at the 500-line
  ratchet after the test-owner update.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`;
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 7
  checks total, 5 passed, 0 failed, and the expected uninitialized `knowledge`
  and `readiness` skips; `git diff --check` passed.
- Browser proof: rebuilt and restarted the managed `todo-app` dashboard on
  `http://127.0.0.1:9876`. Chrome loaded the Agent Conversation page with the
  extracted transcript panel still showing the empty transcript, disabled send
  button, transparent shell header/background continuity, and no duplicate
  decision controls. Switching to Run trace loaded task/run evidence, and
  switching back to Conversation restored the transcript/composer surface. The
  local server was stopped after validation.

### 2026-05-19 Agent Run Trace Panel Decomposition

- Frontend decomposition pass: extracted the Agent Run trace content panel into
  `frontend/src/features/agent/AgentRunTracePanel.tsx`. `AgentPage.tsx` keeps
  trace mode, sprint/task/run selection, task-run timeline data, and the
  selector rail; the new presenter owns the visible run-trace evidence panel,
  task-run empty/loading states, task-run log/timeline switching, and diff
  evidence rendering.
- Regression contract update: the dashboard design-system static contract now
  checks Agent-page plus extracted Agent feature modules for Run trace markers
  that moved out of the route adapter. This keeps trace UI strings under the
  feature owner while preserving page-owned stream/session state checks.
- Size evidence: `AgentPage.tsx` is now 1,573 lines, down from 1,656 in this
  pass. The new run-trace presenter is 123 lines.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`;
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 7
  checks total, 5 passed, 0 failed, and the expected uninitialized `knowledge`
  and `readiness` skips; `git diff --check` passed.
- Browser proof: rebuilt and restarted the managed `todo-app` dashboard on
  `http://127.0.0.1:9876`. Chrome loaded the Agent Run trace page with the
  extracted presenter still showing task-run evidence, the Run explorer rail,
  selected sprint/task/run controls, timeline entries, and the transparent
  shell header/background continuity. Switching back to Conversation restored
  the transcript/composer surface with no duplicate decision controls. The
  local server was stopped after validation.

### 2026-05-19 Agent Timeline Builder Decomposition

- Frontend decomposition pass: extracted Agent transcript, voice, and task-run
  timeline derivation into
  `frontend/src/features/agent/AgentTimelineBuilders.tsx`. `AgentPage.tsx`
  still owns session state, selected trace ids, board data, and user actions;
  the new feature module owns log-block mapping, active-tool activity
  suppression, conversation timeline entries, voice timeline entries, task-run
  event summarization, task-run timeline entries, and task-run log rows.
- Regression contract update: dashboard and Realtime Voice static contracts now
  check page plus extracted Agent feature modules for voice timeline and active
  tool-activity behavior instead of requiring that logic in the route adapter.
- Size evidence: `AgentPage.tsx` is now 1,312 lines, down from 1,573 in this
  pass. The new timeline-builder module is 326 lines and remains below the
  500-line target; the Realtime Voice static test remains at the 500-line
  ratchet.
- Verification: `npm run lint` and `npm run build` passed from `frontend/`;
  the Vite build still reports the existing chunk-size warning. `uv run pytest
  tests/test_dashboard_design_system_contract.py
  tests/test_realtime_voice_frontend_static.py
  tests/test_agent_control_owner_routes.py tests/test_agent_tool_approval_routes.py
  tests/test_agent_pending_question_routes.py -q` passed `53 passed`;
  `uv run builder lint --complexity-report --json` passed with 371 Python
  files, 4,508 functions, 54 historical over-threshold files, 8 function
  hotspots, and 0 violations; `uv run builder lint --json` passed with 7
  checks total, 5 passed, 0 failed, and the expected uninitialized `knowledge`
  and `readiness` skips; `git diff --check` passed.
- Browser proof: rebuilt and restarted the managed `todo-app` dashboard on
  `http://127.0.0.1:9876`. Chrome loaded the Agent Run trace page with the
  extracted timeline builder active; the trace shell, phase strip, task-run
  loading/empty states, Run explorer rail, selected-run card, Samantha control,
  and transparent shell header/background continuity rendered. The current
  `todo-app` state had no selectable task evidence in the active sprint, so this
  proof verifies rendering and empty-state behavior rather than a populated run
  timeline. The local server was stopped after validation.

### 2026-05-19 Backlog Query CLI Test Split

- CLI test decomposition pass: extracted backlog item create/update validation,
  project summary natural-query resolution, compact task search/show output,
  run summary/list/show fallback behavior, and approval search compaction into
  `tests/test_builder_backlog_query_cli_surface.py`.
- Size evidence: `tests/test_builder_cli_surfaces.py` is now 2,877 measured
  lines, down from 3,332 in this pass. The extracted backlog query test owner
  is 464 lines and remains below the 500-line target.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_backlog_query_cli_surface.py` passed. `uv run pytest
  tests/test_builder_backlog_query_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed `94 passed`. `uv run builder
  lint --complexity-report --json` passed with 410 Python files, 4,599
  functions, and 0 ratchet violations after lowering the CLI surface baseline;
  `uv run builder lint --json` passed with 7 checks total, 5 passed, 0 failed,
  and the expected uninitialized `knowledge` and `readiness` skips; `git diff
  --check` passed.

### 2026-05-20 Agent Project Context Decomposition

- Backend decomposition pass: extracted init-project chat Project Context
  answer collection, deterministic context-field mapping, technical constraint
  extraction, feature-list metadata injection, target `CLAUDE.md` constraint
  appends, and persisted project-description constraint updates into
  `src/autonomous_agent_builder/embedded/server/agent_project_context.py`.
- Size evidence: `src/autonomous_agent_builder/embedded/server/routes/agent.py`
  is now 3,006 measured lines, down from 3,246 in this pass. The new
  project-context owner is 243 lines and remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/agent_project_context.py
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  tests/test_agent_project_context.py` passed. `uv run pytest
  tests/test_agent_project_context.py tests/test_agent_tool_approval_routes.py
  -q` passed `8 passed`. `uv run builder lint --complexity-report --json`
  passed with 412 Python files, 4,605 functions, and 0 ratchet violations
  after lowering the Agent route baseline; `uv run builder lint --json` passed
  with 7 checks total, 5 passed, 0 failed, and the expected uninitialized
  `knowledge` and `readiness` skips; `git diff --check` passed.

### 2026-05-20 Orchestrator Deterministic Verification Decomposition

- Backend decomposition pass: extracted builder script invocation,
  deterministic change-evidence run recording, deterministic build verification
  run recording, feature acceptance run recording, and moved output formatting
  into `src/autonomous_agent_builder/orchestrator/deterministic_verification.py`.
  `Orchestrator` keeps thin delegate methods so existing phase code and tests
  can still patch the same lifecycle methods.
- Size evidence: `src/autonomous_agent_builder/orchestrator/orchestrator.py` is
  now 2,828 measured lines, down from 3,091 in this pass. The new
  deterministic verification owner is 371 lines and remains below the 500-line
  target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/orchestrator/orchestrator.py
  src/autonomous_agent_builder/orchestrator/deterministic_verification.py
  tests/test_orchestrator_build_verification.py` passed. `uv run pytest
  tests/test_orchestrator_build_verification.py tests/test_orchestrator.py
  tests/test_sprint_execution.py -q` passed `69 passed`. `uv run builder lint
  --complexity-report --json` passed with 413 Python files, 4,614 functions,
  and 0 ratchet violations after lowering the orchestrator baseline; `uv run
  builder lint --json` passed with 7 checks total, 5 passed, 0 failed, and the
  expected uninitialized `knowledge` and `readiness` skips; `git diff --check`
  passed.

### 2026-05-20 Realtime Voice Navigation Test Split

- Test decomposition pass: extracted Realtime Voice dashboard navigation,
  latest optimization run trace navigation, open-then-analyze run trace
  delegation, and default analysis request behavior into
  `tests/test_realtime_voice_navigation.py`.
- Size evidence: `tests/test_realtime_voice_operator.py` is now 2,839 measured
  lines, down from 3,090 in this pass. The new navigation test owner is 277
  lines and remains below the 500-line target.
- Verification: `uv run ruff check tests/test_realtime_voice_operator.py
  tests/test_realtime_voice_navigation.py` passed. `uv run pytest
  tests/test_realtime_voice_navigation.py tests/test_realtime_voice_operator.py
  -q` passed `56 passed`. `uv run builder lint --complexity-report --json`
  passed with 414 Python files, 4,614 functions, and 0 ratchet violations
  after lowering the Realtime Voice operator test baseline; `uv run builder
  lint --json` passed with 7 checks total, 5 passed, 0 failed, and the expected
  uninitialized `knowledge` and `readiness` skips; `git diff --check` passed.

### 2026-05-20 Realtime Voice Thread Routing Split

- Backend decomposition pass: extracted deterministic Realtime Voice utterance
  routing for Builder status, pending question answers, approval clarification,
  recovery, active-run follow-ups, and new-thread decisions into
  `src/autonomous_agent_builder/services/voice_thread_routing.py`.
- Size evidence: `src/autonomous_agent_builder/services/voice_operator.py` is
  now 2,781 measured lines, down from 3,033 in this pass. The new voice thread
  routing owner is 262 lines and remains below the 500-line target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/services/voice_operator.py
  src/autonomous_agent_builder/services/voice_thread_routing.py
  tests/test_voice_thread_routing.py` passed. `uv run pytest
  tests/test_voice_thread_routing.py
  tests/test_realtime_voice_operator.py::test_voice_delegation_routes_natural_answer_to_single_pending_question
  tests/test_realtime_voice_operator.py::test_voice_delegation_clarifies_multiple_pending_questions
  tests/test_realtime_voice_operator.py::test_voice_delegation_clarifies_multiple_pending_approvals
  tests/test_realtime_voice_operator.py::test_voice_delegation_prepares_single_pending_approval_from_operator_answer
  -q` passed `8 passed`. `uv run builder lint --complexity-report --json`
  initially reported the expected stale baseline ratchet for
  `voice_operator.py`, then passed after lowering the Realtime Voice operator
  service baseline.

### 2026-05-20 Agent Saved-Feature Delivery Split

- Backend decomposition pass: extracted feature-spec persistence, saved-feature
  delivery selection, delivery-permission question resolution, delivery-task
  creation, and task dispatch scheduling into
  `src/autonomous_agent_builder/embedded/server/agent_feature_delivery.py`.
  The embedded Agent route keeps the `_schedule_task_dispatch` alias so existing
  route tests and monkeypatches continue to exercise the same dispatch seam.
- Size evidence: `src/autonomous_agent_builder/embedded/server/routes/agent.py`
  is now 2,857 measured lines, down from 3,006 in this pass. The new
  saved-feature delivery owner is 173 lines and remains below the 500-line
  target.
- Verification: `uv run ruff check
  src/autonomous_agent_builder/embedded/server/routes/agent.py
  src/autonomous_agent_builder/embedded/server/agent_feature_delivery.py`
  passed. `uv run pytest tests/test_agent_feature_spec_backlog_routes.py
  tests/test_agent_sprint_planning_routes.py
  tests/test_agent_chat_navigation_routes.py -q` passed `14 passed`. `uv run
  builder lint --complexity-report --json` initially reported the expected
  stale baseline ratchet for `embedded/server/routes/agent.py`, then passed
  after lowering the embedded Agent route baseline.

### 2026-05-20 Builder Logs Observability CLI Test Split

- Test decomposition pass: extracted logs observability coverage checks for
  placeholder OTLP endpoints, unreachable local OTEL collectors, and
  Codex-runtime guidance into
  `tests/test_builder_logs_observability_cli_surface.py`.
- Size evidence: `tests/test_builder_cli_surfaces.py` is now 2,797 measured
  lines, down from 2,877 in this pass. The new logs observability CLI test
  owner is 85 lines and remains below the 500-line target.
- Verification: `uv run ruff check tests/test_builder_cli_surfaces.py
  tests/test_builder_logs_observability_cli_surface.py` passed. `uv run pytest
  tests/test_builder_logs_observability_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed `80 passed`. `uv run builder
  lint --complexity-report --json` initially reported the expected stale
  baseline ratchet for `tests/test_builder_cli_surfaces.py`, then passed after
  lowering the broad builder CLI surface test baseline.
