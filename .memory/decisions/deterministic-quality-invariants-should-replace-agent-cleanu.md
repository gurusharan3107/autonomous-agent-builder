---
title: Deterministic quality invariants should replace agent cleanup rituals
type: decision
date: 2026-05-04
phase: quality
entity: builder-maintenance
tags: [determinism, verification, docs, cli, codex]
status: active
---

## Decision

Autonomous Builder maintenance should make recurring correctness effortless. Anything that can be proven by code should become a deterministic builder-owned invariant instead of relying on agent memory or context. Memory mutations should automatically reindex and lint; changed code should route to owned docs freshness checks; CLI quality should be executable as a stable JSON score; and closeout should converge on one changed-surface verifier such as builder verify --changed --json. Codex context should be reserved for interpretation, tradeoff analysis, and next-decision synthesis, while deterministic scripts, quality gates, CI, Browser Use proof, and configured verify_review lanes run repeatable validation with the required repo context. Durable guidance belongs in AGENTS.md or skills, but correctness should be enforced by builder commands and CI so maintaining Autonomous Builder becomes second nature rather than a checklist agents may forget.

## Agent Retrieval Summary

Retrieve this memory when working on builder-maintenance, quality, or related decision changes. Use it to preserve the repo-local precedent: Autonomous Builder maintenance should make recurring correctness effortless.

## User-Facing Summary

Autonomous Builder maintenance should make recurring correctness effortless.

## Reusable Guidance

- Treat this as repo-local decision precedent for builder-maintenance.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch builder-maintenance, the quality phase, or related tags: determinism, verification, docs, cli, codex.

## Retrieval Queries

- deterministic quality invariants should replace agent cleanup rituals
- deterministic quality invariants should replace agent cleanu
- builder-maintenance
- quality
- determinism
- verification
- docs
- cli
