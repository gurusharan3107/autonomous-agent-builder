# Create lane — scaffold a new skill

Loaded when the operator picks Create or types "create / scaffold / make a skill for X".

The output skill follows the **webwright structural pattern** (preflight → explore →
author → validate → closeout) and **agentskills.io best practices** (precise
description, Hard Rules, Gotchas, progressive disclosure, evals).

---

## STEP 1 — PREFLIGHT

Do not write any skill file until these are done.

### 1a. Validate the name and location
```bash
SKILL_NAME="<kebab-case-name>"
# Always project-local — never ~/.claude/skills/
# Preflight reads project context; closeout encodes project-specific friction.
# The gotchas and guards produced are shaped by this project's failure modes.
ls .claude/skills/"${SKILL_NAME}" 2>/dev/null && echo "EXISTS — use Refine lane" || echo "ok"
# Name must match: ^[a-z][a-z0-9]*(-[a-z0-9]+)*$
```

### 1b. Confirm real source material
Per agentskills.io best practices, effective skills are grounded in real expertise —
not synthesized from generic theory. Ask via `AskUserQuestion` if the operator cannot
name at least one of:
- A concrete trigger phrase users would actually type
- A real task this skill should solve
- Existing artifacts (code, tasks, runbooks, conversations) to extract from

### 1c. Write scope.md
Pick workspace: `outputs/<skill-name>/`

```markdown
# scope.md — <skill-name>

## Source material
- What real tasks/conversations/code grounds this skill?

## Critical Points
- [ ] CP1: Trigger — what user intent activates this skill? (3+ example phrases)
- [ ] CP2: Hard Rules — what must never happen? What are the failure modes?
- [ ] CP3: Workflow — what are the numbered steps? What does each step produce?
- [ ] CP4: Progressive disclosure — what content is too detailed for SKILL.md body?
- [ ] CP5: Description — ≤1024 chars, imperative phrasing, intent-focused
- [ ] CP6: Evals — what does success look like for 2-3 test prompts?
```

Every section written in the output skill must map back to a CP here.

---

## STEP 2 — EXPLORE

Goal: harvest real expertise before writing a single skill line.

1. Read all source material the operator provided or referenced.
2. Read any existing similar skill in `.claude/skills/` for reference.
3. Draft a description candidate (imperative, trigger-centric, ≤1024 chars).
4. Sketch content outline — one section per CP from scope.md.
5. If source material is too thin to fill the outline, ask for more before continuing.

**Output**: stable description draft + content outline with CP coverage confirmed.

---

## STEP 3 — AUTHOR

Create the output skill directory and files using the templates in
[reference/templates.md](templates.md).

```bash
mkdir -p ".claude/skills/${SKILL_NAME}/reference" \
         ".claude/skills/${SKILL_NAME}/commands" \
         ".claude/skills/${SKILL_NAME}/evals" \
         ".claude/skills/${SKILL_NAME}/scripts"
```

Write files in this order (each maps to a CP):

| File | CP | Contents |
|---|---|---|
| `SKILL.md` | CP1–CP5 | Frontmatter + Hard Rules + Workflow (5 steps) + Reference Files |
| `reference/workflow.md` | CP3 | Detailed step expansion for each workflow step |
| `reference/patterns.md` | CP2 | Domain patterns, gotchas, concrete examples |
| `commands/<verb>.md` | CP1 | Slash command entry point(s) |
| `evals/evals.json` | CP6 | 2-3 test cases with assertions |

Use the templates from [templates.md](templates.md) — do not start from a blank file.

**Key constraint**: SKILL.md body ≤500 lines. If a section grows, move it to
`reference/` and add a pointer with a load condition:
`"Read reference/patterns.md if the task involves X."` — not a generic "see references/".

---

## STEP 4 — VALIDATE

Walk scope.md CP by CP. Tick only with concrete evidence.

