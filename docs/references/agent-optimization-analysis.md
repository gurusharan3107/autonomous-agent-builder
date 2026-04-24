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

## Purpose

The optimization lane exists to help the product improve agent efficiency for a
specific builder task, run, session, or target repository.

It is not a broad analytics persona and it is not a freeform “read everything
and suggest improvements” agent.

Its core invariant is:

the optimization agent reasons over interpreted signals, not raw observability
exhaust.

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

The advisory optimization agent consumes only that compact analysis report.

The agent may recommend changes, compare likely tradeoffs, and connect a signal
to a builder-owned prompt, tool, model, workflow, or documentation choice.

The agent must not become the primary owner of:
- telemetry persistence
- raw observability parsing
- session storage
- trace export behavior
- product-state semantics

Claude Agent SDK remains the runtime mechanism that emits or carries runtime
signals. Builder remains the owner of which reduced signals are persisted and
how they are interpreted for optimization.

## Recommendation Categories

The optimization lane is recommendation-only. Its output should stay within
builder-owned optimization categories such as:
- prompt optimization
- model selection changes
- tool-set tightening
- output compaction
- subagent or delegation changes
- KB, doc, or skill placement changes for repeated instructions
- workflow or phase-shape changes

Recommendations should be grounded in the filtered evidence and should explain
which concrete inefficiency they address.

The optimization lane should not auto-invent implementation details that are
better owned by a later spec, code change, or quality gate.

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

The optimization lane should not confuse “optimize work for this target repo”
with “treat the target repo as the owner of builder runtime policy.”

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
