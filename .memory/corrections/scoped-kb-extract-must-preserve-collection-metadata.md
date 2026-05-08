---
title: Scoped KB extract must preserve collection metadata
type: correction
date: 2026-04-23
phase: implementation
entity: knowledge
tags: [kb, knowledge, extractor, metadata, validation]
status: active
---

## Correction

Targeted `builder knowledge extract --doc ...` runs must preserve the collection-wide `expected_documents` and `blocking_documents` recorded in `extraction-metadata.md`. A scoped refresh that rewrites metadata to only the targeted doc makes `builder knowledge validate --json` report misleading freshness or missing-doc failures. If KB validation regresses right after a targeted extract, inspect `extraction-metadata.md` first before chasing unrelated validator noise.

## Agent Retrieval Summary

Retrieve this memory when working on knowledge, implementation, or related correction changes. Use it to preserve the repo-local precedent: Targeted builder knowledge extract --doc ...

## User-Facing Summary

Targeted builder knowledge extract --doc ...

## Reusable Guidance

- Treat this as repo-local correction precedent for knowledge.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch knowledge, the implementation phase, or related tags: kb, knowledge, extractor, metadata, validation.

## Retrieval Queries

- scoped kb extract must preserve collection metadata
- knowledge
- implementation
- kb
- extractor
- metadata
- validation
