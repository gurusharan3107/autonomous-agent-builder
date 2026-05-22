# Tuning Methodology

> Read [README.md](README.md) first.

How to observe a live agent run and tune boundaries (tools, allowlists, permissions, prompts) so each specialist is effective: right prompt, right tool set, right allow/denylist, right context, right model. Goal: quality with less waste — not arbitrary token rationing.

Two halves: **continuous CLI monitoring** during a run + **per-prompt tuning loop** after.

---

## Continuous CLI Monitoring (always-on)

Any in-flight dashboard run needs `builder` CLI signals streaming in parallel. A 27-turn $0.46 run erroring at the end is cheaper to catch on turn 5 live than turn 27 post-mortem.

Set these streams **before the first operator prompt** of any test cycle; keep running:

| Stream | Catches |
| --- | --- |
| `watch -n 5 'cd <devpulse> && builder board show --json'` | Lane transitions + count drift live. |
| `watch -n 5 'builder logs analyze --session <id> --json'` | Per-turn `prompt_count`, `total_cost_usd`, `raw_token_total`, `cached_tokens`, `cache_ratio`, `chunk_pressure`, `recommended_next_change`. |
| `watch -n 5 'builder logs --error --compact --json'` | New runtime errors, SDK failures, hook denials, gate errors. |
| `watch -n 5 'builder backlog task status <task-id> --json'` | `blocked_reason` updates, `capability_limit` transitions. |
| `watch -n 5 'builder agent sessions --limit 5 --json'` | New agent runs starting (scaffold → code-gen → verifier). |

Cycle without these streams = blind. Harness blocks polling → set up CLI-driven notifications and act on every delta.

---

## Per-Prompt Tuning Loop

After each prompt completes:

### 1. Enumerate tool calls

```bash
builder agent history --session <id> --full --json
```

Each `tool_use` entry = a decision.

### 2. Per tool call: within agent's narrow job?

- Yes → allow.
- No → remove from this agent's allowlist. Out-of-responsibility tool call = allowlist bug, not model misbehavior.

Boundary is set by responsibility, not by "could be useful." Scaffold has Bash (sets up workspace); agent-chat does *not* have Bash (job is operator translation).

### 3. Tool denied but agent needed it

**Introduce or invoke a specialist that owns that job.** Don't widen the current agent's tools. agent-chat wants Write → "delegate to scaffold/code-gen", not "give agent-chat Write."

### 4. Re-run same prompt

Token cost, turn count, blocked-state count all go down. Else tuning wrong:

- Cost up, turns down → check cost-per-turn; maybe OK.
- Cost down, blocked up → too aggressive; agent lost a tool it needed.
- Nothing changed → tuning didn't affect run path; re-examine.

### 5. Cross-check after each iteration

```bash
builder logs analyze --session <id> --json
builder metrics show --json --full
```

Catch regressions in `cache_ratio`, `chunk_pressure`, `avoidable_cost_flags`. Lower token cost + higher chunk pressure = not a win.

---

## When to use

Rapid-iteration tuning. Use during:

- Live testing of new operator scenarios.
- Operator-UX regression rubrics didn't catch.
- Hard-gate failure with unclear cause.
- M2.4 (operator UX polish) iterations.
- `top_cost_drivers` shifts unexpectedly.

Longer-arc systematic optimization (autonomous, composite metric, 2σ noise floor) → [autoresearch loop](../autoresearch/README.md). This file = manual/interactive; autoresearch = autonomous/measured.

## Tuning vs autoresearch

| This file | Autoresearch |
| --- | --- |
| Manual, interactive, within a test cycle. | Autonomous, measured, continuous. |
| Tester judgment. | Hard-gate + 2σ composite test. |
| `builder agent history --full`. | `per_prompt_results.tsv` + `context_breakdown_json`. |
| Output: tool-allowlist + boundary changes. | Output: prompt-shape + context-block changes. |
| Development + live testing. | Optimization sprints (Track B, M3.5). |
| No formal noise floor. | 2σ from `baseline_variance.md`. |

Same kind of fix (less spend per shipped feature); different cadence + rigor. Manual builds intuition; autoresearch mechanizes + validates at scale.

## Common Patterns

Recurring; encoded as memory (see `builder memory search`). Recognizing them skips iterations.

| Pattern | Symptom | Fix |
| --- | --- | --- |
| Tool outside responsibility | agent-chat calls `Bash` / `Write` | Remove from allowlist; delegate. |
| Per-turn variable in cache prefix | `cache_ratio` drops on turn 2 | Move variable out of stable prefix; cache breakpoint between stable + variable. |
| Repeated retrieval | `builder board show` ×4 in one turn | Cache or move to context injection; flag as `avoidable_cost_flag`. |
| Tool-output reinjection | `chunk_pressure_risk: true` after large tool return | Cap at 2K + builder artifact pointer (OPTIMIZE_IDEAS #6). |
| Zero-turn paid run | `prompt_count: 0`, `cost > 0` | Deterministic shortcut bypassed model, or session shouldn't have started. |
| Wrong agent for job | code-gen mutates backlog | Routing bug, not agent bug. Fix routing. |
| Missed AskUserQuestion | Agent dumps 3 questions as prose | Use `AskUserQuestion` card — better UX, fewer turns, solves multi-turn context loss. |

## Closing the loop

Durable improvement →

1. Regression test pinning new behavior.
2. Record in [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) if closing a defect.
3. Memory entry per [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-durable) if non-obvious.
4. Update agent in `src/autonomous_agent_builder/agents/definitions.py`.
5. Update rubric in `docs/rubric/` if boundary changed.

No durable improvement → still log (session notes or `.claude/session-data/`) so next agent doesn't repeat dead end.

## Related

- [FIX-STANDARD.md](FIX-STANDARD.md) — 7-step standard tuning fixes follow.
- [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md) — language contract tuning preserves.
- [EVALUATION.md § Tier 1](EVALUATION.md#tier-1--token--ux-bars-every-release) — bars tuning keeps passing.
- [docs/workflows/agent-quality-tuning-loop.md](../workflows/agent-quality-tuning-loop.md) — broader workflow.
- [docs/rubric/autonomous-builder-agents.md](../rubric/autonomous-builder-agents.md) — per-agent responsibility map.
- [docs/autoresearch/](../autoresearch/README.md) — autonomous companion.