### CP1 — Trigger test
Load the new skill and test the description against prompts.
See [description-testing.md](description-testing.md) for the full eval loop.
Minimum bar: 5 should-trigger + 5 should-not-trigger prompts, ≥80% pass rate.
If failing: description too narrow (broaden scope) or too broad (add boundary clause).

### CP2 — Hard Rules review
Read the Hard Rules section of the output SKILL.md. For each rule:
- Could the agent violate it following the written workflow? If yes → fix the rule or add a guard.
- Is the rule specific to this domain, or generic advice an agent already follows? If generic → delete it.

### CP3 — Workflow walkthrough
Step through the output skill's workflow against one real scenario:
- Does each step produce a named artifact?
- Is the retry/validate loop explicit (not implied)?
- Is the closeout step present and does it include introspect → patch → delete?

### CP4 — Progressive disclosure check
```bash
wc -l ".claude/skills/${SKILL_NAME}/SKILL.md"
# Must be ≤500 lines
```
Verify each `reference/` file has a named load condition in SKILL.md (not just a bullet list).

### CP5 — Description check
```bash
python3 -c "
import re, sys
desc = open('.claude/skills/${SKILL_NAME}/SKILL.md').read()
m = re.search(r'description:\s*[>|]?\s*\n((?:  .+\n)*)', desc)
if not m:
    m = re.search(r'description:\s*\"(.+?)\"', desc, re.DOTALL)
text = (m.group(1) if m else '').replace('\n', ' ').replace('  ', ' ').strip()
print(f'Chars: {len(text)}')
print('PASS' if len(text) <= 1024 else 'FAIL — over 1024 chars')
"
```
Also check: does the description start with an imperative? Does it name trigger phrases
the operator would actually type?

### CP6 — Evals review
Open `evals/evals.json`. For each test case:
- Is the prompt realistic (specific, has context, not vague)?
- Is the expected_output observable (not "looks good")?
- Are the assertions verifiable (pass/fail without judgment)?

If any CP fails: diagnose the specific issue, fix the skill file, re-validate that CP.
Do not declare done with any CP open.

---

## STEP 5 — CLOSEOUT

This closeout is for **create-skill's own run** — the output skill's CLOSEOUT
(for use on every run of that skill) is already templated in `reference/workflow.md`
from the template. Verify that section is present and adapted to the output
skill's domain before declaring the output skill done.

    # introspection.md — <skill-name>

    ## What went perfectly
    - Steps that required zero correction.

    ## Staleness found and fixed
    | Item | Was | Now | File |
    |---|---|---|---|

    ## New patterns added
    | Pattern | Why | File |
    |---|---|---|

    ## Friction points
    | # | Symptom | Root cause | Fix type | Target file + section |
    |---|---|---|---|---|
    | 1 | | | UPDATE STEP / ADD GUARD | |

Apply every row to the output skill files before deleting.
Fix types:
- **UPDATE STEP**: encode the correct form in the procedure so future agents don't re-derive it.
- **ADD GUARD**: explicit "never do X" callout in Hard Rules to stop the mistake before it happens.

```bash
# Verify output skill passes audit
python3 ~/.claude/skills/create-skill/scripts/audit.py \
  ".claude/skills/${SKILL_NAME}" 2>/dev/null \
  || python3 -c "
import sys, re
text = open('.claude/skills/${SKILL_NAME}/SKILL.md').read()
checks = [
  ('has name', bool(re.search(r'^name:', text, re.M))),
  ('has description', bool(re.search(r'^description:', text, re.M))),
  ('has Hard Rules', 'Hard rules' in text or 'Hard Rules' in text),
  ('has Workflow', '## Workflow' in text),
  ('has Closeout', 'CLOSEOUT' in text or 'Closeout' in text),
]
for name, ok in checks:
  print(f'{'PASS' if ok else 'FAIL'} {name}')
sys.exit(0 if all(ok for _, ok in checks) else 1)
"
rm -f "outputs/${SKILL_NAME}/introspection.md"
echo "Closeout complete."
```
