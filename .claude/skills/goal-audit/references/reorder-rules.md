# Autoresearch reorder rules

> Loaded on demand from [goal-audit SKILL.md](../SKILL.md).

## Autoresearch reorder rules

The skill MAY edit `docs/autoresearch/OPTIMIZE_IDEAS.md` when ALL of the following hold:

1. **A single driver maps to a single OPTIMIZE_IDEAS item.** If a driver maps to multiple items (e.g. `reduce_agent-chat_raw_tokens` → 1+2), do not auto-reorder — leave it as a recommendation in INSIGHTS only.
2. **The driver appeared in ≥3 Builder-runtime sessions in scope.** Lower than 3 = noise.
3. **The mapped OPTIMIZE_IDEAS item is not already at position 1.** If it's already top, no action needed.
4. **The item has `Attempts: none` in OPTIMIZE_IDEAS.md.** Never re-promote an already-attempted item without explicit user direction.

When all four hold:
- Move the mapped item to position 1 (cut the section and paste at top, before existing item 1).
- Add the timestamped reorder comment above the moved item.
- Re-number items in the file if the existing numbers (`## 1.`, `## 2.`, ...) need updating.
- Note the reorder in INSIGHTS.md § Autoresearch focus candidates → OPTIMIZE_IDEAS.md actions taken.

The skill never:
- Deletes ideas.
- Edits ROADMAP.md, STATUS.md, NORTH-STAR.md, EVALUATION.md, FIX-STANDARD.md, OPERATOR-LANGUAGE.md, TUNING.md, RESUME.md, INDEX.md, README.md.
- Removes the reorder comment from a prior run.
