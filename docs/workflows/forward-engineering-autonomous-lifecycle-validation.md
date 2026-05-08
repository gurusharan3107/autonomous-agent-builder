# Forward Engineering Autonomous Lifecycle Validation

## Overview

This workflow validates the full clean-slate path of `autonomous-agent-builder` against a brand-new disposable repository. It is the canonical repo-local procedure for testing whether the product can take an empty directory from initialization to onboarding interview to feature specification to backlog generation to task execution to board-visible completion while preserving correct owner boundaries and evidence.

Use this workflow when you need to:

- verify the forward-engineering path against a real disposable repo instead of mocks alone
- reproduce a user-reported failure in clean-slate onboarding or post-onboarding execution
- validate the Agent chat interview and planning flow through the real UI
- harden the product by fixing issues found during a true autonomous run

This workflow is intentionally product-first. Start from the running dashboard
and Agent chat page, act like a normal product user, use `builder logs` as the
canonical runtime evidence surface, and only drop to lower-level inspection
after the real user flow exposes the failure. The CLI boundary and browser-tool
selection rules are defined in
[dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md).

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
- [dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md)
  owns the validation persona, allowed CLI boundary, and user-shaped prompt
  contract.
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

Apply the dashboard-first rule throughout: after `builder init` and
`builder start`, lifecycle mutations must happen through the Agent page,
Backlog, Board, Inbox, or visible approval surfaces. CLI output is evidence,
not a substitute action path.

Minimum evidence:

- disposable repo path
- generated app workspace path if `builder init` or onboarding materializes a
  separate runnable app under `/private/tmp/aab-forward-*`
- `builder --json doctor` output in the disposable repo
- `builder init` result
- selected-runtime guidance exists: `CLAUDE.md` for Claude or `AGENTS.md` for
  Codex; existing user-authored guidance was preserved
- runtime settings evidence from the active product API or current runtime CLI
  surface, including selected `sdk`, `provider`, `model`, capabilities such as
  `native_user_input`, and the active telemetry lane
- for Codex SDK runs, proof that `requestUserInput` questions render through the
  same visible multiple-choice card contract as Claude `AskUserQuestion`; do not
  accept a prose echo of the selected answer as sufficient progress
- `builder start` port and server reachability
- proof of which process owns the tested port, for example `lsof -nP -iTCP:<port>
  -sTCP:LISTEN` plus `lsof -a -p <pid> -d cwd`
- browser snapshots of onboarding, Agent chat, backlog, and board
- inline question-card evidence for requirements: each card appears at the
  bottom of the transcript, the operator answers it through the visible card,
  and the agent autonomously asks the next structured question or emits the
  final backlog payload without requiring a freeform "continue" prompt
- `builder logs --error`
- `builder logs --info --compact --json`
- `builder logs analyze --session <id-or-prefix> --json`
- `builder agent sessions --json`
- `builder agent history --session <id> --full --json`
- Agent page transcript for at least one realistic continuation prompt, such as
  `Continue building my app.`
- proof that Day-0 onboarding did not seed backlog/features/tasks before the
  operator completed the Agent requirements interview
- proof that the continuation prompt caused builder-owned board inspection and
  task dispatch, not an internal-tool approval card or a prose feature menu
- proof that no CLI command was used to create backlog items, queue tasks,
  dispatch work, or approve gates as a substitute for dashboard behavior
- generated-app browser evidence for every shipped feature, including the URL,
  visible navigation path, form/control exercised, and resulting page state
- generated-app Browser Use proof artifact when shell/headless browser proof is
  unstable. The artifact must record the tool, URL, visible user path, and
  post-reload state checks, and a generated-app script may validate that artifact.
  Do not replace Browser Use proof with a failing local Chrome headless script or
  with a database assertion.
- existence of `.agent-builder/agent_builder.db`
- existence and contents of `.claude/progress/feature-list.json`
- whether backlog items are visible through the product surface
- exact stop point if the flow fails
- provider-limit reset evidence when quota blocks progress: raw reset hint,
  normalized `reset_at`, displayed local time, and whether the board exposes
  Recover after the reset
- tests run after each fix
- OTEL configuration used for the run, if enabled
- Codex runtime telemetry fields when Codex SDK is selected, including token
  usage, turn count, duration, telemetry source, and subscription cost source

