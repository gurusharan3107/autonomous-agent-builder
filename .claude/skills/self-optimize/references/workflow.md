# self-optimize — full procedure

Loaded when the skill activates. Step-by-step with exact commands.

## Step 0 — Load last run history

Before collecting new data, check if this skill has run before:

```bash
LAST_RUN=".claude/skills/self-optimize/last-run.json"
if [ -f "$LAST_RUN" ]; then
  cat "$LAST_RUN"
fi
```

If `last-run.json` exists, extract:
- `date` — when the skill last ran
- `themes` — which themes were identified
- `edits_applied` — which themes had surface edits approved and applied

This enables recurrence detection in Step 3: any theme that had an edit applied last run but still shows up now means the fix was insufficient.

If no `last-run.json` exists, this is the first run — skip comparison, note in report.

## Step 1 — Collect

```bash
WINDOW="<operator-chosen: 7d|14d|30d>"
FILTER="autonomous-agent-builder-codex"   # project key substring

# Session transcript analysis
node .claude/skills/goal-audit/scripts/analyze-sessions.mjs \
  --json --since "$WINDOW" --filter-pattern "$FILTER" \
  > /tmp/self-optimize-session.json 2>/tmp/self-optimize-errors.log

# Check for errors
if [ $? -ne 0 ]; then
  cat /tmp/self-optimize-errors.log
  # Abort and report to operator
fi
```

If the filter produces no results, retry without `--filter-pattern` and note in the report that all projects were included.

## Step 2 — Cluster

```bash
python3 .claude/skills/self-optimize/scripts/cluster.py \
  /tmp/self-optimize-session.json \
  > /tmp/self-optimize-themes.json
```

The script outputs JSON:
```json
{
  "window": "30d",
  "total_prompts": 500,
  "themes": [
    {
      "name": "theme_slug",
      "label": "Human-readable label",
      "occurrences": 23,
      "git_fix_commits": 4,
      "example_prompts": ["[date] prompt text…", "…"],
      "keywords_matched": ["keyword1", "keyword2"]
    }
  ]
}
```

Themes are sorted by `occurrences + (git_fix_commits * 2)` descending (git fixes weighted heavier as they represent confirmed code-level mistakes, not just operator phrasing).

## Step 3 — Map

For each theme in the ranked list, first check recurrence:

```python
# Pseudo-logic — apply while reading last-run.json
last_edits = {t["name"] for t in last_run.get("themes", []) if t.get("edit_applied")}
for theme in current_themes:
    theme["recurred"] = theme["name"] in last_edits
    # recurred=True means: fix was applied last run, but pattern still appearing
    # This requires a STRONGER fix (mechanical gate, not just a rule addition)
```

Then for each theme determine:

**Root cause** (pick one):
- `missing` — no rule exists anywhere for this pattern
- `exists-not-enforced` — rule is in a surface but still violated (needs mechanical gate, not a duplicate rule)
- `wrong-surface` — rule exists but in the wrong surface (e.g., in memory but not in AGENTS.md where the agent reads it at decision time)

**Target surface** (priority order — pick the highest that fits):

| Priority | Surface | Use when |
|---|---|---|
| 1 | Specific skill SKILL.md | Mistake happens inside a specific skill's execution |
| 2 | Local `AGENTS.md` | Dev-on-repo rule; agent must check before a class of actions |
| 3 | Global `~/.claude/CLAUDE.md` | Universal doctrine across all projects |
| 4 | `tests/conftest.py` | Test isolation gap (env var leak, missing fixture) |
| 5 | Workflow doc (`docs/workflows/`) | Multi-step procedure needs updating |

**Edit type** (pick one):
- `add-rule` — add missing rule to surface
- `add-gate` — add mechanical check (grep, script, AskUserQuestion) to enforce existing rule
- `move-rule` — rule is in the wrong surface; move it to the correct one
- `strengthen-rule` — rule is present but passive; make it active/imperative

