---
title: Fix root cause at origin; do not stack defense-in-depth patches
type: correction
date: 2026-05-08
phase: implementation
entity: fix-discipline
tags: [fix-discipline, root-cause, prompt-construction]
status: active
---

## Correction

"Fixing so it doesn't happen again" and "fixing the root cause" are different things. Trace any bug from symptom → mechanism → originating decision and fix at the originating decision, not the mechanism. Do not stack double/triple defense-in-depth patches that each handle the symptom one layer further down. Think from first principles.

## Agent Retrieval Summary

Retrieve before adding a guard, defensive check, or new patch. Use this to choose root-cause fixes over symptom patches. When multiple layers each look like the place to fix, pick the one whose fix makes the others unnecessary, then revert the others.

## User-Facing Summary

When a bug shows up in this repo, find where it starts — not where it surfaces. One good fix at the origin beats three guards downstream.

## Reusable Guidance

- For any reported bug, walk the chain: symptom → mechanism → trigger → originating decision. Fix at the originating decision.
- Use `builder` CLI surfaces (logs, observability, metrics, backlog show) to get authoritative state before theorizing. Dashboard is a view; CLI is the trace.
- When tempted to add a guard "just in case", first ask: what would have to be true upstream for this guard to never fire? Make that the fix.
- A patch that uses data already produced elsewhere in the system (sprint design hints, gate evidence, telemetry) is closer to root cause than a new heuristic invented to compensate for that data being ignored.
- Example seen here: ghost code-gen runs (0 tokens, 0 cost) for sprint tasks were initially patched with an orchestrator ghost-run guard and a TestingGate test-file-change WARN. The actual root cause was the upstream task agent prompt not enforcing the per-task `file_ownership_hint` from the sprint design — fixing the prompt prevented the over-implementation, made the ghost run impossible, and made both patches unnecessary. The patches were reverted.

## When To Apply

Apply when about to add a guard, defensive check, or special-case branch. Apply when investigating a recurring bug. Apply when reviewing a PR that adds compensating logic for a data source that already exists.

## Retrieval Queries

- root cause vs symptom
- defense in depth anti-pattern
- first principles fix
- stacked patches band-aid
- ownership hint enforcement
