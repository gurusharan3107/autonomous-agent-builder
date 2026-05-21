# Knowledge Base

This is the single owner doc for the repo-local knowledge base under `.agent-builder/knowledge/`. It covers the document format, extraction, linting, and retrieval contracts for `builder knowledge`. The structural pass/fail gate lives in [quality-gate/knowledge-base.md](quality-gate/knowledge-base.md).

## Overview

The KB serves two audiences:
- **Users:** readable knowledge cards in the dashboard with summary/detail panes.
- **Agents:** bounded retrieval through `builder knowledge summary/show/search` so prompts stay token-efficient.

The split happens across surfaces, not by degrading the authored page. The authored markdown stays readable; frontmatter and section shape make retrieval predictable; CLI surfaces provide the compact agent view.

Repo-local KB bytes should be created and maintained through `builder knowledge add` and `builder knowledge update`, not by scattering ad hoc markdown outside the knowledge root.

## Document Format

Canonical markdown contract for documents stored under `.agent-builder/knowledge/`. Use it for generator output, manual KB edits, dashboard rendering assumptions, `builder knowledge contract`, and `builder knowledge lint`.

When in doubt, `builder knowledge contract --type <doc_type>` is the source of truth for the latest machine-readable contract.

### Core Rules

- Start with valid YAML frontmatter bounded by `---`.
- Include an H1 that matches the document title.
- Write for retrieval and reading, not raw note dumps.
- Keep metadata short and body sections purposeful.
- Use bounded summaries for fast scanning; keep detailed proof in body sections.
- Keep the authored markdown readable for humans on the page; let `builder` retrieval surfaces provide the compact agent-facing adaptation.

### Required Frontmatter

| Field | Type | Notes |
|------|------|------|
| `title` | string | Max 100 chars |
| `tags` | array[string] | Max 10 tags |
| `doc_type` | string | Use a supported KB type |
| `created` | ISO 8601 timestamp | Creation time |
| `auto_generated` | boolean | `true` for generated docs |
| `version` | integer | `>= 1` |

### Optional Frontmatter

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

Tags are first-class retrieval fields across the whole KB. `builder knowledge add/update` should stamp the tags the dashboard and CLI need to filter on, such as `feature`, `testing`, `onboarding`, `browser`.

`card_summary` and `detail_summary` are the bridge between the human doc and the agent-facing CLI. They let `builder` produce compact retrieval output without forcing the whole document body to read like a machine payload.

### Supported Document Types

`context`, `adr`, `api_contract`, `schema`, `runbook`, `system-docs`, `feature`, `testing`, `metadata`, `raw`.

### System-Docs Contract

System docs are the local repo knowledge contract used by `builder knowledge`.

**Presentation fields** (kept separate from body for bounded fetch):

| Field | Max words | Purpose |
|------|-----------|---------|
| `card_summary` | 18 | Result-card preview; repo-specific, not generic framing |
| `detail_summary` | 58 | Reading-pane summary; explains what the doc covers and why it matters |

**Required sections:**

```markdown
# Title

## Overview
## Boundaries
## Invariants
## Evidence
## Change guidance
```

**Section budgets:**

| Section | Purpose | Budget |
|--------|---------|--------|
| `Overview` | Summarize the surface and why it matters | 30-80 words |
| `Boundaries` | Name owning paths, entrypoints, and adjacent surfaces | 20-90 words |
| `Invariants` | List contracts or truths that must remain intact | 20-120 words |
| `Evidence` | Preserve the detailed proof, examples, subsections, or diagrams | 60-420 words |
| `Change guidance` | Tell the operator or agent how to change and verify the surface | 12-60 words |

**Writing guidance:**

- `card_summary` should fit the result list and lead with the actual finding.
- `detail_summary` should not repeat the `card_summary` verbatim.
- `Overview` explains the capability.
- `Boundaries` explains ownership and blast radius.
- `Invariants` lists constraints, not mini-summaries.
- `Evidence` carries the implementation proof.
- `Change guidance` says where to edit and how to verify.

### System Architecture Specialization

`System Architecture` is the clearest place to serve both audiences in one doc. It should:

- Lead with a user mental model before file-heavy proof.
- Include a Mermaid runtime or architecture diagram.
- End with an agent-oriented change map naming which surfaces own which kinds of changes and what data should be inspected first.

File paths are useful in the lower sections for agents; they should not be the first thing a user has to parse.

