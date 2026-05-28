# Refine lane — improve an existing skill

Loaded when the operator picks Refine or types "refine / improve / fix / shrink / update skill X".

---

## PREFLIGHT

1. Identify the target skill path: `.claude/skills/<name>/`
2. Read the existing `SKILL.md` fully.
3. Classify the problem (ask if unclear):

| Symptom | Likely fix |
|---|---|
| "Skill never activates" | Description too narrow → description-testing loop |
| "Skill fires on wrong prompts" | Description too broad → add boundary clause |
| "Skill body is too long / slow" | Progressive disclosure → move bulk to reference/ |
| "Skill produces wrong output" | Workflow gap → add step, guard, or gotcha |
| "Hard Rules are vague" | Sharpen rules → make domain-specific, add "why" |
| "No evals / evals outdated" | Add/update evals/evals.json |

4. Write `scope.md` in `outputs/<skill-name>-refine/` with the specific
   changes needed (one CP per change):

```markdown
# scope.md — <skill-name> refine

## Changes needed
- [ ] CP1: SPECIFIC-CHANGE (e.g. "description too narrow — add proxy phrases")
- [ ] CP2: SPECIFIC-CHANGE (e.g. "no CLOSEOUT step — add introspection loop")
```

---

## DO

Apply changes in this order to avoid thrash:

1. **Description fixes first** — if the skill doesn't activate, everything else
   is moot. Follow [description-testing.md](description-testing.md).

2. **Structural gaps second** — missing PREFLIGHT/EXPLORE/AUTHOR/VALIDATE/CLOSEOUT
   steps. Add the missing step(s) using the templates in [templates.md](templates.md).

3. **Content gaps third** — missing Hard Rules, Gotchas, evals. Add using templates.

4. **Progressive disclosure last** — move bulk content to reference/ only after
   structure and description are solid (moving content changes line count, which
   affects other checks).

For each change: edit the file, confirm the CP is addressed, tick it in scope.md.

---

## CLOSEOUT

1. Run the quality gate:
```bash
python3 -c "
# (paste the quick self-check script from quality-gate.md)
" 2>/dev/null || echo "Check quality-gate.md manually"
```

2. Write introspection.md, apply fixes, delete it (same as Create lane).

3. If the refine was triggered by a description failure, run 5 fresh trigger
   queries as a final sanity check.
