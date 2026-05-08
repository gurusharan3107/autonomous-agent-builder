# Agent Quality Tuning Loop

## Overview

This workflow is the repo-owned loop for improving the quality and context
efficiency of work produced by `autonomous-agent-builder`.

Use it when the tuning target is builder behavior itself rather than only a
single user-visible bug. Typical targets include:

- wrong or wasteful tool selection
- poor model selection
- repeated context overload
- weak prompt or instruction shaping
- bad phase routing
- unnecessary subagent use
- weak or missing runtime evidence

The workflow stays aligned to [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md):
the user should not need to manage workflow, tools, models, or context by hand.

Use [system-improvement-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/system-improvement-loop.md)
instead when the primary problem is a concrete product defect, stale UI,
backend/orchestrator regression, or other user-visible failure that must first
be reproduced through the live product surface.

## Core Principle

Tune from evidence, not from instinct.

Start with a real builder session, reduce it to the smallest useful quality
signals, find the smallest correct owner surface, change that surface, then
rerun the same style of work to prove the behavior improved.

## When To Use

- the builder produces low-quality or wasteful outputs
- the agent uses the wrong tools or too many tools
- the model choice is too weak or too expensive for the task
- prompts or `CLAUDE.md` guidance look bloated, duplicated, or mis-scoped
- a phase agent or subagent is doing work that should belong to the main lane
- `builder logs analyze` shows context-efficiency warnings or suspicious tool
  patterns
- OTEL or builder telemetry needs to be used to understand agent behavior

## Workflow

### 1. Choose A Concrete Tuning Subject

Use one bounded subject:

- one builder session
- one builder run
- one task flow
- one repeated workflow such as planning, design, implementation, verification,
  or reverse engineering

Do not start with "make the agent smarter" as an unbounded ask.

## 2. Collect Builder-Owned Evidence First

Inspect the repo-local evidence before changing prompts or agent definitions.

Use:

- `builder agent sessions --json`
- `builder agent history --session <id> --json`
- `builder agent runtime show --json`
- `builder agent runtime probe --json`
- `builder logs analyze --session <id-or-prefix> --json`
- `builder metrics show --json`
- `builder logs --error`
- `builder logs --info --compact --json`

For forward-engineering and reverse-engineering optimization, first verify the
run was driven through the dashboard-first contract. If lifecycle actions were
performed through mutating CLI commands, the evidence does not prove product
quality; rerun through the Agent page before tuning prompts or models.

Look for:

- model used
- effort and thinking budget used
- tools used and in what order
- repeated or broad retrieval
- duration, cost, and stop reason
- delegated subagent usage
- context-efficiency warnings
- explicit observability gaps
- selected runtime, provider, model, effort, telemetry source, runtime-native
  telemetry health, and builder-product telemetry health
- deterministic recommendation codes, evidence, severity, and next action

If OTEL export is enabled, use it as a strengthening lane for traces and span
timings. Do not skip the builder-owned evidence lane.

## 3. Use Vendor Docs Only As Bounded Runtime-Advisory Input

When the tuning question is specifically about a runtime SDK or harness
contract, use the matching vendor documentation as bounded advisory guidance.
Use Claude docs for Claude Code or Claude Agent SDK behavior, and official
OpenAI/Codex docs for Codex runtime behavior.

Good questions:

- which SDK feature best fits this runtime need
- which permission or approval pattern matches the SDK contract
- whether a session, subagent, hook, or tool pattern is aligned with the SDK
- whether a telemetry or observability pattern matches documented usage
- whether Codex subscription auth, app-server events, or request-user-input
  behavior supports the desired product integration

Guardrails:

- treat vendor docs as docs-grounded advisory only
- require an exact docs page or section for every accepted claim
- use it for SDK-pattern questions, not for general architecture or product
  design
- do not accept it as proof of what this repo currently does
- if the question is about builder runtime behavior or implementation truth,
  escalate back to repo evidence, code review, and tests

Do not use vendor docs for:

- runtime validation of this repo
- code generation
- repo-specific architecture ownership decisions
- broad product quality judgments that are not specific to the selected runtime

## 4. Classify The Failure

Classify the tuning need before editing anything:

- prompt shaping problem
- owner-surface duplication problem
- tool allowlist or permission problem
- phase routing problem
- intent-routing or feature-chat convergence problem
- subagent boundary problem
- model selection problem
- knowledge or retrieval placement problem
- observability gap
- target-app environment or diagnostic-script gap

One session may show multiple symptoms, but choose one primary failure first.

## 5. Map To The Correct Owner Surface

Fix the narrowest correct surface:

- `CLAUDE.md` for runtime contract and repo-specific invariants
- `docs/references/phase-model.md` or phase docs for phase/tool boundary rules
- agent definitions or runner wiring for model/tool/subagent behavior
- `src/autonomous_agent_builder/agents/execution_policy.py` for model, effort,
  subagent, budget, or context strategy changes
- builder-owned knowledge docs for durable retrieval guidance
- target-app scripts or CLIs when the app under construction needs a
  deterministic `dev`, `test`, `lint`, `build`, `doctor`, or `smoke` command
  for builder-owned verification
- quality-gate docs when the failure should become a standing review rule
- logs/observability surfaces when the real blocker is missing evidence

Do not spread one tuning decision across prompts, docs, and code if one owner
surface is enough.

Treat higher model effort as a last-mile knob. Check the prompt contract,
tool boundary, compact evidence, and verification loop before increasing
effort or moving a lane to a stronger model.

## 6. Keep The Tuning Change Bounded

Prefer small, testable changes such as:

- tightening an allowlist
- reducing or restructuring loaded instructions
- moving repeated guidance out of the prompt and into the right retrieval doc
- changing the model for one agent lane
- removing an unjustified subagent
- adding one explicit decision rule for a phase
- exposing one more compact signal in builder-owned telemetry

Avoid broad "rewrite the agent prompt" edits without a precise failure claim.

## 7. Re-run The Same Kind Of Work

Re-run the same task class or session flow and compare:

- output quality
- tool count and relevance
- context-efficiency signals
- cost and duration
- need for subagents
- user-facing burden
- whether Metrics and Observability now expose one clear next optimization
  decision without raw database inspection

The goal is not only "did it still work?" but "did it work with less wasted
context and less operator burden?"

## 8. Promote Durable Rules

If the tuning lesson is likely to recur:

- update a quality gate
- update a workflow
- update `CLAUDE.md`
- update a repo knowledge doc

If the lesson is session-specific only, keep it out of the durable owner docs.

## 9. Record Remaining Gaps Honestly

If the evidence is incomplete, say so explicitly.

Examples:

- builder history is sufficient but OTEL traces are still unavailable
- tool events are visible but prompt content export is intentionally disabled
- model choice improved but phase-level permissions still need follow-up

Do not pretend the lane is tuned if the missing evidence still hides the real
failure mode.

## Default Checklist

- [ ] Chose one bounded tuning subject
- [ ] Captured builder-owned session/log evidence
- [ ] Captured metrics and observability JSON when optimizing runtime behavior
- [ ] Used the Claude docs assistant only when the question was SDK-specific and docs-citable
- [ ] Classified the primary failure mode
- [ ] Mapped the issue to the correct owner surface
- [ ] Applied the smallest correct tuning change
- [ ] Re-ran the same task class or flow
- [ ] Compared quality, cost, context, and tool behavior
- [ ] Confirmed deterministic recommendations stayed rule-backed and visible in
      one tabbed Recommendations panel
- [ ] Promoted only the durable lesson into docs or gates
- [ ] Reported remaining observability or evidence gaps

## Common Anti-Patterns

- tuning from prompt taste instead of real session evidence
- mixing several failure categories into one large speculative edit
- assuming a subagent improves quality without proving net context savings
- adding more instructions when the real problem is wrong tool permissions
- treating telemetry export as complete product understanding
- treating the Claude docs assistant as implementation truth for this repo
- fixing one bad session with an oversized permanent prompt
- fixing natural Agent-page feature requests by adding more broad keywords to
  the intent matcher before checking live SDK behavior, session continuity,
  tool context, and ResultMessage/run telemetry

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [agent-quality.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/agent-quality.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md)
- [system-improvement-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/system-improvement-loop.md)
