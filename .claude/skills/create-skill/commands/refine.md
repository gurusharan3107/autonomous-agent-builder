---
description: Improve an existing skill's structure, description, or content.
argument-hint: <path-to-skill> — what needs fixing (e.g. ".claude/skills/pdf-analyzer — description never triggers")
---

You are operating as the create-skill agent in **Refine lane**. First read
the `SKILL.md` in the parent directory of this `commands/` folder and
`reference/refine.md` next to it, then refine the following skill:

$ARGUMENTS

Follow the Refine lane workflow from `reference/refine.md`:

1. **PREFLIGHT** — read existing skill, classify the problem, write scope.md
   with specific changes needed.
2. **DO** — apply fixes in order: description → structure → content → progressive
   disclosure. Use templates from `reference/templates.md` for missing sections.
3. **CLOSEOUT** — run quality gate, write introspection.md, apply fixes, delete.

If the problem is a description trigger failure, follow
`reference/description-testing.md` as part of step 2.
