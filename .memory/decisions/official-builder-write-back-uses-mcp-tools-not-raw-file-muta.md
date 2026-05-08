---
title: Official builder write-back uses MCP tools, not raw file mutation
type: decision
date: 2026-04-20
phase: implementation
entity: agent-runtime
tags: [sdk-mcp, memory, kb, learning, self-improvement]
status: active
---

## Summary

Expose repo-local durable learning through official builder MCP tools instead of direct file edits.

## Decision

The Claude SDK runner now registers in-process `builder` and `workspace` MCP servers and exposes `kb_add`, `kb_update`, and `memory_add`. Agent prompts should use these tools for durable write-back. Keep direct `.memory/` and KB file edits blocked in hooks, and block `builder memory add` and `builder kb add|update` from Bash inside the agent runtime so write-back stays on the official tool lane.

## Why

The runtime previously advertised read-only `kb_search`, `kb_show`, `memory_search`, and `memory_show`, and it also referenced MCP surfaces that were not actually registered in the SDK runner. That meant the self-improvement loop could recall precedent but not durably learn through the product.

## Evidence

Implemented in `src/autonomous_agent_builder/agents/tools/sdk_mcp.py`, `src/autonomous_agent_builder/agents/runner.py`, `src/autonomous_agent_builder/agents/tool_registry.py`, `src/autonomous_agent_builder/agents/definitions.py`, and `src/autonomous_agent_builder/agents/hooks.py`. Verified with focused tests covering runner MCP registration, tool registry exposure, prompt/tool policy, and hook enforcement.

## Agent Retrieval Summary

Retrieve this memory when working on agent-runtime, implementation, or related decision changes. Use it to preserve the repo-local precedent: Summary Expose repo-local durable learning through official builder MCP tools instead of direct file edits.

## User-Facing Summary

Summary Expose repo-local durable learning through official builder MCP tools instead of direct file edits.

## Reusable Guidance

- Treat this as repo-local decision precedent for agent-runtime.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch agent-runtime, the implementation phase, or related tags: sdk-mcp, memory, kb, learning, self-improvement.

## Retrieval Queries

- official builder write-back uses mcp tools, not raw file mutation
- official builder write back uses mcp tools not raw file muta
- agent-runtime
- implementation
- sdk-mcp
- memory
- kb
- learning
