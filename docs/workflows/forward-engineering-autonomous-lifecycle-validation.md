# Forward Engineering Autonomous Lifecycle Validation

## Overview

This workflow validates the full clean-slate path of `autonomous-agent-builder` against a brand-new disposable repository. It is the canonical repo-local procedure for testing whether the product can take an empty directory from initialization to onboarding interview to feature specification to backlog generation to task execution to board-visible completion while preserving correct owner boundaries and evidence.

Use this workflow when you need to:

- verify the forward-engineering path against a real disposable repo instead of mocks alone
- reproduce a user-reported failure in clean-slate onboarding or post-onboarding execution
- validate the Agent chat interview and planning flow through the real UI
- harden the product by fixing issues found during a true autonomous run

This workflow is intentionally product-first. Start from the running dashboard and Agent chat page, use `builder logs` as the canonical runtime evidence surface, and only drop to lower-level inspection after the real user flow exposes the failure.

## Scope

This workflow covers:

- creating a fresh empty temp repo
- initializing builder in that repo
- launching the embedded server
- driving the onboarding interview through the Agent chat page
- confirming `.claude/progress/feature-list.json` and backlog generation
- starting feature implementation from the created backlog
- tracking execution on the board until terminal state
- monitoring logs continuously
- fixing issues in this repo as they are discovered
- rerunning the same external validation path after each fix

This workflow does not stop at the currently documented embedded execution boundary. If task execution still fails after planning, that boundary becomes the first defect to fix.

## When To Use

Run this workflow for:

- clean-slate onboarding regressions
- embedded interview or feature-list generation failures
- missing or malformed generated backlog after the interview
- task dispatch failures after a forward-engineering run
- release-candidate validation for onboarding, Agent chat, backlog, board, and execution surfaces

Do not use this workflow for:

- existing-repo reverse-engineering validation
- isolated unit-test authoring without real product validation
- doc-only edits that do not affect forward-engineering behavior

## Owner Surfaces

- `builder` owns repo-local product state, runtime evidence surfaces, backlog, board, knowledge, memory, and quality-gate entrypoints.
- The dashboard and Agent chat page are the primary operator-facing validation surfaces.
- `builder logs` is the canonical agent-facing diagnosis lane.
- `workflow --docs-dir docs` owns supporting contracts and workflow documentation.
- Fixes belong in the smallest correct owner surface. Do not patch around a builder-owned runtime defect from a global control-plane surface.

## Preconditions

- `autonomous-agent-builder` repo is available locally and dependencies are installed.
- `builder` CLI resolves from this repo and can run `builder --json doctor`.
- Chrome DevTools MCP is available for browser validation.
- A disposable temp root is available for a fresh repo directory.
- The chosen forward-engineering prompt can produce a bounded initial product without third-party secrets.

## Disposable Repo Rules

Create a repo that is intentionally simple enough to rerun often, but concrete enough to exercise planning and implementation.

Prefer:

- an empty temp directory initialized as a git repo if the implementation path expects git state
- one primary language and one obvious app shape
- a small, bounded product request
- a feature spec that can realistically be completed in one validation loop

Avoid:

- broad product briefs with many pages or integrations
- prompts requiring secrets, vendors, or infrastructure that the disposable repo will not have
- oversized architecture requests that blur whether the failure is in builder or in the chosen scope

Selection checklist:

- [ ] Repo is empty or intentionally minimal before `builder init`
- [ ] Requested product can be expressed in one bounded sentence
- [ ] Initial feature set is small enough to inspect manually
- [ ] The implementation target does not depend on external credentials

## Evidence To Capture

Capture evidence at each stage so every fix is tied to observed behavior.

Minimum evidence:

- disposable repo path
- `builder --json doctor` output in the disposable repo
- `builder init` result
- `builder start` port and server reachability
- browser snapshots of onboarding, Agent chat, backlog, and board
- `builder logs --error`
- `builder logs --info --compact --json`
- existence of `.agent-builder/agent_builder.db`
- existence and contents of `.claude/progress/feature-list.json`
- whether backlog items are visible through the product surface
- exact stop point if the flow fails
- tests run after each fix

