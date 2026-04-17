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
workflow --docs-dir docs/workflows summary chrome-devtools-dashboard-testing
```

## Memory Commands

### List Memories
```bash
workflow memory list                       # All memories
workflow memory list --phase planning      # Filter by phase
workflow memory list --status active       # Filter by status
```

Output format: `- [category] Title (filename.md)`

### Search Memories
```bash
workflow memory search "query text"        # Search all
workflow memory search --entity api "endpoint"  # Filter by entity
```

Returns first 500 chars of matching memories with title and filename.

### Add Memory
```bash
workflow memory add --type decision --phase planning --entity orchestrator --tags "routing,dispatch" "Use deterministic dispatch"
workflow memory add --type correction --phase implementation --entity security --tags "bash,argv" "Never use shell=True"
workflow memory add --type pattern --phase testing --entity gates --tags "concurrency,asyncio" "Run gates with asyncio.gather"
```

Creates file in `.memory/{type}s/` with frontmatter and template structure.

## Memory Types

- **decision**: Tradeoffs, exceptions, precedent-based choices (Trace: Inputs, Policy, Exception, Approval)
- **correction**: Mistakes to prevent, constraints violated (Constraint, What Went Wrong, What To Do Instead)
- **pattern**: Validated approaches to reuse (Context, Approach, Benefits)

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
status: active|superseded|graduated
date: YYYY-MM-DD
---
```

## Common Workflows

**Before making a decision:**
```bash
workflow memory search --entity <component> "what you're deciding"
```

**After making a decision:**
```bash
workflow memory add --type decision --phase <phase> --entity <component> --tags "<tags>" "Decision title"
```

**Check project memories:**
```bash
workflow memory list --status active
```

**Load workflow doc:**
```bash
workflow --docs-dir docs/workflows summary <workflow-name>
```

**Find memories by phase:**
```bash
workflow memory list --phase design
```

**Search within entity:**
```bash
workflow memory search --entity orchestrator "routing"
```
