---
title: "Claude Agent SDK architecture gate"
surface: "claude-agent-sdk"
summary: "Use when changing sdk=claude integration to verify that Claude runtime-mechanics changes do not blur the existing builder and orchestrator boundaries."
commands:
  - "builder --json doctor"
  - "builder map --json"
  - "builder quality-gate builder-cli --json"
  - "builder quality-gate architecture-boundary --json"
  - "builder quality-gate modular-runtime --json"
  - "pytest tests/test_runtime_boundary_gate.py -q"
  - "workflow quality-gate cli-for-agents"
expectations:
  - "Claude SDK-facing changes remain limited to sdk=claude runtime execution mechanics instead of introducing new product-semantics ownership"
  - "routing, blocked states, retries, and human checkpoints are not reassigned implicitly during SDK integration changes"
  - "Claude SDK-backed builder tools still consume the existing builder product contract rather than redefining it"
  - "Claude SDK integration changes do not move backlog, board, knowledge, memory, approval, or metrics semantics into the runtime lane"
  - "runtime files call builder_tool_service instead of importing the CLI bridge or shelling out to builder directly"
  - "one-shot helper lanes stay distinct from the multi-turn runner so backend selection does not silently redefine phase execution"
  - "agents never mutate repo-local knowledge or memory through direct file or database writes outside the builder publish surfaces"
  - "SDK-exposed builder tools mirror builder semantics and machine-readable results instead of inventing a second repo contract"
  - "shared services or stable product APIs are the preferred internal integration path; CLI subprocess bridges are compatibility adapters, not the target architecture"
  - "workspace tools operate inside the isolated cwd with repo hooks and permission mode enforcing deterministic safety boundaries"
  - "vendor-facing auth or SDK setup changes must not blur the repo boundary between execution runtime and product state ownership"
  - "the product should feel like one builder-owned system, not a thin wrapper where the user has to reason about SDK/runtime choices"
  - "Claude phase policy emits model, effort, thinking budget, context strategy, selected subagents, permission policy, hook policy, and reason code as run evidence"
  - "Claude SDK subagents remain bounded specialist evidence lanes and never own lifecycle state, approvals, backlog, board, knowledge, memory, or user questions"
related_docs:
  - "docs/claude-agent-sdk-integration.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/quality-gate/builder-cli.md"
  - "docs/quality-gate/product-lifecycle.md"
  - "docs/quality-gate/state-integrity.md"
---

# Claude Agent SDK architecture gate

## Purpose

Use this gate when changing `sdk=claude` execution seams, Claude Agent SDK
integration, or code paths where Claude runtime mechanics could leak into
builder-owned product state.

## When To Load

Load this gate before:

- changing the agent runner or helper-runtime split
- changing SDK hook wiring, permissions, or MCP integration
- changing SDK-backed builder tools or their machine contracts
- changing auth bootstrap behavior that affects local Claude execution
- changing how `ClaudeRuntime` is selected through the modular runtime factory
- changing whether a responsibility belongs in builder, the orchestrator, or the SDK runtime

## Pass Signals

- the SDK change remains limited to `sdk=claude` runtime execution mechanics
- the builder and orchestrator contracts described in the owner docs still match the code after the change
- runtime helpers and multi-turn runner lanes remain distinct
- SDK-backed tools and chat lanes consume builder-owned product surfaces instead of redefining them
- phase policy evidence records selected subagents, hook policy, permission
  policy, and reason codes so agents can explain runtime choices without
  reading prompt text
- Codex SDK behavior remains covered by the modular-runtime gate, not this Claude-only gate

## Fail Signals

- SDK paths start owning task, approval, gate, backlog, board, knowledge, memory, or metrics semantics
- subprocess compatibility bridges are treated as the target architecture
- auth/setup changes blur runtime ownership boundaries
- Codex SDK behavior is documented as if it inherits Claude hooks, MCP wiring, OneCLI bootstrap, or project-instruction loading
- the user would need to understand SDK/runtime strategy in order to use a builder-owned feature

## Related Docs

- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md)
