---
title: Agent extractor must use shared Claude runtime
type: correction
date: 2026-04-19
phase: implementation
entity: knowledge-agent-extractor
tags: [kb, claude-runtime, timeout, extraction]
status: active
---

## Correction

## Constraint
Agent-based KB extraction must go through the shared Claude runtime so backend choice, auth behavior, and timeout handling stay consistent across the repo.

## What Went Wrong
`src/autonomous_agent_builder/knowledge/agent_extractor.py` was calling the Claude Agent SDK directly. That bypassed `src/autonomous_agent_builder/claude_runtime.py`, so the extraction lane ignored repo-level backend selection and had no bounded timeout. The result looked like a hang even though the real `system-architecture` prompt completed through the CLI backend in roughly 32 to 42 seconds.

## What To Do Instead
Route extractor queries through `run_claude_prompt(...)` in `claude_runtime.py`, keep a bounded timeout in `AgentSettings`, and verify the real prompt path before changing prompt logic. If extraction still fails after that, debug prompt shape or post-processing, not the transport layer.

## Agent Retrieval Summary

Retrieve this memory when working on knowledge-agent-extractor, implementation, or related correction changes. Use it to preserve the repo-local precedent: Constraint Agent-based KB extraction must go through the shared Claude runtime so backend choice, auth behavior, and timeout handling stay consistent across the repo.

## User-Facing Summary

Constraint Agent-based KB extraction must go through the shared Claude runtime so backend choice, auth behavior, and timeout handling stay consistent across the repo.

## Reusable Guidance

- Treat this as repo-local correction precedent for knowledge-agent-extractor.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch knowledge-agent-extractor, the implementation phase, or related tags: kb, claude-runtime, timeout, extraction.

## Retrieval Queries

- agent extractor must use shared claude runtime
- knowledge-agent-extractor
- implementation
- kb
- claude-runtime
- timeout
- extraction
