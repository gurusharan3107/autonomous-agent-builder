# Workflow CLI Usage

Quick reference for the workflow command-line tool.

## Summary Commands

Load reference documents:
```bash
workflow summary <name>                    # From ~/.claude/docs/
workflow --docs-dir <dir> summary <name>   # From custom directory
```

Examples:
```bash
workflow summary claude-md-quality-gate
workflow --docs-dir docs summary design-language
workflow --docs-dir docs/workflows summary memory-retrieval-guide
```

## Project Memory Commands

Project-local memory is owned by `builder memory`. Use `workflow` here for docs/knowledge retrieval, not as the default project-memory lane.

### List Memories
```bash
builder memory list                        # All memories
builder memory list --phase planning       # Filter by phase
builder memory list --type decision        # Filter by memory type
builder memory list --entity orchestrator  # Filter by entity
```

Output format: `- [category] Title (filename.md)`

### Search Memories
```bash
builder memory search "query text"         # Search all
builder memory search --entity api "endpoint"   # Filter by entity
```

Returns first 500 chars of matching memories with title and filename.

### Add Memory
```bash
builder memory contract --json
builder memory add --type decision --phase planning --entity orchestrator --tags "routing,dispatch" --title "Use deterministic dispatch" --content-file memory.md --json
builder memory add --type correction --phase implementation --entity security --tags "bash,argv" --title "Never use shell=True" --content-file memory.md --json
builder memory add --type pattern --phase testing --entity gates --tags "concurrency,asyncio" --title "Run gates with asyncio.gather" --content-file memory.md --json
```

Creates file in `.memory/{type}s/` with frontmatter and template structure. The
content must follow the template from `builder memory contract --json`:

- `## Decision`, `## Pattern`, or `## Correction`
- `## Agent Retrieval Summary`
- `## User-Facing Summary`
- `## Reusable Guidance`
- `## When To Apply`
- `## Retrieval Queries`

Successful mutating commands return `post_mutation` evidence in JSON:
`reindexed`, `lint_passed`, `retrieval_checked`, `retrieval_passed`, and
`retrieved_slug`. If post-mutation lint or retrieval fails, the command exits
non-zero with the failed evidence included.

## Memory Types

- **decision**: Durable product or architecture choice with retrieval-ready context.
- **correction**: Mistake or stale assumption that future agents must avoid.
- **pattern**: Validated approach that should be reused under clear conditions.

## Memory Structure

```
.memory/
├── decisions/          # Decision memories
├── patterns/           # Pattern memories
├── corrections/        # Correction memories
├── INDEX.md           # Human-readable index (auto-generated)
└── routing.json       # Machine-readable routing metadata
```

Each memory has frontmatter:
```yaml
---
type: decision|pattern|correction
phase: design|planning|implementation|testing
entity: component-name
tags: [tag1, tag2, tag3]
status: active|superseded|graduated|invalidated|pruned|flagged
date: YYYY-MM-DD
---
```

## Common Workflows

**Before making a decision:**
```bash
builder memory search --entity <component> "what you're deciding"
```

**After making a decision:**
```bash
builder memory contract --json
builder memory add --type decision --phase <phase> --entity <component> --tags "<tags>" --title "Decision title" --content-file memory.md --json
```

**Check project memories:**
```bash
builder memory list --type decision
```

**Load workflow doc:**
```bash
workflow --docs-dir docs/workflows summary <workflow-name>
```

**Find memories by phase:**
```bash
builder memory list --phase design
```

**Search within entity:**
```bash
builder memory search --entity orchestrator "routing"
```
