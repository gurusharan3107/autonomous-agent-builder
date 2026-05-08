---
title: Use hybrid native OTEL plus builder-normalized telemetry
type: decision
date: 2026-05-04
phase: design
entity: observability-telemetry
tags: [telemetry, observability, otel, codex-sdk, claude-agent-sdk, recommendations]
status: active
---

## Decision

Recommendation: use a hybrid observability model. Keep builder-local active DB telemetry as the canonical product truth for deterministic agent recommendations across project, feature, task, run, phase, gate, approval, runtime, model, tool, cost, failure, retry, artifact, and PR state. Add runtime-native OTEL lanes in parallel: Claude Agent SDK/Claude Code exports Claude-native metrics, logs/events, and traces to the collector; Codex SDK/Codex CLI exports Codex-native OTEL events and metrics through Codex [otel] config to the same collector. Do not force Claude and Codex into one native schema. Dashboard should show Claude native telemetry health, Codex native telemetry health, and builder product telemetry health separately. Recommendation triggers should be deterministic rules over structured facts, with LLMs only explaining the recommendation.

## Agent Retrieval Summary

Retrieve this memory when working on observability-telemetry, design, or related decision changes. Use it to preserve the repo-local precedent: Recommendation: use a hybrid observability model.

## User-Facing Summary

Recommendation: use a hybrid observability model.

## Reusable Guidance

- Treat this as repo-local decision precedent for observability-telemetry.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch observability-telemetry, the design phase, or related tags: telemetry, observability, otel, codex-sdk, claude-agent-sdk, recommendations.

## Retrieval Queries

- use hybrid native otel plus builder-normalized telemetry
- use hybrid native otel plus builder normalized telemetry
- observability-telemetry
- design
- telemetry
- observability
- otel
- codex-sdk
