@AGENTS.md

# autonomous-agent-builder

Runtime contract for builder-owned agent execution in this repo.

## Purpose
- Build through a visible SDLC, not one-shot coding.
- Keep backlog, approvals, quality gates, knowledge, and memory explicit.
- Prefer repo-owned retrieval surfaces over broad file walking.
- Keep this file aligned with the selected runtime behavior and
  project-instruction best practices. Codex optimization instructions belong in
  `AGENTS.md`.

## Operating Model
- Canonical phase boundaries live in [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md).
- Day-0 readiness lives in [day-0-readiness.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/day-0-readiness.md) and gates all autonomous work after `builder init`.
- `builder init` creates the selected runtime's target-repo guidance baseline:
  `CLAUDE.md` for Claude Agent SDK, `AGENTS.md` for Codex SDK. When the
  selected lane changes, builder migrates builder-generated guidance between
  those filenames instead of leaving duplicate active baselines.
- Forward engineering enters `requirements` after readiness; reverse engineering enters repo understanding and `planning` after readiness.
- User-shaped lifecycle validation is dashboard-first. After bootstrap and
  launch, drive backlog, task, approval, and execution behavior through the
  Agent page and visible dashboard surfaces; use `builder` CLI only for
  readiness, observability, read-only state inspection, quality-gate retrieval,
  and maintainer closeout evidence.
- Observability recommendations must separate builder-owned optimization
  candidates from general workflow-state warnings. Approval or blocked-state
  signals belong to builder state surfaces first and must not be emitted as
  deterministic optimization candidates.
- Current task-status implementation order remains `pending/planning -> design/design_review -> implementation -> quality_gates -> pr_creation/review_pending -> build_verify -> done`, with sprint-level plan/design artifacts allowed to let covered tasks skip separate task-level planning/design approvals.
- The orchestrator owns phase routing, retries, blocked-state handling, and progression.
- The orchestrator, not the user, owns follow-up work selection: after completion,
  approval, or provider-limit reset, builder should deterministically resume the
  preserved task or start the next ready task through product events.
- For local generated-app Codex workspaces without a real Git PR target, the
  orchestrator must use deterministic evidence surfaces before model agents:
  `change_evidence` for PR/evidence collection and `build_verify` for
  lint/build/test/browser proof.
- `pr-creator` is only for real Git workspaces with a PR target; `build-verifier`
  is only for verification gaps not already covered by deterministic scripts.
- Provider limits are first-class blocked/capability states with reset metadata,
  not stale gate failures or manual database repair requests.
- Runtime selection is builder-owned configuration. The user-facing lifecycle
  lanes are only `claude` for Claude Agent SDK and `codex_sdk` for Codex SDK.
  Inspect or change them through dashboard Settings, first-run onboarding, or
  `builder agent runtime show|probe|models|set --json`. Compatibility adapters
  must not be used as sprint validation lanes.
- Model, effort, subagent, and context strategy are builder-owned runtime policy
  in `src/autonomous_agent_builder/agents/execution_policy.py`; the user should
  not choose Haiku/Sonnet/Opus or thinking level by hand.
- Claude Agent SDK subagents are bounded specialist evidence lanes only:
  `repo-researcher`, `browser-verifier`, `build-verifier`, `security-reviewer`,
  `pr-reviewer`, and `documentation-agent`. They must return structured
  evidence to the parent run and must not own lifecycle state, approvals,
  backlog, board, knowledge, memory, or user questions.
- When `RUNTIME_SDK=claude`, Claude Agent SDK execution should use the Claude
  Code preset system prompt and project setting sources so target-repo
  `CLAUDE.md` guidance is loaded deterministically without importing Codex-only
  `AGENTS.md` policy.
- When `RUNTIME_SDK=codex_sdk`, builder uses the local Codex app-server/SDK
  JSON-RPC path over `codex login` auth and persists Codex token, turn,
  duration, provider-limit, native user-input, and telemetry-source fields for
  analysis.
- The documentation refresh gate is part of the `quality_gates -> pr_creation`
  boundary: after code/test gates pass or warn, validate maintained-doc
  freshness, invoke the repo-owned documentation bridge only when needed, then
  re-validate before allowing PR creation.
- The optimization phase is model-backed. After build verification, the
  optimization agent must inspect builder recommendations, preflight evidence,
  telemetry, observability, and logs, then update generated-app `CLAUDE.md` /
  `AGENTS.md` runtime guidance and project-local deterministic scripts when the
  evidence shows recurring context or verification needs. Any script it creates
  must record which builder phase or agent should use it and what evidence it
  replaces.
- Agents execute bounded work inside the current phase and produce durable state or evidence.

## Command Lanes

