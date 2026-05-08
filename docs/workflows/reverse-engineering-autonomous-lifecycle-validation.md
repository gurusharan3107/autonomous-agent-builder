# Reverse Engineering Autonomous Lifecycle Validation

## Overview

This workflow validates the full `reverse_engineering` path of
`autonomous-agent-builder` against a real external repository. It is the
canonical repo-local procedure for testing whether the product can take an
existing codebase from clone to readiness, onboarding, backlog generation, task
execution, and board-visible completion while preserving correct owner
boundaries and evidence.

Use this workflow when you need to:

- verify the reverse-engineering path against a real repo instead of fixtures alone
- reproduce a user-reported onboarding or task-execution failure in the `reverse_engineering` lane
- test the real operator flow through the dashboard and Agent chat page
- harden the product by fixing issues as they appear during a real autonomous run

This workflow is intentionally product-first. Reproduce the real user flow
through the running app, act like a normal product user, use `builder logs` as
the canonical first runtime evidence lane, and then fall back to
`builder metrics show --json --full` plus `builder backlog run summary/show`
when the log stream is sparse. Only drop to lower-level inspection when those
product-owned surfaces are not enough to localize the fault. The CLI boundary
and browser-tool selection rules are defined in
[dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md).

Hard rule:

- never use the `autonomous-agent-builder` repo itself as the reverse-engineering validation subject
- always validate the `reverse_engineering` path against a separate external repo clone
- self-hosting hides the planning, retrieval, and implementation-boundary faults this workflow is meant to expose

## Scope

This workflow covers:

- selecting a disposable external repo
- cloning it into a temp directory
- initializing builder in that repo
- launching the embedded server
- driving onboarding through the dashboard and Agent chat page
- confirming feature backlog generation
- starting feature implementation and tracking progress on the board
- monitoring logs and product state during execution
- fixing product issues in this repo as they are discovered
- rerunning the same external validation flow after each fix

This workflow does not assume success. If the product currently stops at an intermediate boundary, that boundary becomes the first defect to fix.

## When To Use

Run this workflow for:

- `reverse_engineering` onboarding regressions
- task dispatch or phase-routing failures after onboarding
- dashboard or Agent-page flows that appear wired but fail in real use
- claims that the reverse-engineering path supports end-to-end autonomous delivery
- release-candidate validation for onboarding, backlog, board, agent, and quality-gate surfaces

Do not use this workflow for:

- clean-slate repo onboarding only
- isolated unit-test authoring without real user-flow validation
- repo-local doc-only updates that do not affect the product path

## Owner Surfaces

- `builder` owns repo-local product state, runtime evidence surfaces, backlog, board, knowledge, memory, and quality-gate entrypoints.
- The dashboard and Agent chat page are the primary operator-facing validation surfaces.
- [dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md)
  owns the validation persona, allowed CLI boundary, and user-shaped prompt
  contract.
- `builder logs` is the canonical agent-facing runtime diagnosis lane.
- `workflow --docs-dir docs` owns supporting contracts and workflow documentation.
- Fixes belong in the smallest correct owner surface. Do not patch around a builder-owned product bug from a global control-plane surface.

## Preconditions

- `autonomous-agent-builder` repo is available locally and dependencies are installed.
- `builder` CLI resolves from this repo and can run `builder --json doctor`.
- Chrome DevTools MCP is available for browser validation.
- A disposable temp root is available for external repo clones.
- The chosen external repo does not require secrets or paid third-party services to reach a meaningful onboarding and implementation path.

## External Repo Selection Rules

Choose a repo that maximizes signal and minimizes unrelated noise.

Prefer:

- public repos
- small or medium codebases
- Python-first repos, because the current reverse-path docs and examples are strongest there
- repos with a clear entrypoint and visible feature surface
- repos that already have tests or at least an obvious implementation target

Avoid:

- the `autonomous-agent-builder` repo itself as the validation subject
- monorepos with heavy bootstrapping
- repos that require cloud credentials, API keys, or private package registries
- repos whose primary complexity is infrastructure rather than application behavior
- repos so small that feature extraction has nothing meaningful to seed

Selection checklist:

- [ ] Disposable clone is allowed
- [ ] Repo can be scanned locally without external credentials
- [ ] Repo has enough structure for KB extraction and feature discovery
- [ ] Repo is small enough to rerun repeatedly after fixes

## Evidence To Capture

Capture evidence at each stage so fixes are tied to observed behavior rather than assumptions.

Apply the dashboard-first rule throughout: after `builder init` and
`builder start`, lifecycle mutations must happen through the Agent page,
Backlog, Board, Inbox, or visible approval surfaces. CLI output is evidence,
not a substitute action path.

Current product note:

- treat `builder logs` as the first diagnosis lane, not the only one
- if `builder logs` returns no matching events but `builder agent history`, `builder metrics`, or `builder backlog run` shows real activity, record that as an observability gap instead of assuming the run lacked useful telemetry

Minimum evidence:

- chosen repo URL and clone path
- `builder --json doctor` output in the external repo
- `builder init` result
- selected-runtime guidance exists: `CLAUDE.md` for Claude or `AGENTS.md` for
  Codex; existing user-authored guidance was preserved
- `builder start` port and server reachability
- browser snapshots of onboarding, Agent chat, backlog, and board
- Inbox/approval snapshots for every human decision gate encountered
- `builder logs --error`
- `builder logs --info --compact --json`
- `builder logs analyze --session <id-or-prefix> --json`
- `builder metrics show --json --full`
- `builder backlog run summary <query> --json` or `builder backlog run show <run-id> --json`
- proof that no CLI command was used to create backlog items, queue tasks,
  dispatch work, or approve gates as a substitute for dashboard behavior
- whether `.agent-builder/agent_builder.db` exists in the external repo
- whether generated feature/backlog artifacts exist and are visible through product surfaces
- final workspace `git status --short` and staged diff summary for the task workspace
- exact failure point if the flow stops
- test rerun evidence after each fix
- repo-local `builder memory` entries created for reusable lessons from the run

## Validation Flow

### 1. Prepare The Builder Repo

From this repo:

1. Confirm repo health with `builder --json doctor`.
2. Read the dashboard-first validation contract.
3. Read the current reverse-engineering and onboarding testing docs in `builder knowledge`.
4. Start from the real product surface, not from code guesses.

If the builder repo already shows a known failing contract such as stale blocking KB docs, note it before starting but continue unless it directly blocks the flow.

### 2. Select And Clone An External Repo

1. Choose one candidate repo using the selection rules above.
2. Clone it into a disposable temp directory.
3. Record the exact clone path.
4. Do not use the builder repo itself as the external validation target.

Recommended pattern:

```bash
cd /tmp
git clone <repo-url> aab-reverse-validate
cd /tmp/aab-reverse-validate
```

### 3. Initialize Builder In The External Repo

Inside the cloned repo:

1. Run `builder --json doctor`.
2. Run `builder init` using the lightest non-interactive form that still exercises the real product path.
3. Confirm repo-local state is created under `.agent-builder/`.
4. Run `builder readiness status --json` and, if needed, `builder readiness assess --json`.
5. Record whether the repo is classified as `reverse_engineering`.

`builder init` and readiness commands are bootstrap and gate evidence. They do
not validate reverse-engineering delivery by themselves. The lifecycle starts
only when the dashboard and Agent page drive repo understanding, planning,
backlog, and execution.

Expected outcome:

- repo-local builder state exists
- target-repo Claude Agent SDK project guidance exists with
  `Mode: reverse_engineering`, deterministic command slots, preservation rules,
  validation rules, telemetry policy, and update rules
- root `.env` exists with runtime settings and safe telemetry defaults:
  selected runtime state is explicit, Claude native OTEL and Codex project-local
  OTEL health are distinguishable from runtime selection, builder active-DB
  telemetry remains the product source of truth, and no raw prompt/tool/body
  export flags are enabled
- the repo is not misclassified as clean-slate
- readiness reports `reverse_engineering` with a precise `state`, `next`, and
  any blocking reasons
- the product can proceed to onboarding only when readiness can reach
  `agent_ready`

Failure handling:

- If classification is wrong, inspect onboarding detection logic first.
- If repo-local state is missing, treat that as a product bug, not operator error.