## Validation Flow

### 1. Prepare The Builder Repo

From this repo:

1. Confirm repo health with `builder --json doctor`.
2. Read the dashboard-first validation contract.
3. Read the forward-engineering testing and onboarding docs in `builder knowledge`.
4. Start from the real product surface rather than code inspection.

If the builder repo already reports blocking KB freshness drift or another documented concern, note it before starting but continue unless it directly blocks the run.

### 2. Create A Fresh Disposable Repo

1. Create a new temp directory.
2. Optionally initialize git if the execution path expects a git-backed workspace.
   Empty forward-engineering directory workspaces are valid. If the target is not
   a git repo, `git status` failures during final verification are advisory
   metadata gaps, not feature failures, as long as build/test/lint/browser proof
   pass and the workspace path is proven.
3. Record the exact path.
4. Do not use the builder repo itself as the forward-engineering target.

Recommended git-backed pattern:

```bash
mkdir -p /tmp/aab-forward-validate
cd /tmp/aab-forward-validate
git init
```

Recommended non-git pattern:

```bash
mkdir -p /tmp/aab-forward-validate
cd /tmp/aab-forward-validate
```

### 3. Initialize Builder In The Disposable Repo

Inside the empty repo:

1. Run `builder --json doctor`.
2. Run `builder init` using the lightest path that still exercises the real onboarding behavior.
3. Confirm repo-local state is created under `.agent-builder/`.
4. Run `builder readiness status --json` and, if needed, `builder readiness assess --json`.
5. Record whether the repo is classified as `forward_engineering`.

`builder init` and readiness commands are bootstrap and gate evidence. They do
not validate the autonomous lifecycle by themselves. The lifecycle starts only
when the dashboard and Agent page drive the next visible product step.

Expected outcome:

- repo-local builder state exists
- target-repo Claude Agent SDK project guidance exists with
  `Mode: forward_engineering`, deterministic command slots, validation rules,
  telemetry policy, and update rules
- root `.env` exists with runtime settings and safe telemetry defaults:
  selected runtime state is explicit, Claude native OTEL and Codex project-local
  OTEL health are distinguishable from runtime selection, builder active-DB
  telemetry remains the product source of truth, and no raw prompt/tool/body
  export flags are enabled
- `.agent-builder/readiness.json` exists or reports a precise `unknown`/`blocked`
  reason with `next`
- the repo is not misclassified as `reverse_engineering`
- the product is ready to launch onboarding

Failure handling:

- If classification is wrong, inspect repo-detect logic first.
- If `.agent-builder/agent_builder.db` is missing, treat that as a product bug.

### 4. Launch The Embedded Product

Inside the disposable repo:

1. Start the product with `builder start --port <port>`.
2. Keep the server running during the full validation pass.
3. Confirm the chosen port is listening.
4. Prove which workspace owns that port before testing UI behavior.
5. Use `builder logs --error` and `builder logs --info --compact --json` as
   the first diagnosis lane if the UI behaves unexpectedly.

Expected outcome:

- the embedded product uses the disposable repo's local state
- the dashboard loads successfully
- runtime evidence is attributable to the disposable repo run, not the main builder workspace

Current validation setup:

- The tested surface may be a generated app workspace rather than the host
  `autonomous-agent-builder` repo.
- In recent forward-engineering validation the generated app ran from a separate
  `/private/tmp/aab-forward-*` workspace on port `9880`, while the host builder
  remained on `9876`.
- Do not assume `9876` is the subject. Prove the target first by checking the
  listener PID and its cwd.

### 5. Drive Onboarding Through The Real UI

Use Browser Use / in-app browser as the default validation surface when
available. Use Computer Use when the visible desktop-browser experience is the
evidence, and use Chrome DevTools MCP when console, network, accessibility-tree,
or screenshot evidence is needed for diagnosis.

1. Open the dashboard for the disposable repo server.
2. Capture an initial snapshot.
3. Select the desired runtime harness from the visible onboarding controls when
   the run is meant to validate Claude versus Codex behavior.
4. Start onboarding from the visible product controls.
5. Watch for classification, progress updates, and terminal readiness state.
6. Check console and network failures if the UI stalls or misreports state.

Expected outcome:

