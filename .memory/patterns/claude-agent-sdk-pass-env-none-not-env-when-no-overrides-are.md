---
title: Claude Agent SDK: pass env=None not env={} when no overrides are needed
type: pattern
date: 2026-04-27
phase: implementation
entity: claude-agent-sdk-runtime
tags: [sdk, env, environment, subprocess, onecli, observability]
status: active
---

## Pattern

When constructing ClaudeAgentOptions, both onecli_env and observability may produce empty dicts. Passing env={} to the SDK may strip all environment variables from the Claude subprocess (empty dict is not the same as 'inherit parent env'). Always collapse an empty merged dict to None:

  merged_env = {
      **(onecli_env.env if onecli_env.active else {}),
      **observability.env,
  }
  options = ClaudeAgentOptions(..., env=merged_env or None)

None signals 'inherit parent process environment'. An empty dict signals 'empty environment'. This matters for PATH, HOME, and any other env vars the Claude CLI subprocess needs to function.

Affected in this repo: claude_runtime.py _run_claude_sdk_prompt was fixed to use this pattern.

## Agent Retrieval Summary

Retrieve this memory when working on claude-agent-sdk-runtime, implementation, or related pattern changes. Use it to preserve the repo-local precedent: When constructing ClaudeAgentOptions, both onecli_env and observability may produce empty dicts.

## User-Facing Summary

When constructing ClaudeAgentOptions, both onecli_env and observability may produce empty dicts.

## Reusable Guidance

- Treat this as repo-local pattern precedent for claude-agent-sdk-runtime.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch claude-agent-sdk-runtime, the implementation phase, or related tags: sdk, env, environment, subprocess, onecli, observability.

## Retrieval Queries

- claude agent sdk: pass env=none not env={} when no overrides are needed
- claude agent sdk pass env none not env when no overrides are
- claude-agent-sdk-runtime
- implementation
- sdk
- env
- environment
- subprocess
