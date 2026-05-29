# hermes-chrome tests

Live end-to-end regression suite for the browser-control capability. Drives a real
Chrome through the bridge and asserts real outcomes (URL / DOM / cursor position).

## test_dashboard_interactions.py

Guards the three click-reliability defects fixed 2026-05-28 (see
`../../skills/hermes-chrome/references/optimize.md` → "Click-reliability invariants"):
exact+visible text matching, occlusion rejection, and cursor motion that lands on
target even when Chrome is not the foreground window.

**Prerequisites**
- Bridge deployed + running: `../scripts/sync.sh` (Chrome open, extension loaded).
- Compatible dashboard at `HERMES_TEST_URL` (default `http://localhost:9876` — the
  Agent Builder dashboard: nav with Board/Metrics/Memory/Settings + a
  `memory-search` input). Incompatible dashboard → suite skips.

**Run**
```bash
python3 .claude/plugin/hermes_chrome/tests/test_dashboard_interactions.py
# or against another target:
HERMES_TEST_URL=http://localhost:3000 python3 .../test_dashboard_interactions.py
```

**Exit codes:** `0` all pass · `1` a real regression · `2` env unavailable/incompatible (skipped).

Run after any change to `service_worker.js` (resolvers) or `cursor-agent.js` (motion).
