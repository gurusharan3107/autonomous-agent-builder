---
title: Use builder CLI telemetry before reopening broad code context
type: pattern
date: 2026-04-24
phase: testing
entity: builder-cli-telemetry
tags: [builder-logs, claude-agent-sdk, agent-debugging, context-efficiency]
status: active
---

## Pattern

For Agent-page or autonomous-run debugging, start with builder CLI surfaces as the agent-efficient evidence path: builder --json doctor, builder map, builder logs --error, builder logs --info --compact --json, and session-scoped builder logs --session <id> --type <event> --json. The working directory matters because builder logs reads the repo-local .agent-builder/agent_builder.db; for external target runs such as /private/tmp/aab-reverse-flasky-..., run builder logs from the target workspace, not only from the source repo. If a needed SDK telemetry field is not available through builder CLI, report the gap explicitly instead of silently scraping internals.

## Agent Retrieval Summary

Retrieve this memory when working on builder-cli-telemetry, testing, or related pattern changes. Use it to preserve the repo-local precedent: For Agent-page or autonomous-run debugging, start with builder CLI surfaces as the agent-efficient evidence path: builder --json doctor, builder map, builder logs --error, builder logs --info --compact --json, and sessio

## User-Facing Summary

For Agent-page or autonomous-run debugging, start with builder CLI surfaces as the agent-efficient evidence path: builder --json doctor, builder map, builder logs --error, builder logs --info --compact --json, and sessio

## Reusable Guidance

- Treat this as repo-local pattern precedent for builder-cli-telemetry.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch builder-cli-telemetry, the testing phase, or related tags: builder-logs, claude-agent-sdk, agent-debugging, context-efficiency.

## Retrieval Queries

- use builder cli telemetry before reopening broad code context
- use builder cli telemetry before reopening broad code contex
- builder-cli-telemetry
- testing
- builder-logs
- claude-agent-sdk
- agent-debugging
- context-efficiency
