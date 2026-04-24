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
