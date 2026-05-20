# Agent Optimization Analysis

Canonical reference for the repo-local optimization and introspection lane used
to improve builder-run efficiency without turning the analysis agent into a
general transcript or observability reader.

Use this doc as the owner surface when changing:
- what optimization analysis is for
- which inputs the optimization lane may consume
- which data must stay out of scope by default
- what kinds of recommendations the optimization lane may emit
- how builder-self optimization differs from target-repo optimization
- where deterministic analysis stops and advisory agent reasoning begins

For Claude runtime mechanics, sessions, hooks, MCP, and auth boundaries, see
[claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md).

For runtime-specific telemetry fields and active-lane ownership, see
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md).

## Purpose

The optimization lane exists to help the product improve agent efficiency for a
specific builder task, run, session, or target repository.

It is not a broad analytics persona and it is not a freeform “read everything
and suggest improvements” agent.

Its core invariant is:

the optimization agent reasons over interpreted signals, not raw observability
exhaust.

For generated-app workspaces, the optimization lane must also preserve builder
ownership. Codex or a maintainer may change autonomous-builder source code,
tests, prompts, runtime policy, hooks, and docs, but app-local files such as
`CLAUDE.md`, `AGENTS.md`, deterministic scripts, hooks, subagents, and
browser acceptance tests must be changed by builder-owned agents or
deterministic builder actions. The operator should see those updates as agent-run timeline
evidence, not as invisible maintainer edits inside the created app workspace.

That invariant keeps the lane:
- token-efficient
- repo-safe
- target-aware
- aligned with builder-owned product state instead of generic runtime drift

## User Experience Contract

The user should be able to ask for optimization analysis in terms of the
current builder work, such as:
- optimize this builder run
- analyze why this task was expensive
- suggest prompt or tool improvements for this repo
- show how to make this reverse-engineering workflow cheaper or faster

The user should not need to specify:
- which telemetry fields matter
- whether the source data came from run history, tool events, or traces
- whether the target is builder itself or another repo under builder control
- how to separate relevant optimization evidence from noisy runtime exhaust

Those are system responsibilities.

For Codex SDK runs, the default optimization score is raw total tokens. Builder
must also expose non-cached + output tokens, cache ratio, phase ceremony tokens,
avoidable-cost flags, top cost drivers, benchmark status, and a concrete
recommended next change. Subscription-backed `$0.00` cost display must not hide
raw-token inefficiency.

The current product split is:

- Metrics answers what is expensive or improving: score, cost/token totals,
  gate pass rate, top drivers, benchmark status, script candidates, and
  `optimization_decision`.
- Observability answers whether the evidence is trustworthy and what to do next:
  telemetry health, runtime aggregates, capability gaps, phase decisions,
  tool-event coverage, and deterministic recommendations.
- `builder logs analyze --session <id-or-prefix> --json` is the agent-facing bridge for prompt/session
  review and must expose the same selected-runtime, telemetry-health, and
  deterministic-recommendation evidence without requiring dashboard scraping.

## Scope And Target Of Analysis

The optimization subject must always be concrete and bounded. The default unit
of analysis is one of:
- a specific builder task
- a specific builder run
- a specific builder session
- the current target workspace or repo associated with that task/run/session

The lane may analyze `autonomous-agent-builder` itself when builder is running
on this repo. In that case, the subject is still the same bounded task/run
scope; the fact that builder is optimizing itself does not authorize broader
repo-wide introspection.

For external targets, the optimization lane should interpret the evidence in
the context of that target repo or delivery mode:
- forward engineering
- reverse engineering
- implementation work
- verification work
- documentation refresh

The optimization lane should explain how builder behavior should adapt for that
target. It should not reinterpret the target repo as the owner of builder
runtime policy.

## Allowed Inputs

The optimization lane may consume only filtered signals that materially help
explain inefficiency or suggest improvement.

### Run Summary Signals

Allowed run-level inputs include compact summary fields such as:
- agent name
- phase
- model
- turn count
- duration
- stop reason
- cost
- input, output, and cache-token counts
- task outcome state such as success, stall, budget hit, max-turn hit, or
  operator-blocked state

These fields are the default optimization evidence because they are compact and
already interpreted enough to support bounded reasoning.

### Workflow And Progress Signals

Allowed workflow-shape inputs include reduced progress signals derived from
session-level todo tracking such as:
- total todo count for the analyzed run
- completion ratio
- long-stalled `in_progress` work
- repeated reopening or duplication patterns
- evidence that the task was over-fragmented or poorly sequenced

Todo-derived signals are useful when they explain workflow inefficiency,
operator confusion, or avoidable turn growth.

The preferred source is a deterministic reduction of `TodoWrite` activity into
compact workflow signals, not raw todo history replay.

### Per-Step Signals

Per-step usage may be included only when it explains a likely optimization
issue, for example:
- repeated retries
- repeated tool loops
- unusually expensive steps
- duplicated work across turns
- oversized intermediate outputs

Per-step usage should be deduplicated before reaching the optimization agent
when the same logical step may appear multiple times in runtime telemetry.

