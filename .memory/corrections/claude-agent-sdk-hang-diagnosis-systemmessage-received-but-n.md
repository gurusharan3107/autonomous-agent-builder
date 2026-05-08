---
title: Claude Agent SDK hang diagnosis: SystemMessage received but no further output
type: correction
date: 2026-04-27
phase: implementation
entity: claude-agent-sdk-runtime
tags: [sdk, diagnosis, hang, SystemMessage, probe, availability]
status: active
---

## Correction

If a Claude Agent SDK query starts (you see SystemMessage in logs or the process clearly launches) but then produces no output and eventually times out, the cause is almost always a missing or mis-wired can_use_tool callback.

The subprocess uses a stdio control protocol for permission requests. When can_use_tool is absent, the first tool permission request from the subprocess has nowhere to send its response. The subprocess blocks waiting. It does not error — it just waits forever.

This was the root cause of the availability probe timeout in this repo. The probe was calling _run_claude_sdk_prompt which used query(prompt=plain_string) with no can_use_tool — the SDK would initialise (SystemMessage visible) but never respond.

Diagnosis steps when you see a hang after SystemMessage:
1. Check whether can_use_tool is set on ClaudeAgentOptions — if absent, that is the cause.
2. Check whether the prompt is a plain string while can_use_tool IS set — SDK raises ValueError immediately (not a hang).
3. Check whether the callback returns a plain dict or SimpleNamespace — SDK raises TypeError at the first tool call (not a hang, but a crash after partial output).

Do NOT use AAB_SKIP_AVAILABILITY_CHECK or similar skip flags as a fix. Fix the call site instead.

## Agent Retrieval Summary

Retrieve this memory when working on claude-agent-sdk-runtime, implementation, or related correction changes. Use it to preserve the repo-local precedent: If a Claude Agent SDK query starts (you see SystemMessage in logs or the process clearly launches) but then produces no output and eventually times out, the cause is almost always a missing or mis-wired can_use_tool callback.

## User-Facing Summary

If a Claude Agent SDK query starts (you see SystemMessage in logs or the process clearly launches) but then produces no output and eventually times out, the cause is almost always a missing or mis-wired can_use_tool callback.

## Reusable Guidance

- Treat this as repo-local correction precedent for claude-agent-sdk-runtime.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch claude-agent-sdk-runtime, the implementation phase, or related tags: sdk, diagnosis, hang, SystemMessage, probe, availability.

## Retrieval Queries

- claude agent sdk hang diagnosis: systemmessage received but no further output
- claude agent sdk hang diagnosis systemmessage received but n
- claude-agent-sdk-runtime
- implementation
- sdk
- diagnosis
- hang
- SystemMessage
