---
title: Optimize runtime behavior from browser evidence plus builder telemetry
type: pattern
date: 2026-04-24
phase: testing
entity: runtime-validation
tags: [browser, telemetry, builder-logs, verification]
status: active
---

## Pattern

When improving autonomous-agent-builder runtime behavior, start with browser-based validation of the real operator flow, then use builder CLI telemetry and builder logs as the canonical compact evidence lane. Only drop to lower-level DB or server inspection when builder-owned evidence is insufficient. Do not optimize only from static code inspection when the live product surface or builder logs can prove the behavior more directly.

## Agent Retrieval Summary

Retrieve this memory when working on runtime-validation, testing, or related pattern changes. Use it to preserve the repo-local precedent: When improving autonomous-agent-builder runtime behavior, start with browser-based validation of the real operator flow, then use builder CLI telemetry and builder logs as the canonical compact evidence lane.

## User-Facing Summary

When improving autonomous-agent-builder runtime behavior, start with browser-based validation of the real operator flow, then use builder CLI telemetry and builder logs as the canonical compact evidence lane.

## Reusable Guidance

- Treat this as repo-local pattern precedent for runtime-validation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch runtime-validation, the testing phase, or related tags: browser, telemetry, builder-logs, verification.

## Retrieval Queries

- optimize runtime behavior from browser evidence plus builder telemetry
- optimize runtime behavior from browser evidence plus builder
- runtime-validation
- testing
- browser
- telemetry
- builder-logs
- verification
