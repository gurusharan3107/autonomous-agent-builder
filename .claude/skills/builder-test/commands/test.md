---
description: Run the 6-phase builder verification loop after a source change.
argument-hint: <scope?> <operator-instruction?>  e.g. "static", "unit", "e2e 'implement X'"
---

You are operating as the builder-test agent. First read the `SKILL.md` in
the parent directory of this `commands/` folder, then execute the verification
loop for this task:

$ARGUMENTS

Follow the builder-test workflow from `SKILL.md`.
Refer to `reference/workflow.md` for the detailed phase procedure.
Refer to `reference/assertions.md` for the assertion catalog and bad-string
patterns when running Phase 1 or Phase 2.

If no scope argument is provided, run all 6 phases.
If a scope is provided (e.g. "static", "unit", "e2e"), run only that phase
after completing Phase 0 (preconditions always run).

End with the Phase 5 PASS/WARN/FAIL verdict table.
