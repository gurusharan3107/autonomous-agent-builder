# Autonomous Lifecycle Validation

Canonical dashboard-first workflow for validating `autonomous-agent-builder`
from operator intent to shipped generated-app behavior, and for troubleshooting
the builder when visible lifecycle state is wrong.

Use this workflow when validating forward engineering, reverse engineering,
Board/Backlog/approval behavior, generated-app acceptance, runtime evidence,
metrics, observability, or post-ship recovery.

## Decision Rule

Validate product behavior through the dashboard. Use `builder` CLI only for
bootstrap, readiness, logs, metrics, read-only state evidence, and maintainer
diagnosis. Do not use CLI mutation, database writes, raw API calls, or manual
generated-app edits to stand in for Agent, Backlog, Board, Inbox, approval, or
browser lifecycle actions.

If the dashboard, Board, metrics, logs, runtime, or generated app disagree,
the system under test is Autonomous Builder. Fix the owning builder surface and
rerun the same operator path.

## Operator Contract

Act as a normal product user after bootstrap:

- use the Agent page for requirements, clarification, planning, and
  continuation prompts
- use Backlog, Board, Inbox, approvals, Metrics, Observability, and visible
  recovery actions for lifecycle decisions
- use `@Chrome` first for browser-visible dashboard and generated-app proof;
  if Chrome is unavailable, use `$browser-use:browser`; if that is blocked and
  browser control is still needed, use `@Computer`
- prompt in product language, not internal command language
- keep lifecycle actions visible in the product
- after approving a sprint plan or delivery scope, the Agent page should start
  the first generated delivery task directly. The operator must not need to type
  a follow-up such as `start`, know backlog/task language, or bridge the
  approval into dispatch manually.
- after one generated task completes and integrates, Builder should dispatch the
  next serial generated task when no model-backed clarification or operator
  decision is outstanding. Board task state, Recent Agent Runs, Agent-page run
  status, and metrics must move together.
- if generic chat edits the generated app directly while Board state stays
  queued/planning, or if approval/completion requires an unnecessary manual
  dispatch prompt, treat that as a Builder lifecycle bug.

Allowed diagnostic CLI evidence:

- `builder --json doctor`
- `builder readiness status --json`
- `builder readiness assess --json`
- `builder board show --json`
- `builder backlog task status <task-id> --json`
- `builder backlog task show <task-id> --full --json`
- `builder logs --error --json`
- `builder logs --info --compact --json`
- `builder logs analyze --session <id-or-prefix> --json`
- `builder metrics show --json`
- `builder metrics show --json --full --limit 10`
- `builder agent sessions --json`
- `builder agent history --session <id> --full --json`
- `builder agent runtime show --json`
- `builder backlog run summary <query> --json`
- `builder backlog run show <run-id> --json`

Forbidden lifecycle substitutes:

- creating backlog items through CLI instead of Agent/Backlog flow
- dispatching or recovering tasks through CLI to prove the operator path
- approving gates through CLI or database edits
- marking tasks or sprints complete through database mutation
- editing the generated app by hand to satisfy acceptance
- accepting a Board `Shipped` label without final checkout and browser proof

## Entry Paths

| Path | Subject | Required Proof |
|---|---|---|
| Forward engineering | disposable empty or generated-app workspace | requirements clarification, backlog creation, sprint approval, implementation, validation, generated-app Chrome proof |
| Reverse engineering | disposable external repo clone | readiness, repo understanding, planning, backlog/task creation, implementation, validation, external-repo proof |
| Troubleshooting | current dashboard-visible defect | visible symptom, builder evidence, root-cause owner, focused fix, same-path retest |

Do not use `autonomous-agent-builder` itself as the reverse-engineering
validation subject. Use a separate disposable external repo clone so planning,
retrieval, implementation boundaries, and workspace integration are tested for
real.

## Forward Engineering Flow

1. Prepare the builder repo.
   - Run `builder --json doctor`.
   - Check the repo-local quality gate or owner doc relevant to the planned
     change.
   - Start the dashboard with `builder start --port 9876` when browser testing
     is needed.

