# Knowledge Extraction

## Purpose

`builder knowledge extract` generates seed system-docs for the current repository under `.agent-builder/knowledge/`.

This lane exists to give:

- users readable repo documentation in the dashboard
- agents bounded, retrievable context through `builder knowledge`
- one durable local knowledge surface for codebase understanding

## Command

```bash
builder knowledge extract
builder knowledge extract --force
builder knowledge extract --json
builder knowledge extract --no-validate
```

`builder knowledge extract` is the canonical local KB orchestration surface. Onboarding
and agent-triggered KB generation should consume this command's JSON contract
instead of calling extractor or validator internals directly.

## Current Output Set

The extractor currently generates these seed system docs:

- `Project Overview`
- `Technology Stack`
- `Dependencies`
- `System Architecture`
- `Code Structure`
- `Database Models`
- `API Endpoints`
- `Business Overview`
- `Workflows and Orchestration`
- `Configuration`
- `Agent System`
- `Extraction Metadata`

These are published into the local KB collection and surfaced through the dashboard and CLI.

## Extraction Contract

Generated seed system docs follow the contract described in [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md):

- frontmatter with required metadata
- `card_summary` for result-card preview
- `detail_summary` for reading-pane summary
- body sections:
  - `Overview`
  - `Boundaries`
  - `Invariants`
  - `Evidence`
  - `Change guidance`

The extractor should produce precise summaries, not generic disclaimers like “this generated document...”.

For `System Architecture` specifically, the generated doc should do three jobs in one pass:

- give the user a product-level mental model of how the system works
- show a runtime diagram so the relationships are visible, not just described
- preserve an agent-oriented change map that names the owning surfaces and the data needed before making changes

## Retrieval Model

Extraction is only half the contract. Retrieval matters just as much.

### Default Agent Lane

Use bounded retrieval first:

```bash
builder knowledge summary "workflows"
builder knowledge show workflows-and-orchestration --section Evidence
builder knowledge show workflows-and-orchestration --json
```

`builder knowledge summary <query>` is the agent-safe default because it returns a compact slice:

- card summary
- detail summary
- boundaries
- top invariants
- change guidance

### Deeper Reads

Escalate only when needed:

```bash
builder knowledge show <doc>
builder knowledge show <doc> --section <heading>
builder knowledge show <doc> --full
```

Use `--section` before `--full` to stay token-efficient.

## Extraction Flow

1. Scan the checked-in repository.
2. Run the seed system-doc generators.
3. Normalize output into the KB markdown contract.
4. Publish docs into `.agent-builder/knowledge/system-docs/`.
5. Write `Extraction Metadata`.
6. Run lint plus deterministic validation by default; agent advisory is opt-in via `builder knowledge validate --use-agent`.
7. Return a machine-readable next-step contract for onboarding/agent consumers.

## Design Goals

### For Users

- readable knowledge cards
- concise reading-pane summaries
- clear section hierarchy
- proof preserved in the body

### For Agents

- bounded default retrieval
- stable `--json` contract
- selective section fetches
- low-token orientation before deep reads

## Operational Notes

- Extraction works offline against the local repository.
- `--force` regenerates existing docs.
- The canonical seed collection is `.agent-builder/knowledge/system-docs/`.
- The canonical local KB owner is `.agent-builder/knowledge/`; `system-docs` is only one collection inside it.
- Maintained repo-local docs should be inserted through `builder knowledge add` or `builder knowledge update`, with tags that make filtering explicit.
- Maintained `feature` and `testing` docs should link to the active feature or task they gate, so freshness is machine-checkable during delivery.
- Validation is on by default; disable only for debugging with `--no-validate`.

## Verification

```bash
builder knowledge extract --force
builder knowledge lint
builder knowledge validate
builder knowledge summary "technology stack"
builder knowledge show technology-stack --section Evidence
```

## Related Docs

- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md)
- [knowledge-document-linting.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-linting.md)
- [quality-gate/knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