### 4. Launch The Embedded Product

Inside the external repo:

1. Start the product with `builder start --port <port>`.
2. Keep the server running during the full validation pass.
3. Confirm the chosen port is listening.
4. Use `builder logs --error` and `builder logs --info --compact --json` as the first diagnosis lane if the UI behaves unexpectedly.

Expected outcome:

- the embedded product uses the external repo's local state
- the dashboard loads successfully
- runtime evidence is attributable to the external repo run, not the main builder workspace

### 5. Drive Onboarding Through The Real UI

Use Browser Use / in-app browser as the default validation surface when
available. Use Computer Use when the visible desktop-browser experience is the
evidence, and use Chrome DevTools MCP when console, network, accessibility-tree,
or screenshot evidence is needed for diagnosis.

1. Open the dashboard for the external repo server.
2. Capture an initial snapshot.
3. Start onboarding from the visible product controls.
4. Watch for classification, progress updates, and terminal readiness state.
5. Check console and network failures if the UI stalls or misreports state.

Expected outcome:

- onboarding progresses through the `reverse_engineering` path
- readiness reaches `agent_ready` only after repo scan, KB extract, and KB
  validate pass
- no clean-slate interview is substituted unless the repo truly requires it
- the UI reflects the real backend state

Do not rely on browser appearance alone. Correlate the UI with `builder logs`.

### 6. Use The Agent Chat Page To Produce A Feature Spec

From the Agent chat page in the external repo run:

1. start the conversation from the actual product surface
2. provide a bounded feature request against the cloned repo
3. let the agent generate or refine the feature spec through the intended UI path
4. watch logs for hidden backend failures while the chat appears active

Do not include model names, effort levels, MCP tool names, backlog ids, phase
names, or implementation instructions that a normal product user would not
know. The builder must choose workflow, model, effort, tools, context strategy,
and next phase from product state and the inspected repo.

The feature request should be:

- small enough to complete in one validation pass
- meaningful enough to exercise planning and implementation
- compatible with the selected repo's stack

Good feature shape:

- add one small user-visible enhancement
- improve one existing endpoint or screen
- introduce one bounded behavior plus tests

Avoid:

- broad refactors
- dependency overhauls
- features requiring secrets or external services

### 7. Confirm Feature Backlog Creation

After the Agent chat completes the spec step:

1. inspect the backlog surface in the UI
2. confirm the feature list is visible as product state, not only as conversation text
3. verify the created items belong to the external repo run
4. use logs if the UI claims success but backlog state is missing

Expected outcome:

- at least one feature exists in backlog
- the feature is actionable and tied to the repo context
- the data shape is stable enough to continue into implementation

Hard checks:

- The Backlog page must show the created feature as a visible row, not only as a count.
- If the total count and rendered groups disagree, treat the dashboard projection as defective.
- Status values such as `backlog` must not disappear because a fixed UI status order omits them.
- The Agent reply "saved to backlog" is not sufficient unless the Backlog page shows the feature after reload.

### 8. Start Feature Implementation

For each feature selected from backlog:

1. initiate implementation through the product surface that owns execution
2. confirm the feature creates or advances task state
3. monitor task phase changes
4. check whether the board reflects status changes in near real time

Expected progression:

- approved delivery scope becomes an executable task set through the product's
  planning path; the backlog item itself should not be treated as the task when
  sprint planning is enabled
- dispatch starts from a visible pending or queued state
- phases move forward through the orchestrator-owned lifecycle

If execution does not start, treat the exact stop point as the defect under test.
Do not use `builder backlog` or task-dispatch commands to move past the defect
while claiming the reverse-engineering product path works.

Hard checks:

- A request like "create the feature spec and ship it" must both persist the feature and create or dispatch the delivery task.
- A follow-up like "ship this saved feature" must resolve to the latest relevant saved feature without requiring the user to restate all context.
- Dispatch must work for the active task as well as the next queued task. If an approval failure or server restart leaves a task mid-phase, the Board must provide a visible way to resume that active task.
- Dispatch must be idempotent per task while a run is active. Approval auto-dispatch and a manual Board click must not start duplicate agents for the same task.