## Step 4 — Present

Show the operator a ranked table:

```
## Recurring Mistake Analysis — last <window>

| # | Theme | Occurrences | Git fixes | Root cause | Target surface | Edit type |
|---|---|---|---|---|---|---|
| 1 | ... | 23 | 4 | missing | AGENTS.md | add-rule |
| 2 | ... | 19 | 6 | exists-not-enforced | autoresearch/SKILL.md | add-gate |
...

Proposed edits for each:
[Theme 1]: Add rule "..." to AGENTS.md § Required Triggers
[Theme 2]: Add Hard Rule #N "before exiting lane, grep for X"
...
```

Show the ranked table. For recurred themes, call them out explicitly:

```
⚠ RECURRED (fix was applied last run but pattern still appearing — needs stronger fix):
  - <theme>: last edit was <surface: what was added>. Current count: N. Needs: mechanical gate.

New themes (not seen in last run):
  - <theme>: N occurrences. Proposed: <edit>
```

Then `AskUserQuestion`:
```
question: "Which themes should I apply fixes for?"
header:   "Themes to fix"
multiSelect: true
options: [one per theme — prefix ⚠ RECURRED for themes that recurred]
```

Only proceed with themes the operator selects.

## Step 5 — Edit

For each approved theme:

1. Read the target surface file.
2. Find the exact insertion point (end of the relevant section, or after the last related rule).
3. Make the minimal targeted edit — no cleanup of surrounding text, no reformatting.
4. Verify the edit landed: `grep -n "<key phrase from new rule>" <file>`.

**Edit placement guide:**

| Target | Section to add to |
|---|---|
| AGENTS.md `add-rule` (pre-action) | `## Required Triggers` — end of section |
| AGENTS.md `add-rule` (prohibition) | `## Dead Ends` — end of section |
| AGENTS.md surface routing | `## Surface Ownership` |
| Skill SKILL.md `add-gate` | `## Hard rules` — numbered, after last existing rule |
| global CLAUDE.md universal doctrine | `## Rules` — after the related existing rule |
| tests/conftest.py | `isolate_runtime_settings` delenv block |

## Step 6 — Memory

For each applied edit, write a memory entry:

```
File: <project-memory-dir>/feedback_<slug>.md
---
name: <slug>
description: <one-line hook for MEMORY.md index>
metadata:
  type: feedback
---
<Rule itself>

**Why:** <evidence from session analysis — date, occurrence count, example prompt>
**How to apply:** <when/where this rule fires>
```

Then add a line to `MEMORY.md`:
```
- [<Title>](<file>.md) — <one-line hook>
```

## Step 7 — Closeout

```bash
# 1. Write last-run.json (MUST happen before reporting done)
python3 - <<'EOF'
import json, datetime
from pathlib import Path

themes_applied = []  # populate from Step 5 — list of {name, edit_applied: bool, surface, edit_type}
run = {
    "date": datetime.date.today().isoformat(),
    "window": "<operator-chosen window>",
    "total_prompts_analyzed": "<from cluster output>",
    "themes": themes_applied,
}
Path(".claude/skills/self-optimize/last-run.json").write_text(json.dumps(run, indent=2))
EOF

# 2. Self-validate
cd .claude/skills/self-optimize && ./scripts/validate.sh
cd -

# 3. Verify each edit landed
grep -n "<phrase>" <edited-file>

# 4. Verify memory entries exist
ls <project-memory-dir>/feedback_<slug>.md
```

Report format:
```
## Self-optimize complete — <date>

Last run: <date of previous run, or "first run">
Themes analyzed: <N total> | <N recurred from last run> ⚠ | <N new>

Applied <N> edits across <M> surfaces:
- <surface>: <what was added> [new | stronger-gate for recurred]
- ...

Saved <N> memory entries.
Validation: PASS / WARN (list any findings)

Next suggested run: in <14d|30d depending on change velocity>
```
