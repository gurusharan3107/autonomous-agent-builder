# Design Progress

## 2026-05-12

- Completed: removed the duplicate shell Design drawer so appearance tuning is owned by Settings only.
- Completed: wired Board density to the persisted `boardDensity` runtime preference instead of hardcoding comfortable cards.
- Completed: renamed the Agent chat tab to `Conversation`; direct Agent entry now defaults to `Conversation` so direct typed chat starts in the operator transcript, with `Voice` and `Run trace` as sibling tabs.
- Completed: added a compact Run trace right rail with sprint selection, dense task rows, dense agent-run rows, and selected-run metrics.
- Completed: restored the Conversation right rail with session metadata, selected task context, and recent agent runs.
- Completed: unified the Agent page top header/control row across Conversation and Run trace, and replaced the selected task/run blue rail with a muted compact selection state.
- Superseded: do not manually copy dashboard bundles. Frontend source changes are published by running `builder start --port 9876` from the generated app workspace.
- Verified: `python scripts/check_dashboard_design_tokens.py --json`.
- Verified: `pytest tests/test_dashboard_design_system_contract.py tests/test_dashboard_api.py tests/test_embedded_dashboard_streams.py -q`.
- Verified: `builder quality-gate dashboard-ux --json`.
- Verified: `builder lint --json`.

Current audit:

- Verified again: `python scripts/check_dashboard_design_tokens.py --json`
  passed with no findings.
- Verified again: `pytest tests/test_dashboard_design_system_contract.py
  tests/test_dashboard_api.py tests/test_embedded_dashboard_streams.py -q`
  passed `49` tests.
- Verified again: `pnpm build` from `frontend/` succeeded. Vite still reports
  the app bundle is larger than the default 500 kB chunk warning threshold.
- Verified again: `builder quality-gate dashboard-ux --json`, `builder
  lint --json`, `git diff --check`, and `builder verify --changed --execute
  --json` passed for the current clean workspace.
- Fixed and verified: `pnpm lint` now exits cleanly after moving the
  `sprintTaskIds` object inside the `useMemo` that uses it.
- Fixed and verified: `workflow --docs-dir docs summary design-language` now
  resolves to `docs/design-docs/design-language.md`, matching the owner map and
  dashboard UX gate reference.
- Updated and verified: Agent default mode is now `Conversation` (`chat`) with a
  local-storage migration for browsers that saved the prior `Run trace`
  default. The current Chrome session opens Agent directly into `Conversation`
  after `builder start --port 9876` from `todo-app`.
- Voice preflight evidence: clicking `Start voice` in Chrome currently surfaces
  `Requested device not found`; no backend Realtime request was observed, so
  this pass is blocked by local audio-device availability rather than Realtime
  API setup.
- Needs route regression triage: the broader route suite
  `pytest tests/test_builder_tool_service.py tests/test_embedded_agent_routes.py
  tests/test_tool_registry.py tests/test_workspace_tools_runtime.py
  tests/test_definitions.py -q` currently reports `135 passed, 8 failed`.
  The failures cover runtime repair, sprint-planning phase transition,
  AskUserQuestion resume, Codex init question cards, and forward-engineering
  feature-list/provider-limit/new-thread behavior.

Remaining:

- Capture browser screenshots of live Board, Agent Conversation, Agent Run trace, and Settings after `builder start --port 9876`.
- Complete a visual reference-vs-live convergence pass against `/Users/gurusharan/Documents/remote-claude/active/apps/apps-design-system/Autonomous-agent-builder`.
- Validate the interactive voice/question/approval paths in the Conversation thread with live runtime evidence.
- Commit the Agent default-mode, hook-stability, design-language, and operator-rubric updates after validation.
- Fix or classify the 8 broader embedded Agent route failures before using the new Conversation/Run trace surface for final Realtime voice acceptance.
