---
title: Workflow and memory creation ONLY via CLIs
type: decision
date: 2026-04-20
phase: implementation
entity: documentation-creation
tags: [workflow, builder, cli-only]
status: active
---

## Decision

Never use direct Write/Edit for docs or memory. Use 'builder' and 'workflow' CLIs only. This ensures: proper metadata tracking, searchability, version control, audit trail.

## Agent Retrieval Summary

Retrieve this memory when working on documentation-creation, implementation, or related decision changes. Use it to preserve the repo-local precedent: Never use direct Write/Edit for docs or memory.

## User-Facing Summary

Never use direct Write/Edit for docs or memory.

## Reusable Guidance

- Treat this as repo-local decision precedent for documentation-creation.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch documentation-creation, the implementation phase, or related tags: workflow, builder, cli-only.

## Retrieval Queries

- workflow and memory creation only via clis
- documentation-creation
- implementation
- workflow
- builder
- cli-only
