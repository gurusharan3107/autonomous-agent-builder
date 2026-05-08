---
title: Reverse-engineering validation must use an external repo
type: decision
date: 2026-04-24
phase: planning
entity: validation
tags: [reverse-engineering, testing, external-repo]
status: active
---

## Decision

Use a disposable external repo clone for reverse-engineering validation. Do not use autonomous-agent-builder itself as the validation subject because self-hosting hides planning, retrieval, and implementation-boundary defects that the workflow is meant to expose.

## Agent Retrieval Summary

Retrieve this memory when working on validation, planning, or related decision changes. Use it to preserve the repo-local precedent: Use a disposable external repo clone for reverse-engineering validation.

## User-Facing Summary

Use a disposable external repo clone for reverse-engineering validation.

## Reusable Guidance

- Treat this as repo-local decision precedent for validation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch validation, the planning phase, or related tags: reverse-engineering, testing, external-repo.

## Retrieval Queries

- reverse-engineering validation must use an external repo
- reverse engineering validation must use an external repo
- validation
- planning
- reverse-engineering
- testing
- external-repo
