---
title: Reverse-engineering validation must follow product-visible state to shipped
type: pattern
date: 2026-04-25
phase: testing
entity: reverse-engineering-autonomous-lifecycle-validation
tags: [reverse-engineering, browser-validation, backlog, inbox, dispatch, quality-gates, shipping]
status: active
---

## Pattern

Before running reverse-engineering validation, treat the browser as the primary operator lane and logs as the evidence lane. Do not trust chat text until Backlog visibly renders the feature, Board shows the task, Inbox exposes the right approval, and the task reaches Shipped or an honest blocked state. Check for hidden count/render mismatches, unrelated approvals in Inbox, active-task resume after restarts, duplicate dispatch after approvals, SDK resume across different workspaces, pytest/plugin/PYTHONPATH pollution, documentation gates validating the wrong root, PR/build phases claiming success with only unstaged changes, and untracked scratch files in the task workspace. Continue past each fixed defect and rerun the same browser step; the validation is not complete when the first bug disappears.

## Agent Retrieval Summary

Retrieve this memory when working on reverse-engineering-autonomous-lifecycle-validation, testing, or related pattern changes. Use it to preserve the repo-local precedent: Before running reverse-engineering validation, treat the browser as the primary operator lane and logs as the evidence lane.

## User-Facing Summary

Before running reverse-engineering validation, treat the browser as the primary operator lane and logs as the evidence lane.

## Reusable Guidance

- Treat this as repo-local pattern precedent for reverse-engineering-autonomous-lifecycle-validation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch reverse-engineering-autonomous-lifecycle-validation, the testing phase, or related tags: reverse-engineering, browser-validation, backlog, inbox, dispatch, quality-gates, shipping.

## Retrieval Queries

- reverse-engineering validation must follow product-visible state to shipped
- reverse engineering validation must follow product visible s
- reverse-engineering-autonomous-lifecycle-validation
- testing
- reverse-engineering
- browser-validation
- backlog
- inbox