- onboarding follows the `forward_engineering` path
- readiness reaches `agent_ready`
- common init phases, including `repo_scan` and work-item seed, are recorded as
  passed before the requirements interview opens
- KB extract and validate are recorded as skipped/deferred, not failed
- runtime selection writes the same `.env` keys as Settings and leaves only the
  selected telemetry lane enabled
- Codex SDK runs show native user-input support in runtime evidence
  (`sdk=codex_sdk`, `native_user_input=true`) and ask requirement questions
  through the same visible card flow as Claude `AskUserQuestion`
- the UI reflects real backend state
- the tested browser tab is the generated app or disposable repo server you
  explicitly proved in step 4, not the host builder by accident

Do not treat a visually complete page as sufficient evidence. Correlate the UI with logs.

### 5A. Run The Generated App As A User-Visible Acceptance Target

After the builder ships a feature that changes the generated application, start
or restart the generated app from the disposable repo root and test it in
Browser Use as a normal user.

Recommended command shape for Python/Flask targets:

```bash
cd <disposable-repo>
FLASK_DEBUG=0 python -m <generated_package>
```

Validation requirements:

1. prove the generated app listener PID and cwd, just as with the builder
   dashboard
2. open the generated app in Browser Use
3. navigate only through visible links, buttons, forms, and page controls
4. submit realistic user input and verify durable page state after navigation
5. restart or reload the app after shipped code changes before revalidating
6. for Codex validation, prefer Browser Use DOM snapshots or screenshots for the
   browser proof. If the generated app also includes a `browser-proof` script, it
   should either run a stable app-local browser check or validate a recorded
   Browser Use proof artifact. A crashing local Chrome headless path is a product
   validation blocker, not a reason to mark the feature shipped.

Do not rely on framework debug reloaders as validation infrastructure. If a
generated app server reloads when files in the host builder repo change, treat
that as an environment-isolation smell and restart it from the disposable repo
with debug reload disabled.

### 6. Use The Agent Chat Page To Run The Init-Project Interview

From the Agent chat page in the disposable repo run:

1. start the real interview flow from the product
2. answer as a user with a bounded one-sentence product brief
3. continue through any follow-up prompts until the interview reaches completion
4. watch logs for backend failures even if the chat UI appears active

Do not include model names, effort levels, MCP tool names, backlog ids, phase
names, or implementation instructions that a normal product user would not
know. The builder must choose workflow, model, effort, tools, context strategy,
and next phase from product state.

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

Question-card operating discipline:

- Treat `AskUserQuestion` and Codex/OpenAI `request_user_input` cards as the
  same product interaction contract.
- The card should remain in chronological transcript order at the bottom. Do
  not hoist the newest card above the transcript as a testing workaround.
- Browser Use pointer movement can scroll the transcript while moving toward a
  target. Treat that as browser-automation behavior unless a normal human
  interaction is also broken.
- Use a fresh DOM snapshot after any failed click before retrying. Prefer a
  scoped locator for the visible option/card instead of repeating a stale click.
- Do not encode Browser Use pointer-movement workarounds into the application unless a
  normal human-visible interaction is broken.
- After a question answer, the expected agent behavior is autonomous
  continuation: ask the next structured requirement card or produce the final
  `FEATURE_LIST_JSON`. A plain acknowledgement such as "selected X" or
  `No response from agent` is a requirements-flow defect.

After the interview finishes, record the active builder session ids with:

```bash
builder agent sessions --json
```

Use the resulting session ids when correlating Agent chat behavior with
`builder agent history` and `builder logs analyze`.

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

For the current forward-engineering lane, do not jump directly from product
backlog to board expectations. Validate the product-owned sprint-planning step.
Do not create queue approvals, queued sprint tasks, or generated implementation
tasks with
`builder backlog` commands during this step.

1. Use the Agent page to initiate sprint planning.
2. Reply with `all` or a bounded list of backlog ids/titles.
3. Confirm the product raises a single queue approval for the selected sprint
   backlog items.
4. Approve the queue request.
5. Confirm the approval moves the selected items from product backlog to sprint
   backlog to `queued`.
6. Confirm sprint planning decomposes the approved feature into multiple
   implementation tasks; the backlog item itself must not become the task.