## Validation Flow

### 1. Prepare The Builder Repo

From this repo:

1. Confirm repo health with `builder --json doctor`.
2. Read the forward-engineering testing and onboarding docs in `builder knowledge`.
3. Start from the real product surface rather than code inspection.

If the builder repo already reports blocking KB freshness drift or another documented concern, note it before starting but continue unless it directly blocks the run.

### 2. Create A Fresh Disposable Repo

1. Create a new temp directory.
2. Optionally initialize git if the execution path expects a git-backed workspace.
3. Record the exact path.
4. Do not use the builder repo itself as the forward-engineering target.

Recommended pattern:

```bash
mkdir -p /tmp/aab-forward-validate
cd /tmp/aab-forward-validate
git init
```

### 3. Initialize Builder In The Disposable Repo

Inside the empty repo:

1. Run `builder --json doctor`.
2. Run `builder init` using the lightest path that still exercises the real onboarding behavior.
3. Confirm repo-local state is created under `.agent-builder/`.
4. Record whether the repo is classified as `forward_engineering`.

Expected outcome:

- repo-local builder state exists
- the repo is not misclassified as `existing_repo`
- the product is ready to launch onboarding

Failure handling:

- If classification is wrong, inspect repo-detect logic first.
- If `.agent-builder/agent_builder.db` is missing, treat that as a product bug.

### 4. Launch The Embedded Product

Inside the disposable repo:

1. Start the product with `builder start --port <port>`.
2. Keep the server running during the full validation pass.
3. Confirm the chosen port is listening.
4. Use `builder logs --error` and `builder logs --info --compact --json` as the first diagnosis lane if the UI behaves unexpectedly.

Expected outcome:

- the embedded product uses the disposable repo's local state
- the dashboard loads successfully
- runtime evidence is attributable to the disposable repo run, not the main builder workspace

### 5. Drive Onboarding Through The Real UI

Use Chrome DevTools MCP for operator-facing validation.

1. Open the dashboard for the disposable repo server.
2. Capture an initial snapshot.
3. Start onboarding from the visible product controls.
4. Watch for classification, progress updates, and terminal readiness state.
5. Check console and network failures if the UI stalls or misreports state.

Expected outcome:

- onboarding follows the `forward_engineering` path
- `repo_scan` does not run on this lane
- the UI reflects real backend state

Do not treat a visually complete page as sufficient evidence. Correlate the UI with logs.

### 6. Use The Agent Chat Page To Run The Init-Project Interview

From the Agent chat page in the disposable repo run:

1. start the real interview flow from the product
2. answer as a user with a bounded one-sentence product brief
3. continue through any follow-up prompts until the interview reaches completion
4. watch logs for backend failures even if the chat UI appears active

The product brief should be:

- small enough to finish in one validation pass
- concrete enough to generate 1-3 inspectable features
- compatible with a simple local-first project

Good prompt shape:

- build a small local notes app with create, edit, and list views
- create a tiny task tracker with one screen and basic persistence
- scaffold a minimal API plus one page and tests

Avoid:

- marketplace or multi-tenant products
- auth-heavy or vendor-heavy systems
- prompts that require cloud services on day one

### 7. Confirm Feature Spec And Backlog Creation

After the interview completes:

1. confirm `.claude/progress/feature-list.json` exists and is valid
2. inspect the backlog surface in the UI
3. confirm the generated features are visible as product state, not only as conversation text
4. verify the created items belong to the disposable repo run
5. use logs if the UI claims success but backlog state is missing

Expected outcome:

- the feature spec is materialized as a durable artifact
- at least one feature exists in backlog
- the data shape is stable enough to continue into execution

### 8. Start Feature Implementation

For each generated feature selected from backlog:

1. initiate execution through the product surface that owns it
2. confirm feature selection creates or advances task state
3. monitor task phase changes
4. check whether the board reflects status changes in near real time

Expected progression:

- backlog items become executable tasks
- dispatch begins from a visible pending state
- phases move forward through the orchestrator-owned lifecycle

