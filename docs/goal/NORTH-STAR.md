# North Star

> **Read [README.md](README.md) first.**

## Mission

Make **Autonomous Agent Builder** the preferred application for taking software from idea to shipped — over Codex CLI and Claude Code — for both non-technical operators and experienced developers, by owning the full SDLC inside one chat-first, dashboard-backed operating environment that runs on either the Claude Agent SDK or the Codex SDK with identical product behavior.

This is not a wrapper around model providers. It is the operating environment for agent-era software delivery.

## What "Preferred" Means

"Preferred" is a three-fold bar. All three must be true for the product to claim it has won. Each bar is enforced by a tier in [EVALUATION.md](EVALUATION.md).

### Bar 1 — Operator UX Win (Tier 1 evidence)

A non-technical operator can take an idea (typed or spoken) all the way to a shipped, browser-visible feature in a real app — without ever needing to know what a *lifecycle*, *sprint*, *task*, *worktree*, *permission mode*, *recover*, *dispatch*, *MCP*, *SDK*, *gate*, or *backlog* is. Builder asks only the product questions a thoughtful product manager would ask. Builder owns every internal concern.

Codex CLI and Claude Code cannot pass this bar today. They expose model, tool, context, and execution choices to the user. We hide all of them behind product surfaces.

### Bar 2 — Developer Economics Win (Tier 1 + Tier 3 evidence)

For an experienced developer, the same feature ships through Builder using **fewer tokens, fewer turns, less wall-clock time, and fewer manual approvals** than the same feature in Codex CLI or Claude Code, while producing **stronger durable state** (memory, knowledge, metrics, audit trail). Both runtime lanes (Claude Agent SDK and Codex SDK) hit the existing performance bars: `cache_ratio > 5x` after turn 2, `chunk_pressure_risk: false`, `avoidable_cost_flags: []`, and head-to-head wins on canonical benchmark tasks.

This is the bar that proves Builder is not just easier — it's also cheaper and faster when measured honestly.

### Bar 3 — Lifecycle Completeness Win (Tier 2 evidence)

Builder is the only tool in this comparison set that covers **requirements → design → backlog → implementation → verification → ship → optimize** as one coherent loop with durable state, dashboard-visible evidence, and resumability across operator sessions, agent crashes, and runtime switches. Codex CLI and Claude Code are stateless point tools. Builder is an environment.

"Lifecycle completeness" means the product can be exited mid-cycle and re-entered later (by a different operator, on a different runtime lane, on a different machine) and the system knows exactly where work stopped, what's blocked, what's queued, and what shipped.

## Two Runtime Lanes, One Product

The product behaves identically from the operator's perspective whether the active runtime is **Claude Agent SDK** (`claude`) or **Codex SDK** (`codex_sdk`). Internally, each lane is implemented through its native primitives — Claude Agent SDK uses hooks, permissions, MCP, subagents, and AskUserQuestion; Codex SDK uses app-server events, native user-input requests, MCP elicitations, request permissions, and Codex telemetry. The lifecycle owner (Builder orchestrator) is the same.

A milestone is not complete until both lanes pass the relevant tier of evaluation against the same operator scenarios. Lane-asymmetric wins are explicitly tracked as gaps in [STATUS.md](STATUS.md), not silently accepted.

## Differentiators (What Codex CLI and Claude Code Cannot Do)

These are the decisive product capabilities that no plain agent CLI can match. Every epoch in [ROADMAP.md](ROADMAP.md) must protect and deepen at least one of these. If a roadmap item weakens a differentiator, the item is wrong.

1. **Chat-only operator surface backed by a real dashboard.** Operator never sees `--flag` syntax, model picker, or runtime switch unless they explicitly ask. Status, evidence, and approvals live in product surfaces (Agent page, Board, Backlog, Inbox, Voice).
2. **Durable lifecycle state.** Backlog, sprints, tasks, approvals, gates, blocked-reasons, recovery paths, and shipped evidence persist across sessions, runtime switches, machine restarts, and operator changes. The dashboard is the source of truth, not chat history.
3. **Builder-owned agent intelligence.** Model, effort, tool allowlist, subagent set, prompt shape, context size, retrieval strategy, and runtime policy are *product policy*, not user choices. Operator says what they want; Builder decides how.
4. **Native two-lane runtime.** First-class Claude Agent SDK and Codex SDK support with identical product behavior. The operator can switch lanes mid-project without losing state or attribution.
5. **Memory and knowledge as system responsibilities.** Repo-local memory (`.memory/`) and knowledge base (`builder knowledge`) accumulate durable lessons automatically. Future sessions inherit precedent, not start from zero.
6. **Cost-aware execution as a product property.** Token usage, cache ratios, chunk pressure, and avoidable-cost flags are first-class evidence visible in dashboard Metrics and CLI. Optimization is the product's job, not the user's.
7. **Voice as a peer operator surface.** Realtime voice (Samantha) is a first-class interaction lane, not a bolt-on. Voice and chat share the same Agent state and same approval flow.
8. **Resumability after session drop.** The product is designed for context drops and agent handover. A new agent pointed at `docs/goal/` can continue any in-flight work from `STATUS.md` alone.

## Non-Goals

Things the product must never become, even if they would be easier:

- A thin wrapper over Codex CLI or Claude Code that just adds a UI.
- A manual orchestration layer where the user still has to pick model/tools/context.
- A documentation store with no execution capability.
- A loose set of integrations without one coherent operating model.
- A "power-user" tool that requires understanding internals to be useful.
- A single-runtime product (only Claude SDK or only Codex SDK is unacceptable).

## Design Principles (Always-On)

These principles, validated repeatedly in the existing sprint history, govern every design decision:

- **Chat-first for the user, structured execution under the hood.**
- **Durable state over ephemeral agent behavior.**
- **Retrieval before guesswork.**
- **Progressive disclosure over context overload.**
- **System-owned workflow decisions over user micromanagement.**
- **Cost-efficient execution without lowering quality.**
- **Agent-friendly surfaces and CLIs wherever possible.**
- **One coherent operating environment for project delivery.**
- **Root causes over symptom patches.** SDK-grounded fixes; never workarounds.

## Agent Working Principles (Always-On)

These are the four principles that govern how the agent works inside this framework — distinct from the product design principles above, which describe what the product must become.

1. **Ask, don't assume.** If something is unclear, ask before writing a single line. Use [`AskUserQuestion`](../rubric/sdk-backed-agent-page-agent.md) for bounded operator choices. Ambiguity costs less to resolve than to undo.
2. **Simplest solution first.** Do not add abstractions, flexibility, or generality that weren't explicitly requested. Three similar lines beats a premature abstraction. Same rule as the autoresearch loop's "simpler wins ties."
3. **Don't touch unrelated code.** If a file or function is not directly part of the current task, do not modify it. Scope drift is the most common cause of regression — keep the diff focused.
4. **Flag uncertainty explicitly.** If you are not confident in an approach, say so before proceeding. The user will redirect; the cost of saying "I'm not sure if X is the right layer" is far lower than the cost of patching the wrong layer.

## When This File Changes

`NORTH-STAR.md` changes only when the *mission* or the *definition of "preferred"* itself changes. Day-to-day work does not touch this file. A change here usually implies updates to [ROADMAP.md](ROADMAP.md) and [EVALUATION.md](EVALUATION.md).
