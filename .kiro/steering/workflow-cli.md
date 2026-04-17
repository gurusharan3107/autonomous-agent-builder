---
inclusion: auto
---

# Workflow CLI

Windows: `workflow` hangs. Use `python $HOME/.claude/bin/workflow.py` instead.

## Commands

```bash
# Docs
python $HOME/.claude/bin/workflow.py summary <name>
python $HOME/.claude/bin/workflow.py --docs-dir docs summary <name>

# Memory
python $HOME/.claude/bin/workflow.py memory list [--phase <phase>]
python $HOME/.claude/bin/workflow.py memory search "<query>"
python $HOME/.claude/bin/workflow.py memory add --type <type> --phase <phase> --entity <entity> --tags "<tags>" "Title"
```

Types: decision, correction, pattern