### Use `builder` for repo-local product state
- Start with `builder --json doctor`, then `builder map`, then the exact owned surface you need.
- Use `builder readiness status --json` to inspect Day-0 readiness, and `builder readiness assess --json` to recompute the gate.
- Use `builder agent`, `builder board`, `builder backlog`, `builder quality-gate`, `builder knowledge`, `builder memory`, and `builder metrics` for repo-local state.
- Use `builder agent runtime show|probe|models|set --json` for runtime
  selection and diagnostics. Do not hand-edit runtime state when the public
  command can express the same change.
- During forward/reverse lifecycle validation, do not use mutating `builder`
  commands to create backlog items, queue tasks, dispatch runs, approve gates,
  or simulate user progress; those actions must be browser-visible product
  behavior. See [dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md).
- Treat `builder backlog` as the canonical lifecycle surface for `project`, `item`, `task`, `approval`, and `run`.
- Use `builder backlog item create --type feature|improvement|optimization|incident` for backlog entries. Do not reintroduce a separate `builder backlog feature` control owner.
- At testing or workflow-validation closeout, convert durable findings into typed backlog items with `--source validation`: `incident` for observed product failures, `improvement` for required product hardening, and `optimization` for efficiency or agent-experience improvements. Also save reusable general anecdotes to `builder memory` when they would help the next agent avoid the same trap.

### Use `workflow` for repo docs and broader retrieval
- Use `workflow --docs-dir docs summary/read/search ...` for repo workflow docs and references.
- Use `workflow knowledge ...` for global or cross-project knowledge.
- Do not treat `workflow` as a builder-owned write surface.

## Ownership Boundaries
- `builder` owns repo product semantics: backlog, board, approvals, quality gates, knowledge, memory, and visible SDLC state.
- Claude Agent SDK owns runtime mechanics: sessions, tool execution, hooks, permissions, MCP, streaming, and bounded agent loops.
- `CLAUDE.md` is the Claude Agent SDK runtime/project-instruction surface.
- `AGENTS.md` is for Codex agents optimizing this builder; do not import Codex
  control-plane guidance into Claude runtime prompts.
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
- When tuning the builder's own prompt/tool/model/subagent/context behavior,
  load `builder quality-gate claude-agent-sdk --json` and
  `workflow --docs-dir docs summary agent-quality-tuning-loop`.
- When changing runtime selection, adapters, probes, or dashboard runtime
  settings, load `builder quality-gate modular-runtime --json`.
- When changing Claude-Agent-SDK telemetry or observability policy, load
  `workflow --docs-dir docs summary claude-agent-sdk-telemetry-observability`.
- For Claude-Agent-SDK-specific best-practice clarification, the Claude docs
  assistant may be used only as a bounded docs-cited advisory lane for the
  builder's own runtime policy questions such as permissions, sessions, hooks,
  subagent patterns, or telemetry setup. Do not use it as a normal lane while
  building user applications, and do not treat it as proof of this repo's
  implementation behavior; escalate those questions to builder logs, code, and
  tests.
- Agent-facing retrieval should stay concise, stable, and actionable: compact discovery, bounded summary, exact show/read, deterministic misses, and retry guidance.
- Keep API retrieval routes in sync across the main app and embedded server so `/api/...` never falls through to SPA HTML.

## Delivery Rules
- Use `project -> item -> task` as the delivery hierarchy. Feature work is represented as `item --type feature`, not as a separate backlog command family.
- Prefer updating task state and producing evidence over leaving progress only in conversation text.
- If work is blocked on approval, missing context, or missing prerequisites, surface that through product state instead of improvising.
- Keep operator-facing questions in the top-level interactive lane. Background phases should hand back a bounded blocked decision to the Agent page instead of improvising hidden freeform chat.
- Do not infer vague user intent into a mutating lifecycle action. If the next
  product action is not clear from durable state, ask through `AskUserQuestion`
  or the Agent page's equivalent structured question before changing backlog,
  sprint, task, approval, or runtime state.

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
- For the full workspace lifecycle, run `workflow --docs-dir docs summary task-workspace-isolation`.

## Entry Points
- Dashboard/frontend testing: Playwright CLI skill (`$HOME/.claude/skills/playwright/scripts/playwright_cli.sh`); see agent memory `browser-testing-use-playwright-cli-avoid-chrome-devtools-mcp`.
- Dashboard-first lifecycle validation: `workflow --docs-dir docs summary dashboard-first-validation`
- Task workspace lifecycle: `workflow --docs-dir docs summary task-workspace-isolation`

## Review Rule
- Before editing this file, run `builder quality-gate claude-md --json`.
- Also run `builder quality-gate architecture-boundary --json` when the change affects owner boundaries outside this file.

## Placement
- Keep this file short and operational.
- Keep long procedures in `docs/workflows/`.