### Tool-Efficiency Signals

Allowed tool-efficiency inputs include:
- repeated calls with near-identical intent
- failure counts or retry patterns
- high-latency calls
- oversized tool responses
- avoidable tool fan-out
- clear cases where a narrower or more structured tool contract would reduce
  turns or tokens

Tool inputs and outputs should be reduced to the smallest signal needed to
explain the inefficiency.

If tool telemetry is collapsed into generic event names such as `agent_output`,
that is itself an observability gap. Recommendations may still use run-level
and phase-level evidence, but tool-specific optimization claims should be
withheld until the tool taxonomy is specific enough to prove them.

### Telemetry-Health Signals

Allowed telemetry-health inputs include:

- selected runtime
- Claude native telemetry status, signal support, sensitive flags, and collector
  reachability
- Codex native telemetry status, project-local `[otel]` config path, exporter,
  endpoint, collector reachability, emitted signal support, trace metadata,
  feedback, and analytics when `codex_sdk` is selected
- non-selected runtime config readiness and historical access, clearly labeled
  separately from current telemetry emission
- Builder product telemetry completeness and missing canonical facts

Telemetry health should gate recommendation confidence. For example, missing or
unreachable collectors on the selected lane can trigger a telemetry-readiness
recommendation, while inactive-lane collector state should only affect future
readiness or config guidance. Complete builder-product telemetry lets the agent
trust Board, Metrics, Observability, and `builder logs analyze` as product
evidence.

### Prompt And Context-Efficiency Signals

Allowed prompt and context signals include:
- repeated stable prefixes
- bloated recurring instructions
- evidence that durable instructions should live in owner docs, skills, or KB
- context growth that is disproportionate to task progress
- output verbosity that should be compacted before re-entry into later turns

The optimization lane may reason about prompt shape and context-management
policy, but should do so from compact summary signals rather than raw transcript
replay by default.

### Runtime Guidance And Script Signals

Allowed runtime-guidance inputs include:

- the generated app's builder-generated `CLAUDE.md` and `AGENTS.md`
- discovered setup, dev-server, test, lint, typecheck, build, format, and
  smoke/browser commands
- deterministic script candidates with stable codes, triggers, expected users,
  and the evidence they replace
- exact command validation from builder preflight evidence, logs, observability,
  and metrics summaries

The optimization agent may update app-local runtime guidance or add
deterministic scripts only after the recommendation is workspace-scoped and the
exact command or owner surface has been validated. Any new script must state
which builder phase or agent should use it, the exact invocation, and what
model-backed work or validation evidence it replaces. Recommended scripts that
cannot be validated must be deferred or rejected rather than marked applied.

## Excluded Inputs

The optimization lane must not default to consuming data that is broad, noisy,
or irrelevant to efficiency decisions.

Excluded by default:
- full transcripts
- raw todo history
- raw repo-wide logs
- full traces or events dumps
- arbitrary file contents
- secrets
- auth material
- raw environment payloads
- unrelated metrics with no plausible link to optimization decisions

These inputs may only be surfaced after a deterministic reducer has already
converted them into a bounded optimization signal. Even then, the reduced signal
should be preferred over the raw source.

The optimization lane must never rely on “read everything first” behavior.

## Deterministic Analysis Vs Advisory Agent Boundary

Builder owns the deterministic collection and filtering step.

That deterministic layer decides:
- which signals are relevant
- how noisy runtime evidence is reduced
- which repeated events are deduplicated
- which issues are concrete enough to present for recommendation
- which recommendations are emitted as stable rule codes with severity,
  evidence, trigger, and next action

The advisory optimization agent consumes only that compact analysis report.

The agent may recommend changes, compare likely tradeoffs, and connect a signal
to a builder-owned prompt, tool, model, workflow, or documentation choice.

The agent must not become the primary owner of:
- telemetry persistence
- raw observability parsing
- session storage
- trace export behavior
- product-state semantics

LLMs may explain deterministic recommendations, but rule triggers must remain
code-owned and auditable. The dashboard should present those rule-backed
recommendations in the same tabbed Recommendations panel as advisory
optimization, phase, and script recommendations so users see one decision
surface rather than competing panels.

The selected runtime remains the mechanism that emits or carries runtime
signals: Claude Agent SDK for `sdk=claude` and Codex app-server events for
`sdk=codex_sdk`. Builder remains the owner of which reduced signals are
persisted and how they are interpreted for optimization.

After deterministic preflight, builder must persist a post-preflight decision
instead of treating recommendations as self-explanatory. That decision records:

- which deterministic actions were applied
- which recommendation codes were applied, rejected, deferred, not applicable,
  or observed as historical evidence
- which recommendations remain unresolved
- whether model-backed advisory review is required
- why the target is `generated_app` or `builder_source`
- how the conclusion maps to Claude Agent SDK and Codex SDK owner surfaces

