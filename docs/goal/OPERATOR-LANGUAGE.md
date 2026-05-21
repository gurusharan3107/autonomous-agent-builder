# Operator Language and Scenarios

> **Read [README.md](README.md) first.**

This file defines the language contract for every operator-facing surface and the scripted scenarios used to validate operator behavior. It binds both sides of the operator transcript: the human/tester acting as operator AND the agent responding to them.

A real operator is a non-technical product user. They do not know what a "lifecycle", "scaffold tool", "worktree", "permission mode", or "Recover button" is, and they will not type those words. Testing the product with internals-laden prompts hides real operator-UX bugs, because the agent gets a free hint that bypasses the disambiguation work it should be doing.

## Banned Operator-Facing Terms

These terms are forbidden in operator-facing UI copy, Agent transcripts, Voice transcripts, Board labels, Backlog labels, Inbox messages, Settings, and approval cards — **unless the operator literally typed them first, verbatim, in a prior turn**:

```
write hook            permission mode        allowlist             dispatch
gate                  worktree               scaffold               blocked_reason
can_use_tool          allowed_tools          MCP                    mcp__builder__*
subagent              SDK                    session_id             cwd
hook policy           lifecycle              phase                  dispatch flow
quality gate          code-gen               agent-chat             recover
recovery action       bounded                raw logs               full logs
chunk                 token pressure         backlog                sprint
task id               scaffold tool          permission             tool approval
```

The agent must own the concept internally; the operator-side prompt must use product language.

### Two recoverable exceptions

1. **The operator typed the term verbatim first.** Once the operator says "worktree" or "permission", the agent may use that term in its reply. The agent's reply must not introduce a *different* banned term.
2. **`Recover` may appear in the agent's reply** if and only if the dashboard exposes a visible Recover control AND that control is actually functional for the current blocked state. A `409 task_not_recoverable` with the Recover button still rendered is a hard operator-trust failure.

## Operator Prompt Shapes

### Good operator prompts (use these when testing)

```
"I want a developer pulse dashboard for my team's GitHub activity."
"It's still not working. When can I see the dashboard?"
"Add a search box to the page I just saw."
"This button is broken — fix it."
"What's the holdup?"
"Show me what shipped."
"Drop the persistence idea and keep the rest."
"Make it faster."
```

### Bad operator prompts (never use these for testing)

```
"Recover the blocked task and dispatch it through the proper lifecycle."
"Use the scaffold tool to set up the workspace."
"Approve the sprint plan and trigger the next phase."
"Override the permission policy so Write is enabled."
"Invoke delegate_to_builder_agent."
"Call get_builder_agent_update."
"Set answer_value to the recommended option."
"Run telemetry analysis with compact logs."
```

These are implementation details. The operator should speak in product language and let Realtime or the Agent page choose the right Builder tool, retrieval, or delegation path.

## Operator Scenarios

Every code change to agent definitions, tool allowlists, or phases must be validated against this scenario list before merging. Scenarios are grouped: forward engineering (F), edge / failure (E), reverse engineering (R).

### Forward Engineering (F1-F10)

- **F1:** Fresh workspace → "I want a developer pulse dashboard for my team" — agent-chat asks 3-5 product questions → scaffold decides stack → planner approves → code-gen implements → ship with browser proof.
- **F2:** "Add a search box to my dashboard" — incremental on existing app; skip scaffold; capture as improvement; plan/approve/implement.
- **F3:** "This button is broken — fix it" — repo-researcher locates; capture incident; code-gen patches; build-verifier confirms; ship.
- **F4:** "Make it faster" — clarify which surface; measure; capture optimization; plan; implement.
- **F5:** "Drop the persistence feature" mid-sprint — confirm, supersede task, update backlog.
- **F6:** "What's the status?" — read board/runs/metrics; answer in product language; no mutations.
- **F7:** "Show me a screenshot of what shipped" — invoke build-verifier; embed result in chat.
- **F8:** "Make it better" (ambiguous) — ask structured questions; do not capture until intent is clear.
- **F9:** "Yes, ship it" — approve sprint; trigger dispatch.
- **F10:** "What's the weather?" — politely redirect; no tool calls.

### Edge / Failure (E1-E9)

- **E1:** code-gen fails mid-sprint — orchestrator marks blocked with actionable text; auto-retry once if transient; never ask operator about Write / permissions / worktree.
- **E2:** provider limit hit — pause with `capability_limit` + reset metadata; auto-resume on reset.
- **E3:** approval rejected — ask "what should change?" with structured options.
- **E4:** concurrent tabs — state consistent; second tab inherits same session.
- **E5:** transient SDK / network error — retry with backoff; surface only if persistent.
- **E6:** irreversible action requested — structured confirmation with explicit consequence text before any mutation.
- **E7:** sprint completion — summarize shipped scope, browser proof, cost; ask "what's next?".
- **E8:** stack mismatch discovered late — block + offer migration path; never silently break.
- **E9:** operator answers a question card with freeform text — parse intent; route to the matching lifecycle action.

### Reverse Engineering (R1-R3)

- **R1:** "Help me understand this codebase" — repo-researcher inventories; summarize in product language.
- **R2:** "Add tests to this Java repo" — scaffold detects existing Java/Maven; registers junit/checkstyle gates; does not rescaffold.
- **R3:** "Migrate to TypeScript" — capture as project with multi-sprint plan; approve per phase.

## How To Validate

The scripted operator prompts for live runtime validation (Claude lane and Codex lane) live in [docs/PROMPT.md](../PROMPT.md). That file is the canonical script source for [EVALUATION.md § Tier 2.5](EVALUATION.md#25--rubric--quality-gate-pass-bar) rubric runs.

When running an operator scenario:

1. Use the exact prompt wording from [docs/PROMPT.md](../PROMPT.md) (or this file's scripts above).
2. Do not coach the agent with banned terms.
3. Answer follow-up cards with the first `(Recommended)` option unless the scenario specifies a different answer.
4. Verify the agent's reply does not introduce banned terms.
5. Verify the visible product surfaces (Agent, Board, Backlog, Inbox, Voice) maintain the language contract.

## When This File Changes

- New banned term identified → add to the table above; commit alongside the rubric or code change that surfaced it.
- New operator scenario discovered → add to the F / E / R lists; update relevant rubric files in `docs/rubric/`.
- Banned-term audit on a release surface fails → record the failure in [STATUS.md § Recent Decisions](STATUS.md#recent-decisions) and patch the producer per [FIX-STANDARD.md](FIX-STANDARD.md).

## Related

- [README.md § Hard Rules item 7](README.md#hard-rules-non-negotiable-for-every-agent-in-every-session) — the procedural rule mandating operator language compliance.
- [EVALUATION.md § Tier 1.2 — Operator UX bars](EVALUATION.md#12--operator-ux-bars-per-session) — the bar that uses this contract.
- [docs/rubric/operator-limits.md](../rubric/operator-limits.md) — operator capability limits rubric.
- [docs/rubric/sdk-backed-agent-page-agent.md](../rubric/sdk-backed-agent-page-agent.md) — SDK-backed Agent page behavior contract.
- [docs/rubric/realtime-voice-agent-page-agent.md](../rubric/realtime-voice-agent-page-agent.md) — Realtime Voice behavior contract.
- [docs/PROMPT.md](../PROMPT.md) — canonical operator prompt scripts for both runtime lanes.
- [FIX-STANDARD.md](FIX-STANDARD.md) — the standard for fixing any language violation.
