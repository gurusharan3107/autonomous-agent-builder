---
title: "Knowledge Base quality gate"
surface: "knowledge-base"
summary: "`builder knowledge validate` is the review gate for repo-local knowledge quality: deterministic validation stays authoritative, and maintained docs remain verifiable and fresh."
commands:
  - "builder knowledge validate"
  - "builder knowledge validate --verbose"
  - "builder knowledge validate --json"
  - "builder knowledge validate --use-agent"
  - "builder knowledge validate --use-agent --model claude-opus-4-7"
expectations:
  - "deterministic validation remains authoritative for the seed system-doc corpus"
  - "maintained knowledge docs remain current enough that validation and delivery checks can rely on them"
  - "seed system docs remain the deterministic corpus generated from the checked-in codebase"
  - "feature and testing docs stay inside the maintained local knowledge system instead of drifting into ad hoc notes"
  - "maintained feature and testing docs keep the links needed for delivery-time freshness checks"
  - "maintained feature and testing docs record a canonical `main` commit baseline plus owned paths for diff-bounded freshness checks"
  - "deterministic validation remains authoritative even when agent advisory runs"
  - "ready=true in onboarding depends on the deterministic result, not the advisory result"
  - "the blocking-doc set stays explicit and machine-verifiable"
  - "retrieval remains separate from validation; use builder knowledge summary/show for reading"
  - "authored knowledge docs stay readable for human operators while builder retrieval surfaces provide the compact agent-facing view"
related_docs:
  - "docs/knowledge-extraction.md"
  - "docs/knowledge-document-format.md"
  - "docs/knowledge-document-linting.md"
  - "docs/claude-agent-sdk-integration.md"
---

# Knowledge Base Quality Gate

## Purpose

`builder knowledge validate` is the quality gate for the repo-local knowledge base
under `.agent-builder/knowledge/`.

Use it after extraction or major knowledge-contract changes to check whether
the local corpus is still valid, fresh enough to rely on, and correctly split
between deterministic blocking docs and broader maintained docs.

## Current Authoritative Enforcement

Today, the deterministic validator is authoritative for the seed system-doc
corpus and its blocking docs.

This gate is the validation contract, not the owner doc for the whole
knowledge system.

## Validation Modes

### Deterministic

Default mode validates only the currently blocking docs through evidence
manifests. The default blocking set is promoted per doc; at this stage the
authoritative blocking docs are:

- `system-architecture`
- `dependencies`
- `technology-stack`

The deterministic gate checks:

- blocking-doc presence
- shared manifest schema
- allowed blocking claim types
- live citation resolution
- dependency-hash freshness
- maintained-doc commit baselines against `main`
- unresolved or contradicted blocking claims

`ready=true` in onboarding depends on this deterministic result, not on agent
advisory output.

### Agent Advisory

Use `--use-agent` when you want Claude to review the generated KB after the
deterministic gate completes. Advisory results never convert a deterministic
failure into a pass.

Auth note:

- agent advisory depends on Claude being authenticated through Claude Code's
  supported auth surfaces
- deterministic validation remains authoritative even when advisory runs
- see [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
  for the repo-specific auth model and local CLI env bootstrap behavior

## Recommended Pipeline

```bash
builder knowledge extract --force
builder knowledge lint --strict --kb-dir system-docs
builder knowledge validate
```

When maintained system docs are introduced beyond the seed system-doc
collection, the review question remains the same: are they current enough and
linked well enough that delivery-time validation can rely on them?

For maintained `feature` and `testing` docs, canonical freshness should stay
anchored to the repo's canonical baseline branch. In this repo that is `main`.
The baseline contract lives in
[main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md):

- `documented_against_ref` should match the repo's canonical baseline branch
- `documented_against_commit` should record the last canonical baseline commit
- `owned_paths` should bound diff-based stale detection and refresh selection
- older maintained docs may show migration warnings until they are backfilled,
  but newly refreshed docs should stamp the canonical fields

If you need to debug extraction without blocking on the quality gate:

```bash
builder knowledge extract --force --no-validate
```

If you need to confirm the documented Claude auth state before the agent lane:

```bash
claude auth status
```

## What Good Output Looks Like

A strong validation target should:

- cover the expected local repo surfaces through deterministic seed docs
- keep maintained system docs aligned with current features, workflows, and
  verification behavior
- use precise `card_summary` and `detail_summary` fields
- keep `Overview`, `Boundaries`, and `Invariants` distinct
- preserve implementation proof in `Evidence`
- tell the operator or agent what to edit and verify in `Change guidance`
- make testing expectations discoverable so the agent can follow the repo's API
  or browser validation path without broad re-search
- mark non-blocking docs as non-authoritative until they are promoted
- preserve the dual-audience split: readable markdown body for humans, bounded
  retrieval summaries for agents

## Validation vs Retrieval

Validation checks quality. Retrieval keeps context bounded.

Do not optimize by making the authored markdown body read like a compact
machine payload. The document should remain readable on the page; the compact
agent-oriented view belongs to `builder knowledge summary/show/search`.

The intended consumption path remains:

```bash
builder knowledge summary "query"
builder knowledge show <doc> --section Evidence
builder knowledge show <doc> --json
```

Do not use the quality gate as the primary retrieval surface.

## Current CLI Help Surface

`builder knowledge validate --help` currently exposes:

- `--kb-dir`
- `--json`
- `--verbose`
- `--use-agent / --no-use-agent`
- `--model`

## Related Docs

- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md)
- [knowledge-extraction.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-extraction.md)
- [knowledge-document-linting.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-linting.md)
- [main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md)
