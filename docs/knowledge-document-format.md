# Knowledge Document Format

## Purpose

This is the canonical markdown contract for documents stored under `.agent-builder/knowledge/`.
Use it for:

- generator output
- manual KB edits
- dashboard rendering assumptions
- `builder knowledge contract`
- `builder knowledge lint`

Repo-local KB bytes should be created and maintained through `builder knowledge add`
and `builder knowledge update`, not by scattering ad hoc markdown outside the
knowledge root. Subfolders are fine; the root owner remains `.agent-builder/knowledge/`.

When in doubt, treat `builder knowledge contract --type <doc_type>` as the source of truth for the latest machine-readable contract.

## Core Rules

- Start with valid YAML frontmatter bounded by `---`.
- Include an H1 that matches the document title.
- Write for retrieval and reading, not raw note dumps.
- Keep metadata short and body sections purposeful.
- Use bounded summaries for fast scanning; keep detailed proof in body sections.
- Keep the authored markdown readable for humans on the page; let `builder`
  retrieval surfaces provide the compact agent-facing adaptation.

## Required Frontmatter

Every KB document must include:

| Field | Type | Notes |
|------|------|------|
| `title` | string | Max 100 chars |
| `tags` | array[string] | Max 10 tags |
| `doc_type` | string | Use a supported KB type |
| `created` | ISO 8601 timestamp | Creation time |
| `auto_generated` | boolean | `true` for generated docs |
| `version` | integer | `>= 1` |

## Optional Frontmatter

Common optional fields:

| Field | Type | Notes |
|------|------|------|
| `updated` | ISO 8601 timestamp | Last update time |
| `wikilinks` | array[string] | Related local docs |
| `source_url` | string | For ingested external sources |
| `source_title` | string | Source display title |
| `source_author` | string | Source author |
| `date_published` | ISO date string | External publish date |
| `card_summary` | string | Short result-card summary |
| `detail_summary` | string | Longer reading-pane summary |
| `linked_feature` | string | Related feature identifier for maintained docs |
| `feature_id` | string | Stable feature linkage for maintained docs |
| `task_id` | string | Stable task linkage for maintained docs |
| `refresh_required` | boolean | Use `true` for maintained docs that must be refreshed as work changes |
| `documented_against_commit` | string | Canonical baseline-branch commit the maintained doc was last refreshed against |
| `documented_against_ref` | string | Canonical ref for maintained-doc freshness; use the repo's canonical branch (`main` in this repo) |
| `owned_paths` | array[string] | Repo-relative paths or directories used for diff-based freshness checks |
| `last_verified_at` | ISO 8601 timestamp | Required for testing docs |
| `verified_with` | string | Optional verification command or lane |

Tags are first-class retrieval fields across the whole knowledge base, not just
system-docs. `builder knowledge add/update` should stamp the tags you want the
dashboard and CLI to filter on, such as `feature`, `testing`, `onboarding`, or
`browser`.

`card_summary` and `detail_summary` are the main bridge between the human doc
and the agent-facing CLI. They should help `builder` produce compact retrieval
output without forcing the whole document body to read like a machine payload.

## Supported Document Types

Current KB types:

- `context`
- `adr`
- `api_contract`
- `schema`
- `runbook`
- `system-docs`
- `feature`
- `testing`
- `metadata`
- `raw`

## System-Docs Contract

System docs are the local repo knowledge contract used by `builder knowledge`.

### Presentation Fields

These are intentionally separate from the body so the UI and CLI can fetch bounded context:

| Field | Max words | Purpose |
|------|-----------|---------|
| `card_summary` | 18 | Result-card preview; repo-specific, not generic framing |
| `detail_summary` | 58 | Reading-pane summary; explains what the doc covers and why it matters |

### Required Sections

System docs must contain:

```markdown
# Title

## Overview
## Boundaries
## Invariants
## Evidence
## Change guidance
```

### Section Expectations

