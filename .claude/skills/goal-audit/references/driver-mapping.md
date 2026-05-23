# Driver-to-idea mapping (static)

> Loaded on demand from [goal-audit SKILL.md](../SKILL.md).

## Driver-to-idea mapping (static)

Apply this table against the three streams in `aggregated_drivers`. The first column names the stream + value; the second names the target OPTIMIZE_IDEAS item.

### Stream 1 — `recommended_next_change` (one value per session)

| Value | OPTIMIZE_IDEAS item(s) |
| --- | --- |
| `truncate_tool_output_before_reinjection` | 6 (cap tool-output reinjection) |
| `reduce_agent-chat_raw_tokens` | 1+2 (multi-item — advisory only, no auto-reorder) |
| `bounded_retrieval_shortcut` | 4+5 (multi-item — advisory only) |
| `maintain_current_flow` | no autoresearch action — record "system stable" in INSIGHTS |

### Stream 2 — `avoidable_cost_flags` (zero-or-more flags per session)

| Value | OPTIMIZE_IDEAS item(s) |
| --- | --- |
| `large_command_output` | 6 |
| `chunk_pressure_large_event` | 6 |
| `chunk_pressure_risk_large_event` | 6 |
| `repeated_retrieval` | 4+5 (multi-item — advisory only) |
| `repeated_scan` / `redundant_scan` | 4+5 (multi-item — advisory only) |
| `phase_ceremony_oversize` / `phase_ceremony_tokens` | 7 (delete inactive phase-context) |
| `gate_feedback_oversize` / `gate_feedback_oversized` | 9 (compact gate feedback) |
| `intake_loop_length` (heuristic from session-report: ≥3 intake prompts before first ship) | 3 (AskUserQuestion for intake) |

### Stream 3 — `agent_names_with_avoidable_tokens` (zero-or-more per session)

These are agent names from `top_cost_drivers` where `avoidable_token_estimate > 0`. Per-agent attribution doesn't always map cleanly to a single OPTIMIZE_IDEAS item; treat as diagnostic unless the same agent recurs.

| Agent name | OPTIMIZE_IDEAS item(s) (only when `sessions ≥ 3`) |
| --- | --- |
| `code-gen` | 8 (subagent for code-gen) |
| `agent-chat` | 1+2 (multi-item — advisory only) |
| `optimization-agent` | (no idea — usually a Builder ownership boundary issue, surface in INSIGHTS) |
| (other) | (unmapped — surface in INSIGHTS and propose adding to this table) |

### Heuristic signals from session_report (not in aggregated_drivers)

| Heuristic | OPTIMIZE_IDEAS item |
| --- | --- |
| `session_report.cache_breaks_over_100k > 5` clustering on a single runtime lane | 10 (cache header per-runtime-lane) — *advisory*, never auto-reorder |

If a value appears in any stream that is not in this table, record it in INSIGHTS § Section B as `(unmapped)` and propose adding it to this table under § Recommended actions.