### 9. Track Progress On The Board

The board is the canonical operator summary during implementation.

For each active task:

1. confirm the task appears on the board
2. confirm status changes match orchestrator progression
3. confirm blocked or retry states are visible and honest
4. confirm completed work reaches a terminal visible state

A board bug includes:

- missing tasks that exist in backlog or task state
- current-sprint lanes that show tasks from older shipped sprints by default
- no visible sprint selector when more than one sprint exists
- stale status after a backend transition
- impossible transitions
- silent failures where logs show errors but the board stays optimistic
- active work hidden behind a disabled or mis-targeted dispatch button
- duplicate phase runs for one task after approval or rapid operator clicks

### 10. Validate Inbox And Approval Gates

Use the Inbox as a required validation surface, not an optional shortcut.

For every planning, design, PR, or other approval gate:

1. open the Inbox from the header icon
2. confirm the badge count matches the visible pending queue
3. select the approval tied to the feature under test
4. do not approve unrelated seed/onboarding approvals while validating a feature flow
5. open the full approval page
6. verify the thread, gate evidence, agent runs, and decision controls render without server errors
7. approve or request changes from the UI, then return to the Board

Hard checks:

- Approval pages must tolerate mixed legacy/current timestamp shapes.
- Approval resolution must update the Board and Inbox without a manual database edit.
- Approval auto-dispatch must not race with a manual Board dispatch.
- The approval page is the operator decision surface; do not bypass it with direct API calls unless debugging after the browser path fails.

### 11. Validate Phase Boundaries And Workspaces

During design, implementation, quality gates, PR creation, and build verification, check that each phase is using the correct owner and filesystem root.

Required checks:

- Design output should be passed forward as compact context, not by resuming a Claude session in a different `cwd`.
- Implementation must run in the task workspace and must not resume a previous SDK session from repo root.
- Quality gates must test the task workspace code, with local `src/` preferred over installed site packages when the repo uses a `src` layout.
- Global pytest plugins from the operator machine must not poison external repo test runs.
- Documentation freshness must validate the external project root KB, not the isolated task workspace unless the task workspace intentionally owns `.agent-builder/knowledge`.
- PR creation and build verification must reuse the same persisted task workspace unless a documented recovery flow replaces it.

When any phase fails with an opaque SDK or process error, check for a workspace/session boundary issue before changing prompts.

### 12. Monitor Runtime Evidence Continuously

Use logs throughout the run, not only after failure.

Primary commands:

```bash
builder logs --error
builder logs --info --compact --json
builder logs analyze --session <id-or-prefix> --json
```

Watch for:

- classification errors
- route failures
- missing dispatch handlers
- agent runner failures
- phase retries
- quality-gate failures
- database or state-isolation mistakes
- embedded server using the wrong repo root
- SDK resume attempts across different working directories
- pytest failures caused by host-level plugin autoload
- package import resolution using installed dependencies instead of the task workspace
- documentation refresh validation against the wrong root
- duplicate dispatch starts for the same task

When the UI and logs disagree, trust logs first and then trace the UI bug.

### 13. Validate PR Creation, Build Verify, And Shipping

Continue after quality gates pass. Do not stop at "feature implemented" if the product claims an autonomous lifecycle.

Required checks:

1. Dispatch PR creation from the Board.
2. Confirm PR creation produces a reviewable approval gate or a clear transport/auth block.
3. Open the PR review in Inbox and approve it from the browser.
4. Confirm the task advances to build verification.
5. Dispatch or observe build verification.
6. Confirm the task reaches the Shipped lane or records an honest blocked/failed state.
7. Inspect the task workspace status after shipping.

Hard checks:

- PR creation must not call the run complete when only unstaged changes exist unless the review surface clearly exposes that state.
- Transient scratch files must be removed before shipping or explicitly reported as intentional.
- Build verification must not run twice for the same task because of approval auto-dispatch plus manual dispatch.
- If a real GitHub PR cannot be created because the external repo is not writable, the product should surface a clear transport/auth limitation instead of silently claiming shipped.

### 14. Fix Issues At The Smallest Correct Surface

When the flow breaks:

