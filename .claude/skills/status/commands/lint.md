# /status lint

Check `docs/goal/ROADMAP.md` + `STATUS.md` against the goal-docs **Maintenance
Contract** (see `SKILL.md`) and verify `goal-overview.html` is in sync. Run this
**before and after** editing ROADMAP/STATUS.

```bash
python3 .claude/skills/status/scripts/lint_goal_docs.py            # exit 2 on ERROR
python3 .claude/skills/status/scripts/lint_goal_docs.py --strict   # exit 1 on WARN too
```

Findings:
- **ERROR** (blocks): missing STATUS Current Position rows; HTML out of sync
  (run `/status update`); missing file.
- **WARN** (advisory): open item over 240 chars / no `Pn` priority; closed item over
  160 chars / no evidence pointer; inline work-log lines; duplicate item id.

Report ERRORs first, then WARNs. **Fix the source markdown** — never the HTML.
Compact over-budget items by moving the work-log to STATUS.md *Current Item In Flight*
and the closure detail to git/CHANGELOG/`.memory`, leaving a one-line entry behind.
