---
title: Generated app workspace changes must be builder-owned
type: correction
date: 2026-05-06
phase: optimization
entity: generated-app-workspace-boundary
tags: [optimization-agent, runtime-guidance, generated-app, builder-agents, memory]
status: active
---

## Correction

Codex may change the autonomous-agent-builder implementation, contracts, tests, and owner docs, but must not directly edit surfaces inside a created app workspace. App workspace updates such as `CLAUDE.md`, `AGENTS.md`, deterministic scripts, hooks, subagents, Playwright tests, or runtime guidance must be performed by builder-owned agents or deterministic builder actions and recorded as part of that agent run.

## Agent Retrieval Summary

Retrieve this memory when validating or fixing optimization-agent behavior, runtime guidance refresh, generated-app workspaces, or any workflow where an app-local file needs to change.

The operating rule is: inspect created app workspaces for evidence, but implement the capability in autonomous builder and exercise it through builder-owned agents or deterministic actions. Do not bypass the product lane by directly editing the generated app workspace.

## User-Facing Summary

Generated app workspace changes should be made by the builder system itself, not by Codex directly. Codex should improve the autonomous builder so the right builder-owned agent or deterministic action performs and records those changes.

## Reusable Guidance

- Direct fixes belong in the autonomous builder repo: source code, tests, owner docs, runtime policy, prompts, hooks, and orchestration.
- Created app workspace surfaces are evidence and targets for builder-owned execution, not direct Codex patch targets.
- Runtime guidance updates must appear as builder-agent or deterministic-action work, with timeline evidence.
- Optimization-agent changes must be grounded in preflight evidence, telemetry, observability, logs, and exact command validation before marking recommendations applied.

## When To Apply

Apply this whenever work touches generated app `CLAUDE.md`, `AGENTS.md`, scripts, hooks, subagents, Playwright tests, runtime guidance, or recommendation decisions from the optimization phase.

## Retrieval Queries

- generated app workspace boundary
- optimization agent runtime guidance app workspace
- builder owned agents update CLAUDE AGENTS scripts
- deterministic scripts trigger phase agent
- do not directly edit created app workspace
