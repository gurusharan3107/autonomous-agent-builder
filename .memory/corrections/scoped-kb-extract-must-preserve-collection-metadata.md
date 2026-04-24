---
title: Scoped KB extract must preserve collection metadata
type: correction
date: 2026-04-23
phase: implementation
entity: knowledge
tags: [kb, knowledge, extractor, metadata, validation]
status: active
---

Targeted `builder knowledge extract --doc ...` runs must preserve the collection-wide `expected_documents` and `blocking_documents` recorded in `extraction-metadata.md`. A scoped refresh that rewrites metadata to only the targeted doc makes `builder knowledge validate --json` report misleading freshness or missing-doc failures. If KB validation regresses right after a targeted extract, inspect `extraction-metadata.md` first before chasing unrelated validator noise.
