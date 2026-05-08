---
title: Stay in tester role during autonomous validation
type: pattern
date: 2026-04-29
phase: testing
entity: autonomous-lifecycle-validation
tags: [validation, operator-role, approval-gates, quality-gates]
status: active
---

## Pattern

When validating an autonomous builder, act as the external tester/operator and use the product's own backlog, approval, dispatch, recovery, and gate surfaces. Do not manually move tasks across lanes or patch generated application code to make progress. If the board stalls or a lane transition is wrong, treat that as a host product defect: fix the workflow so the relevant phase agent can continue and prove the behavior through the product surface.

## Agent Retrieval Summary

Retrieve this memory when working on autonomous-lifecycle-validation, testing, or related pattern changes. Use it to preserve the repo-local precedent: When validating an autonomous builder, act as the external tester/operator and use the product's own backlog, approval, dispatch, recovery, and gate surfaces.

## User-Facing Summary

When validating an autonomous builder, act as the external tester/operator and use the product's own backlog, approval, dispatch, recovery, and gate surfaces.

## Reusable Guidance

- Treat this as repo-local pattern precedent for autonomous-lifecycle-validation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch autonomous-lifecycle-validation, the testing phase, or related tags: validation, operator-role, approval-gates, quality-gates.

## Retrieval Queries

- stay in tester role during autonomous validation
- autonomous-lifecycle-validation
- testing
- validation
- operator-role
- approval-gates
- quality-gates
