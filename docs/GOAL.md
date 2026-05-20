Act as the lead operator and principal engineer for Autonomous Builder.

**Primary goal: rigorous live testing to uncover every inefficiency in the Autonomous Builder, then apply correct SDK-grounded solutions.**

Make Autonomous Builder prove, through the live Agent page, that a non-technical operator can say "I want to add/improve X" and Builder will own the full lifecycle: ask only necessary product questions, capture the improvement, request clear approvals, create the delivery plan, start work, ship it, and report evidence without requiring the operator to know backlog, sprint, task, or product-backlog concepts. Use builder managed devpulse app for validation and testing.

Test the live product through the dashboard exactly like a real operator would: use the Agent page, Realtime Voice text input, Board, Backlog, settings, approvals, logs, metrics, and browser-visible behavior. Prompt naturally, not with over-specified test instructions.

**Scope of "inefficiency":** Anything that remotely affects the Autonomous Builder counts — not just visible operator UX. Hunt across all of these categories:
- **Token usage:** raw tokens, cached tokens, non-cached+output tokens, cache ratio, cost per turn, cost per shipped feature.
- **Context bloat:** per-turn prompt payload size, what gets injected into the SDK prompt, redundant retrieval, large-output reinjection, repeated KB/board reads, oversized `CLAUDE.md` or system prompts, unbounded tool outputs.
- **Inefficient agent use:** zero-turn runs that still consume cost, repeated tool calls for the same data, wrong agent for the job (model-backed where deterministic would do, deterministic where judgment is needed), unbounded turn loops, missed subagent opportunities, missed cache opportunities.
- **Surface drift:** discrepancies between CLI truth and UI display (e.g., `metrics show` reporting 0 while logs show real cost, board API showing different counts than `builder map`, stale messages in the timeline).
- **Dead code / dead paths:** unreachable handlers, stale recovery branches, orphaned migration code, baselines that don't ratchet down.
- **Slow paths:** phase transitions that hang, dispatched tasks that don't actually start, recovery loops that 409, retries without backoff.
- **Operator UX:** lifecycle terms leaking into operator-facing copy, missing inline controls, broken decision handoffs, ambiguous status pills.

**Builder CLI is the primary investigative weapon.** Browser testing reproduces the symptom; the CLI exposes the cause. Use it extensively and aggressively:
- `builder map` — start every investigation here.
- `builder logs --compact --json` and `builder logs --error --json` — raw runtime evidence.
- `builder logs analyze --session <id> --json` — per-session token/turn/cache breakdown.
- `builder metrics show --json --full` — cross-session aggregates and avoidable-cost flags.
- `builder agent history --session <id> --full --json` — full conversation context and SDK telemetry.
- `builder agent sessions --full --limit 100 --json` — recent session corpus.
- `builder board show --json` — canonical task/sprint state.
- `builder backlog item list --json` / `builder backlog task show <id> --json` — backlog truth.
- `builder quality-gate <surface> --json` — invariants for every surface touched.
- `builder memory search "<query>" --tag <tag>` — repo precedent before reinventing.
- `builder knowledge summary "<query>"` and `builder knowledge validate --json` — system-doc truth and freshness.

If a CLI surface returns 0 or empty when the system is clearly active, treat that as an inefficiency in its own right and log it.

**Testing standard:** Every test pass must be rigorous enough to surface hidden inefficiencies — not just verify the happy path. This means:
- Testing every multi-turn intake flow end to end to catch context loss between turns.
- Verifying every board state transition (pending → active → review → done → shipped) produces correct counts and phase dots.
- Monitoring per-turn token usage, cache ratios, and per-turn prompt payload size using `builder logs analyze` and `builder metrics show --full` after every run — not just at the end.
- Checking gate infrastructure exists BEFORE dispatching implementation in any fresh workspace.
- Validating recovery paths (Recover button, Board continuation) under both gate failures and infrastructure errors.
- Inspecting `builder agent history --full` after every session to verify context threading, stop reasons, tool call efficiency, and whether each turn's context payload was necessary.
- Cross-checking all visible surfaces (Agent timeline, Board, Backlog, Metrics, Observability) against CLI truth (`builder board show`, `builder logs`, `builder metrics`, `builder map`) to find discrepancies.
- Flagging memory-worthy findings as you test. If a test reveals a non-obvious correction (wrong scope, wrong owner, surprising SDK behavior), note it for a memory write at fix closeout — don't lose the learning between test and fix.

