---
title: "Architecture boundary quality gate"
surface: "architecture-boundary"
summary: "Use when changing runtime-boundary docs or implementation seams to verify that the documented builder, orchestrator, SDK, and subagent boundaries remain clear."
commands:
  - "workflow --docs-dir=docs summary quality-gate/architecture-boundary"
  - "workflow --docs-dir=docs read quality-gate/architecture-boundary"
  - "builder quality-gate claude-md --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "builder quality-gate builder-cli --json"
  - "pytest tests/test_runtime_boundary_gate.py -q"
  - "builder map --json"
expectations:
  - "runtime-boundary changes preserve the ownership split already documented in the owner surfaces"
  - "workflow progression, retries, and blocked-state handling are not reassigned implicitly during the change"
  - "SDK-facing changes remain limited to runtime mechanics such as loops, sessions, tools, hooks, permissions, streaming, and MCP"
  - "Codex subagents remain optional specialist lanes instead of a required product layer"
  - "shared services or stable contracts are preferred over deeper CLI subprocess coupling"
  - "runtime and SDK files cross the builder boundary through builder_tool_service instead of importing the CLI bridge or shelling out to builder directly"
  - "owner surfaces stay explicit in both docs and code rather than being left to inference"
  - "the user still experiences one coherent builder product instead of choosing runtime and workflow strategy manually"
related_docs:
  - "docs/MISSION.md"
  - "docs/claude-agent-sdk-integration.md"
  - "docs/workflows/architecture-boundary-review.md"
---

# Architecture Boundary Quality Gate

## Purpose

Use this gate when changing repo-local runtime guidance, architecture docs,
or implementation boundaries that could blur the existing split across:

- `builder` product responsibilities
- orchestrator responsibilities
- Claude Agent SDK runtime responsibilities
- Codex subagent usage in this repo

This gate is not the source of truth for that split. Use it to verify that the
change still matches the owner surfaces in
[CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md),
[MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md),
and
[claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md).

## When To Load

Load this gate before:

- editing [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- changing orchestrator, runner, tool-bridge, or runtime-boundary behavior
- introducing or expanding Codex subagent roles for this repo
- adding a new builder-facing architecture or delivery abstraction
- changing the broader owner split that adjacent surfaces such as `CLAUDE.md` must still match

## Review Focus

Check whether the change preserves the documented owner split rather than
redefining it inside this gate.

## Gate Questions

Ask these before claiming the change is correct:

1. Does the change still match the ownership split already documented in the owner docs?
2. Does the orchestrator-facing behavior stay in the same lane instead of letting agents self-route?
3. Does Claude Agent SDK stay limited to runtime mechanics rather than product semantics?
4. Are Codex subagents still optional specialist lanes rather than a required architecture layer?
5. Is the change moving internal integration toward shared services and stable contracts rather than deeper CLI subprocess coupling?
6. Does the change reduce user burden instead of pushing model, workflow, or context-management choices back onto the user?
7. Is the owner surface explicit in code and docs, not left to inference?

## Pass Signals

- The documented owner split still matches the code and adjacent docs.
- One surface clearly owns each responsibility.
- The user still experiences one coherent product.
- Runtime docs and implementation point to the same owner.
- Subagent roles are justified by a stable task class, not by naming preference.

## Fail Signals

- The change causes the SDK to pick up task, backlog, KB, memory, or approval semantics.
- A CLI subprocess becomes the default internal boundary where a shared service should own the logic.
- A Codex subagent is added because it sounds useful, not because a recurring bounded task class exists.
- `CLAUDE.md`, the architecture doc, and code imply different owners for the same responsibility.
- The user would now need to decide workflow, model, or context strategy that the product should choose.

## Recommended Verification

Read:

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- [claude-md.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-md.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [architecture-boundary-review.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/architecture-boundary-review.md)

Check code when relevant:

- `src/autonomous_agent_builder/orchestrator/`
- `src/autonomous_agent_builder/agents/runner.py`
- `src/autonomous_agent_builder/agents/tools/`
- `src/autonomous_agent_builder/onboarding.py`

## Anti-Patterns

- encoding product ownership mainly in agent prompts instead of product/runtime docs
- creating multiple review agents where one reusable architecture-review lane is enough
- solving an internal service-boundary problem by adding more CLI wrappers
- treating architecture review as style commentary rather than owner-surface validation

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [claude-md.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-md.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [architecture-boundary-review.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/architecture-boundary-review.md)