### System-Doc Families

- `system-docs`: seed repository docs generated deterministically from code and manifests.
- `feature`: maintained docs for product capabilities and behavior that the agent should keep current. Link to the active feature or task and record canonical `main` freshness baseline.
- `testing`: maintained verification docs telling the agent how to validate a feature (API and browser-based checks). Link to the active feature or task, include `last_verified_at`, record canonical `main` freshness baseline.
- `metadata`: freshness, provenance, coverage, and extraction status artifacts.

Seed `system-docs`, `feature`, and `testing` docs should use the same section shape unless a narrower family-specific contract is promoted later. Canonical freshness applies only to maintained `feature` and `testing` docs; deterministic seed `system-docs` remain governed by evidence manifests and dependency-hash freshness.

### Example System-Doc

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

## Extraction

`builder knowledge extract` generates seed system-docs for the current repository under `.agent-builder/knowledge/`.

This lane gives:
- Users readable repo documentation in the dashboard.
- Agents bounded, retrievable context through `builder knowledge`.
- One durable local knowledge surface for codebase understanding.

### Command

```bash
builder knowledge extract
builder knowledge extract --force
builder knowledge extract --json
builder knowledge extract --no-validate
```

`builder knowledge extract` is the canonical local KB orchestration surface. Onboarding and agent-triggered KB generation should consume this command's JSON contract instead of calling extractor or validator internals directly.

### Current Output Set

The extractor currently generates: `Project Overview`, `Technology Stack`, `Dependencies`, `System Architecture`, `Code Structure`, `Database Models`, `API Endpoints`, `Business Overview`, `Workflows and Orchestration`, `Configuration`, `Agent System`, `Extraction Metadata`.

These are published into the local KB collection and surfaced through the dashboard and CLI.

Embedded dashboard KB routes must resolve local knowledge from the app's configured project root, not from the process current working directory. When one Builder process serves a managed project from a different launch CWD, `/api/knowledge/*` and `/api/kb/*` still read, validate, list, and delete only that project's `.agent-builder/knowledge/` tree.

### Extraction Contract

