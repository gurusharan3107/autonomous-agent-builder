# Autoresearch loop introspection

*Generated 2026-05-23T17:52:14Z by `.claude/skills/autoresearch/scripts/introspect.py`. Overwritten each close-out — `git log` for history.*

## 1. Token economics — where do tokens go?

- No per-prompt rows yet (zero iterations). Section becomes meaningful once `optimize_results.tsv` has rows.

## 2. Cumulative loop ROI

- **Spent:** $8.69 across all iterations (per-prompt cost sum).
- **Kept iterations:** 0.
- **Cumulative composite savings:** 0.0% vs original baseline.
- **Break-even:** $8.69 spent, no kept iterations yet — loop is net-negative.

## 3. What worked

No iterations recorded yet. This report becomes meaningful after the first iteration
lands a row in `optimize_results.tsv`. Re-run `introspect.py` after iteration #1.

## 4. What didn't

- No discarded iterations yet.

## 5. What's redundant

- **Hard gates `cache`, `chunk`, `avoid`, `rate`, `build`, `ship` never discriminated** (always pass or always fail). Worth tightening or removing.

## 6. What's noisy

- All fixtures within 25% σ/mean threshold (good).
- **Anchor attribution drift:** 0/23 prompts have >10% unattributed tokens (0.0%).

## 7. Idea backlog

- **0 attempted / 0 remaining** of 0 total in `OPTIMIZE_IDEAS.md`.

## 8. Lean recommendations

*Ranked by `(expected token reduction × applicability)`. Each item is actionable today — no speculation.*

- **Loop has spent $8.69 with zero kept iterations.** Either the 2σ bar is too tight (re-run baseline with N=10 to tighten σ) or ideas are systematically over-ambitious. Try smaller, more targeted ideas; the best ideas usually touch <50 lines.
- **No iterations recorded yet.** Run Recipe 1 + Recipe 2 first; introspection becomes useful after ≥5 iterations.

## 9. KB leads (from `workflow knowledge`)

Articles relevant to making the loop leaner. Read with: `workflow knowledge read <slug>`.

**Query:** `prompt caching token cost`

- `2026-04-07-cache-read-tokens-track-separately-measure-caching-savings`
    > ## Insight Claude's prompt caching returns `cache_read_input_tokens` (tokens read from cache at ~10%
- `2026-04-07-reasoning-models-require-manual-token-submission`
    > …or the autonomous-agent-builder's ClaudeCodeRunner: always extract `usage.input_tokens` and `usage.
- `2026-03-27-exact-prefix-preservation-prompt-caching`
    > …licability In the Claude Code harness: when appending tool call outputs to the prompt history, ensu

**Query:** `context engineering token reduction`

- `2026-04-04-monorepo-baseline-context`
    > Monorepo context baseline ~20k tokens, 10% of window
- `2026-04-04-observation-masking-beats-llm-summarization`
    > Observation masking beats LLM summarization for context reduction — 50%+ cost, equal or better perfo
- `2026-04-04-fic-40-60-percent-optimal-compact-at-60`
    > FIC targets 40-60% context utilization as optimal zone — compact at 60%, not 80%

**Query:** `agent skill bundle minimal context`

- `2026-04-04-preload-skills-into-subagent-context`
    > Preload skill content into subagent context at startup
- `2026-04-04-passive-context-beats-active-skill-retrieval`
    > Passive context (always-loaded docs index) beats active skill retrieval — 100% vs 53% on framework e
- `2026-04-04-structured-memory-across-context-windows`
    > Agents require formalized persistent memory outside context windows

**Query:** `fixture redundancy benchmark variance`

- `2026-04-05-abstract-benchmark-runner-for-agnostic-loops`
    > Abstract BenchmarkRunner makes improvement loops benchmark-agnostic
- `2026-04-07-ai-generated-tests-are-structural-signal-not-behavioral-gate`
    > AI-generated tests are structural signal only — green tests do not mean correct behavior; use approv
- `2026-04-07-regime-shift-adaptation-should-be-benchmarked-explicitly`
    > regime-shift-adaptation-should-be-benchmarked-explicitly

## Raw stats

```json
{
  "verdict_distribution": {
    "total": 0,
    "kept": 0,
    "discarded": 0,
    "crashed": 0,
    "pending": 0,
    "keep_rate": 0
  },
  "compound_effect": {
    "applicable": false
  },
  "gate_utility": {
    "cache": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    },
    "chunk": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    },
    "avoid": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    },
    "rate": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    },
    "build": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    },
    "ship": {
      "pass": 0,
      "fail": 0,
      "discriminating": false
    }
  },
  "baseline_noise": {
    "noisy_fixtures": [],
    "stable_count": 1
  },
  "per_prompt_anchors": {
    "scanned": 23,
    "drift_runs": 0,
    "drift_pct": 0.0
  },
  "idea_velocity": {
    "applicable": true,
    "total_ideas": 0,
    "attempted": 0,
    "remaining": 0
  }
}
```
