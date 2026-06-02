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
| "Skill produces wrong output" | Workflow gap → add step, guard, or gotcha; confirm with output-eval baseline ([output-eval.md](output-eval.md)) |
| "Not sure the skill even helps" | Run output-quality baseline ([output-eval.md](output-eval.md)) — measure the with/without delta before adding more |
| "Hard Rules are vague" | Sharpen rules → make domain-specific, add "why" |
| "No evals / evals outdated" | Add/update evals/evals.json |

### Triage each finding before fixing

Disconfirming — "how could this still be wrong / recur / be the wrong surface":
1. **Observed or latent?** → priority; don't over-fix a reasoned-only risk.
2. **Could a correct-operating agent still hit it?** **YES → fix code/script; NO → fix how-to doc.** Often both.
3. **This instance, or the class?** → fix the structure, not the symptom.
4. **Owner file?** code→`scripts/` · how-to→`operate.md` · conventions→`best-practices.md` · change/troubleshoot→`agent-handbook.md` · optimize→`optimize.md`. Fix on owner; cross-link, don't duplicate.
5. **Enforceable (eval/assertion/gate) over drifting prose?**

Don't manufacture changes — intentional or not-real → leave it.

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
