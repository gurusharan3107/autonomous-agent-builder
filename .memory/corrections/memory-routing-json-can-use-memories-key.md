---
title: Memory routing.json can use memories key
type: correction
date: 2026-04-18
phase: implementation
entity: memory-api
tags: [memory, routing, json, ui]
status: active
---

## Correction

## Constraint
Project-local agent memory is indexed by `.memory/routing.json`, and real repos may store entries under `memories` rather than `entries`.

## What Went Wrong
The memory API only read `entries`, so the Memory page rendered as empty even when `.memory` contained active items.

## What To Do Instead
Accept both `entries` and `memories` when loading `.memory/routing.json`, and prefer the live project-local `.memory` index over assumptions copied from older fixtures.

## Agent Retrieval Summary

Retrieve this memory when working on memory-api, implementation, or related correction changes. Use it to preserve the repo-local precedent: Constraint Project-local agent memory is indexed by .memory/routing.json, and real repos may store entries under memories rather than entries.

## User-Facing Summary

Constraint Project-local agent memory is indexed by .memory/routing.json, and real repos may store entries under memories rather than entries.

## Reusable Guidance

- Treat this as repo-local correction precedent for memory-api.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch memory-api, the implementation phase, or related tags: memory, routing, json, ui.

## Retrieval Queries

- memory routing.json can use memories key
- memory routing json can use memories key
- memory-api
- implementation
- memory
- routing
- json
- ui
