# Reverse Engineering Autonomous Lifecycle Validation

## Overview

This workflow validates the full existing-repo path of `autonomous-agent-builder` against a real external repository. It is the canonical repo-local procedure for testing whether the product can take an existing codebase from clone to onboarding to backlog generation to task execution to board-visible completion while preserving correct owner boundaries and evidence.

Use this workflow when you need to:

- verify the reverse-engineering path against a real repo instead of fixtures alone
- reproduce a user-reported onboarding or task-execution failure in the existing-repo lane
- test the real operator flow through the dashboard and Agent chat page
- harden the product by fixing issues as they appear during a real autonomous run

This workflow is intentionally product-first. Reproduce the real user flow through the running app, use `builder logs` as the canonical runtime evidence lane, and only drop to lower-level inspection when the product surface is not enough to localize the fault.

Hard rule:

- never use the `autonomous-agent-builder` repo itself as the reverse-engineering validation subject
- always validate the existing-repo path against a separate external repo clone
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

- existing-repo onboarding regressions
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

Minimum evidence:

- chosen repo URL and clone path
- `builder --json doctor` output in the external repo
- `builder init` result
- `builder start` port and server reachability
- browser snapshots of onboarding, Agent chat, backlog, and board
- `builder logs --error`
- `builder logs --info --compact --json`
- whether `.agent-builder/agent_builder.db` exists in the external repo
- whether generated feature/backlog artifacts exist and are visible through product surfaces
- exact failure point if the flow stops
- test rerun evidence after each fix

## Validation Flow

### 1. Prepare The Builder Repo

From this repo:

1. Confirm repo health with `builder --json doctor`.
2. Read the current reverse-engineering and onboarding testing docs in `builder knowledge`.
3. Start from the real product surface, not from code guesses.

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
4. Record whether the repo is classified as `existing_repo`.

Expected outcome:

- repo-local builder state exists
- the repo is not misclassified as clean-slate
- the product can proceed to onboarding

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

Use Chrome DevTools MCP for operator-facing validation.

1. Open the dashboard for the external repo server.
2. Capture an initial snapshot.
3. Start onboarding from the visible product controls.
4. Watch for classification, progress updates, and terminal readiness state.
5. Check console and network failures if the UI stalls or misreports state.

Expected outcome:

- onboarding progresses through the existing-repo path
- no clean-slate interview is substituted unless the repo truly requires it
- the UI reflects the real backend state

Do not rely on browser appearance alone. Correlate the UI with `builder logs`.

### 6. Use The Agent Chat Page To Produce A Feature Spec

From the Agent chat page in the external repo run:

1. start the conversation from the actual product surface
2. provide a bounded feature request against the cloned repo
3. let the agent generate or refine the feature spec through the intended UI path
4. watch logs for hidden backend failures while the chat appears active

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

### 8. Start Feature Implementation

For each feature selected from backlog:

1. initiate implementation through the product surface that owns execution
2. confirm the feature creates or advances task state
3. monitor task phase changes
4. check whether the board reflects status changes in near real time

Expected progression:

- backlog item becomes an executable task or task set
- dispatch starts from a visible pending state
- phases move forward through the orchestrator-owned lifecycle

If execution does not start, treat the exact stop point as the defect under test.

### 9. Track Progress On The Board

The board is the canonical operator summary during implementation.

For each active task:

1. confirm the task appears on the board
2. confirm status changes match orchestrator progression
3. confirm blocked or retry states are visible and honest
4. confirm completed work reaches a terminal visible state

A board bug includes:

- missing tasks that exist in backlog or task state
- stale status after a backend transition
- impossible transitions
- silent failures where logs show errors but the board stays optimistic

### 10. Monitor Runtime Evidence Continuously

Use logs throughout the run, not only after failure.

Primary commands:

```bash
builder logs --error
builder logs --info --compact --json
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

When the UI and logs disagree, trust logs first and then trace the UI bug.

### 11. Fix Issues At The Smallest Correct Surface

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

Do not:

- skip directly to broad refactors
- patch docs to hide a runtime defect
- rely on internal database inspection as the first-line operator validation path

### 12. Rerun After Every Fix

After each fix:

1. rerun the mandatory local tests for the changed component
2. restart the external repo server if needed
3. repeat the exact failed step in the real UI
4. continue the lifecycle instead of stopping at the first recovered checkpoint

This workflow is only complete when the recovered path reaches the current intended terminal state, not merely when the first bug disappears.

## Component Test Mapping

Use this minimum mapping when the corresponding surface changes during a fix:

- Onboarding: `tests/test_onboarding_api.py`, `tests/test_api_routes.py`, `tests/test_embedded_agent_routes.py`
- Orchestrator and gates: `tests/test_orchestrator_gates.py`, `tests/test_runtime_boundary_gate.py`, `tests/test_api_routes.py`
- Agent runtime: `tests/test_definitions.py`, `tests/test_agent_runner.py`, `tests/test_tool_registry.py`, `tests/test_hooks.py`, `tests/test_builder_tool_service.py`
- Knowledge base: `tests/test_kb_publisher.py`, `tests/test_kb_evidence_graph.py`, `tests/test_embedded_kb_routes.py`, plus `builder knowledge validate --json`
- CLI: `tests/test_builder_cli_surfaces.py`, `tests/test_cli_output.py`
- API routes and dashboard: `tests/test_api_routes.py`, `tests/test_system_architecture_mvp.py`

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

## Completion Criteria

The workflow is complete only when all of the following are true:

- an external repo was cloned into a disposable temp directory
- builder initialized repo-local state in that repo
- onboarding completed through the real product surface
- the Agent chat page produced a feature spec that materialized into backlog state
- backlog items were executable through the product surface
- execution progress was visible on the board
- issues found during the run were fixed in this repo and verified
- the rerun reached the furthest intended terminal state without hidden errors

If the current product contract still ends earlier, document the exact verified stop point as a known boundary and do not overclaim end-to-end support.

## Anti-Patterns

- using the builder repo itself as the reverse-engineering target
- validating only through `curl` while ignoring the real dashboard and Agent chat page
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
7. failures found
8. fixes applied
9. tests run
10. rerun outcome
