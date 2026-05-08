---
title: Check run terminal state after target tests pass
type: pattern
date: 2026-04-30
phase: testing
entity: reverse-engineering-autonomous-lifecycle-validation
tags: [reverse-engineering, agent-page, documentation-agent, validation]
status: active
---

## Pattern

Reverse-engineering validation can produce correct target code while the builder run remains live or blocked in documentation closeout. After target tests pass, also inspect Agent page state plus builder agent history/logs for stop_reason, running status, KB publish errors, and permission-denied tool loops before declaring the workflow complete.

## Agent Retrieval Summary

Retrieve this memory when working on reverse-engineering-autonomous-lifecycle-validation, testing, or related pattern changes. Use it to preserve the repo-local precedent: Reverse-engineering validation can produce correct target code while the builder run remains live or blocked in documentation closeout.

## User-Facing Summary

Reverse-engineering validation can produce correct target code while the builder run remains live or blocked in documentation closeout.

## Reusable Guidance

- Treat this as repo-local pattern precedent for reverse-engineering-autonomous-lifecycle-validation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch reverse-engineering-autonomous-lifecycle-validation, the testing phase, or related tags: reverse-engineering, agent-page, documentation-agent, validation.

## Retrieval Queries

- check run terminal state after target tests pass
- reverse-engineering-autonomous-lifecycle-validation
- testing
- reverse-engineering
- agent-page
- documentation-agent
- validation
