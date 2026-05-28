# Quality gate — done checklist

A skill is **not done** until every item below is true. Work through them in
order; stop and fix before continuing.

---

## Gate 0 — Location (hard)

- [ ] Skill is in `.claude/skills/<name>/` — not `~/.claude/skills/`
  (project-local: preflight reads project context; closeout encodes
  project-specific friction. Global placement would spread project-specific
  gotchas and guards to unrelated projects.)

## Gate 1 — Structure
- [ ] `name` in frontmatter matches directory name (kebab-case)
- [ ] `reference/workflow.md` exists with PREFLIGHT → CLOSEOUT expansion
- [ ] `evals/evals.json` exists with ≥2 test cases, each with `assertions`
- [ ] `commands/<verb>.md` exists if the skill has slash command entry points
- [ ] `SKILL.md` body is ≤500 lines (`wc -l SKILL.md`)

## Gate 2 — Description

- [ ] Description is ≤1024 characters
- [ ] Description starts with an imperative ("Use when...", "Analyze...", "Build...")
- [ ] Description names ≥3 trigger phrases operators would actually type
- [ ] Description has a boundary clause if the skill overlaps with adjacent skills
- [ ] Description trigger test passed: ≥80% pass rate on 10 queries (5 should-trigger, 5 should-not-trigger)

## Gate 3 — Workflow completeness

- [ ] Workflow has exactly 5 steps: PREFLIGHT, EXPLORE, AUTHOR, VALIDATE, CLOSEOUT
- [ ] PREFLIGHT writes `scope.md` with Critical Points before any main work
- [ ] VALIDATE walks scope.md CP by CP with cited evidence (not implied)
- [ ] VALIDATE has an explicit retry loop: diagnose → fix → re-validate
- [ ] CLOSEOUT has: write introspection.md → apply fixes → delete introspection.md
- [ ] CLOSEOUT includes staleness scan — cross-referenced files verified to exist
- [ ] CLOSEOUT includes symbol/assertion freshness — each asserted symbol grepped
- [ ] CLOSEOUT includes pattern review — prune dead patterns, annotate guards, encode new
- [ ] introspection.md deletion is stated as the done signal (not implied)
- [ ] Every `reference/` file has a named load condition in SKILL.md body
  (e.g. "Read reference/patterns.md if X" — not a generic bullet list)

## Gate 4 — Hard Rules

- [ ] Hard Rules section exists
- [ ] Rules are domain-specific — not generic advice the agent already follows
- [ ] "Never generate from training data alone" rule present (or equivalent)
- [ ] "Never declare done until every CP is ticked" rule present
- [ ] "Never leave introspection.md after closeout" rule present
- [ ] "Never skip CLOSEOUT" rule present (even on clean runs — prevents drift)

## Gate 5 — Evals

- [ ] Each test prompt is realistic (has context, file paths, or personal detail)
- [ ] Each `expected_output` is observable (names an artifact or value — not "looks good")
- [ ] Each assertion is verifiable pass/fail (not a subjective quality judgment)
- [ ] At least one test case covers an edge case or boundary condition

## Gate 6 — Closeout (final)

- [ ] introspection.md was written (friction table is non-empty or "none" is explicit)
- [ ] Every friction point has a corresponding edit applied to skill files
- [ ] introspection.md has been deleted from workspace
- [ ] All scope.md CPs are ticked with cited evidence

---

## Quick self-check script

```bash
python3 - <<'PY'
import re, sys, pathlib, json

skill = pathlib.Path(".claude/skills/SKILL-NAME")
errors = []

# Gate 1
for f in ["SKILL.md", "reference/workflow.md", "evals/evals.json"]:
    if not (skill / f).exists():
        errors.append(f"MISSING: {f}")

skill_text = (skill / "SKILL.md").read_text()
lines = skill_text.splitlines()
if len(lines) > 500:
    errors.append(f"SKILL.md too long: {len(lines)} lines (max 500)")

# Gate 2
m = re.search(r'description:\s*[>|]?\s*\n((?:  .+\n)+)', skill_text)
if not m:
    m = re.search(r'description:\s*"(.+?)"', skill_text, re.DOTALL)
desc = (m.group(1) if m else "").replace("\n", " ").replace("  ", " ").strip()
if len(desc) > 1024:
    errors.append(f"description too long: {len(desc)} chars")
if not re.match(r'^[A-Z]', desc):
    errors.append("description should start with capital (imperative)")

# Gate 3
for step in ["PREFLIGHT", "EXPLORE", "AUTHOR", "VALIDATE", "CLOSEOUT"]:
    if step not in skill_text:
        errors.append(f"MISSING workflow step: {step}")

# Gate 4
if "Hard rules" not in skill_text and "Hard Rules" not in skill_text:
    errors.append("MISSING: Hard Rules section")

# Gate 5
evals_path = skill / "evals/evals.json"
if evals_path.exists():
    evals = json.loads(evals_path.read_text())
    cases = evals.get("evals", [])
    if len(cases) < 2:
        errors.append(f"evals: need ≥2 test cases, have {len(cases)}")
    for c in cases:
        if not c.get("assertions"):
            errors.append(f"eval {c.get('id')}: missing assertions")

if errors:
    print("\n".join(f"FAIL {e}" for e in errors))
    sys.exit(1)
else:
    print("PASS all gates")
PY
```
