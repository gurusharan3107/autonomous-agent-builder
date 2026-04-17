Always read ~/.claude/CLAUDE.md on session start and then read project local CLAUDE.md

## Triggers

| When | Command | Purpose |
|------|---------|---------|
| BEFORE dashboard changes | `python $HOME/.claude/bin/workflow.py --docs-dir docs summary design-language` | Visual identity |
| BEFORE technical decisions | `python $HOME/.claude/bin/workflow.py memory search --entity <entity> "<query>"` | Check precedent |
| AFTER dashboard changes | `./scripts/deploy_dashboard.ps1` | Build frontend |
| AFTER non-obvious decisions | `python $HOME/.claude/bin/workflow.py memory add --type decision ...` | Document with Trace |
| AFTER friction | Encode in `.kiro/steering/<topic>.md` | Prevent recurrence |
| END of session | Follow Self-Introspection section below | Continuous improvement |

## When to Check What

| Scenario | Check | Command |
|----------|-------|---------|
| Starting task | Memory for precedent | `python $HOME/.claude/bin/workflow.py memory search "<query>"` |
| Unfamiliar workflow | Workflow doc | `python $HOME/.claude/bin/workflow.py --docs-dir docs/workflows summary <name>` |
| Dashboard/frontend work | Design language | `python $HOME/.claude/bin/workflow.py --docs-dir docs summary design-language` |
| Editing CLAUDE.md | Quality gate | `python $HOME/.claude/bin/workflow.py summary claude-md-quality-gate` |
| Creating docs | Doc creation guide | `python $HOME/.claude/bin/workflow.py summary workflow-doc-creation` |
| Architecture decisions | Principles | `python $HOME/.claude/bin/workflow.py summary AGENT-PRINCIPLES` |
| Repeated friction | Steering files | Auto-loaded (`.kiro/steering/*.md`) |
| Quick command lookup | AGENTS.md | Always loaded (this file) |
| Project context | CLAUDE.md | Always loaded (read first) |

## Quick Commands

| Command | Purpose |
|---------|---------|
| `./scripts/deploy_dashboard.ps1` | Build frontend |
| `builder start --port 9876` | Start server |
| `Get-NetTCPConnection -LocalPort 9876` | Check server |
| `listProcesses` | List processes |
| `pytest --collect-only` | Collect tests |
| `python $HOME/.claude/bin/workflow.py summary <name>` | Load doc |
| `python $HOME/.claude/bin/workflow.py memory list` | List memories |

## Surface Ownership

| Surface | Content | When |
|---------|---------|------|
| AGENTS.md | Triggers, commands, ≤3 lines | Always-visible |
| Steering | Patterns, ❌/✅, friction | Repeated mistakes |
| Workflow docs | Multi-step procedures | Infrequent + complex |
| Scripts | Executable automation | Repetitive commands |
| CLAUDE.md | Project rules, architecture | Project-specific |
| Memory | Decisions, patterns, corrections | Non-obvious choices |

## Compression & Deduplication Doctrine

**Every word = token. Every token = precious.**

### Compression Rules
- Sacrifice grammar for brevity
- No over-explanation
- Every line carries weight
- Remove filler words
- Use tables over prose
- ❌/✅ format over paragraphs
- Commands over descriptions

### Deduplication Rules
- One source of truth per concept
- No repetition across surfaces
- Reference, don't duplicate
- If in CLAUDE.md, not in AGENTS.md
- If in steering, not in AGENTS.md
- Memory captures decisions, not patterns already in code

### Audit Checklist
- Can this be said in fewer words?
- Is this duplicated elsewhere?
- Does every line add new information?
- Can prose become a table?
- Can explanation become example?
- Is this obvious from context?

### Examples

❌ **Verbose:**
```
The workflow CLI has a problem on Windows where the PowerShell 
wrapper doesn't expand the $HOME variable correctly, which causes 
it to hang. To work around this issue, you should use Python directly.
```

✅ **Compressed:**
```
Windows: `workflow` hangs. Use `python $HOME/.claude/bin/workflow.py`.
```

❌ **Duplicated:**
- AGENTS.md: "Use MCP Chrome DevTools for testing"
- Steering: "Use MCP Chrome DevTools for testing"
- Memory: "Decision to use MCP Chrome DevTools"

✅ **Deduplicated:**
- AGENTS.md: `mcp_chrome_devtools_*` (commands only)
- Memory: Decision with Trace (why, not what)
- Steering: (removed - covered by AGENTS.md)

## Decision Tree

1. ≤3 lines? → AGENTS.md
2. Repeated mistake? → Steering (`.kiro/steering/`)
3. Complex workflow? → Workflow doc (`docs/workflows/`) + trigger
4. Repetitive commands? → Script (`scripts/`) + AGENTS.md
5. Non-obvious decision? → Memory (`.memory/`)
6. Project-specific? → CLAUDE.md

## Self-Introspection

**When:** End of session OR after significant friction

**Check:**
- Repeated mistakes?
- Wrong tool/command?
- Platform issues?
- Server/process confusion?
- Non-obvious decision?
- **Verbose content?**
- **Duplication across surfaces?**

**Actions by type:**

| What | Where | Command |
|------|-------|---------|
| Repeated mistake pattern | Steering | Create `.kiro/steering/<topic>.md` |
| Non-obvious decision | Memory (decision) | `workflow memory add --type decision --phase <phase> --entity <entity> --tags "<tags>" "<title>"` |
| Validated approach | Memory (pattern) | `workflow memory add --type pattern --phase <phase> --entity <entity> --tags "<tags>" "<title>"` |
| Mistake to prevent | Memory (correction) | `workflow memory add --type correction --phase <phase> --entity <entity> --tags "<tags>" "<title>"` |
| Quick command | AGENTS.md | Edit this file (if ≥3 uses) |
| Complex procedure | Workflow doc | Create `docs/workflows/<name>.md` |

**Memory criteria (must have ≥1):**
- Exception granted to policy
- Tradeoff between competing concerns
- Prior precedent invoked
- Mistake worth preventing
- Non-obvious approach validated

**NOT memory:**
- Obvious from code/config
- Standard practices
- Temporary workarounds
- Implementation details

**Compress:** ≤50% original length. **Deduplicate:** one source of truth.

## Testing

Dashboard: MCP Chrome DevTools (not curl). See: `python $HOME/.claude/bin/workflow.py --docs-dir docs/workflows summary chrome-devtools-dashboard-testing`
