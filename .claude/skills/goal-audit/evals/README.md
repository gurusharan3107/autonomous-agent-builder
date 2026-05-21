# goal-audit evals

This directory contains test cases for the `goal-audit` skill, following the [Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills) guide.

## Files

- **`evals.json`** — Test case definitions: prompt, expected_output, assertions per case.

## Why these tests don't include input file fixtures

Unlike a CSV or PDF skill where inputs can be bottled, `goal-audit` reads two **live data sources**:

1. The user's Claude Code session transcripts under `~/.claude/projects/`.
2. The user's Builder workspaces (devpulse, todo-app, etc.) for `builder agent sessions` / `builder logs analyze` data.

A frozen fixture would not exercise the skill's actual behavior. Instead, the test cases assert on **process correctness** (does the workflow run end to end? does it follow the dry-run contract? does it respect the reorder criteria?) rather than narrative correctness. Narrative quality (whether the model's observations are wise) is a human-review concern.

## Running an eval iteration

Per the evaluating-skills guide, the canonical pattern is `with_skill` vs `without_skill` runs in a workspace tree:

```
goal-audit-workspace/
└── iteration-N/
    ├── happy-path-clean-system/
    │   ├── with_skill/{outputs,timing.json,grading.json}
    │   └── without_skill/{outputs,timing.json,grading.json}
    ├── dry-run-no-writes/
    │   └── ...
    ├── reorder-criteria-validation/
    │   └── ...
    └── benchmark.json
```

For each test case:

1. **Snapshot mutable state** before the run: `docs/goal/INSIGHTS.md`, `docs/autoresearch/OPTIMIZE_IDEAS.md`. The skill mutates these; snapshots let assertions diff before vs after.
2. **Run with-skill** in an isolated subagent (`Agent` tool, fresh context). Provide the skill path and the test prompt. Save the resulting INSIGHTS/OPTIMIZE_IDEAS state to `outputs/`.
3. **Run without-skill** with the same prompt, no skill. Save to baseline `outputs/`.
4. **Grade assertions** by inspecting `outputs/` against `evals.json` assertions. Record PASS/FAIL with evidence in `grading.json`.
5. **Restore mutable state** to the snapshot. Eval runs must be idempotent vs production.

A future `scripts/run_evals.py` could automate steps 1-5; for v1 of the skill we run them manually as needed.

## When to expand the test set

Per the guide: start with 2-3 cases (we have 3). Expand when:

- A real invocation produces surprising output → add a test case capturing the surprise.
- A new driver appears in `aggregated_drivers` that isn't in the mapping table → add a coverage case.
- The reorder logic is changed → add a case that exercises the new path.

Do NOT expand the test set until at least one full iteration has been run and graded.

## Stop condition

Per the guide: stop iterating when results are consistently passing, human-review feedback is empty, or you stop seeing meaningful improvement between iterations.
