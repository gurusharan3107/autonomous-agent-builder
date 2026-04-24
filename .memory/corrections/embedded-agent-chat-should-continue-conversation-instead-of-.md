---
title: Embedded agent chat should continue conversation instead of CLI resume
type: correction
date: 2026-04-19
phase: implementation
entity: agent chat runner
tags: [agent-chat, resume, claude-sdk, embedded-server]
status: active
---

## Constraint
Embedded agent chat follow-up turns must use SDK conversation continuity, not CLI `--resume`.

## What Went Wrong
The runner treated `resume_session` as `options.resume`, which maps to Claude CLI `--resume`. In the embedded chat lane, the request already carries the prior session id through `client.query(..., session_id=resume_session)`. On the second turn this double-resume shape crashed with `Process error (exit 1): Command failed with exit code 1 ... Check stderr output for details`, even though the same browser flow succeeded on turn one.

## What To Do Instead
When a prior chat session exists, set `options.continue_conversation = True` and keep passing the prior id through `query(..., session_id=resume_session)`. Verify with a two-turn browser replay on `/` plus a focused runner test so `hi` followed by `which cli do you have access to?` returns normally instead of failing on turn two.
