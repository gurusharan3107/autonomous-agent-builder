---
description: Scaffold a new skill following the webwright pattern and agentskills.io best practices.
argument-hint: <skill-name> — what this skill should do (e.g. "pdf-analyzer extract tables from PDFs")
---

You are operating as the create-skill agent in **Create lane**. First read
the `SKILL.md` in the parent directory of this `commands/` folder and
`reference/create.md` next to it, then scaffold the following skill:

$ARGUMENTS

Follow the Create lane workflow from `reference/create.md`:

1. **PREFLIGHT** — validate name, confirm source material, write `scope.md`.
2. **EXPLORE** — read source material; draft description; outline content per CP.
3. **AUTHOR** — create directory + files from `reference/templates.md`.
4. **VALIDATE** — tick every CP in scope.md with cited evidence, including
   trigger test (≥80% pass rate on 10 queries).
5. **CLOSEOUT** — introspection.md → patch skill files → delete.

The output skill must pass all gates in `reference/quality-gate.md` before
you declare done.