7. Confirm one sprint execution plan and one shared sprint design are attached
   to the generated tasks.
8. Confirm the board shows those tasks only after approval.
9. Confirm that approval immediately dispatches the next ready task when one is
   available, without requiring a second Board click.

The approved sprint should use a sprint-level plan/design artifact before
task-level implementation begins. Validate that queued task metadata includes:

- sprint item ids and dependency order
- batch id and batch index
- risk flags and recommended model/effort
- per-task implementation brief derived from the sprint plan/design, not the
  full requirements transcript
- shared generated-app acceptance expectations
- runtime tool strategy for the selected harness, including Codex SDK app-server
  telemetry when `RUNTIME_SDK=codex_sdk`

Tasks covered by this sprint artifact should not run separate task-level
planner/designer phases unless the sprint design marks the task as requiring
task-specific design.

For each generated feature selected from backlog after sprint planning:

1. initiate execution through the product surface that owns it
2. confirm feature selection creates or advances task state
3. monitor task phase changes
4. check whether the board reflects status changes in near real time
5. after the feature ships, open the generated app in Browser Use and validate
   the feature through visible user navigation, forms, buttons, and page state

A feature is not browser-accepted if it only works behind a guessed URL. The
generated app must expose a visible route, link, or control that a normal user
can discover from the app surface. For example, if a feature adds an RC detail
or checks page, the RC list must expose a visible path to that page; manually
typing `/rcs/1/checks` only proves the route exists, not that the product is
usable.

Also test the normal post-onboarding continuation path from the Agent page.
Use the kind of prompt a product user would write, not an implementation-aware
operator prompt:

```text
Continue building my app.
```

Expected behavior:

- the builder inspects board/backlog state itself
- safe read-only builder and workspace inspection tools do not create approval
  cards
- if a deterministic next task exists, the builder selects it by status and
  priority and dispatches it
- builder-owned task dispatch does not expose internal MCP tool names to the
  user as an approval request in this continuation lane
- if the next action is blocked by a real approval, missing prerequisite, or
  provider limit, the product state reports that blocker instead of returning a
  generic feature menu
- provider-limit blocked cards expose reset timing and a dashboard Recover
  action for use after the provider reset
- absolute provider reset hints that include a timezone, such as
  `resets 9:30pm (Asia/Calcutta)`, are normalized to UTC correctly and are
  displayed to the user as the intended local reset time

Failures to treat as product bugs:

- the Agent page asks "which feature should we build next?" when board state
  already defines a deterministic next task
- the Agent page asks for approval to use read-only internal inspection tools
- the Agent page asks for approval to dispatch the builder-selected task after
  the user explicitly asked to continue building
- approval succeeds but the next ready sprint task waits idle until the user
  clicks Dispatch task
- the chat claims dispatch happened but the board/task state does not advance

Expected progression:

- product backlog items stay non-board-visible until sprint planning plus queue
  approval complete
- approved queued items become executable tasks
- approved queued items carry a shared sprint plan/design handoff
- dispatch begins from a visible queued or pending board state, depending on the
  current projection contract
- approval auto-dispatch and manual Board dispatch stay idempotent, so a 409
  conflict represents an already-active/non-dispatchable task and does not start
  duplicate agents
- phases move forward through the orchestrator-owned lifecycle; sprint-covered
  tasks may skip directly from queued/pending into implementation when their
  sprint plan and design are already present
- stale background `OPERATOR_DECISION_JSON` handoffs are cleared when the task is
  recovered or re-enters implementation. A repaired workspace must not keep
  showing an old "workspace only has AGENTS.md" blocker after the generated app
  files exist.
- final verifier output is parsed semantically: explicit failed checks block the
  task, but known advisory metadata checks such as `git status` on a non-git
  directory workspace do not.

If execution still stops at the documented embedded-path boundary, treat that as the first defect to fix rather than an acceptable endpoint.

### 9. Track Progress On The Board

The board is the canonical operator summary during execution.

For each active task:

1. confirm the task appears on the board
2. confirm status changes match orchestrator progression
3. confirm blocked or retry states are visible and honest
4. confirm completed work reaches a terminal visible state

For multi-sprint runs:

1. confirm the Board defaults to the current sprint
2. confirm lane cards are filtered to the selected sprint's generated tasks
3. confirm older shipped sprint tasks are reachable through the sprint selector
4. use `All sprints` only as a diagnostic view, not as the default operator view

