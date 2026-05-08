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

## Agent Retrieval Summary

Retrieve this memory when working on quality-gates, testing, or related decision changes. Use it to preserve the repo-local precedent: Decision Run quality gates concurrently using asyncio.gather with per-gate timeouts.

## User-Facing Summary

Decision Run quality gates concurrently using asyncio.gather with per-gate timeouts.

## Reusable Guidance

- Treat this as repo-local decision precedent for quality-gates.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch quality-gates, the testing phase, or related tags: asyncio, concurrency, gates.

## Retrieval Queries

- concurrent quality gates with asyncio.gather
- concurrent quality gates with asyncio gather
- quality-gates
- testing
- asyncio
- concurrency
- gates
