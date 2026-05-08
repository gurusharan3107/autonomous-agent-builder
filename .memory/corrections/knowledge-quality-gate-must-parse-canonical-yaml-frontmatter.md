---
title: Knowledge quality gate must parse canonical YAML frontmatter tags
type: correction
date: 2026-04-19
phase: implementation
entity: knowledge-quality-gate
tags: [knowledge, quality-gate, yaml, retrieval]
status: active
---

## Correction

## Constraint
The rule-based local KB quality gate must validate canonical YAML frontmatter, not a formatting accident. Reverse-engineering docs are published through the canonical builder writer, which emits block-style YAML lists for tags and optional wikilinks.

## What Went Wrong
The searchability check in `src/autonomous_agent_builder/knowledge/quality_gate.py` only looked for inline `tags: [a, b]` syntax with a regex. The extractor and publisher were already generating correct block-style YAML lists, so the rule-based gate incorrectly reported `0.0 tags per document` and failed searchability even when the corpus had strong tags. That created a false quality failure and pointed work at the generated docs instead of the gate.

## What To Do Instead
Parse frontmatter with the same YAML-safe approach used by the KB stack, then count tags from the parsed list. Treat canonical YAML as the contract, keep tag thresholds the same unless there is a real product reason to change them, and add regression tests that prove block-style YAML tag lists pass searchability.

## Agent Retrieval Summary

Retrieve this memory when working on knowledge-quality-gate, implementation, or related correction changes. Use it to preserve the repo-local precedent: Constraint The rule-based local KB quality gate must validate canonical YAML frontmatter, not a formatting accident.

## User-Facing Summary

Constraint The rule-based local KB quality gate must validate canonical YAML frontmatter, not a formatting accident.

## Reusable Guidance

- Treat this as repo-local correction precedent for knowledge-quality-gate.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch knowledge-quality-gate, the implementation phase, or related tags: knowledge, quality-gate, yaml, retrieval.

## Retrieval Queries

- knowledge quality gate must parse canonical yaml frontmatter tags
- knowledge quality gate must parse canonical yaml frontmatter
- knowledge-quality-gate
- implementation
- knowledge
- quality-gate
- yaml
- retrieval
