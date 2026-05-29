# Autoresearch loop introspection

*Generated 2026-05-29T06:57:00Z by `.claude/skills/autoresearch/scripts/introspect.py`. Overwritten each close-out — `git log` for history.*

## 1. Token economics — where do tokens go?

- **1 iterations recorded** consuming ~30,594 non-cached+output tokens total.
- **Average per iteration:** 30,594 non-cached+output tokens.

Top agents by cumulative cost (the ones to target with lean ideas first):

(no per-prompt rows have non-zero token counts)

## 2. Cumulative loop ROI

- **Spent:** $35.94 across all iterations (per-prompt cost sum).
- **Kept iterations:** 0.
- **Cumulative composite savings:** 0.0% vs original baseline.
- **Break-even:** $35.94 spent, no kept iterations yet — loop is net-negative.

## 3. What worked

- **0/1 iterations kept** (0% keep rate).

## 4. What didn't

- **1 discarded** iterations grouped by reason:
  - `no_reason_recorded`: 1

## 5. What's redundant

- **Too few iterations (1/10) to assess gate discrimination.** Per-gate signal is recorded but not yet statistically meaningful.

## 6. What's noisy

- **Fixture A**: σ/mean = 25.5% (target: <25%). Timing-fragile.
- **Fixture B**: σ/mean = 56.1% (target: <25%). Timing-fragile.
- **Fixture C**: σ/mean = 26.5% (target: <25%). Timing-fragile.
- **Anchor attribution drift:** 0/159 prompts have >10% unattributed tokens (0.0%).

## 7. Idea backlog

- **1 attempted / 10 remaining** of 11 total in `OPTIMIZE_IDEAS.md`.

## 8. Lean recommendations

*Ranked by `(expected token reduction × applicability)`. Each item is actionable today — no speculation.*

- **Loop has spent $35.94 with zero kept iterations.** Either the 2σ bar is too tight (re-run baseline with N=10 to tighten σ) or ideas are systematically over-ambitious. Try smaller, more targeted ideas; the best ideas usually touch <50 lines.
- **Fixture B σ is 56.1% of mean** (threshold: 25%). It's too timing-fragile to gate verdicts on. Either raise its `timeout_s` in `run.py` FIXTURES dict (catches slow-but-correct runs that currently look like noise), or drop it from the baseline set.

## 9. KB leads (from `workflow knowledge`)

*KB query skipped: skipped via --skip-kb*

## Raw stats

```json
{
  "verdict_distribution": {
    "total": 1,
    "kept": 0,
    "discarded": 1,
    "crashed": 0,
    "pending": 0,
    "keep_rate": 0.0
  },
  "compound_effect": {
    "applicable": false
  },
  "gate_utility": {
    "_measurable": true,
    "_measured_n": 1,
    "cache": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    },
    "chunk": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    },
    "avoid": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    },
    "rate": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    },
    "build": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    },
    "ship": {
      "pass": 1,
      "fail": 0,
      "discriminating": false
    }
  },
  "baseline_noise": {
    "noisy_fixtures": [
      [
        "A",
        25.5
      ],
      [
        "B",
        56.1
      ],
      [
        "C",
        26.5
      ]
    ],
    "stable_count": 0
  },
  "per_prompt_anchors": {
    "scanned": 159,
    "drift_runs": 0,
    "drift_pct": 0.0
  },
  "idea_velocity": {
    "applicable": true,
    "total_ideas": 11,
    "attempted": 1,
    "remaining": 10
  }
}
```