If execution still stops at the documented embedded-path boundary, treat that as the first defect to fix rather than an acceptable endpoint.

### 9. Track Progress On The Board

The board is the canonical operator summary during execution.

For each active task:

1. confirm the task appears on the board
2. confirm status changes match orchestrator progression
3. confirm blocked or retry states are visible and honest
4. confirm completed work reaches a terminal visible state

A board defect includes:

- missing tasks that exist in backlog or task state
- stale status after a backend transition
- impossible transitions
- silent failures where logs show errors but the board remains optimistic

### 10. Monitor Runtime Evidence Continuously

Use logs throughout the run, not only after failure.

Primary commands:

```bash
builder logs --error
builder logs --info --compact --json
```

Watch for:

- onboarding misclassification
- missing embedded interview state
- `feature-list.json` write failures
- route failures
- missing dispatch handlers
- agent runner failures
- phase retries
- quality-gate failures
- embedded server using the wrong repo root

When the UI and logs disagree, trust logs first and then trace the UI bug.

### 11. Fix Issues At The Smallest Correct Surface

When the flow breaks:

1. capture the exact user-facing failure
2. capture the matching builder logs
3. classify the owner surface
4. patch the smallest correct implementation point
5. run the mandatory tests for the changed component
6. rerun the same disposable-repo validation step

Common owner mapping:

- forward-engineering misclassification -> `src/autonomous_agent_builder/onboarding.py` plus onboarding tests
- interview route or session bug -> embedded agent routes plus embedded route tests
- missing or malformed feature artifact -> interview write path plus onboarding and API tests
- dispatch or phase bug -> orchestrator or quality gate surface plus orchestrator tests
- UI-only mismatch -> frontend/dashboard surface plus browser retest and route verification
- KB seed or publish bug -> knowledge publisher/evidence graph plus KB tests and validation

Do not:

- stop after planning and call that end to end
- patch docs to hide a runtime defect
- rely on direct DB inspection as the first-line validation path

### 12. Rerun After Every Fix

After each fix:

1. rerun the mandatory local tests for the changed component
2. restart the disposable repo server if needed
3. repeat the exact failed step in the real UI
4. continue the lifecycle instead of stopping at the first recovered checkpoint

This workflow is only complete when the recovered path reaches the current intended terminal state, not merely when the first visible bug disappears.

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

### If The Repo Is Misclassified As Existing Repo

- stop and fix classification before testing later lifecycle stages
- do not debug downstream behavior on the wrong onboarding lane

### If The Interview Completes But No Durable Feature Artifact Exists

- treat that as a product failure
- the forward-engineering path must materialize a durable feature spec, not only a transcript

### If Backlog Exists But Execution Does Not Start

- treat the dispatch boundary as the primary defect
- confirm whether it is the known current embedded limitation or a regression
- implement the missing owner behavior before claiming clean-slate end-to-end support

### If The Board Does Not Reflect Task Reality

- compare board state with task state and logs
- fix the projection or refresh path, not the symptom text

## Completion Criteria

The workflow is complete only when all of the following are true:

- a fresh disposable repo was created
- builder initialized repo-local state in that repo
- onboarding completed through the real product surface
- the Agent chat interview produced a durable feature spec and backlog
- backlog items were executable through the product surface
- execution progress was visible on the board
- issues found during the run were fixed in this repo and verified
- the rerun reached the furthest intended terminal state without hidden errors

If the current product contract still ends earlier, document the exact verified stop point as a known boundary and do not overclaim end-to-end support.

## Anti-Patterns

- using the builder repo itself as the clean-slate target
- validating only with HTTP requests while ignoring the real dashboard and Agent chat page
- treating browser appearance without log correlation as sufficient evidence
- declaring success when `feature-list.json` exists but execution is not wired
- continuing past a wrong onboarding mode
- using an oversized product brief that obscures the real product defect

## Output Template

Use this structure when reporting a run:

1. disposable repo path
2. product brief used in the interview
3. onboarding result
4. feature artifact result
5. backlog result
6. board/execution result
7. failures found
8. fixes applied
9. tests run
10. rerun outcome

