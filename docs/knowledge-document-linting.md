# Knowledge Document Linting

## Purpose

`builder knowledge lint` enforces the markdown contract for local KB documents before they reach the dashboard or downstream agent retrieval paths.

Linting is the structural gate. It checks format and contract compliance.
Quality evaluation is handled separately by `builder knowledge validate`.

## Command

```bash
builder knowledge lint
builder knowledge lint --strict
builder knowledge lint --verbose
builder knowledge lint --kb-dir system-docs
builder knowledge lint --content-file path/to/doc.md
```

## What Lint Checks

### Frontmatter

- valid YAML
- required fields present
- field type correctness
- valid timestamps
- bounded title and tag lengths

### Body

- non-empty markdown body
- at least one heading
- minimum body length
- section content not trivially empty

### Structure

- expected heading hierarchy
- system-doc required sections
- readable markdown structure for parsing and dashboard rendering

## System-Docs Enforcement

For `doc_type: system-docs`, `feature`, or `testing`, lint expects:

- H1 title matching the document title
- `Overview`
- `Boundaries`
- `Invariants`
- `Evidence`
- `Change guidance`

It also checks the new presentation-oriented frontmatter shape when present:

- `card_summary`
- `detail_summary`

These fields are optional, but generated seed system docs should include them.

For maintained `feature` and `testing` docs, the wider KB contract also expects task or feature linkage metadata plus freshness timestamps where applicable:

- `feature_id` or `linked_feature`
- `task_id` when the doc is task-specific
- `updated` when `refresh_required: true`
- `last_verified_at` for `testing` docs

## Strict Mode

`--strict` promotes warnings to failures.

Use it when:

- regenerating the local seed system-doc corpus
- changing extractor prompts or generator logic
- tightening the KB contract

## Single-Document Lanes

For targeted debugging:

```bash
builder knowledge lint --content-file docs/sample.md
builder knowledge lint --content-file -
builder knowledge lint --content "..."
```

This is the fastest way to test a draft contract without writing into the KB tree first.

## Recommended Workflow

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

## Lint vs Validate

| Command | Purpose |
|--------|---------|
| `builder knowledge lint` | Contract and formatting gate |
| `builder knowledge validate` | Quality and usefulness gate |

Use both. Lint prevents malformed docs; validate judges whether the docs are actually useful.

## Current CLI Help Surface

`builder knowledge lint --help` currently exposes:

- `--kb-dir`
- `--content`
- `--content-file`
- `--strict`
- `--verbose`

If this changes, update this doc and [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md) together.

## Related Docs

- [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md)
- [knowledge-extraction.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-extraction.md)
- [quality-gate/knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
