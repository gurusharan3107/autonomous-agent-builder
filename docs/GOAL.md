# Goal

Make Autonomous Agent Builder a reliable builder-owned software delivery
product.

This document is the acceptance contract for the product mission in
[MISSION.md](MISSION.md). It does not replace the mission. It turns the mission
and repo-local memory precedent into concrete proof requirements for delivery
work.

## Core Product Contract

The user should experience one coherent product: describe intent in chat,
approve when needed, watch work progress, and inspect evidence.

The user should not need to know:

- special prompts
- which runtime, model, or effort level to use
- which tool or workflow phase is next
- how to manage context, memory, or knowledge
- how to recover from runtime-specific failures
- which SDK shipped earlier work

Builder owns the software delivery lifecycle: backlog, sprint planning,
approvals, execution, verification, optimization, memory, knowledge, and
recovery.

## State And Runtime Contract

- The active Builder DB is canonical for product state, task state, runtime
  attribution, recommendations, costs, logs, metrics, and observability.
- Claude Agent SDK and Codex SDK are runtime lanes, not separate products.
- Runtime switching affects future runs only.
- Historical tasks, shipped work, metrics, observability, logs, costs, task
  names, sprint state, approvals, memory, knowledge, and runtime attribution
  must remain visible and correct.
- Runtime-native telemetry may differ, including OTEL schemas, but Metrics,
  Observability, Board, logs analysis, and recommendations must expose
  normalized Builder facts.
- Subagents are bounded evidence lanes, not owners of lifecycle state.

## User Intent Contract

The Builder agent should infer the next right action from backlog, shipped work,
active sprint state, memory, knowledge, logs, telemetry, observability, and
quality gates.

If intent is genuinely ambiguous, the Builder should ask one focused question.
It should not require the user to memorize prompts, name internal tools, select
runtime-specific behavior, or manually manage phase transitions.

Normal user language is part of the acceptance surface. A request like
`Ship the next feature from the todo app backlog.` must route into product
backlog delivery, sprint planning, or the next required approval. It must not
fall through to internal setup, documentation, runtime-baseline, or stale
pending tasks unless the user explicitly asked for those tasks.

## Forward-Engineering Intake Contract

For clean-slate forward-engineering work, Day-0 onboarding prepares the
workspace, readiness state, runtime guidance, and Agent interview. It must not
create backlog items, features, tasks, sprint candidates, or Board cards.

Initial product backlog creation happens only after the operator talks to the
Agent, the Agent completes requirements intake, and the agreed feature list is
materialized as product state.

## Runtime Lane Contract

Codex SDK should be used for Codex-native implementation and verification flows
where app-server events, tool routing, model and effort controls, credit
estimates, and cache behavior help.

Claude Agent SDK should be used for Claude-native planning, implementation,
review, subagents, hooks, permissions, session continuity, ResultMessage usage,
and OTEL capabilities where they improve quality or cost.

The UI should expose one lifecycle. Observability should explain which runtime
capability powered each run and what fallback was used when a native signal was
missing.

Runtime switching is proven by shipped work, not by settings alone. The next
feature must actually ship through the selected runtime, and the dashboard must
still explain both historical and current runtime attribution.

Codex SDK lanes must be designed for app-server stability and token efficiency:
agents should keep command output bounded, redirect verbose logs, avoid
foreground long-lived dev servers, and stop background servers after browser
validation. Plugin manifest warnings, OTEL export noise, or transport-close
noise should be compacted and classified as runtime diagnostics instead of
becoming the product failure reason when useful agent output and evidence exist.

## Verification Contract

Verification should be feature-level, not only task-level.

The feature verifier should behave like a tester against the approved acceptance
criteria before generating tests. It should inspect the user-visible app flow,
use model-backed judgment to decide whether the feature is actually correct,
fix product or test issues when needed, and only then create or update focused
Playwright tests for the accepted behavior.

Later validation should run those acceptance tests first. If they fail, Builder
should trigger the verifier to decide whether the product regressed or the test
is stale, then fix the right surface.

Generated-app feature delivery should not be blocked by unrelated repo-local
knowledge or documentation drift. Knowledge citation validity, dependency hash
freshness, and maintained-doc checks should block only when the task owns docs,
knowledge, or a required maintained-doc update. Otherwise they should become
advisory optimization or documentation work, not a sprint delivery blocker.

