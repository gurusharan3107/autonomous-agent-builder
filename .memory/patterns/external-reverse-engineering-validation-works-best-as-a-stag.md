---
title: External reverse-engineering validation works best as a staged runtime drill
type: pattern
date: 2026-04-23
phase: testing
entity: reverse-engineering-lifecycle
tags: [reverse-engineering, testing, embedded-server, external-repo]
status: active
---

## Summary

For reverse-engineering validation on an external repo, the most reliable sequence is: clone into a clean temp repo, run `builder init`, complete onboarding until `ready: true`, verify deterministic KB extraction before trusting UI state, then test feature-spec chat, backlog, dispatch, approval, and board as separate runtime surfaces.

## Reusable pattern

- Treat repo-boundary discovery as an early check when cloning into temp directories so parent `.agent-builder` state cannot leak into the fresh repo.
- For reverse-engineering repos, make KB extraction and validation green before judging the dashboard or chat behavior; stale or invalid system-docs can create misleading downstream failures.
- Keep the feature-spec lane separate from the documentation-maintenance lane. A request to create or plan a feature should not be auto-routed into maintained-doc refresh just because the current task has doc expectations.
- Validate embedded task execution in phases: dispatch should advance task state, approval submission should publish cleanly, and approval details should tolerate mixed timestamp forms from existing rows.
- When using the Agent page for live validation, distinguish product bugs from provider/runtime limits. If the specialist route is correct but the provider returns a limit/reset message, the lane is blocked externally rather than by routing logic.

## What to check next time

Start with onboarding status, KB validity, dashboard feature/task state, then chat routing, then dispatch/approval/board transitions. This order isolates builder-owned defects earlier and reduces time spent debugging downstream symptoms.
