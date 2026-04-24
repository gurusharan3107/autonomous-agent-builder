---
title: Project memory captures real-time friction precedent
type: decision
date: 2026-04-18
phase: design
entity: memory-cli
tags: [memory, friction, retrieval]
status: active
---

## Decision

Treat project memory as a real-time friction and precedent surface: record what failed, what worked, and what future agents should do instead when the same codebase situation recurs.

## Trace

- Inputs: While implementing builder memory lifecycle commands, the user clarified that memory is generated during active code work to prevent repeated mistakes on similar actions.
- Why this matters: Without this framing, memory drifts into generic progress logging instead of retrieval-grade operational precedent.
- Operational effect: Favor memory entries for reusable corrections, decisions, and patterns tied to concrete repo friction; do not use memory as a session changelog.
