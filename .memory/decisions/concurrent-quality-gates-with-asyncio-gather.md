---
title: Concurrent quality gates with asyncio.gather
type: decision
date: 2026-04-14
phase: testing
entity: quality-gates
tags: [asyncio, concurrency, gates]
status: active
---

## Decision

Run quality gates concurrently using asyncio.gather with per-gate timeouts. AND-aggregate results (all must pass).

## Trace

- Inputs: 4 gates (Ruff, pytest, Semgrep, Trivy) each taking 5-30s sequentially
- Policy: Total gate time must be <60s for acceptable developer experience
- Exception: None
- Approval: Performance benchmarks showed 3.2x speedup
