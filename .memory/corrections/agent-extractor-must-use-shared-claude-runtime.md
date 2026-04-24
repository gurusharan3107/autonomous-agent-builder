---
title: Agent extractor must use shared Claude runtime
type: correction
date: 2026-04-19
phase: implementation
entity: knowledge-agent-extractor
tags: [kb, claude-runtime, timeout, extraction]
status: active
---

## Constraint
Agent-based KB extraction must go through the shared Claude runtime so backend choice, auth behavior, and timeout handling stay consistent across the repo.

## What Went Wrong
`src/autonomous_agent_builder/knowledge/agent_extractor.py` was calling the Claude Agent SDK directly. That bypassed `src/autonomous_agent_builder/claude_runtime.py`, so the extraction lane ignored repo-level backend selection and had no bounded timeout. The result looked like a hang even though the real `system-architecture` prompt completed through the CLI backend in roughly 32 to 42 seconds.

## What To Do Instead
Route extractor queries through `run_claude_prompt(...)` in `claude_runtime.py`, keep a bounded timeout in `AgentSettings`, and verify the real prompt path before changing prompt logic. If extraction still fails after that, debug prompt shape or post-processing, not the transport layer.
