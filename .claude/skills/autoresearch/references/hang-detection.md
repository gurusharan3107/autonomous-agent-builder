# Hang detection — diagnose, don't re-investigate

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## When a hang is detected — diagnose, don't re-investigate

The watchdog dumps to `/tmp/autoresearch/diagnostics/<UTC>-pid<PID>/`. Before diagnosing by hand, run the catalogued pattern matcher:

```bash
python3 .claude/skills/autoresearch/scripts/diagnose_hang.py <dump-dir>
# or
python3 .claude/skills/autoresearch/scripts/diagnose_hang.py <dump-dir> --json
```

Five hang classes are catalogued in [`KNOWN_PATTERNS.md`](../KNOWN_PATTERNS.md): API contract drift (P1), free-text scoping (P2), watchdog single-signal false positive (P3), subprocess pipe deadlock (P4), sprint merge missing `main` branch (P5). The matcher reports `{pattern_id, confidence, evidence, fix_pointer}` for the top match, or `unknown` if no pattern fires. On `unknown`, diagnose by hand — and then **add the new pattern to `KNOWN_PATTERNS.md` AND a matcher to `diagnose_hang.py`** before closing the Fix lane. The two must stay in sync (freshness sweep enforces this); next session compounds value off your work today.