1. capture the exact user-facing failure
2. capture the matching builder logs
3. classify the owner surface
4. patch the smallest correct implementation point
5. run the mandatory tests for the changed component
6. rerun the same external-repo validation step

Common owner mapping:

- onboarding classification bug -> `src/autonomous_agent_builder/onboarding.py` plus onboarding tests
- missing API shape or wrong payload -> API routes plus route tests
- dispatch or phase bug -> orchestrator or quality gate surface plus orchestrator tests
- UI-only mismatch -> frontend/dashboard surface plus browser retest and route verification
- KB extraction bug -> knowledge publisher/evidence graph plus KB tests and validation
- approval page or Inbox bug -> approval/dashboard routes plus dashboard API tests and browser retest
- duplicate dispatch bug -> dispatch route or background-run guard plus API route tests
- workspace/session boundary bug -> orchestrator phase code plus task-workspace tests
- quality-gate environment bug -> quality gate runner plus a real external workspace command
- PR/build hygiene bug -> agent definition/prompt contract plus agent-definition tests

Do not:

- skip directly to broad refactors
- patch docs to hide a runtime defect
- rely on internal database inspection as the first-line operator validation path

### 15. Rerun After Every Fix

After each fix:

1. rerun the mandatory local tests for the changed component
2. restart the external repo server if needed
3. repeat the exact failed step in the real UI
4. continue the lifecycle instead of stopping at the first recovered checkpoint

This workflow is only complete when the recovered path reaches the current intended terminal state, not merely when the first bug disappears.

### 16. Save Reusable Agent Anecdotes

Close every reverse-engineering validation run by saving the general lessons that would make the next agent faster and less error-prone.

This is maintainer closeout after the user-shaped product run. It is not part
of the simulated user path and must not be counted as evidence that the
dashboard lifecycle works.

Use `builder memory add` for repo-local memory. Do not store these lessons only in chat, because future agents start from repo retrieval surfaces.

Save memory when the run reveals:

- a browser-visible state that was misleading or incomplete
- an owner-boundary mistake that caused wasted debugging
- a checkpoint that would have caught the issue earlier
- a product surface that must be checked before trusting a success claim
- a recurring test-environment or workspace-isolation hazard

Good memory shape:

- type: `pattern`, unless the lesson is a correction to a repeated mistake
- phase: `testing`
- entity: `reverse-engineering-autonomous-lifecycle-validation`
- tags: include `reverse-engineering` plus the affected surfaces, such as `backlog`, `inbox`, `dispatch`, `quality-gates`, `shipping`, or `workspace-hygiene`
- content: compact general anecdotes, not a changelog of files edited

Good anecdote examples:

- "Do not trust Agent chat success text until Backlog renders the feature after reload."
- "Inbox badge count is not enough; identify the approval tied to the feature under test before approving."
- "If a phase fails opaquely, check workspace/session boundaries before changing prompts."
- "A shipped task still needs workspace hygiene evidence; untracked scratch files are a workflow gap."

Do not save:

- one-off command transcripts
- obvious facts already encoded in this workflow
- implementation details that will stale quickly
- memories that bypass the browser path or encourage direct database/API validation as the primary lane

## Component Test Mapping

Use this minimum mapping when the corresponding surface changes during a fix:

- Onboarding: `tests/test_onboarding_api.py`, `tests/test_api_routes.py`, `tests/test_embedded_agent_routes.py`
- Orchestrator and gates: `tests/test_orchestrator_gates.py`, `tests/test_runtime_boundary_gate.py`, `tests/test_api_routes.py`
- Agent runtime: `tests/test_definitions.py`, `tests/test_agent_runner.py`, `tests/test_tool_registry.py`, `tests/test_hooks.py`, `tests/test_builder_tool_service.py`
- Knowledge base: `tests/test_kb_publisher.py`, `tests/test_kb_evidence_graph.py`, `tests/test_embedded_kb_routes.py`, plus `builder knowledge validate --json`
- Quality-gate runner: `tests/e2e/test_pipeline.py`, `tests/test_orchestrator_gates.py`, plus a real external workspace command when import paths or pytest environment changed
- CLI: `tests/test_builder_cli_surfaces.py`, `tests/test_cli_output.py`
- API routes and dashboard: `tests/test_api_routes.py`, `tests/test_system_architecture_mvp.py`
- Approval and Inbox: `tests/test_dashboard_api.py`, `tests/test_dashboard_streams.py`, `tests/test_api_routes.py`, plus browser approval retest
- Frontend projection: affected route tests plus browser reload of the exact dashboard page
- Agent prompt contracts: `tests/test_definitions.py`

