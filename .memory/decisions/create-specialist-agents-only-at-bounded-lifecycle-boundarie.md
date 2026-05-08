---
title: Create specialist agents only at bounded lifecycle boundaries
type: decision
date: 2026-04-24
phase: design
entity: specialist-agent-routing
tags: [claude-agent-sdk, subagents, specialists, orchestration]
status: active
---

## Decision

Specialist agents should be introduced when the task crosses a bounded lifecycle boundary that benefits from a separate Claude Agent SDK subagent contract, such as documentation maintenance, coding implementation, testing/verification, or architecture review. The parent/orchestrator keeps product semantics, phase progression, and builder state ownership; the specialist receives bounded context, approved tools, and a clear deliverable. Do not create a specialist just to compensate for weak routing or vague prompts; first fix the parent prompt/tool/session contract and use builder telemetry to prove where the boundary actually fails.

## Agent Retrieval Summary

Retrieve this memory when working on specialist-agent-routing, design, or related decision changes. Use it to preserve the repo-local precedent: Specialist agents should be introduced when the task crosses a bounded lifecycle boundary that benefits from a separate Claude Agent SDK subagent contract, such as documentation maintenance, coding implementation, testin

## User-Facing Summary

Specialist agents should be introduced when the task crosses a bounded lifecycle boundary that benefits from a separate Claude Agent SDK subagent contract, such as documentation maintenance, coding implementation, testin

## Reusable Guidance

- Treat this as repo-local decision precedent for specialist-agent-routing.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch specialist-agent-routing, the design phase, or related tags: claude-agent-sdk, subagents, specialists, orchestration.

## Retrieval Queries

- create specialist agents only at bounded lifecycle boundaries
- create specialist agents only at bounded lifecycle boundarie
- specialist-agent-routing
- design
- claude-agent-sdk
- subagents
- specialists
- orchestration