2. Prepare the target workspace.
   - Use a disposable app workspace.
   - Empty non-git workspaces are valid for generated apps.
   - If the target is not a git repo, final `git status` is advisory metadata,
     not a feature blocker when build/test/lint/browser proof pass.

3. Drive requirements through the Agent page.
   - Ask for the product in normal language.
   - For the first product-specific prompt in a clean-slate workspace, expect
     the selected model to decide whether to answer directly, ask
     product-tailoring questions, or capture the scope. Broad first-product asks
     should gather user-specific requirements before backlog capture so the
     first backlog is tailored to the user's intended audience, workflow, data,
     desired first outcome, persistence/privacy expectation, and product tone
     rather than a generic MVP for the product category. The requirements
     interview may ask as many product-shaping questions or follow-up rounds as
     the specification needs; batch independent questions when efficient, and
     stop when the first shippable scope is genuinely clear.
   - Structured product questions should render as three suggested options with
     the recommended option first plus an inline custom-answer text box. After
     the operator answers, the timeline must keep the answer visible on the
     question card for later review.
   - Answer clarification questions in the browser.
   - Confirm the product produces durable backlog/sprint state after
     requirements are clear.
   - While the Agent is working, the Conversation surface should keep visible
     tool activity as a live count until the next agent response replaces it;
     the operator should not see empty transient tool boxes or a blank wait
     state.

4. Approve scope through visible product surfaces.
   - Review backlog and sprint proposals in the dashboard.
   - Approve or reject through visible approval controls.
   - Do not create tasks, queue work, or approve gates through CLI mutation.

5. Implement through the Board.
   - Dispatch only when the Board shows a dispatchable task and no conflicting
     active task is running.
   - Natural continuation prompts such as "continue the remaining verification
     task" must dispatch the current sprint's existing dispatchable task; they
     must not fall back into sprint planning while Board-eligible work already
     exists.
   - Natural ready-delivery follow-ups that are not read-only status,
     documentation, feature-spec, or explicit sprint-planning requests must let
     the selected runtime inspect Builder state and choose the next tool chain;
     do not add phrase-specific backend shortcuts that require magic wording.
   - Watch active task, queued tasks, blocked state, shipped state, latest run,
     runtime, turns, cost, tokens, duration, and recovery actions.
   - Compare the Board against `builder board show --json` and task `--full`
     output when visible state is surprising.

6. Validate and ship.
   - Generated-app behavior must be proven in Chrome through visible
     navigation, forms, controls, route changes, reload, and persistence checks
     relevant to the approved feature.
   - Build/test/lint evidence should come from the generated app's own scripts
     and be surfaced through builder task/run state.
   - A sprint is shipped only when the final target checkout contains the
     integrated generated work and browser verification passes.

## Reverse Engineering Flow

1. Select a disposable external repo.
   - Use a repo small enough to rerun repeatedly.
   - Clone into a temp path separate from `autonomous-agent-builder`.

2. Bootstrap and readiness-check the external repo.
   - Run `builder init`.
   - Confirm `builder --json doctor`.
   - Confirm `builder readiness status --json` or
     `builder readiness assess --json`.
   - Confirm selected-runtime project guidance exists: `CLAUDE.md` for Claude
     Agent SDK, `AGENTS.md` for Codex SDK.

3. Drive onboarding and planning through the dashboard.
   - Use Agent-page prompts in product language.
   - Require visible Backlog/Board/approval evidence for planned work.

4. Implement and validate through the same Board flow.
   - Prefer the target repo's existing commands and conventions.
   - Treat missing or stale telemetry as a builder observability gap, not proof
     that no work happened.

## Troubleshooting Loop

Start from the visible symptom, then compare product state against builder-owned
evidence in this order:

1. Chrome-visible dashboard or generated-app behavior.
2. Board state: `builder board show --json`. Treat this as compact pipeline
   state; follow `builder backlog task status <task-id> --json` for focused
   diagnosis instead of expanding raw board payloads.