Generated seed system docs follow the [Document Format](#document-format) contract: frontmatter with required metadata, `card_summary` for card preview, `detail_summary` for reading-pane summary, and body sections (`Overview` / `Boundaries` / `Invariants` / `Evidence` / `Change guidance`).

The extractor should produce precise summaries, not generic disclaimers like "this generated document...".

For `System Architecture` specifically, the generated doc should do three jobs in one pass:
- Give the user a product-level mental model of how the system works.
- Show a runtime diagram so the relationships are visible, not just described.
- Preserve an agent-oriented change map that names the owning surfaces and the data needed before making changes.

### Extraction Flow

1. Scan the checked-in repository.
2. Run the seed system-doc generators.
3. Normalize output into the KB markdown contract.
4. Publish docs into `.agent-builder/knowledge/system-docs/`.
5. Write `Extraction Metadata`.
6. Run lint plus deterministic validation by default; agent advisory is opt-in via `builder knowledge validate --use-agent`.
7. Return a machine-readable next-step contract for onboarding/agent consumers.

### Operational Notes

- Extraction works offline against the local repository.
- `--force` regenerates existing docs.
- The canonical seed collection is `.agent-builder/knowledge/system-docs/`.
- The canonical local KB owner is `.agent-builder/knowledge/`; `system-docs` is only one collection inside it.
- Maintained repo-local docs should be inserted through `builder knowledge add` or `builder knowledge update`, with tags that make filtering explicit.
- Maintained `feature` and `testing` docs should link to the active feature or task they gate, so freshness is machine-checkable during delivery.
- Validation is on by default; disable only for debugging with `--no-validate`.

## Linting

`builder knowledge lint` enforces the markdown contract for local KB documents before they reach the dashboard or downstream agent retrieval paths.

Linting is the **structural gate** — checks format and contract compliance. Quality evaluation is handled separately by `builder knowledge validate`.

### Command

```bash
builder knowledge lint
builder knowledge lint --strict
builder knowledge lint --verbose
builder knowledge lint --kb-dir system-docs
builder knowledge lint --content-file path/to/doc.md
```

### What Lint Checks

**Frontmatter:** valid YAML, required fields present, field type correctness, valid timestamps, bounded title and tag lengths.

**Body:** non-empty markdown body, at least one heading, minimum body length, section content not trivially empty.

**Structure:** expected heading hierarchy, system-doc required sections, readable markdown structure for parsing and dashboard rendering.

### System-Docs Enforcement

For `doc_type: system-docs`, `feature`, or `testing`, lint expects:

- H1 title matching the document title
- Sections: `Overview`, `Boundaries`, `Invariants`, `Evidence`, `Change guidance`

It also checks the presentation-oriented frontmatter shape when present: `card_summary`, `detail_summary`. These fields are optional, but generated seed system docs should include them.

For maintained `feature` and `testing` docs, the wider KB contract also expects task or feature linkage metadata plus freshness timestamps where applicable:

- `feature_id` or `linked_feature`
- `task_id` when the doc is task-specific
- `updated` when `refresh_required: true`
- `last_verified_at` for `testing` docs

### Strict Mode

`--strict` promotes warnings to failures. Use it when:

- Regenerating the local seed system-doc corpus.
- Changing extractor prompts or generator logic.
- Tightening the KB contract.

### Single-Document Lanes

For targeted debugging:

```bash
builder knowledge lint --content-file docs/sample.md
builder knowledge lint --content-file -
builder knowledge lint --content "..."
```

Fastest way to test a draft contract without writing into the KB tree first.

### Recommended Workflow

For generator or contract changes:

```bash
builder knowledge contract --type system-docs
builder knowledge extract --force
builder knowledge lint --strict --kb-dir system-docs
builder knowledge validate
```

For manual doc edits:

```bash
builder knowledge lint --content-file path/to/doc.md
```

### Lint vs Validate

| Command | Purpose |
|--------|---------|
| `builder knowledge lint` | Contract and formatting gate |
| `builder knowledge validate` | Quality and usefulness gate |

Use both. Lint prevents malformed docs; validate judges whether docs are actually useful.

`builder knowledge lint --help` currently exposes: `--kb-dir`, `--content`, `--content-file`, `--strict`, `--verbose`. If this changes, update this doc.

## Retrieval

Extraction is only half the contract. Retrieval matters just as much.

### Default Agent Lane

Use bounded retrieval first:

```bash
builder knowledge summary "workflows"
builder knowledge show workflows-and-orchestration --section Evidence
builder knowledge show workflows-and-orchestration --json
```

`builder knowledge summary <query>` is the agent-safe default because it returns a compact slice: card summary, detail summary, boundaries, top invariants, change guidance.

### Deeper Reads

Escalate only when needed:

```bash
builder knowledge show <doc>
builder knowledge show <doc> --section <heading>
builder knowledge show <doc> --full
```

Use `--section` before `--full` to stay token-efficient.

### User vs Agent Reading Shapes

| Audience | Surface |
|---|---|
| User-facing | Card preview from `card_summary`, reading-pane summary from `detail_summary`, full body sections for deeper understanding |
| Agent-facing | `builder knowledge summary <query>` for bounded context, `builder knowledge show <doc> --section <heading>` for targeted expansion, `builder knowledge show <doc> --full` only when full prose is necessary |

The UI should stay readable. The CLI should stay token-efficient.

### Design Goals

**For users:** readable knowledge cards, concise reading-pane summaries, clear section hierarchy, proof preserved in the body.

**For agents:** bounded default retrieval, stable `--json` contract, selective section fetches, low-token orientation before deep reads.

## Validation Commands

```bash
# Format / contract
builder knowledge contract --type system-docs

# Lint
builder knowledge lint
builder knowledge lint --strict
builder knowledge lint --verbose
builder knowledge lint --kb-dir system-docs
builder knowledge lint --content-file path/to/doc.md

# Extract
builder knowledge extract
builder knowledge extract --force
builder knowledge extract --json
builder knowledge extract --no-validate

# Validate (quality)
builder knowledge validate
builder knowledge validate --use-agent

# Retrieve
builder knowledge summary "<query>"
builder knowledge show <doc>
builder knowledge show <doc> --section <heading>
builder knowledge show <doc> --full
builder knowledge show <doc> --json
```

## Related Docs

- [quality-gate/knowledge-base.md](quality-gate/knowledge-base.md) — pass/fail expectations for KB freshness and contract compliance
- [claude-agent-sdk-integration.md](claude-agent-sdk-integration.md) — KB freshness within the runtime contract
- [goal/INDEX.md](goal/INDEX.md) — owner-map placement