For generated apps, app-local command guidance and deterministic scripts should
run before a model call. If any actionable recommendations remain, the
model-backed optimization agent must review the compact preflight packet and
return a lifecycle decision for each remaining recommendation rather than
leaving the same item in the dashboard indefinitely. For builder-source work,
residual prompt, tool, model, phase, or workflow recommendations may be routed
to the model-backed optimization agent after preflight using the same compact
packet.

The Recommendations panel shows open recommendation codes only. Applied,
rejected, not-applicable, deferred, and historical observed items remain in the
payload for auditability but must not keep rendering as current operator work.

## Recommendation Categories

The optimization lane is recommendation-only. Its output should stay within
builder-owned optimization categories such as:
- prompt optimization
- model selection changes
- tool-set tightening
- output compaction
- subagent or delegation changes
- runtime-harness selection or telemetry-coverage changes
- generated-app runtime guidance refresh when app-local `CLAUDE.md` or
  `AGENTS.md` is builder-generated but stale after implementation discovers
  deterministic setup, run, test, lint, or build commands
- KB, doc, or skill placement changes for repeated instructions
- workflow or phase-shape changes

Recommendations should be grounded in the filtered evidence and should explain
which concrete inefficiency they address.

The optimization lane should not auto-invent implementation details that are
better owned by a later spec, code change, or quality gate.

## Owner-Surface Routing

Every recommendation must name the smallest likely owner surface.

Use this routing before proposing a change:

- prompt or system instruction: the agent had correct state available but
  misunderstood the task, lacked a completion contract, skipped verification,
  or exposed internal workflow choices to the user
- `src/autonomous_agent_builder/agents/execution_policy.py`: the issue is model,
  effort, subagent, budget, or context strategy for one lane
- orchestrator or backend code: the issue is phase routing, state transition,
  blocked-state handling, task dispatch, approval handling, or retry behavior
- builder CLI/API: the issue is missing compact read-only evidence, unstable
  JSON, weak `next` guidance, or poor observability access for agents
- tool or MCP contract: the issue is tool selection, permission boundary,
  side-effect policy, retry behavior, or missing connection to a system the
  builder should operate
- knowledge, memory, or docs: the issue is repeated retrieval friction, stale
  owner guidance, or context that belongs outside the prompt
- observability: the issue is missing stop reasons, correlation ids, tool
  counts, token/cost fields, phase spans, or telemetry coverage

Do not recommend raising model effort until prompt contracts, tool boundaries,
and lightweight verification signals have been checked.

## Builder-Self Vs External-Target Interpretation

When builder runs on itself, recommendations should focus on builder-owned
surfaces such as:
- prompts
- tool contracts
- phase boundaries
- KB or reference-doc placement
- context-management policy

When builder runs on another repo, recommendations should still target builder
behavior, but interpreted through the demands of that external target. For
example:
- reverse-engineering runs may need tighter bounded retrieval
- forward-engineering runs may need different model or subagent choices
- verification-heavy runs may need more compact tool evidence and less broad
  context replay
- generated or target apps may need a deterministic app-owned `dev`, `test`,
  `lint`, `build`, `doctor`, or `smoke` command so builder can diagnose the app
  without expanding prompts or asking the user to coordinate the environment

The optimization lane should not confuse “optimize work for this target repo”
with “treat the target repo as the owner of builder runtime policy.”

Target-app CLIs or scripts are valid optimization recommendations when they
reduce repeated ambiguity in setup, verification, or diagnosis. They are not a
replacement for dashboard-first validation and they should not become a burden
the user must understand before the builder can proceed.

For generated apps, post-ship optimization should prefer app-local, SDK-loaded
guidance before spending model tokens. If builder-generated `CLAUDE.md` or
`AGENTS.md` exists and the app manifest now exposes concrete commands, the
deterministic optimization lane may refresh those files and record the command
timeline as `builder runtime guidance refresh`. This keeps the next Claude or
Codex SDK run focused on the app's known commands without asking the user to
remember prompt wording.

## Ownership Contract

`builder` owns:
- telemetry persistence and retrieval surfaces
- deterministic filtering and reduction
- optimization-analysis policy
- how optimization recommendations map back to product-owned surfaces

Claude Agent SDK owns:
- runtime execution
- sessions
- hooks
- permissions
- MCP
- runtime-emitted telemetry mechanics

Owner docs such as `CLAUDE.md`, repo references, KB docs, workflows, and skills
remain the canonical places where durable optimization outcomes should be
encoded once a recommendation is accepted.

Do not create a second freeform owner surface for “agent optimization policy”
outside this reference contract.

## Validation Expectations

Changes to this contract should be reviewed against three questions:

1. Does the optimization lane stay bounded to filtered, optimization-relevant
   signals rather than raw runtime exhaust?
2. Does the doc preserve the builder-versus-SDK ownership boundary?
3. Does the doc stay contract-oriented rather than drifting into a detailed
   implementation spec?

If a future change needs concrete schema fields, storage design, reducer logic,
or CLI/API payload definitions, that detail should live in the owning code or a
follow-up implementation spec rather than expanding this reference doc into a
build plan.

## Related Docs

- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/builder-cli.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
