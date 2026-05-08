---
title: Reject stale gates and feed exact command output back
type: pattern
date: 2026-04-29
phase: testing
entity: quality-gate-feedback-loop
tags: [validation, quality-gates, feedback, implementation]
status: active
---

## Pattern

Do not approve a feature when approval evidence contains stale WARN/UNSUPPORTED_LANGUAGE gates or generic labels such as LINT_FAILED without command output. Quality gates for generated apps must run the actual project scripts (for example npm run lint, npm test -- --run, npm run build) and failures should include the exact command, exit code, and output in the implementation retry prompt. This makes the implementation agent repair the real issue instead of guessing.

## Agent Retrieval Summary

Retrieve this memory when working on quality-gate-feedback-loop, testing, or related pattern changes. Use it to preserve the repo-local precedent: Do not approve a feature when approval evidence contains stale WARN/UNSUPPORTED_LANGUAGE gates or generic labels such as LINT_FAILED without command output.

## User-Facing Summary

Do not approve a feature when approval evidence contains stale WARN/UNSUPPORTED_LANGUAGE gates or generic labels such as LINT_FAILED without command output.

## Reusable Guidance

- Treat this as repo-local pattern precedent for quality-gate-feedback-loop.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch quality-gate-feedback-loop, the testing phase, or related tags: validation, quality-gates, feedback, implementation.

## Retrieval Queries

- reject stale gates and feed exact command output back
- quality-gate-feedback-loop
- testing
- validation
- quality-gates
- feedback
- implementation