A board defect includes:

- missing tasks that exist in backlog or task state
- tasks from an older shipped sprint appearing in the current sprint lanes
- no way to switch between current and older sprints
- stale status after a backend transition
- impossible transitions
- silent failures where logs show errors but the board remains optimistic
- stale blocked copy from a previous agent run after a newer run has advanced or
  completed the task
- a task marked `done` when the latest verifier output contains a real `FAIL`
  line for build, test, lint, browser proof, or acceptance criteria
- a sprint that remains `verify` or `implementation` after all generated sprint
  tasks are done and final verification has passed
- sprint-stage details are shown as always-visible orchestration tables instead
  of click-through sidebars
- task cards show raw token counts where the primary card metric should be cost
  usage, including `subscription` for Codex subscription-backed runs

### 10. Monitor Runtime Evidence Continuously

Use logs throughout the run, not only after failure.

Primary commands:

```bash
builder logs --error
builder logs --info --compact --json
builder logs analyze --session <id-or-prefix> --json
```

`builder logs analyze` should expose compact runtime aggregates so agents can
diagnose cost and ceremony without ad hoc database queries:

- per-agent runs, turns, token counts, cost, duration, and stop reasons
- raw-token optimization summary, including non-cached + output tokens, cache
  ratio, phase ceremony tokens, avoidable-cost flags, top cost drivers,
  benchmark status, and recommended next change
- runtime SDK, provider, model, effort, telemetry source, and cost source
- planning/design ceremony cost versus implementation cost
- approval wait time
- provider-limit count and reset readiness
- tool-count and missing-tool-event signals

For low-risk local generated-app sprints on Codex SDK, routine PR creation
should use deterministic evidence collection instead of a model-backed
`pr-creator` run unless a real git/PR integration target is enabled.

Watch for:

- onboarding misclassification
- missing embedded interview state
- `feature-list.json` write failures
- route failures
- missing dispatch handlers
- dispatch-only chat turns whose latest `run_status` remains `running=true`
  after `mcp__builder__task_dispatch` returned a dispatched task
- agent runner failures
- phase retries
- quality-gate failures
- embedded server using the wrong repo root
- generated app running on a different port or cwd than the tab being tested
- stale board state caused by validating the wrong workspace

If the session is relevant to optimization work, collect both:

```bash
builder agent history --session <id> --full --json
builder logs analyze --session <id-or-prefix> --json
```

Builder-local history is the primary qualitative evidence lane. OTEL, when
enabled, is a structural supplement for latency, tool-churn, and cross-run
comparison.

For a user-shaped continuation that dispatches work in the background, expected
log evidence includes a terminal `run_status` with
`stop_reason=task_dispatched` and the correlated task id/status. Treat a
dispatched task paired with an indefinitely running chat turn as a product
observability defect.

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
- stale operator decision or invalid recovery target -> task recovery service plus
  recovery tests
- false done state after failed verifier output -> orchestrator build-verifier
  result parsing plus orchestrator tests
- final sprint does not become shipped -> sprint finalization in the orchestrator
  plus board/API projection tests
- generated app browser proof flakes in shell Chrome but passes through Browser
  Use -> generated-app proof script/artifact boundary plus Browser Use evidence
- UI-only mismatch -> frontend/dashboard surface plus browser retest and route verification
- KB seed or publish bug -> knowledge publisher/evidence graph plus KB tests and validation

Do not:

- stop after planning and call that end to end
- patch docs to hide a runtime defect
- rely on direct DB inspection as the first-line validation path
- assume the host builder server is the generated app under test

## Optional OTEL Setup For Optimization Runs

Use OTEL when the goal is not only functional validation but also agent-quality
optimization across multiple forward-engineering runs.

Minimum repo-owned inputs:

```bash
export AAB_CLAUDE_OTEL_ENABLED=1
export AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318
```

Replace the endpoint with the actual OTLP collector for the validation run.
Copied placeholders such as `http://your-collector:4318` are configuration
drafts, not usable telemetry backends.

Recommended additions:

```bash
export AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES='service.version=1.0,deployment.environment=local'
export AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true
```

