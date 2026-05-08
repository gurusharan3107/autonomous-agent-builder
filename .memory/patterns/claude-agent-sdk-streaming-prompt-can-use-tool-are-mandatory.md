---
title: Claude Agent SDK: streaming prompt + can_use_tool are mandatory in all call paths
type: pattern
date: 2026-04-27
phase: implementation
entity: claude-agent-sdk-runtime
tags: [sdk, can_use_tool, streaming, subprocess, hang, critical]
status: active
---

## Pattern

The SDK wraps Claude Code CLI as a subprocess. Three rules must ALL hold or the subprocess hangs or raises immediately:

1. STREAMING PROMPT FORMAT — never pass a plain string to query() or client.query() when can_use_tool is set. The SDK raises ValueError at the call site. Always use an async generator yielding the envelope dict:
   async def _prompt_stream():
       yield {
           'type': 'user', 'session_id': session_id or '',
           'message': {'role': 'user', 'content': prompt},
           'parent_tool_use_id': None,
       }

2. can_use_tool MUST ALWAYS BE WIRED — even for background/non-interactive runs that don't need an approval gate. Omitting it leaves the subprocess permission callback channel closed: the process initialises (you see SystemMessage) then hangs indefinitely. Use an auto-approve fallback:
   from claude_agent_sdk.types import PermissionResultAllow
   async def _auto_approve(tool_name, input_data, context):
       return PermissionResultAllow(updated_input=input_data)
   The capability surface is still constrained by allowed_tools, so auto-approving is safe.

3. can_use_tool RETURN TYPE — the callback MUST return PermissionResultAllow or PermissionResultDeny from claude_agent_sdk.types. Returning a plain dict raises TypeError inside the SDK's internal handler (_internal/query.py line ~285). SimpleNamespace is equally broken. Never use either as a fallback.

Affected files in this repo that were corrected:
- claude_runtime.py: _run_claude_sdk_prompt (probe + one-shot queries)
- agents/runner.py: _execute_query (main phase execution)
- onboarding.py: _run_builder_kb_extract_via_agent (KB extraction agent)
- embedded/server/routes/agent.py: _permission_allow/_permission_deny (removed broken SimpleNamespace fallback)

Rule of thumb: any new SDK call site must have (a) streaming generator prompt, (b) can_use_tool set to auto-approve or caller-supplied, (c) callback returning PermissionResultAllow/PermissionResultDeny.

## Agent Retrieval Summary

Retrieve this memory when working on claude-agent-sdk-runtime, implementation, or related pattern changes. Use it to preserve the repo-local precedent: The SDK wraps Claude Code CLI as a subprocess.

## User-Facing Summary

The SDK wraps Claude Code CLI as a subprocess.

## Reusable Guidance

- Treat this as repo-local pattern precedent for claude-agent-sdk-runtime.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch claude-agent-sdk-runtime, the implementation phase, or related tags: sdk, can_use_tool, streaming, subprocess, hang, critical.

## Retrieval Queries

- claude agent sdk: streaming prompt + can_use_tool are mandatory in all call paths
- claude agent sdk streaming prompt can use tool are mandatory
- claude-agent-sdk-runtime
- implementation
- sdk
- can_use_tool
- streaming
- subprocess