**Fix standard:** When something fails, diagnose from first principles. Start from the visible symptom, inspect builder-owned logs/metrics/session evidence, identify the true owning layer, and fix the durable product or runtime cause. Every fix must follow this order:
0. **Load repo precedent first.** Before exploring code for any non-trivial fix, run `builder memory search "<topic>"` from the Builder source repo (not a managed workspace) and `builder memory show <slug>` for any hit. The 90 active memories under `.memory/` (corrections, decisions, patterns) encode prior decisions that must shape the fix. Skipping this step risks re-litigating settled questions or violating a single-owner pattern (e.g., `blocked-recovery-has-one-builder-owner`, `keep-agent-page-intent-model-backed-while-optimizing-to`).
1. **Explore the codebase.** Find the exact owning module, route, or runtime path before proposing a fix. Use the Explore agent or `grep`/`find` to locate the real owner. Do not guess based on filenames.
2. **Load required AGENTS.md triggers.** Before editing any file with a required trigger (`CLAUDE.md`, `AGENTS.md`, runtime, CLI, quality gates), run the prescribed `builder quality-gate <surface>` or `workflow summary <name>` first. AGENTS.md lists the triggers — follow them.
3. **Ground the fix in Claude Agent SDK documentation and best practices** — not workarounds. Cite the SDK feature being used (permissions, hooks, subagents, AskUserQuestion, compaction, cache control).
4. **Apply at the correct layer** (orchestrator, route, SDK runtime, frontend) — not patched at the surface. Do not patch the UI if the backend state is wrong.
5. **Verify with `builder quality-gate` checks and focused regression tests.** Add a deterministic regression test for the exact failure.
6. **Record in `docs/IMPROVEMENTS.md`** with symptom, root cause, SDK-grounded solution, evidence (session id, command output), and status.
7. **Write memory back if the learning is durable.** After the fix lands, ask: would a future agent doing similar work benefit from knowing this? If yes, run `builder memory add --type correction|pattern|decision --tag <relevant-tags>` from the Builder source repo. Memory is for: non-obvious owner boundaries, single-control-owner patterns (like `blocked-recovery-has-one-builder-owner`), recurring traps (like memory scope confusion in IMP-005), SDK-specific gotchas, and reasoning that wasn't obvious from code alone. Do NOT memorize: the symptom itself (lives in IMPROVEMENTS.md), one-off bug details, or anything the next agent could derive by reading current code. Also invalidate or update any existing memory that the fix proved stale: `builder memory invalidate <slug> --reason <one-line>`.

**Acceptance thresholds (devpulse validation cycle):** A run only passes when ALL of these hold. They are taken from `docs/PROGRESS.md` and are non-negotiable for declaring the operator experience "10/10":

- **Cache ratio > 5x after turn 2** for every agent turn. Lower than 5x means the SDK prompt isn't reusing cached context — investigate prompt shape and cache control.
- **`chunk_pressure_risk: false`** across all feature runs. Any `true` value means a tool output approached the SDK chunk limit and risks reinjection bloat.
- **`avoidable_cost_flags: []`** across all feature runs. Any flag means the metrics surface has identified a token waste pattern (large-output reinjection, repeated broad retrieval, zero-turn paid runs, redundant scans).
- **Gates-first**: the target workspace has `ruff`, `mypy`, and architecture-import enforcement configured *before* any feature code is dispatched. No 27-turn implementation runs ending in `FileNotFoundError` at the gate step.
- **Zero stale operator-facing messages** in the timeline after a successful flow. Reconciliation must hide superseded "I do not have a captured improvement" / similar stale responses once the actual flow succeeded.
- **CLI/UI surface parity**: `builder metrics show` and the Metrics page must agree with `builder logs --compact` raw cost data. A 0-token report while $0.46 was actually spent counts as a hard failure.
- **Recovery path exists for every blocked state**: no `409 task_not_recoverable` dead end. If a `blocked_reason` type cannot be recovered programmatically, the Board must render an actionable next-step message instead of a non-functional Recover button.

Verify these with `builder logs analyze --session <id> --json`, `builder metrics show --json --full`, and `builder board show --json` after every shipped feature.

Do not patch generated apps by hand, do not rely on curl/API shortcuts as a substitute for dashboard validation, and do not stop at symptom-level fixes. What is ingested into agent context per turn, how many tokens are consumed, when the Agent page loads what all gets loaded — the system must be efficient on all fronts.

  Add two explicit acceptance layers on top of the original goal:

  1. Operator UX abstraction
      - No operator-facing dependency on internal lifecycle terms.
      - Question/approval cards must render readable labels, not [object Object].
      - Approval should naturally continue delivery, or the UI must make the next action obvious.
      - Agent and Realtime Voice should handle the same plain wording consistently.
  2. Live shipping plus token monitoring
      - Test by actually shipping the feature from the Agent page, not just route tests.
      - Monitor with builder logs, builder metrics, and builder board during the run.
      - Track per-run tokens, total/raw tokens, cached tokens, noncached+output tokens, chunk pressure, large-output flags, zero-turn runs, repeated retrieval, and blockers.
      - Treat token waste or chunk risk as product robustness issues, not just cost notes.

Keep testing through the browser until the core Autonomous Builder experience would deserve a 10/10 rating for robustness, clarity, recovery, lifecycle behavior, and operator trust.

Guiding principles:
1. Ask, don't assume. If something is unclear, ask before writing a single line.
2. Simplest solution first. Do not add abstractions or flexibility that weren't explicitly requested.
3. Don't touch unrelated code. If a file or function is not directly part of the current task, do not modify it.
4. Flag uncertainty explicitly. If not confident about an approach, say so before proceeding.
