# Skill artifacts — explainer live-data + self-introspection

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Living explainer — `docs/autoresearch/autoresearch-explainer.html`

Single-file explainer that combines hand-curated prose (why/when to use, lanes, architecture, gates, FAQ) with four auto-updated regions: **baseline summary, scatter, raw runs, iterations history**. Built with the `html-artifact` skill's *report* lane + `auto-update-regions` pattern. The four data zones are wrapped in HTML comment fences (`<!-- AUTOUPDATE:name v=1 -->...<!-- /AUTOUPDATE:name -->`); everything outside the fences is human-owned.

**Regenerator:** `scripts/render_iterations.py`, bundled with this skill. Runs as part of every Baseline + Iterate closeout. Reads `optimize_results.tsv` + `baseline_runs.tsv` + `baseline_runs_summary.json`, computes per-iteration verdict + composite delta in % + σ units, writes `iterations.json` and rewrites only the bytes inside each named fence.

```bash
python3 .claude/skills/autoresearch/scripts/render_iterations.py            # write json + rewrite explainer fences
python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run  # report only
python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only # skip explainer rewrite
```

**Hand-curated zones are safe to edit.** Architecture tables, FAQ, gates, lane procedures, and section prose stay outside the fences. The rewriter refuses to write if any of the four expected fences is missing — restore from the [html-artifact `auto-update-regions` reference](https://github.com/anthropics/html-effectiveness) (or `~/.claude/skills/html-artifact/references/auto-update-regions.md`) if drift breaks them.

**Architecture drift is a warning, not an auto-rewrite.** When a new script lands in `scripts/autoresearch/` or `.claude/skills/autoresearch/scripts/` that the explainer doesn't mention, `render_iterations.py` prints a drift line — operator updates the table by hand at next closeout.

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
