---
title: Documentation agent maintains shared user and agent KB
type: decision
date: 2026-04-22
phase: implementation
entity: documentation-agent
tags: [kb, docs, agent, system-docs]
status: active
---

## Decision

The embedded documentation-agent owns repo-local knowledge maintenance for both human users and future agents. It should refresh broader app context through the canonical builder knowledge extract lane for system-docs and keep maintained feature docs agent-friendly with purpose, key files, change guidance, verification, and reminders. It must stay within .agent-builder/knowledge and not write memory or docs/.

## Agent Retrieval Summary

Retrieve this memory when working on documentation-agent, implementation, or related decision changes. Use it to preserve the repo-local precedent: The embedded documentation-agent owns repo-local knowledge maintenance for both human users and future agents.

## User-Facing Summary

The embedded documentation-agent owns repo-local knowledge maintenance for both human users and future agents.

## Reusable Guidance

- Treat this as repo-local decision precedent for documentation-agent.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch documentation-agent, the implementation phase, or related tags: kb, docs, agent, system-docs.

## Retrieval Queries

- documentation agent maintains shared user and agent kb
- documentation-agent
- implementation
- kb
- docs
- agent
- system-docs
