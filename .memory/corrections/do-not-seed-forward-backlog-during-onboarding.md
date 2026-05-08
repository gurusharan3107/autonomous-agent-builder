---
title: Do not seed forward backlog during onboarding
type: correction
date: 2026-05-07
phase: implementation
entity: forward-engineering-onboarding
tags: [forward-engineering, onboarding, backlog, dashboard]
status: active
---

## Correction

Forward-engineering onboarding must not create backlog items, features, or tasks. Day-0 readiness only prepares the workspace and Agent interview. Backlog creation happens after the operator talks to the Agent and the Agent writes the agreed feature list.

## Agent Retrieval Summary

Retrieve this before changing onboarding, Agent requirements intake, Board, Backlog, or generated-app lifecycle validation. If a clean-slate workspace shows backlog or queued board tasks before the operator has completed the Agent requirements interview, treat it as a product bug.

## Reusable Guidance

- `builder init` may create builder state and the bootstrap Agent session.
- It must leave feature/task counts at zero for `forward_engineering`.
- Board and Backlog routes should clean legacy seed rows from old runs when no
  Agent-generated `.claude/progress/feature-list.json` exists.
- Only the Agent requirements interview should materialize the initial feature list and product backlog.

## User-Facing Summary

Clean-slate forward-engineering projects should not show backlog items or queued
Board tasks until the operator has talked to the Agent and agreed on the first
feature list.

## When To Apply

Apply this when changing onboarding, readiness, Board/Backlog APIs, Agent
requirements intake, or generated-app lifecycle validation.

## Retrieval Queries

- forward engineering onboarding backlog seed
- clean slate board queued before agent interview
- agent creates backlog after operator requirements
