---
name: run-gates
description: Run all quality gate scripts for autonomous-agent-builder and report results. Use this skill whenever the user says "run gates", "check quality gates", "run quality checks", "pre-commit check", "validate the repo", "are the gates passing", or before committing or opening a PR. Also trigger proactively after any batch of edits to Python or CLI files.
disable-model-invocation: true
---

Run all gates from the repo root, even if earlier ones fail — the user needs the full picture, not just the first failure.

## Steps

```bash
cd /home/gurusharangupta/code/autonomous-agent-builder-codex-architecture-review/autonomous-agent-builder-codex-architecture-review

ruff check src/ tests/ 2>&1; echo "EXIT:$?"
python scripts/pre_commit_checks.py 2>&1; echo "EXIT:$?"
python scripts/check_quality_gate_contracts.py 2>&1; echo "EXIT:$?"
python scripts/validate_cli_wrappers.py 2>&1; echo "EXIT:$?"
python scripts/documentation_freshness_ci.py 2>&1; echo "EXIT:$?"
```

## Output format

Print a summary table after all scripts finish:

```
Gate                              Status   Exit
--------------------------------  -------  ----
ruff check                        PASS     0
pre_commit_checks                 FAIL     1
check_quality_gate_contracts      PASS     0
validate_cli_wrappers             PASS     0
documentation_freshness_ci        WARN     1
```

- **PASS** = exit 0
- **FAIL** = exit non-zero, blocking
- **WARN** = exit non-zero but script name contains "freshness" or "doc" (non-blocking by convention)

For any FAIL, quote the first error line from that script's output so the user knows where to look without scrolling.
