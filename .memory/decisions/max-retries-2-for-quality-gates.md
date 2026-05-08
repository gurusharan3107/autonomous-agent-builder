---
title: MAX_RETRIES=2 for quality gates
type: decision
date: 2026-04-14
phase: testing
entity: quality-gates
tags: [retries, gates, threshold]
status: active
---

## Decision

Set MAX_RETRIES=2 for all quality gates. After 2 failures, escalate to CAPABILITY_LIMIT and route to dead-letter queue.

## Trace

- Inputs: Gate failure data showing 85% of fixable failures resolved within 2 retries
- Policy: Minimize wasted compute on unfixable failures
- Exception: None
- Approval: Data-driven threshold from gate failure analysis

## Agent Retrieval Summary

Retrieve this memory when working on quality-gates, testing, or related decision changes. Use it to preserve the repo-local precedent: Decision Set MAX_RETRIES=2 for all quality gates.

## User-Facing Summary

Decision Set MAX_RETRIES=2 for all quality gates.

## Reusable Guidance

- Treat this as repo-local decision precedent for quality-gates.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch quality-gates, the testing phase, or related tags: retries, gates, threshold.

## Retrieval Queries

- max_retries=2 for quality gates
- max retries 2 for quality gates
- quality-gates
- testing
- retries
- gates
- threshold
