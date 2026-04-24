# autonomous-agent-builder

Runtime contract for how this repo's builder advances work through explicit phases.

## Purpose
- Build through a visible SDLC, not one-shot coding.
- Keep backlog, approvals, quality gates, knowledge, and memory explicit.
- Prefer repo-owned retrieval surfaces over broad file walking.

## Operating Model
- Canonical phase boundaries live in [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md).
- Forward engineering starts in `requirements`; existing-product feature delivery starts in `planning`.
- Current task-status implementation order remains `planning -> design -> implementation -> quality_gates -> pr_creation -> build_verify` until runtime alignment work updates the status model.
- The orchestrator owns phase routing, retries, blocked-state handling, and progression.
- The documentation refresh gate is part of the `quality_gates -> pr_creation`
  boundary: after code/test gates pass or warn, validate maintained-doc
  freshness, invoke the repo-owned documentation bridge only when needed, then
  re-validate before allowing PR creation.
- Agents execute bounded work inside the current phase and produce durable state or evidence.

## Command Lanes

### Use `builder` for repo-local product state
- Start with `builder --json doctor`, then `builder map`, then the exact owned surface you need.
- Use `builder agent`, `builder board`, `builder backlog`, `builder quality-gate`, `builder knowledge`, `builder memory`, and `builder metrics` for repo-local state.
- Treat `builder backlog` as the canonical lifecycle surface for `project`, `feature`, `task`, `approval`, and `run`.

### Use `workflow` for repo docs and broader retrieval
- Use `workflow --docs-dir docs summary/read/search ...` for repo workflow docs and references.
- Use `workflow knowledge ...` for global or cross-project knowledge.
- Do not treat `workflow` as a builder-owned write surface.

## Ownership Boundaries
- `builder` owns repo product semantics: backlog, board, approvals, quality gates, knowledge, memory, and visible SDLC state.
- Claude Agent SDK owns runtime mechanics: sessions, tool execution, hooks, permissions, MCP, streaming, and bounded agent loops.
- Codex subagents are optional specialist lanes, not a product-semantic owner.
- Nothing in this runtime owns or mutates `~/.codex`; treat it as external control-plane state.
- The product should feel like one builder-owned system. Do not push runtime or workflow choice back onto the user.

## Runtime Auth
- OneCLI is the canonical local auth boundary for Claude child processes in this repo when enabled.
- Keep repo `.env` to non-secret OneCLI routing or control values such as `AAB_ONECLI_ENABLED`, `ONECLI_URL`, `ONECLI_API_KEY`, `ONECLI_AGENT`, and `AAB_ONECLI_FAIL_CLOSED`.
- Do not pass real `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` values through repo-local runtime env into Claude child processes when OneCLI is active; the child should receive OneCLI-derived proxy, CA, and placeholder auth env only.
- Keep the implementation at the runtime boundary before Claude launch. Do not move OneCLI bootstrap into prompts, hooks, MCP tools, or provider-specific wrappers.
- Use [docs/claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md) for the detailed repo-local Claude and OneCLI integration contract.

## Retrieval Defaults
- Prefer bounded discovery first: `summary`, `search`, `map`, board views, or task views before full reads.
- Use `builder knowledge summary <query>` before `builder knowledge show <doc> --full`.
- Use `workflow --docs-dir docs summary <name>` before `workflow read <name>`.
- Load `workflow --docs-dir docs summary phase-model` when changing phase boundaries, operator questioning, or per-phase permission policy.
- Agent-facing retrieval should stay concise, stable, and actionable: compact discovery, bounded summary, exact show/read, deterministic misses, and retry guidance.
- Keep API retrieval routes in sync across the main app and embedded server so `/api/...` never falls through to SPA HTML.

## Delivery Rules
- Use `project -> feature -> task` as the delivery hierarchy.
- Prefer updating task state and producing evidence over leaving progress only in conversation text.
- If work is blocked on approval, missing context, or missing prerequisites, surface that through product state instead of improvising.
- Keep operator-facing questions in the top-level interactive lane. Background phases should hand back a bounded blocked decision to the Agent page instead of improvising hidden freeform chat.

## Knowledge And Memory
- Use `builder knowledge` for repo-local system knowledge. If manifests, entrypoints, routing, or runtime wiring change, refresh with `builder knowledge extract --force` and re-run `builder knowledge validate --json`.
- For delivery-time maintained-doc freshness, use the internal builder-owned
  validation and documentation-bridge lane rather than treating a CLI
  subprocess or post-`main` workflow as the primary owner.
- Use `workflow knowledge` only for external or cross-project knowledge, not repo-local implementation truth.
- Use `builder memory` only for reusable decisions, validated patterns, or corrections. Do not store obvious facts, temporary notes, or generic advice.
- Keep knowledge and memory mutations on builder-owned publish surfaces. Do not write them directly through files or database shortcuts.

## State And Isolation
- `Task` is the execution unit.
- `Workspace` is the filesystem execution unit.
- Stable workspace `cwd` is part of task identity.
- Sessions preserve conversation continuity, not filesystem isolation.
- Resume is only reliable when it reuses the same workspace `cwd`.
- For the full workspace lifecycle, use [task-workspace-isolation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/task-workspace-isolation.md).

## Entry Points
- Dashboard/frontend testing: [chrome-devtools-dashboard-testing.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/chrome-devtools-dashboard-testing.md)
- Task workspace lifecycle: [task-workspace-isolation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/task-workspace-isolation.md)

## Review Rule
- Before editing this file, run `builder quality-gate claude-md --json`.
- Also run `builder quality-gate architecture-boundary --json` when the change affects owner boundaries outside this file.

## Placement
- Keep this file short and operational.
- Keep long procedures in `docs/workflows/`.