For a broad end-to-end fix, run the union of all affected sets.

## Decision Points

### If Onboarding Misclassifies The Repo

- stop and fix classification before testing later lifecycle stages
- do not continue on the wrong path and then debug downstream noise

### If Backlog Is Generated But Execution Cannot Start

- treat the dispatch boundary as the primary defect
- confirm whether the stop is a known current boundary or a regression
- implement the missing owner behavior before claiming reverse-path support

### If The Board Does Not Reflect Task Reality

- compare board state with task state and logs
- fix the projection or refresh path, not the symptom text

### If The Agent Chat Produces Conversation But No Durable Product State

- treat that as a product failure
- spec creation must materialize into backlog or task state, not remain transcript-only

### If The Inbox Badge Is Nonzero

- open Inbox and identify every pending approval before approving anything
- approve only the gate for the feature under test
- leave unrelated seed or onboarding approvals untouched unless they are part of the validation goal

### If Quality Gates Pass Locally But Fail In The Product

- compare the product runner environment with the manual command
- check `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, `PYTHONPATH`, repo `src/` layout, and installed package shadowing
- fix the product runner environment rather than weakening the repo tests

### If Documentation Refresh Blocks After KB Validation Passes

- verify which root the docs gate is validating
- project-level KB validation belongs to the external repo root
- task-worktree validation is only correct when the task workspace owns the KB being refreshed

### If PR Creation Or Build Verify Leaves Dirty Workspace State

- inspect `git status --short` in the task workspace
- distinguish staged implementation changes from untracked scratch files
- tighten the responsible agent contract or cleanup behavior before calling the workflow shipped

## Completion Criteria

The workflow is complete only when all of the following are true:

- an external repo was cloned into a disposable temp directory
- builder initialized repo-local state in that repo
- Day-0 readiness reached `agent_ready` for `reverse_engineering`
- onboarding completed through the real product surface
- the Agent chat page produced a feature spec that materialized into backlog state
- backlog items were executable through the product surface
- execution progress was visible on the board
- Inbox approvals for the validated feature were opened and resolved through the browser
- quality gates ran against the intended workspace code and test environment
- documentation freshness validated the intended project root
- PR creation and build verification either reached Shipped or surfaced a clear, honest transport/auth limitation
- task workspace hygiene was checked after shipping
- no mutating CLI command was used as a substitute for user-visible backlog,
  task, approval, or dispatch behavior
- issues found during the run were fixed in this repo and verified
- the rerun reached the furthest intended terminal state without hidden errors
- reusable agent anecdotes from the run were saved to repo-local `builder memory`

If the current product contract still ends earlier, document the exact verified stop point as a known boundary and do not overclaim end-to-end support.

## Anti-Patterns

- using the builder repo itself as the reverse-engineering target
- validating only through `curl` while ignoring the real dashboard and Agent chat page
- using mutating `builder` CLI commands to create backlog items, queue tasks,
  approve gates, dispatch runs, or move phases while claiming the dashboard path
  works
- treating browser success without log correlation as sufficient evidence
- declaring success when backlog exists but execution is not wired
- fixing symptoms in docs or prompts when the true fault is in routing, orchestration, or API state
- continuing past a misclassified onboarding mode
- testing against a repo that requires secrets and then blaming builder for unrelated setup failures

## Output Template

Use this structure when reporting a run:

1. external repo chosen and why
2. exact clone path
3. onboarding result
4. Agent chat result
5. backlog result
6. board/execution result
7. Inbox/approval result
8. quality-gate and documentation-gate result
9. PR/build/shipping result
10. workspace hygiene result
11. failures found
12. fixes applied
13. tests run
14. rerun outcome
15. reusable anecdotes saved to memory
