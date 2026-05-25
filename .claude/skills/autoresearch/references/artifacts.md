# Skill artifacts — explainer live-data + self-introspection

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Living explainer — `docs/autoresearch/autoresearch-explainer.html`

Single-file explainer combining hand-curated prose (why/when to use, lanes, architecture, gates, FAQ) with live data panels that render client-side from an embedded JSON snapshot. All data lives in one place: `<script id="autoresearch-data" type="application/json">` near the bottom of the file. JavaScript reads it at page load and renders fixture grid, scatter chart (color-coded green/orange/red vs the 2σ floor), raw runs table, and iterations history.

**Single source of truth:** `baseline_runs_summary.json` + `baseline_runs.tsv` + `optimize_results.tsv`. `render_iterations.py` reads those files and writes the snapshot into the HTML. You never edit numbers in the HTML — only the prose sections.

**Refresh is automatic.** `freshness_sweep.py` calls `render_iterations.py` at the start of every run, so the single required closeout command (`python3 freshness_sweep.py`) also refreshes the data block. No separate render step needed.

```bash
python3 .claude/skills/autoresearch/scripts/render_iterations.py            # refresh data block + write iterations.json
python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run  # show what would change
python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only # write iterations.json only
```

**Architecture drift is a warning, not an auto-rewrite.** When a new script lands in `scripts/autoresearch/` or `.claude/skills/autoresearch/scripts/` that the explainer doesn't mention, `render_iterations.py` prints a drift line — update the architecture table by hand at next closeout.

## Self-introspection — `docs/autoresearch/INTROSPECTION.md`

`scripts/introspect.py` answers the meta-question: **does the loop pay for itself?** Runs as part of every Baseline + Iterate closeout; overwrites `INTROSPECTION.md`. Git history is the canonical record.

Sections: token economics (which agent costs most); cumulative loop ROI ($ spent vs composite savings); what worked / didn't / redundant / noisy; KB-grounded leads from pinned `workflow knowledge` queries; lean recommendations ranked by `(expected token reduction × applicability)`.

Tolerant of malformed data — TSV column drift surfaces as the highest-priority recommendation rather than crashing.

```bash
python3 .claude/skills/autoresearch/scripts/introspect.py             # write + stdout summary
python3 .claude/skills/autoresearch/scripts/introspect.py --quiet     # write only
python3 .claude/skills/autoresearch/scripts/introspect.py --stdout-only  # don't overwrite
python3 .claude/skills/autoresearch/scripts/introspect.py --skip-kb   # skip workflow knowledge queries
```