3. Task state: `builder backlog task status <task-id> --json` and
   `builder backlog task show <task-id> --full --json`.
4. Logs: `builder logs --error --json`,
   `builder logs --info --compact --json`, and
   `builder logs analyze --session <id-or-prefix> --json`; use
   `builder logs analyze --session <id-or-prefix> --full --json` only when the
   compact summary names a prompt or tool event that needs raw detail.
5. Metrics: `builder metrics show --json`, especially recent runs, tokens,
   cost, run status, duration, and gate pass rate.
6. Runtime metadata: `builder agent sessions --json`,
   `builder agent history --session <id> --full --json`, and
   `builder agent runtime show --json`.
7. Server logs or direct DB reads only when builder-owned evidence is
   insufficient. Do not use direct DB writes as a fix.
8. Official SDK docs and installed package signatures when runtime behavior
   involves SDK options, model support, hooks, permissions, session behavior,
   or result semantics.

Classify the true owner:

| Symptom | Owner To Fix |
|---|---|
| UI stale or misleading | dashboard API, frontend projection, streaming, or state derivation |
| Board lane wrong | board projection, run-state aggregation, lifecycle policy |
| dispatch/recovery wrong | orchestrator, recovery policy, approval lifecycle |
| ineffective agent run | runtime invocation, SDK options, error classification, prompt, tools, permissions |
| workspace merge/shipping failure | task workspace integration, git/materialization, final checkout proof |
| acceptance too weak/strict | gate evidence, verifier handoff, generated-test expectations |
| generated app missing behavior | make builder repair through Agent/Board lifecycle, never manual app edit |

## Shipping And Integration Proof

Do not trust a shipped or verified sprint state until all of these are true:

- task workspace changes were committed or otherwise builder-materialized
- sprint/task branch was integrated into the target checkout
- final target checkout contains the generated app files
- generated app build/test/lint expectations passed or produced explicit,
  accepted warnings
- browser-visible acceptance proof exercises the actual final app through the
  `@Chrome` / `$browser-use:browser` / `@Computer` ladder
- Board/Backlog/Metrics/Logs agree about terminal state and run evidence
- the Agent page Conversation timeline includes a final shipped closeout with
  implementation, test, browser-proof, integration, and token evidence. If the
  chat transcript only says work started while Board shows shipped, fix the
  Builder-owned closeout projection before calling the flow complete.
- active Agent-page chat runs have been drained or closed before reusing the
  same process for another embedded app validation. A stale run holding a DB
  connection can make the next app instance's evidence unreliable.

If the task workspace has the working app as dirty/uncommitted changes while
`main` or the sprint branch only has guidance or metadata commits, the shipped
state is false. Re-block or recover through builder-owned lifecycle surfaces.

## Runtime Evidence Rules

Model-backed runs with zero tokens, zero cost, no tool activity, or SDK/API
error text in assistant output are suspect. Treat them as ineffective until
logs, metrics, run records, and task evidence prove useful work happened.

For Claude Agent SDK changes:

- verify installed SDK version and live signatures
- check official SDK docs for options, hooks, permissions, session semantics,
  and unsupported fields
- do not keep sending options the active model or SDK rejects
- add focused regression coverage for error classification and result
  persistence

## Closeout

Before calling validation complete:

- Board and Backlog state match the lifecycle contract.
- Metrics and logs show no unresolved ineffective-agent, stale-metric,
  runtime, SDK, or acceptance-gate issue.
- Generated-app browser proof is tied to the shipped sprint/task.
- Any builder regression found has a root-cause fix and focused tests.
- Reusable lessons are stored in `builder memory` from the builder repo cwd.

## Anti-Patterns

- "The generated app is wrong, so edit it directly."
- "The task is on the Board, so the lifecycle is correct."
- "A completed AgentRun means useful work happened."
- "Zero tokens are fine for model-backed agents."
- "CLI dispatch proves the operator flow works."
- "A dashboard bug can be diagnosed from code alone."
- "A deterministic gate failure means loosen the gate before checking whether
  the agent failed to create required behavior or tests."
