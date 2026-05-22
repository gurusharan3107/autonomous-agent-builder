# Operator Language and Scenarios

> Read [README.md](README.md) first.

Language contract for operator-facing surfaces + scripted validation scenarios. Binds both sides: human-as-operator AND agent reply.

A real operator is non-technical. They don't know "lifecycle", "scaffold tool", "worktree", "permission mode", "Recover button". Testing with internals-laden prompts hides operator-UX bugs by handing the agent free hints.

## Banned Operator-Facing Terms

Forbidden in operator UI, Agent / Voice transcripts, Board, Backlog, Inbox, Settings, approval cards — **unless the operator typed them verbatim first**:

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

Agent owns concept internally; operator-side prompt uses product language.

### Exceptions

1. **Operator typed verbatim first.** Agent may echo that one term. Must not introduce a *different* banned term.
2. **`Recover`** only when dashboard exposes a functional Recover control. `409 task_not_recoverable` with Recover still rendered = operator-trust failure.

## Operator Prompt Shapes

### Good (use for testing)

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

### Bad (never for testing)

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

Implementation details. Operator speaks product language; Realtime / Agent page chooses Builder tool, retrieval, delegation.

## Operator Scenarios

Every change to agent definitions, allowlists, or phases validated against this list before merge. Groups: forward (F), edge/failure (E), reverse (R).

### Forward Engineering (F1-F10)

- **F1:** Fresh workspace → "I want a developer pulse dashboard for my team" — agent-chat asks 3-5 product questions → scaffold decides stack → planner approves → code-gen implements → ship with browser proof.
- **F2:** "Add a search box to my dashboard" — incremental; skip scaffold; capture as improvement; plan/approve/implement.
- **F3:** "This button is broken — fix it" — repo-researcher locates; capture incident; code-gen patches; build-verifier confirms; ship.
- **F4:** "Make it faster" — clarify which surface; measure; capture optimization; plan; implement.
- **F5:** "Drop the persistence feature" mid-sprint — confirm, supersede task, update backlog.
- **F6:** "What's the status?" — read board/runs/metrics; answer in product language; no mutations.
- **F7:** "Show me a screenshot of what shipped" — invoke build-verifier; embed result.
- **F8:** "Make it better" (ambiguous) — structured questions; no capture until intent clear.
- **F9:** "Yes, ship it" — approve sprint; trigger dispatch.
- **F10:** "What's the weather?" — politely redirect; no tool calls.

### Edge / Failure (E1-E9)

- **E1:** code-gen fails mid-sprint — orchestrator marks blocked with actionable text; auto-retry once if transient; never ask operator about Write / permissions / worktree.
- **E2:** provider limit hit — pause with `capability_limit` + reset metadata; auto-resume.
- **E3:** approval rejected — ask "what should change?" with structured options.
- **E4:** concurrent tabs — state consistent; second tab inherits same session.
- **E5:** transient SDK / network error — retry with backoff; surface only if persistent.
- **E6:** irreversible action requested — structured confirmation with explicit consequence text before any mutation.
- **E7:** sprint completion — summarize shipped scope, browser proof, cost; ask "what's next?".
- **E8:** stack mismatch discovered late — block + offer migration; never silently break.
- **E9:** operator answers a question card with freeform text — parse intent; route to matching action.

### Reverse Engineering (R1-R3)

- **R1:** "Help me understand this codebase" — repo-researcher inventories; summarize in product language.
- **R2:** "Add tests to this Java repo" — scaffold detects Java/Maven; registers junit/checkstyle gates; does not rescaffold.
- **R3:** "Migrate to TypeScript" — capture as project with multi-sprint plan; approve per phase.

## How To Validate

Scripted prompts for live runtime validation (both lanes): [docs/PROMPT.md](../PROMPT.md). Canonical source for [EVALUATION.md § Tier 2.5](EVALUATION.md#25--rubric--quality-gate-pass-bar) rubric runs.

When running a scenario:

1. Use exact prompt wording from [docs/PROMPT.md](../PROMPT.md) or scripts above.
2. Don't coach the agent with banned terms.
3. Answer cards with first `(Recommended)` option unless scenario says otherwise.
4. Verify agent reply has no banned terms.
5. Verify Agent / Board / Backlog / Inbox / Voice keep the contract.

## When This File Changes

- New banned term → add table row; commit with the surfacing rubric/code change.
- New scenario → add to F/E/R; update relevant `docs/rubric/`.
- Banned-term audit fails on a release surface → record in [STATUS.md § Recent Decisions](STATUS.md#recent-decisions); patch producer per [FIX-STANDARD.md](FIX-STANDARD.md).

## Related

- [README.md § Hard Rules](README.md#hard-rules-non-negotiable) — operator-language rule.
- [EVALUATION.md § Tier 1.2](EVALUATION.md#12--operator-ux-bars-per-session) — UX bar using this contract.
- [docs/rubric/operator-limits.md](../rubric/operator-limits.md), [sdk-backed-agent-page-agent.md](../rubric/sdk-backed-agent-page-agent.md), [realtime-voice-agent-page-agent.md](../rubric/realtime-voice-agent-page-agent.md).
- [docs/PROMPT.md](../PROMPT.md) — canonical prompt scripts.
- [FIX-STANDARD.md](FIX-STANDARD.md) — fixing language violations.
