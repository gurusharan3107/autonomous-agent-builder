---
title: "Architecture quality gate"
surface: "architecture-boundary"
summary: "Use when changing runtime-boundary docs, implementation seams, the domain model, layering, adapters, orchestrator, runtime, or the event model to verify the documented builder, orchestrator, SDK, and subagent ownership stays clear and the core architecture invariants hold."
commands:
  - "workflow --docs-dir=docs summary quality-gate/architecture-boundary"
  - "workflow --docs-dir=docs read quality-gate/architecture-boundary"
  - "builder quality-gate claude-md --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "builder quality-gate modular-runtime --json"
  - "builder quality-gate builder-cli --json"
  - "builder map --json"
  - "builder verify --changed --execute --json"
  - "pytest tests/test_runtime_boundary_gate.py -q"
expectations:
  - "runtime-boundary changes preserve the ownership split already documented in the owner surfaces"
  - "workflow progression, retries, and blocked-state handling are not reassigned implicitly during the change"
  - "SDK-facing changes remain limited to runtime mechanics such as loops, sessions, tools, hooks, permissions, streaming, and MCP"
  - "runtime selection keeps claude and codex_sdk user-facing lanes distinct while compatibility adapters remain internal"
  - "Codex subagents remain optional specialist lanes instead of a required product layer"
  - "shared services or stable contracts are preferred over deeper CLI subprocess coupling"
  - "runtime and SDK files cross the builder boundary through builder_tool_service instead of importing the CLI bridge or shelling out to builder directly"
  - "owner surfaces stay explicit in both docs and code rather than being left to inference"
  - "the user still experiences one coherent builder product instead of choosing runtime and workflow strategy manually"
  - "core concepts remain stable: project, feature, task, run, gate, approval, session, workspace, knowledge, memory"
  - "UI, CLI, API routes, services, orchestrator, persistence, runtime adapters, and SDK tools remain separated by owner responsibility"
  - "CLI, dashboard, SDK tools, and internal agents adapt over shared services instead of duplicating lifecycle logic"
  - "events and streams are projections of canonical state, not a second truth source"
  - "new agents, gates, workflows, models, and product surfaces can be added without duplicating phase movement or retry logic"
related_docs:
  - "docs/claude-agent-sdk-integration.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/references/phase-model.md"
  - "docs/workflows/architecture-boundary-review.md"
---

# Architecture Quality Gate

## Purpose

Use this gate when changing repo-local runtime guidance, architecture docs,
implementation boundaries, the domain model, layering, adapter design, or
deterministic orchestration that could blur the existing split across:

- `builder` product responsibilities
- orchestrator responsibilities
- Claude Agent SDK runtime responsibilities
- Codex SDK/app-server runtime responsibilities
- Codex subagent usage in this repo

This gate covers two layers of the same concern: the broad **owner boundaries**
between those surfaces, and the stricter **architecture invariants** that keep
the domain model, layering, adapters, and event model coherent. It is not the
source of truth for that split. Use it to verify that the change still matches
the owner surfaces in
[CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
and
[claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md).

## When To Load

Load this gate before:

- editing [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- changing orchestrator, runner, tool-bridge, or runtime-boundary behavior
- introducing or expanding Codex subagent roles for this repo
- adding a new builder-facing architecture or delivery abstraction
- changing the broader owner split that adjacent surfaces such as `CLAUDE.md` must still match
- changing orchestrator state transitions, retry policy, blocked-state handling, or phase routing
- changing runtime adapters, SDK tools, CLI adapters, dashboard routes, or service boundaries
- changing event streaming, logs, metrics, observability, or product telemetry projections
- changing domain model names or ownership of project/task/run/gate/approval/session/workspace state

## Review Focus

Check whether the change preserves the documented owner split and the core
domain invariants rather than redefining either inside this gate.

## Gate Questions

Ask these before claiming the change is correct:

1. Does the change still match the ownership split already documented in the owner docs?
2. Does the orchestrator-facing behavior stay in the same lane instead of letting agents self-route?
3. Does Claude Agent SDK stay limited to runtime mechanics rather than product semantics?
4. Are Codex subagents still optional specialist lanes rather than a required architecture layer?
5. Is the change moving internal integration toward shared services and stable contracts rather than deeper CLI subprocess coupling?
6. Does the change reduce user burden instead of pushing model, workflow, or context-management choices back onto the user?
7. Is the owner surface explicit in code and docs, not left to inference?
8. Do the core concepts (project, feature, task, run, gate, approval, session, workspace, knowledge, memory) keep stable names and a single owner?
9. Do events and streams stay projections of canonical state rather than becoming a second source of truth?
10. Can the new surface be added by adapting over shared services instead of duplicating phase movement or retry logic?

## Pass Signals

- The documented owner split still matches the code and adjacent docs.
- One surface clearly owns each responsibility.
- The user still experiences one coherent product.
- Runtime docs and implementation point to the same owner.
- Subagent roles are justified by a stable task class, not by naming preference.
- Product state remains owned by services/persistence and surfaced through adapters.
- Runtime lanes execute work but do not redefine backlog, board, approval, memory, knowledge, or metrics semantics.
- Command/query split stays explicit and machine-readable.
- Failures are isolated with preserved state and a clear restart path.

## Fail Signals

- The change causes the SDK to pick up task, backlog, KB, memory, or approval semantics.
- A CLI subprocess becomes the default internal boundary where a shared service should own the logic.
- A Codex subagent is added because it sounds useful, not because a recurring bounded task class exists.
- `CLAUDE.md`, the architecture doc, and code imply different owners for the same responsibility.
- The user would now need to decide workflow, model, or context strategy that the product should choose.
- Route handlers, UI code, CLI code, runtime adapters, and agent prompts each invent state transitions.
- Event streams become required as truth rather than evidence/projection.
- New abstractions duplicate existing owners instead of tightening the boundary.

## Recommended Verification

Read:

- [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- [claude-md.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-md.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [architecture-boundary-review.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/architecture-boundary-review.md)

Check code when relevant:

- `src/autonomous_agent_builder/orchestrator/`
- `src/autonomous_agent_builder/agents/runner.py`
- `src/autonomous_agent_builder/runtime/`
- `src/autonomous_agent_builder/agents/tools/`
- `src/autonomous_agent_builder/onboarding.py`

## Anti-Patterns

- encoding product ownership mainly in agent prompts instead of product/runtime docs
- creating multiple review agents where one reusable architecture-review lane is enough
- solving an internal service-boundary problem by adding more CLI wrappers
- treating architecture review as style commentary rather than owner-surface validation
- letting events or projections become a required source of truth

## Related Docs

- [claude-md.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-md.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [architecture-boundary-review.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/architecture-boundary-review.md)
