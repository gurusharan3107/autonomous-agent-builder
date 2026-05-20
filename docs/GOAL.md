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

## Per-Agent Boundaries (first principles)

Each agent has one job, derived from the customer requirement. Its tool
allowlist must match that job exactly — no broader. Mismatches become
operator-UX leaks (agent asks the user about permissions, Write hooks,
dispatch, worktrees, etc.).

- **agent-chat**: translate operator intent into Builder lifecycle moves and
  explain Builder state in product language. Tools: Read, `mcp__builder__*`
  read + narrow lifecycle mutations (backlog item create, sprint approve,
  task dispatch/supersede, task recover), AskUserQuestion-equivalent. NO
  Write, NO Edit, NO raw Bash. If the operator needs files written, agent-chat
  must invoke a lifecycle MCP that triggers the scaffold or code-gen agent —
  it must never write code itself.
- **scaffold** (runtime-decided, model-backed): pick the stack from feature
  intent, ask the operator only if the stack is genuinely ambiguous, scaffold
  the appropriate config files, register language-appropriate gates. Tools:
  Read/Write/Edit/Bash inside workspace, mcp__workspace__* run_command/
  run_tests, AskUserQuestion, language-aware gate-registration tool. NO
  backlog/board mutations. **Scaffold is not Python-specific** — it decides
  stack at runtime per feature/operator intent.
- **code-gen**: implement one approved task inside its worktree. Tools: Read/
  Write/Edit/Glob/Grep/Bash with `cwd=worktree`, mcp__workspace__*. NO
  backlog/board mutations. NO writes outside the worktree (enforced by
  `enforce_workspace_boundary` hook).
- **build-verifier**: run lint/test/build/browser proofs and return structured
  evidence. Tools: Read, mcp__workspace__ run_tests/run_linter/run_command,
  read-only Bash. NO Write/Edit, NO mutations.
- **repo-researcher**: read-only repo discovery for reverse engineering and
  for diagnosing existing surfaces. Read/Glob/Grep, mcp__builder__* reads.
  NO Write/Edit, NO mutations.
- **doc-bridge**: maintained-doc freshness at the delivery edge. Edit on docs
  paths only. NO Bash, NO Write outside docs/.

## Tuning Methodology

### Continuous CLI monitoring (always-on, not on-demand)

While ANY agent run is in flight on the dashboard, the tester must have
`builder` CLI signals streaming in parallel. Do not wait until the agent
"settles" to inspect — a 27-turn $0.46 run that errors at the end is much
cheaper to catch on turn 5 via live CLI than at turn 27 via post-mortem.

Set up these streams before the first operator prompt of any test cycle and
keep them running for the whole cycle (foreground tail, persistent Monitor,
or equivalent — whatever your harness supports):

- `watch -n 5 'cd <devpulse-workspace> && builder board show --json'`
  → catches Board lane transitions (pending → active → blocked → done →
  shipped) and count drift in real time.
- `watch -n 5 'builder logs analyze --session <id> --json'`
  → catches per-turn changes in prompt_count, total_cost_usd, raw_token_total,
  cached_tokens, cache_ratio, chunk_pressure, recommended_next_change.
- `watch -n 5 'builder logs --error --compact --json'`
  → fires on every new runtime error, SDK failure, hook denial, gate error.
- `watch -n 5 'builder backlog task status <task-id> --json'`
  → catches blocked_reason updates and capability_limit transitions on the
  task under test.
- `watch -n 5 'builder agent sessions --limit 5 --json'`
  → catches new agent runs starting (scaffold → code-gen → verifier chain).

A test cycle running without these streams is functionally blind. If your
harness blocks the tester from continuous polling, set up CLI-driven
notifications that fire on each delta and act on every delta as it arrives.

### Per-prompt tuning loop

After each operator prompt completes:

1. `builder agent history --session <id> --full --json` — enumerate every
   tool call the agent actually made.
2. For each tool call ask: is this within the agent's narrow job?
   - If yes, allow.
   - If no, move the tool OUT of this agent's allowlist.
3. For each tool call that was DENIED but the agent genuinely needed: prefer
   introducing or invoking a different agent that owns that job over widening
   the current agent's tools. Default to narrow specialists; broaden only when
   no specialist fits.
4. Re-run the same operator prompt after tuning. Token cost, turn count, and
   blocked-state count must all go down. If they don't, the tuning was wrong.
