---
title: "Deterministic vs model-backed Agent behavior rubric"
tags: ["agent-page", "realtime", "rubric", "deterministic", "model-backed"]
doc_type: "rubric"
created: "2026-05-13"
---

# Deterministic Vs Model-Backed Agent Behavior Rubric

## Purpose

Use this rubric to decide when Autonomous Builder should answer or act through a
deterministic product path, and when it should let the selected model runtime
interpret the operator's intent and choose Builder tools.

The goal is operator trust. Deterministic paths should make obvious product
actions fast and reliable. They must not make the Agent feel like a narrow
command router that ignores the operator's real question.

Token savings are not a product-quality goal by themselves. Saving tokens must
never be used as the reason to make a dependent operator request deterministic.
Use compact context and bounded tools to make model-backed work efficient, but
do not trade away model intelligence when the operator needs judgment.

For the Codex SDK / OpenAI runtime lane, this follows the official SDK
direction: keep tool orchestration model-backed, make the prompt and tool
surface cache-friendly, and report cached-token reuse explicitly instead of
turning ambiguous operator intent into a fixed shortcut.

For the Claude Agent SDK runtime lane, this follows the official SDK direction:
preserve the agent loop where Claude evaluates the prompt, decides tool calls,
receives tool results, and continues until a result or limit. Tune tool scope,
permissions, hooks, `AskUserQuestion`, subagents, tool search, compaction,
effort, turn/budget limits, and usage telemetry before changing behavior.

## Decision Rule

Use deterministic behavior when all of these are true:

- The input is an explicit UI control or exact read-only state request, not a
  free-form typed prompt that asks Builder to decide what to do.
- The answer or action is fully determined by Builder-owned state.
- No prioritization, judgment, diagnosis, tradeoff, or synthesis is required.
- The action is read-only or already covered by an explicit safe product
  contract.
- The response can honestly say what state was read or what action was taken.

Use model-backed intelligence when any of these are true:

- The operator asks what to do, what matters, why it matters, or what to fix
  next.
- The request depends on intent, project context, recent evidence, or multiple
  possible Builder tools.
- The answer requires diagnosis, ranking, synthesis, tradeoffs, or explanation.
- The operator wording is natural and could map to more than one product action.
- The Agent should inspect bounded evidence, then decide which tool or action is
  appropriate.
- The only argument for determinism is cost, latency, or token reduction.
- The request could mutate backlog, Board, sprint, task, feature, approval,
  runtime, or delivery state.

## Deterministic Behavior

Deterministic behavior is for exact product semantics. It should be boring,
fast, auditable, and impossible to misinterpret as model judgment.

| Control or event | Correct deterministic behavior | Required evidence |
| --- | --- | --- |
| Board navigation button or resolved navigation event | Navigate to `/board`. | `voice_navigation_request` or equivalent navigation event. |
| Observability navigation button or resolved navigation event | Navigate to `/observability`. | Navigation event with route and source. |
| Board status refresh button | Read Board state and summarize current counts. | Builder DB/API state, zero model tokens when handled directly. |
| Approvals status refresh button | Read approval/prepared-action state. | Approval state, no mutation. |
| Runtime selector control | Set future-run runtime to `codex_sdk` and explain attribution stays historical. | Runtime settings event/log. |
| Observability summary refresh | Read the same Builder-owned observability summary and explain that state. | `dashboard_observability_summary` or equivalent product summary. |

Deterministic responses must not:

- Invent recommendations.
- Rank next work unless the ranking is encoded in Builder state.
- Hide uncertainty behind a canned answer.
- Turn broad "what should I do?" questions into fixed status checks.
- Substitute CLI/API shortcuts for required dashboard lifecycle actions.
- Optimize token usage by removing the model from a judgment-dependent request.
- Interpret typed operator prompts as fixed commands or magic words.

## Model-Backed Intelligence

Model-backed behavior is for dependent operator intent. The model should reason
over bounded Builder-owned evidence, then choose available tools or explain the
recommended next action. If the model is unclear after bounded evidence, it must
ask through `AskUserQuestion` or the Agent page's equivalent structured question.
Typed operator prompt interpretation is always model-backed.

| Operator wording | Correct model-backed behavior | Guardrail |
| --- | --- | --- |
| "What can you tell me from observability data, what should I fix next?" | Use bounded observability/metrics/log evidence, synthesize the highest-priority fix, and explain why. | Provide a compact context pack first; avoid raw or `--full` dumps unless needed. |
| "Is this run efficient?" | Inspect run evidence, metrics, and relevant logs, then judge efficiency. | Use `builder logs analyze --session <id> --json` or compact equivalents before broad commands. |
| "Recover the blocked work." | Inspect current Board/task failure state, choose the safe recovery path, and ask for approval if mutation is risky. | Do not auto-dispatch destructive or ambiguous recovery. |
| "Mark everything shipped and clear the backlog." | Use runtime judgment to inspect read-only Backlog/Board state, explain risk, and ask for the exact visible product action or approval needed. | Do not invent "don't-ask mode" or claim bulk mutation without a granted tool and visible approval/prepared-action evidence. |
| "Continue building." | Let the selected model inspect Board/task state and choose the next dispatch, recovery, or question tool call. | If bounded evidence does not make the next product action clear, ask through `AskUserQuestion`. |
| "What should I test next?" | Inspect current lifecycle state and recommend coverage gaps. | Tie the answer to Board, Backlog, logs, or metrics evidence. |
| "This error looks wrong. Why?" | Diagnose from visible symptom to Builder-owned logs and runtime evidence. | Do not stop at UI text; identify the owning layer. |