## Optimization Contract

Optimization starts from evidence, not impressions.

Builder’s value over using Codex or Claude Code directly is that it can observe
each specialist agent in the delivery lifecycle, identify where that agent is
ineffective, and improve the Builder-owned control surface that made the work
slow, noisy, or low quality.

Optimization must not mean arbitrary token caps. It means reducing wasted
context and elapsed time by giving each agent the right prompt, tools, allowlist,
denylist, context packet, model, and stop condition for its specific job.

Before changing prompts, tools, permissions, models, routing, hooks,
deterministic scripts, or other control surfaces, inspect:

- task agent runs
- runtime attribution
- token and cost data
- cached and noncached tokens
- command timelines
- deterministic checks
- build, test, and browser proof
- `builder metrics show --json --full`
- `builder logs --info --compact --json`
- `builder logs analyze --json`
- relevant Memory and Knowledge entries

When metrics, observability, or logs show an agent repeatedly doing work outside
its job, failing to use the right tool, over-reading context, producing noisy
output, waiting on avoidable approvals, or taking too many turns to reach a
quality result, fix the responsible Builder surface instead of blaming the
underlying SDK.

Repeated model work should become deterministic Builder-owned scripts, lint,
quality gates, or verify checks when the success condition is machine-checkable.

## Control Surface Rules

- `CLAUDE.md` owns runtime contracts and stable phase invariants.
- Agent definitions own agent mindset, tool boundaries, and stop conditions.
- Orchestrator routing owns lane selection and lifecycle state.
- Deterministic scripts own repeatable build, verify, evidence, and diagnostic
  work.
- Metrics and Observability own explanation and recommendations.
- Memory owns reusable project precedent.
- Knowledge owns maintained project understanding.
- Dashboard owns user-visible proof, not hidden truth.
- Local generated-app workspaces without a real Git or PR target should use
  deterministic change evidence instead of model-backed PR ceremony.
- Task drawers should show task-local work such as code generation and build
  verification. Sprint-level feature verification, generated acceptance tests,
  and optimization-agent runs should appear as phase evidence under Verify or
  Shipped so the user can inspect them without confusing them with one task's
  implementation timeline.

## Acceptance Test

A realistic user should be able to:

1. Use the Agent page with normal product language.
2. Plan and approve sprint work.
3. Ship one sprint through Codex SDK from that normal language.
4. See shipped Codex work on Board, Metrics, Observability, logs, Memory, and
   Knowledge, with correct task, phase, run, cost, token, and runtime
   attribution.
5. Switch future runtime to Claude Agent SDK.
6. Ship the next sprint through Claude Agent SDK without corrupting Codex
   history.
7. See Claude work layered on top with correct runtime attribution and preserved
   Codex history.
8. Switch future runtime back to Codex SDK.
9. Ship another sprint without losing Claude or Codex history.
10. Inspect optimization recommendations that explain actions taken, commands
    run, and expected benefit.

The acceptance test should role-play as a real user, not as an agent that knows
internal implementation details. It should prove that Builder infers the next
right action or asks one focused clarification question, rather than requiring
prompt incantations.

## Required Proof

Work is not complete until evidence exists from:

- Browser validation on the actual running generated app Builder instance
- Agent, Board, Backlog, Metrics, Observability, Memory, and Knowledge pages
- `builder memory list --json`
- targeted `builder memory search`, `builder memory summary`, and
  `builder memory show`
- `builder memory lint --json` after memory changes
- `builder lint --json`
- `builder verify --changed --execute --json`
- relevant quality gates:
  - product lifecycle
  - dashboard UX
  - state integrity
  - builder CLI
  - Claude Agent SDK when touched
  - Codex SDK when touched
- `builder logs analyze --json`
- Metrics and Observability evidence showing what happened, what changed, what
  failed, and what optimization remains

## Definition Of Done

The Builder can ship real features through both Codex SDK and Claude Agent SDK
from the user's normal chat workflow, preserve historical state across runtime
switches, surface trustworthy evidence, and turn repeated inefficiency into
deterministic product capability.