5. Cross-check `builder logs analyze --session <id> --json` and
   `builder metrics show --json --full` after every tuning iteration to catch
   regressions in cache ratio, chunk pressure, and avoidable-cost flags.

## Forbidden Operator Language

This rule binds **both sides** of the operator transcript: the human / tester
acting as operator AND the agent responding to them. A real operator is a
non-technical product user — they do not know what a "lifecycle", "scaffold
tool", "worktree", "permission mode", or "Recover button" is, and they will
not type those words. Testing the product with internals-laden prompts hides
real operator-UX bugs, because the agent gets a free hint that bypasses the
disambiguation work it should be doing.

Banned terms (unless the operator literally typed them first, verbatim, in a
prior turn): write hook, permission mode, allowlist, dispatch, gate, worktree,
scaffold, blocked_reason, can_use_tool, allowed_tools, MCP, mcp__builder__*,
subagent, SDK, session_id, cwd, hook policy, lifecycle, phase, dispatch flow,
quality gate, code-gen, agent-chat, recover, recovery action.

The agent must own the concept internally; the operator-side prompt must use
product language.

**Good operator prompts (use these shapes when testing):**
- "I want a developer pulse dashboard for my team's GitHub activity."
- "It's still not working. When can I see the dashboard?"
- "Add a search box to the page I just saw."
- "This button is broken — fix it."
- "What's the holdup?"
- "Show me what shipped."
- "Drop the persistence idea and keep the rest."
- "Make it faster."

**Bad operator prompts (do not use when testing):**
- "Recover the blocked task and dispatch it through the proper lifecycle."
- "Use the scaffold tool to set up the workspace."
- "Approve the sprint plan and trigger the next phase."
- "Override the permission policy so Write is enabled."

The word "recover" may appear in the **agent's reply** only if the dashboard
exposes a visible Recover control AND that control is actually functional for
the current blocked state. A 409 "task_not_recoverable" with the Recover
button still rendered is a hard operator-trust failure.

## Operator Scenarios (forward, edge, reverse)

Forward engineering:

- F1: fresh workspace → "I want a developer pulse dashboard for my team" —
  agent-chat asks 3-5 product questions → scaffold decides stack → planner
  approves → code-gen implements → ship with browser proof.
- F2: "Add a search box to my dashboard" — incremental on existing app; skip
  scaffold; capture as improvement; plan/approve/implement.
- F3: "This button is broken — fix it" — repo-researcher locates; capture
  incident; code-gen patches; build-verifier confirms; ship.
- F4: "Make it faster" — clarify which surface; measure; capture optimization;
  plan; implement.
- F5: "Drop the persistence feature" mid-sprint — confirm, supersede task,
  update backlog.
- F6: "What's the status?" — read board/runs/metrics; answer in product
  language; no mutations.
- F7: "Show me a screenshot of what shipped" — invoke build-verifier; embed
  result in chat.
- F8: "Make it better" (ambiguous) — ask structured questions; do not capture
  until intent is clear.
- F9: "Yes, ship it" — approve sprint; trigger dispatch.
- F10: "What's the weather?" — politely redirect; no tool calls.

Edge cases / failure scenarios:

- E1: code-gen fails mid-sprint — orchestrator marks blocked with actionable
  text; auto-retry once if transient; never ask operator about
  Write/permissions/worktree.
- E2: provider limit hit — pause with `capability_limit` + reset metadata;
  auto-resume on reset.
- E3: approval rejected — ask "what should change?" with structured options.
- E4: concurrent tabs — state consistent; second tab inherits same session.
- E5: transient SDK / network error — retry with backoff; surface only if
  persistent.
- E6: irreversible action requested — structured confirmation with explicit
  consequence text before any mutation.
- E7: sprint completion — summarize shipped scope, browser proof, cost; ask
  "what's next?".
- E8: stack mismatch discovered late — block + offer migration path; never
  silently break.
- E9: operator answers a question card with freeform text — parse intent;
  route to the matching lifecycle action.

Reverse engineering:

- R1: "Help me understand this codebase" — repo-researcher inventories;
  summarize in product language.
- R2: "Add tests to this Java repo" — scaffold detects existing Java/Maven;
  registers junit/checkstyle gates; does not rescaffold.
- R3: "Migrate to TypeScript" — capture as project with multi-sprint plan;
  approve per phase.

Every code change to agent definitions, tool allowlists, or phases must be
validated against this scenario list before merging.
