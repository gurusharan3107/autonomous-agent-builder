# /status update

Regenerate the live numbers in `docs/goal/goal-overview.html` from the canonical
markdown. Deterministic and idempotent.

```bash
python3 .claude/skills/status/scripts/build_goal_overview.py
```

Regenerates: `#artifact-data` JSON, the `<!-- gen:* -->` markers (`snapshot_date`,
`epoch`, `milestone`, `roadmap_totals`, `priorities`), and per-milestone meters.
The `priorities` region lists open `[ ]` items carrying an inline `` `Pn` `` token,
sorted P0→P3. Run `/status lint` first if you just edited ROADMAP/STATUS.

Then:
1. Report the printed change summary + new totals (or "no change — already in sync").
2. On non-zero exit, surface the error verbatim and STOP — a required file or
   `<!-- gen:NAME -->` marker is missing, or `STATUS.md` Current Position is
   unparseable. Fix the source; never hand-edit the HTML.
3. Offer to `/status open` the refreshed page.

Prove idempotency after a patch:

```bash
python3 .claude/skills/status/scripts/build_goal_overview.py --check   # exit 0 = in sync
```
