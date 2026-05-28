# Audit lane — check skill conformance

Loaded when the operator picks Audit or types "audit / check / validate skill(s)".

Runs deterministic checks against agentskills.io spec and project standards.
Produces findings with severity: **hard** (must fix) or **soft** (should fix).

---

## Run

```bash
# Single skill
python3 ~/.claude/skills/create-skill/scripts/audit.py \
  ".claude/skills/<skill-name>"

# All local skills
python3 ~/.claude/skills/create-skill/scripts/audit.py --all

# Machine-readable
python3 ~/.claude/skills/create-skill/scripts/audit.py \
  ".claude/skills/<skill-name>" --json
```

If the global audit.py isn't available, run the inline quality-gate script
from [quality-gate.md](quality-gate.md) instead.

---

## Check IDs and remediation

| ID | Check | Severity | Fix |
|---|---|---|---|
| A01 | `name` frontmatter present | hard | Add `name: <kebab>` |
| A02 | `name` equals directory name | hard | Rename dir or frontmatter |
| A03 | `name` is kebab-case | hard | Rename to `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` |
| A04 | `description` present | hard | Add description field |
| A05 | `description` ≤1024 chars | soft | Shorten or use Refine lane |
| A06 | SKILL.md body ≤500 lines | soft | Move bulk to `reference/` |
| A07 | Hard Rules section present | soft | Add `## Hard Rules` |
| A08 | Workflow section present | soft | Add `## Workflow` |
| A09 | CLOSEOUT step present | soft | Add CLOSEOUT to workflow |
| A10 | `evals/evals.json` present | soft | Add 2-3 test cases |
| A11 | reference/ files have load conditions | soft | Add "Read X if Y" triggers |
| A12 | Description starts with imperative | soft | Rewrite with "Use when..." |

Hard findings → switch to Refine lane.
Soft findings → can ship but Refine is recommended.

---

## Output format

```
SKILL: .claude/skills/<name>
A01 PASS  name: create-skill
A02 PASS  dir: create-skill
A03 PASS  kebab-case
A04 PASS  description present
A05 PASS  description: 842 chars
A06 PASS  body: 87 lines
A07 PASS  Hard Rules found
A08 PASS  Workflow found
A09 SOFT  CLOSEOUT not found in workflow steps
A10 SOFT  evals/evals.json missing
---
Hard: 0  Soft: 2  → Refine recommended
```
