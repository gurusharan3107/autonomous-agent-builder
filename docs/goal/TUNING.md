# Tuning Methodology

> **Read [README.md](README.md) first.**

This file describes how to observe a live agent run and how to tune agent boundaries (tools, allowlists, permissions, prompts) so each specialist becomes effective at its job: right prompt, right tool set, right allowlist and denylist, right context, right model for the work. The goal is quality with less wasted context and time — not arbitrary token rationing.

The methodology has two halves: **continuous CLI monitoring** during a run, and **the per-prompt tuning loop** after a run.

---

## Continuous CLI Monitoring (always-on, not on-demand)

While ANY agent run is in flight on the dashboard, the tester must have `builder` CLI signals streaming in parallel. Do not wait until the agent "settles" to inspect — a 27-turn $0.46 run that errors at the end is much cheaper to catch on turn 5 via live CLI than at turn 27 via post-mortem.

Set up these streams **before the first operator prompt of any test cycle** and keep them running for the whole cycle (foreground tail, persistent Monitor, or equivalent — whatever your harness supports):

| Stream | What it catches |
| --- | --- |
| `watch -n 5 'cd <devpulse-workspace> && builder board show --json'` | Board lane transitions (pending → active → blocked → done → shipped) and count drift in real time. |
| `watch -n 5 'builder logs analyze --session <id> --json'` | Per-turn changes in `prompt_count`, `total_cost_usd`, `raw_token_total`, `cached_tokens`, `cache_ratio`, `chunk_pressure`, `recommended_next_change`. |
| `watch -n 5 'builder logs --error --compact --json'` | Every new runtime error, SDK failure, hook denial, gate error. |
| `watch -n 5 'builder backlog task status <task-id> --json'` | `blocked_reason` updates and `capability_limit` transitions on the task under test. |
| `watch -n 5 'builder agent sessions --limit 5 --json'` | New agent runs starting (scaffold → code-gen → verifier chain). |

A test cycle running without these streams is **functionally blind**. If your harness blocks the tester from continuous polling, set up CLI-driven notifications that fire on each delta and act on every delta as it arrives.

---

## Per-Prompt Tuning Loop

After each operator prompt completes, run this loop:

### 1. Enumerate every tool call the agent actually made

```bash
builder agent history --session <id> --full --json
```

Look at the `tool_use` entries in order. Each one is a decision the agent made about what to inspect or mutate.

### 2. For each tool call, ask: is this within the agent's narrow job?

- **If yes → allow.** The agent used the right tool for its responsibility.
- **If no → move the tool OUT of this agent's allowlist.** A tool call outside the agent's responsibility is a tool-allowlist bug, not a model misbehavior.

The boundary is set by the agent's responsibility, not by what tools "could be useful." A scaffold agent has Bash because it has to set up the workspace; agent-chat does *not* have Bash because its job is operator translation, not code mutation.

### 3. For each tool call that was DENIED but the agent genuinely needed

**Prefer introducing or invoking a different agent that owns that job** over widening the current agent's tools. Default to narrow specialists; broaden only when no specialist fits.

This rule keeps agent boundaries from drifting. If agent-chat keeps wanting to call Write, the answer is "agent-chat must delegate to a scaffold or code-gen agent" — not "give agent-chat Write."

### 4. Re-run the same operator prompt after tuning

Token cost, turn count, and blocked-state count must **all go down**. If they don't, the tuning was wrong:

- Token cost went up but turn count went down → maybe acceptable; check whether the cost-per-turn improved meaningfully.
- Token cost went down but blocked-state count went up → tuning was too aggressive; the agent lost a tool it needed.
- Nothing changed → the tuning didn't affect the actual run path; re-examine.

### 5. Cross-check after every iteration

```bash
builder logs analyze --session <id> --json
builder metrics show --json --full
```

Catch regressions in `cache_ratio`, `chunk_pressure`, and `avoidable_cost_flags`. A tuning that lowers token cost while raising chunk pressure is not a win.

---

## When to Use This Methodology

This is the rapid-iteration version of agent tuning. Use it during:

