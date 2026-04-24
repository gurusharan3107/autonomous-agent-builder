---
title: Create specialist agents only at bounded lifecycle boundaries
type: decision
date: 2026-04-24
phase: design
entity: specialist-agent-routing
tags: [claude-agent-sdk, subagents, specialists, orchestration]
status: active
---

Specialist agents should be introduced when the task crosses a bounded lifecycle boundary that benefits from a separate Claude Agent SDK subagent contract, such as documentation maintenance, coding implementation, testing/verification, or architecture review. The parent/orchestrator keeps product semantics, phase progression, and builder state ownership; the specialist receives bounded context, approved tools, and a clear deliverable. Do not create a specialist just to compensate for weak routing or vague prompts; first fix the parent prompt/tool/session contract and use builder telemetry to prove where the boundary actually fails.
