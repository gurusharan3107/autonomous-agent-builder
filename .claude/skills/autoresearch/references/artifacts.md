# Skill artifacts — iterations map + self-introspection

> Loaded on demand from [autoresearch SKILL.md](../SKILL.md).

## Visual iteration map — `docs/autoresearch/iterations.html`

Single-file static page that visualizes baseline + every iteration's verdict, composite delta, 6-hard-gate status, A→E promotion. Reads `iterations.json` first, then the embedded `window.ITERATIONS` block as fallback (for `file://` viewing).

**Regenerator:** `scripts/render_iterations.py`, bundled with this skill. Runs as part of every Baseline + Iterate closeout. Reads `optimize_results.tsv` + `baseline_runs_summary.json`, computes per-iteration verdict + composite delta in % + σ units, writes `iterations.json` and rewrites the embedded data block between `// __ITERATIONS_DATA_START__` and `// __ITERATIONS_DATA_END__`.

```bash
python3 .claude/skills/autoresearch/scripts/render_iterations.py            # write json + html
python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run  # report only
python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only # skip html rewrite
```

**Do not hand-edit `iterations.html`.** Layout, CSS, render code, and the structural markers are the contract the regenerator depends on. To change shape, edit the skill's template once and let the next regeneration propagate.

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
