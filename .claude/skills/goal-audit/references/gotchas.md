# Gotchas

> Loaded on demand from [goal-audit SKILL.md](../SKILL.md).

## Gotchas

These are specific traps the model will fall into without being told. They are the highest-value content in this skill.

- **`maintain_current_flow` is a healthy signal, not an absence of data.** When `aggregated_drivers.recommended_next_change` is dominated by `maintain_current_flow` (e.g. 6 of 6 sessions), the correct INSIGHTS verdict is "system stable, no autoresearch action." Do not invent a driver to recommend just because the skill ran.
- **`top_cost_drivers` may be a list of dicts OR a list of strings** depending on the Builder version. The collector normalizes this; trust `aggregated_drivers.top_cost_drivers` (a dict keyed by driver name), not the raw `analyze[*].top_cost_drivers`.
- **Cache breaks ≠ user intent shift.** A cache break at >100K is a *high-cost* prompt, not necessarily a *direction-pivot* prompt. Read the `context` array on the cache_break to see surrounding prompts — pivots cluster in 2-3 prompts of the same flavor ("are we aligned?", "is X updated?"). A single isolated cache break is usually a tool result blowing up the prefix.
- **`recent_prompts` is recency-ranked, not token-weighted.** Earlier in this skill's life, a `top_prompts` field was used; it was removed because token weight meant the first heavy planning prompt of a session would dominate the list forever and silently bury fresh short prompts. Always read `recent_prompts` (newest first) AND `cache_breaks` (pivot moments) for intent — and trust short recent prompts even if their token count is low.
- **Project key encoding is lossy.** `-home-gurusharangupta-Builder-Workspace-devpulse` could decode multiple ways because real paths contain `-`. The collector tries known prefixes; if a project's `builder_signals` is empty, the path may have failed to resolve — check `warnings[]`.
- **Builder-runtime sessions ≠ Claude Code sessions.** They are different transcript universes. session-report data is Claude Code; `builder agent sessions` is Builder runtime. The same fixture run on devpulse will appear in both, but with different IDs.
- **Do not edit `docs/IMPROVEMENTS.md` or `docs/SPRINT-PROGRESS.md`.** Those are living working docs but they have a specific update protocol that is not part of this audit. Reference them in INSIGHTS for cross-link, never modify.
- **Do not run the skill more than once per day per project.** Running it multiple times in quick succession produces redundant entries with the same data and dilutes the change-over-time signal in INSIGHTS.
- **If the user asks to compare to last week's audit, do not write a new entry.** Read the last 2 entries in INSIGHTS.md and diff them in your conversation reply.
- **`session_report.by_project` is already filtered to Builder projects** by `analyze-sessions.mjs --filter-pattern`. The collector trusts the analyzer; there is no second defensive filter in Python.
- **Use `--since-run` for same-day follow-up audits; use `--since 7d` for session-opening audits.** `--since-run` only shows new signal since the last entry — if the last entry was hours ago, most of the window is empty and the audit adds little value. Use the full window when starting a new session or after a gap of ≥2 days.
- **Always embed `<!-- collected_at: ... -->` in new INSIGHTS entries** (the format in Step 5 requires it). Without it, `--since-run` falls back to midnight of the entry's date, which can re-analyze up to 24h of already-seen data.
- **Do not recommend what is already on ROADMAP.md.** Before writing Section C, scan `goal_snapshot.ROADMAP.md` for each candidate action. A `[ ]` match means it is already tracked — say so and skip. A `[x]` match means it is done — credit it as closed, do not re-recommend. Only actions with no ROADMAP match are genuine gaps worth recommending.