| Section | Purpose | Budget |
|--------|---------|--------|
| `Overview` | Summarize the surface and why it matters | 30-80 words |
| `Boundaries` | Name owning paths, entrypoints, and adjacent surfaces | 20-90 words |
| `Invariants` | List contracts or truths that must remain intact | 20-120 words |
| `Evidence` | Preserve the detailed proof, examples, subsections, or diagrams | 60-420 words |
| `Change guidance` | Tell the operator or agent how to change and verify the surface | 12-60 words |

### Writing Guidance

- `card_summary` should fit the result list and lead with the actual finding.
- `detail_summary` should not repeat the `card_summary` verbatim.
- `Overview` explains the capability.
- `Boundaries` explains ownership and blast radius.
- `Invariants` lists constraints, not mini-summaries.
- `Evidence` carries the implementation proof.
- `Change guidance` says where to edit and how to verify.

## User vs Agent Retrieval

The KB supports two different reading shapes:

- User-facing:
  - card preview from `card_summary`
  - reading-pane summary from `detail_summary`
  - full body sections for deeper understanding
- Agent-facing:
  - `builder knowledge summary <query>` for bounded context
  - `builder knowledge show <doc> --section <heading>` for targeted expansion
  - `builder knowledge show <doc> --full` only when full prose is necessary

The UI should stay readable. The CLI should stay token-efficient.

That split should happen across surfaces, not by degrading the authored page:

- the markdown body stays readable, structured, and evidence-backed
- frontmatter and section shape make retrieval predictable
- `builder knowledge summary/show/search` provide the bounded agent view

### System Architecture Specialization

`System Architecture` is the clearest place to serve both audiences in one doc.
It should therefore:

- lead with a user mental model before file-heavy proof
- include a Mermaid runtime or architecture diagram
- end with an agent-oriented change map that says which surfaces own which kinds of changes and what data should be inspected first

File paths are useful in the lower sections for agents. They should not be the first thing a user has to parse.

## System-Doc Families

- `system-docs`: seed repository docs generated deterministically from code and manifests.
- `feature`: maintained docs for product capabilities and behavior that the agent should keep current. These should link to the active feature or task they describe and record their canonical `main` freshness baseline.
- `testing`: maintained verification docs that tell the agent how to validate a feature, including API and browser-based checks. These should link to the active feature or task they gate, include `last_verified_at`, and record their canonical `main` freshness baseline.
- `metadata`: freshness, provenance, coverage, and extraction status artifacts.

Seed `system-docs`, `feature`, and `testing` docs should all use the same section shape unless a narrower family-specific contract is promoted later.

Canonical freshness applies only to maintained `feature` and `testing` docs. Deterministic seed `system-docs` remain governed by evidence manifests and dependency-hash freshness, not `documented_against_commit`.

## Example System-Doc

```markdown
---
title: "Workflows and Orchestration"
tags: ["workflow", "architecture", "agents"]
doc_type: "system-docs"
doc_family: "seed"
created: "2026-04-19T12:10:01.663609"
auto_generated: true
version: 1
card_summary: "Execution phases, orchestrator routing, and agent handoffs that move work through the delivery pipeline."
detail_summary: "Use this document to orient around execution phases, orchestrator routing, and the agent handoffs or retries that move work through the pipeline."
---

# Workflows and Orchestration

Short lede paragraph that frames why this surface matters.

## Overview
Describe the capability and why it matters.

## Boundaries
Name paths, entrypoints, and neighboring surfaces.

## Invariants
- Constraint one
- Constraint two

## Evidence
Preserve code-level proof, subsections, examples, or diagrams here.

## Change guidance
State where to edit and what to verify.
```

## Validation Commands

```bash
builder knowledge contract --type system-docs
builder knowledge lint
builder knowledge lint --strict
builder knowledge lint --verbose
builder knowledge lint --kb-dir system-docs
```

## Related Docs

- [knowledge-extraction.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-extraction.md)
- [knowledge-document-linting.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-linting.md)
- [quality-gate/knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