Model-backed responses must:

- Preserve the selected runtime lane (`claude` or `codex_sdk`).
- Use compact Builder-owned evidence first.
- Prefer structured tools and product surfaces over ad hoc shell discovery.
- Ask one short question only when bounded retrieval cannot resolve intent.
- Treat backlog, Board, sprint, task, feature, or approval mutation as
  runtime-judged, tool-bound work: the model may execute requested mutations
  through granted Builder tools when the exact target and consequence are clear
  or visible approval confirms them, but it must not claim it will mark, clear,
  delete, approve, deny, dispatch, or ship state from broad wording alone.
- Keep final answers operator-facing, not implementation-internal.
- Treat token efficiency as a constraint on evidence shape, not as permission to
  skip reasoning.

## Token Optimization Direction

When a model-backed request looks expensive, optimize in this order:

1. Preserve model-backed intent and tool selection for judgment requests.
2. Remove duplicated or raw context from the prompt before changing behavior.
3. Put stable policy and tool guidance before dynamic per-turn evidence so
   prompt caching can work.
4. Put dynamic operator, Board, metrics, logs, and observability evidence near
   the end of the turn.
5. Prefer bounded Builder evidence and compact tool outputs over raw logs or
   `--full` payloads.
6. Consider deferred tool loading or tool search for large tool catalogs when
   the selected SDK supports it.
7. Use compaction at meaningful workflow boundaries, preserving completed
   actions, IDs, tool outcomes, blockers, and the next goal.
8. Show raw tokens, cached tokens, and non-cached-plus-output tokens separately
   in product telemetry.

Claude-specific token/context tuning should additionally track cache creation
tokens, cache read tokens, result subtype, stop reason, `max_turns` or
`max_budget_usd` stops, approval/question pauses, subagent use, and compaction
boundaries. Use hooks for deterministic safety and feedback around tool calls;
do not use hooks or permission rules as a replacement for model-backed
diagnosis, synthesis, or recommendation prompts.

Do not count prompt caching as a reason to ignore waste. Cached raw tokens may
be much cheaper than fresh tokens, but repeated broad retrieval, raw output
reinjection, or unclear token reporting are still Builder robustness defects.

## Realtime Voice

Realtime Voice is allowed to do simple deterministic controls directly:

- Navigate dashboard pages.
- Read obvious product status.
- Switch runtime with future-run attribution.
- Prepare or delegate task actions when the operator intent is clear.

Realtime Voice must delegate to the SDK-backed Agent when the request requires
analysis, diagnosis, prioritization, or synthesis. Examples:

- "Analyze this run."
- "What should I fix next?"
- "Why did this fail?"
- "Recover this without losing progress."

Delegation should preserve the operator's wording and create normal Agent-page
evidence. It should not translate a thoughtful question into a canned
deterministic status response.

## SDK-Backed Agent

The SDK-backed Agent should stay model-backed for dependent intent while using
deterministic helpers as evidence and action primitives.

Good pattern:

1. Builder prepares a bounded context pack for known high-risk evidence surfaces
   such as observability, metrics, logs, Board, Backlog, and approvals.
2. The model interprets the operator's intent.
3. The model uses compact tools or product state as needed.
4. Builder records the transcript, tool events, run status, runtime attribution,
   and observability.

Bad pattern:

1. A broad question is captured by a deterministic substring matcher.
2. The Agent returns a fixed page/status answer.
3. The operator has to rephrase to get actual reasoning.

Another bad pattern:

1. A dependent question goes to the model with no bounded product context.
2. The model discovers evidence through broad raw shell commands.
3. Runtime transport fails or the transcript becomes noisy.

## Review Checklist

- Is this operator request an action, a state read, or a judgment request?
- Would two competent operators expect the same exact result?
- Is the required source of truth already encoded in Builder state?
- Would a deterministic response hide uncertainty or skip useful reasoning?
- Is this being made deterministic only to save tokens or avoid model cost? If
  yes, keep it model-backed and make the evidence path more compact instead.
- Can Builder provide bounded context so the model can reason without raw dumps?
- Does the result preserve runtime attribution and visible dashboard evidence?
- Is the behavior consistent across Realtime Voice text mode and SDK-backed
  Agent wording?

## Validation

Useful checks:

```bash
PYTHONPATH=src pytest tests/test_embedded_agent_routes.py tests/test_realtime_voice_operator.py -q
PYTHONPATH=src pytest tests/test_codex_app_server_runtime.py -q
builder logs --info --compact --json
builder metrics show --json --full --limit 5
```

Browser validation remains required for dashboard lifecycle flows. CLI evidence
can diagnose and prove runtime behavior, but it is not a substitute for visible
Agent, Realtime Voice, Board, Backlog, Settings, approval, and Observability
behavior.

## Related Docs

- [SDK-backed Agent page agent rubric](sdk-backed-agent-page-agent.md)
- [Realtime voice Agent page agent rubric](realtime-voice-agent-page-agent.md)
- [Operator capability limits](operator-limits.md)
- [Runtime switch dashboard contract](../references/runtime-switch-dashboard-contract.md)
- [Autonomous lifecycle validation](../workflows/autonomous-lifecycle-validation.md)