The runtime will translate these repo-owned settings into the Claude child
process OTEL environment. Keep builder-local evidence as the primary review
surface:

- `builder agent sessions --json`
- `builder agent history --session <id> --full --json`
- `builder logs analyze --session <id-or-prefix> --json`

Use OTEL for:

- cross-run latency comparison
- tool-duration hotspots
- model and cost baselining
- correlation between builder session ids and structural traces

Do not use OTEL as a transcript warehouse. Keep content-heavy export flags off
unless a narrow debugging window explicitly requires them.

### 12. Rerun After Every Fix

After each fix:

1. rerun the mandatory local tests for the changed component
2. restart the disposable repo server if needed
3. repeat the exact failed step in the real UI
4. continue the lifecycle instead of stopping at the first recovered checkpoint

This workflow is only complete when the recovered path reaches the current intended terminal state, not merely when the first visible bug disappears.

### 13. Save Validation Closeout Findings

Close every substantial forward-engineering validation run through durable
builder-owned surfaces, not only the chat transcript.

This is maintainer closeout after the user-shaped product run. It is not part
of the simulated user path and must not be counted as evidence that the
dashboard lifecycle works.

Create typed backlog items with `--source validation` when the run reveals
follow-up work:

- `incident` for observed product failures
- `improvement` for required product hardening
- `optimization` for efficiency, context, model, or agent-experience work

Save a repo-local `builder memory` anecdote when the lesson would help the next
agent avoid the same validation trap.

Good memory shape:

- type: `pattern`, unless it corrects a repeated mistake
- phase: `testing`
- entity: `forward-engineering-autonomous-lifecycle-validation`
- tags: include `forward-engineering` plus affected surfaces such as
  `agent-page`, `dispatch`, `approval`, `provider-limit`, `quality-gates`, or
  `context-efficiency`
- content: compact reusable behavior, not a command transcript or file changelog

Good anecdote examples:

- "Use realistic Agent-page prompts; do not make the prompt describe internal
  builder responsibilities."
- "If Agent chat says dispatch happened, verify board/task state before calling
  the lifecycle advanced."
- "When UI and logs disagree, treat the mismatch as a product bug and fix the
  projection or event write path."

Do not save:

- one-off command transcripts
- obvious facts already in this workflow
- memories that encourage bypassing the Agent page as the primary validation
  surface
- stale implementation details that will drift faster than the workflow

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
- Day-0 readiness reached `agent_ready` for `forward_engineering`
- onboarding completed through the real product surface
- the Agent chat interview produced a durable feature spec and backlog
- backlog items were executable through the product surface
- a realistic Agent page continuation prompt selected and dispatched the
  deterministic next task without requiring internal-tool approval
- execution progress was visible on the board
- the Board defaulted to the current sprint, with prior sprint tasks available
  only through the sprint selector or `All sprints`
- every sprint-generated task is `done`
- the approved sprint feature is `done`
- the current sprint is `shipped`, `verification_status=passed`, and the Board
  phase strip visibly marks `Shipped` active with `0` blocked tasks
- generated-app tests, lint, build, and Browser Use acceptance proof all pass for
  the shipped feature
- no mutating CLI command was used as a substitute for user-visible backlog,
  task, approval, or dispatch behavior
- issues found during the run were fixed in this repo and verified
- the rerun reached the furthest intended terminal state without hidden errors

If the current product contract still ends earlier, document the exact verified stop point as a known boundary and do not overclaim end-to-end support.

## Anti-Patterns

- using the builder repo itself as the clean-slate target
- validating only with HTTP requests while ignoring the real dashboard and Agent chat page
- using mutating `builder` CLI commands to create backlog items, queue tasks,
  approve gates, dispatch runs, or move phases while claiming the dashboard path
  works
- treating browser appearance without log correlation as sufficient evidence
- treating logs/database state without Browser Use proof as sufficient evidence
  for user-visible generated-app behavior
- declaring success when `feature-list.json` exists but execution is not wired
- declaring success when all tasks are `done` but the sprint is not `shipped`
- declaring failure solely because `git status` is unavailable in an intentionally
  non-git disposable directory workspace
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
7. generated-app Browser Use proof result
8. final sprint and feature shipped state
9. failures found
10. fixes applied
11. tests run
12. rerun outcome