- Live testing of new operator scenarios.
- Debugging an operator-UX regression that the rubrics didn't catch.
- Investigating a hard-gate failure where the cause is unclear from logs alone.
- Roadmap item M2.4 (operator UX polish) iterations.
- Any time the per-session `top_cost_drivers` shifts unexpectedly.

For longer-arc systematic optimization (where the loop is fully autonomous, the metric is composite, and a 2σ noise floor governs keep/discard), use the [autoresearch loop](../autoresearch/README.md) instead. Tuning methodology here is the manual / interactive version; autoresearch is the autonomous / measured version.

## Relationship to autoresearch

| Tuning methodology (this file) | Autoresearch loop |
| --- | --- |
| Manual, interactive, iterative within a test cycle. | Autonomous, measured, runs continuously. |
| Decisions made by the tester / operator. | Decisions made by hard-gate + 2σ composite test. |
| Per-prompt diagnosis using `builder agent history --full`. | Per-prompt diagnosis using `per_prompt_results.tsv` + `context_breakdown_json`. |
| Output: tool-allowlist changes, agent boundary refinements. | Output: prompt-shape changes, context-block adjustments. |
| Used in development and live testing. | Used in optimization sprints (Track B, M3.5). |
| No formal noise floor; tester judgment. | Formal 2σ noise floor from `baseline_variance.md`. |

Both methods produce the same kind of fix (smaller token spend per shipped feature); they differ in cadence, automation level, and rigor. Use tuning methodology to develop intuition; use autoresearch to mechanize and validate the intuition at scale.

## Common Tuning Patterns

These patterns have repeatedly shown up in past tuning loops and are encoded as memory entries (see `builder memory search`). Recognizing them lets you skip several iterations.

| Pattern | What it looks like | Fix |
| --- | --- | --- |
| Tool call outside responsibility | agent-chat calls `Bash` / `Write` | Remove tool from allowlist; delegate to specialist agent. |
| Per-turn variable in cache prefix | `cache_ratio` drops on turn 2 of every session | Move per-turn content out of stable prefix; cache breakpoint between stable and variable blocks. |
| Repeated retrieval | Agent calls `builder board show` 4× in one turn | Cache the result or move to context injection; if it must re-read, mark as `avoidable_cost_flag`. |
| Tool output reinjection | `chunk_pressure_risk: true` after a tool returned a large output | Cap reinjection at 2K tokens with builder artifact pointer per `OPTIMIZE_IDEAS.md` item 6. |
| Zero-turn paid run | `prompt_count: 0`, `cost: > 0` | Runtime started a turn that produced no output; deterministic shortcut bypassed the model, or session shouldn't have been started. |
| Wrong agent for the job | code-gen makes backlog mutations | code-gen has no MCP backlog tools; the orchestrator routed to the wrong agent. Fix the routing, not the agent. |
| Missed AskUserQuestion | Agent dumps three questions as prose | Replace with `AskUserQuestion` structured card — better UX, lower turn count, solves multi-turn context loss. |

## Closing the Loop

A tuning iteration that produces a durable improvement should:

1. Be backed by a regression test that pins the new behavior.
2. Be recorded in [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) if it closed a defect.
3. Produce a memory entry per [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable) if the learning is non-obvious.
4. Update the relevant agent definition in `src/autonomous_agent_builder/agents/definitions.py`.
5. Update the relevant rubric in `docs/rubric/` if the boundary itself changed.

A tuning iteration that did not produce a durable improvement should still be logged (in session notes or `.claude/session-data/`) so the next agent doesn't repeat the dead end.

## Related

- [FIX-STANDARD.md](FIX-STANDARD.md) — the 7-step standard tuning fixes follow.
- [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md) — language contract every tuning must preserve.
- [EVALUATION.md § Tier 1](EVALUATION.md#tier-1--token--ux-bars-every-release) — bars every tuning must keep passing.
- [docs/workflows/agent-quality-tuning-loop.md](../workflows/agent-quality-tuning-loop.md) — broader workflow this methodology is part of.
- [docs/rubric/autonomous-builder-agents.md](../rubric/autonomous-builder-agents.md) — the per-agent responsibility map tuning enforces.
- [docs/autoresearch/](../autoresearch/README.md) — the autonomous companion to this manual methodology.
