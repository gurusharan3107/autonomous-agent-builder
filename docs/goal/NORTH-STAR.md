# North Star

> Read [README.md](README.md) first.

## Mission

Make **Autonomous Agent Builder** the preferred app for taking software from idea to shipped — over Codex CLI and Claude Code — for both non-technical operators and experienced developers. One chat-first, dashboard-backed operating environment that runs identically on Claude Agent SDK or Codex SDK.

Not a model-provider wrapper. The operating environment for agent-era software delivery.

## What "Preferred" Means

Three bars; all must hold. Each enforced by a tier in [EVALUATION.md](EVALUATION.md).

### Bar 1 — Operator UX Win (Tier 1)

Non-technical operator: idea → shipped browser-visible feature, no exposure to *lifecycle*, *sprint*, *task*, *worktree*, *permission mode*, *recover*, *dispatch*, *MCP*, *SDK*, *gate*, *backlog*. Builder asks only product questions; owns every internal concern.

Codex CLI / Claude Code expose model, tool, context, execution choices. Builder hides all behind product surfaces.

### Bar 2 — Developer Economics Win (Tier 1 + Tier 3)

Same feature ships with **fewer tokens, fewer turns, less wall-clock, fewer manual approvals** than Codex CLI / Claude Code, plus **stronger durable state** (memory, knowledge, metrics, audit). Both lanes hit: `cache_ratio > 5x` after turn 2, `chunk_pressure_risk: false`, `avoidable_cost_flags: []`, head-to-head wins on canonical benchmarks.

Easier *and* cheaper *and* faster, measured honestly.

### Bar 3 — Lifecycle Completeness Win (Tier 2)

Only tool covering **requirements → design → backlog → implementation → verification → ship → optimize** as one coherent loop with durable state, dashboard evidence, resumability across operator sessions, agent crashes, runtime switches. Codex CLI / Claude Code are stateless point tools. Builder is an environment.

Exit mid-cycle, re-enter later (different operator, different lane, different machine) — system knows where work stopped, what's blocked, queued, shipped.

## Two Runtime Lanes, One Product

Identical operator behavior on `claude` or `codex_sdk`. Internally: Claude uses hooks/permissions/MCP/subagents/AskUserQuestion; Codex uses app-server events/`request_user_input`/MCP elicitations/request permissions/telemetry. Lifecycle owner (orchestrator) is the same.

Milestone not complete until both lanes pass the relevant tier on same scenarios. Lane-asymmetric wins → gaps in [STATUS.md](STATUS.md), never silent.

## Differentiators

Capabilities no plain agent CLI matches. Every epoch in [ROADMAP.md](ROADMAP.md) protects + deepens at least one. Item that weakens a differentiator is wrong.

1. **Chat-only operator surface backed by a real dashboard.** No `--flag`, no model picker, no runtime switch unless asked. Status / evidence / approvals in product surfaces.
2. **Durable lifecycle state.** Backlog, sprints, tasks, approvals, gates, blocked-reasons, recovery, shipped evidence persist across sessions / lane switches / restarts / operator changes. Dashboard is truth, not chat.
3. **Builder-owned agent intelligence.** Model, effort, allowlist, subagents, prompt, context, retrieval, runtime policy are *product policy*. Operator says what; Builder decides how.
4. **Native two-lane runtime.** First-class Claude + Codex SDK, identical product behavior. Lane switch mid-project preserves state + attribution.
5. **Memory and knowledge as system responsibilities.** `.memory/` + `builder knowledge` accumulate durable lessons automatically. Future sessions inherit precedent.
6. **Cost-aware execution as a product property.** Token usage, cache ratios, chunk pressure, avoidable-cost flags are first-class evidence in dashboard + CLI. Optimization is the product's job.
7. **Voice as a peer operator surface.** Realtime voice (Samantha) is first-class. Voice + chat share state + approval flow.
8. **Resumability after session drop.** New agent pointed at `docs/goal/` continues from `STATUS.md` alone.
9. **Executable governance via project-local skills.** Audit, optimization, knowledge-freshness, and session-continuity disciplines live as project-local skills under [.claude/skills/](../../.claude/skills/). They aren't optional tooling — they're how this framework runs. Skills auto-trigger on operator phrases (`/start`, `/autoresearch`, etc.), enforce hard rules mechanically (e.g. autoresearch's `freshness_sweep.py`), and chain into each other so the operator stops being the message bus between disciplines.

## Non-Goals

- Thin wrapper over Codex CLI / Claude Code with a UI.
- Manual orchestration where user picks model/tools/context.
- Doc store with no execution.
- Loose integrations without a coherent operating model.
- "Power-user" tool requiring internals knowledge.
- Single-runtime product (Claude-only or Codex-only).

## Design Principles (Always-On)

- Chat-first for the user; structured execution underneath.
- Durable state over ephemeral agent behavior.
- Retrieval before guesswork.
- Progressive disclosure over context overload.
- System-owned workflow decisions over user micromanagement.
- Cost-efficient execution without lowering quality.
- Agent-friendly surfaces and CLIs wherever possible.
- One coherent operating environment for project delivery.
- Root causes over symptom patches. SDK-grounded fixes; never workarounds.

## Agent Working Principles (Always-On)

Distinct from product design principles — these govern how the agent works.

1. **Ask, don't assume.** Unclear → ask before writing. Use [`AskUserQuestion`](../rubric/sdk-backed-agent-page-agent.md) for bounded choices. Ambiguity costs less to resolve than to undo.
2. **Simplest solution first.** No abstractions / flexibility / generality not asked for. Three similar lines > premature abstraction.
3. **Don't touch unrelated code.** Not part of current task → don't modify. Scope drift causes regression.
4. **Flag uncertainty explicitly.** Not confident → say so before proceeding. Saying "I'm not sure if X is the right layer" costs less than patching the wrong layer.
5. **Subtract before you add.** Apply the first-principles algorithm *while building*, not as later cleanup: question the requirement, delete/reuse before adding, treat every new file/abstraction/doc as permanent token + maintenance mass. Canonical doctrine: `workflow read principles --section Core` (question requirement → delete → simplify → accelerate → automate last). The [`elon`](../../.claude/skills/elon/SKILL.md) skill is only the retrospective backstop — the default is to build this way.

## When This File Changes

Only when mission or definition of "preferred" itself changes. Change here usually implies [ROADMAP.md](ROADMAP.md) + [EVALUATION.md](EVALUATION.md) updates.
