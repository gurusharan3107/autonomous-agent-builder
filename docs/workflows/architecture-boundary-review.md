# Architecture Boundary Review

## Overview
Use this workflow when the task is to judge whether `autonomous-agent-builder` is drawing the right boundaries between product/domain surfaces and agent-runtime surfaces.

This is the right lane for questions like:
- what should belong to `builder` versus Claude Agent SDK
- whether a Codex subagent should exist for a review lane
- whether orchestration, runtime, and domain responsibilities are crossing
- whether a boundary rule belongs in code, a workflow doc, `CLAUDE.md`, or `AGENTS.md`

## Core Principle
Use a dedicated architecture reviewer only for bounded second-pass analysis. Codex subagents are opt-in, consume extra tokens, and are most useful for specialized parallel or isolated review lanes, not for routine thinking.

## When To Use
- builder CLI vs service-layer ownership reviews
- orchestrator vs agent responsibility reviews
- Claude Agent SDK or Codex integration boundary checks
- owner-surface placement decisions for repeated architectural friction
- explicit user requests for a second opinion through a specialized review agent

## Skip When
- the task is a straightforward bug fix or small implementation edit
- the answer can be produced directly from one or two files without a second lane
- the issue is product behavior debugging rather than architecture review
- the user did not ask for delegation and the main lane is not blocked

## Codex Role
The project-scoped Codex role is `architecture_reviewer`, defined in:
- [.codex/config.toml](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/.codex/config.toml)
- [.codex/agents/architecture-reviewer.toml](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/.codex/agents/architecture-reviewer.toml)

Use that role for read-only review of:
- boundary maps
- owner-surface placement
- Codex subagent design
- Claude Agent SDK best-practice compliance

## Spawn Criteria
Spawn `architecture_reviewer` only when at least one of these is true:
- the user explicitly asks for a subagent, second opinion, or delegated architecture review
- the task compares multiple owner surfaces and the answer is not obvious from one file or one doc
- the main lane is doing implementation work and a parallel read-only architecture pass can run independently

Do not spawn it when:
- the task is a direct implementation request with a clear owner
- the answer is already obvious from the orchestrator, runner, or one workflow doc
- the main lane would have to stop and wait on the review before doing any other useful work

## Recommended Prompt Shape
When spawning `architecture_reviewer`, keep the ask bounded and artifact-oriented.

Use a prompt shaped like:

```text
Review the current boundary for <topic>.
Build a current-state boundary map from the repo docs and code.
Check the design against official <Codex or Claude Agent SDK> guidance only where needed.
Return:
1. Boundary map
2. Findings and risks
3. Recommended owner surface for each concern
4. Smallest durable next step
Do not edit files.
```

## Role Strategy
Start with one reusable architecture-review lane only.

Add another Codex role only if:
- a second task class becomes recurring
- its boundary is materially different from `architecture_reviewer`
- the new role would change tools, sandbox, or output contract in a stable way

Good future candidates, if they become recurring, are:
- read-only code-path exploration
- deterministic background monitoring
- narrow implementation worker

Do not create separate agents for every review dimension such as architecture, boundaries, best practices, or docs when one read-only review lane can cover them.

## Expected Output
The review should return:
- current boundary map
- concrete findings or risks
- recommended owner surface for each concern
- smallest durable next step

## Anti-Patterns
- creating a specialized agent for every concern instead of one reusable review lane
- using a subagent because it exists, rather than because the task is bounded and benefits from isolation
- letting the review lane make product-priority or implementation decisions
- encoding long architectural guidance in `AGENTS.md` instead of a retrievable doc
