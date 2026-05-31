---
title: "Backend service architecture rubric"
tags: ["backend", "architecture", "services", "runtime", "rubric"]
doc_type: "rubric"
created: "2026-05-18"
---

# Backend Service Architecture Rubric

## Purpose

Use this rubric to review Builder backend changes for domain ownership, service
boundaries, runtime isolation, performance, and maintainability. It is the lens
for backend review before optimizing code or moving logic across modules.

This rubric complements the architecture quality gates. The gates provide
pass/fail checks. This rubric defines the architectural judgment behind those
checks.

## Grounding

- Product state is owned by Builder services and persistence. Routes, CLI
  commands, dashboard streams, runtime adapters, and SDK tools adapt that state.
- Runtime lanes execute work. They do not redefine backlog, board, approval,
  memory, knowledge, metrics, phase, or gate semantics.
- Events, logs, metrics, and streams are evidence/projections of canonical
  state, not alternate sources of truth.
- Backend optimization must preserve functionality and lifecycle semantics.
- Python files target 500 lines or fewer. Existing files above 500 lines are
  historical debt only when listed in the complexity baseline with owner and an
  extraction plan; new behavior should reduce those files or move into focused
  owner modules.

## Decomposition Architecture

Use a modular-monolith, ports-and-adapters shape:

- Routes and CLI commands are adapters. They validate input, call one owner, and
  serialize output. They must not own lifecycle policy, orchestration loops, or
  duplicate state transitions.
- Domain services own state transitions and invariants. Examples include task
  dispatch, approvals, phase status, runtime settings, Realtime voice handoff,
  completion digest, and knowledge publishing.
- Query/projection builders own read models for dashboards, logs, metrics, and
  transcripts. They do not mutate canonical state.
- Runtime adapters own SDK/provider mechanics and return typed results. They do
  not decide backlog, approval, phase, or recovery semantics.
- Serializers and API models live beside the adapter surface when they are pure
  contracts. They should move out of route files once the contract grows beyond
  trivial request/response shapes.
- Tests follow the same boundary. Route smoke tests stay small; behavior suites
  move into focused test modules named for the owner surface.

## Placement Principles

Place code by its reason to change:

- Shared system modules are for stable primitives or contracts used by multiple
  owners. Examples: typed API models, event publication contracts, runtime
  interfaces, status payload builders, file-boundary validators, design tokens,
  and command/query DTOs. They must have narrow inputs/outputs and no hidden
  product workflow ownership.
- Focused owner modules are for one workflow or invariant family. Examples:
  Agent chat-turn publication, Agent control-owner reconciliation, voice
  completion digest, task recovery, sprint execution, phase projection, and
  dashboard metrics projection. They may call shared primitives, but they own
  exactly one policy seam.
- Adapter modules are for transport. API routes, embedded routes, CLI commands,
  SDK tools, and dashboard streams parse inputs, call one focused owner, and
  serialize evidence. They should not grow business rules merely because they
  are close to the request.
- Runtime modules are for provider mechanics. Claude, Codex, Realtime, local
  tools, retries, token accounting, and streaming callbacks belong there only
  when they are provider mechanics, not Builder lifecycle decisions.
- Test modules mirror ownership. Shared-contract tests live beside shared
  primitives; workflow tests live beside the focused owner; route tests prove
  the adapter still wires the owner into the public surface.

Do not promote code to the shared system just because two files currently need
it. Promote only when the abstraction is stable, named in domain language, and
can be tested without importing a route or CLI command. If the rule depends on
Agent-page, Board, Voice, phase, approval, or task semantics, keep it in that
focused owner until at least two independent owners need the same contract.

Preferred extraction patterns:

- Command handler for state-changing operations such as answering a decision,
  starting delivery, or recovering a task.
- Query service for read-only Board, Agent history, Metrics, Observability, and
  transcript projections.
- Policy object or strategy for routing, capability decisions, provider-limit
  classification, deterministic recommendations, or phase transitions.
- Serializer/presenter for operator-safe text, timeline events, and compact CLI
  payloads.
- Runtime adapter for provider-specific calls, streaming, retries, and token
  accounting.

Avoid extraction that merely moves private helpers into `utils`, `common`, or a
catch-all service. A split is valid only when the new module has a clear owner,
stable inputs/outputs, and focused tests.

## Scoring

Use the same scale for every category:

| Score | Meaning |
| --- | --- |
| 0 | Violates a product invariant, corrupts state, or breaks recovery. |
| 1 | Works through duplicated policy, hidden coupling, or route-local special cases. |
| 2 | Functionally correct but leaves boundary ambiguity, weak evidence, or avoidable cost. |
| 3 | Aligned with service ownership, state invariants, and focused verification. |
| 4 | Aligned and reduces future drift through clearer APIs, stronger tests, or simpler runtime boundaries. |

## Rubric

| Category | Pass Standard | Fail Signals |
| --- | --- | --- |
| Domain ownership | Feature, task, run, approval, gate, memory, knowledge, workspace, and metric concepts have one service or domain owner. | Routes, CLI commands, runtime adapters, and UI endpoints each reimplement lifecycle transitions. |
| Route thinness | API routes validate inputs, call service methods, translate responses, and stream evidence. Long-running orchestration lives in named services or runtime modules. Route files stay at or move toward the 500-line target. | Route handlers contain chat loops, task dispatch policy, retry semantics, large output-normalization branches, or keep growing above 500 lines. |
| Service contracts | Services expose typed inputs/outputs, deterministic errors, and narrow command/query methods. Private helpers are not consumed across module boundaries. | A service imports another module's underscored helper, returns ad hoc dictionaries with unstable shapes, or forces callers to know storage details. |
| Command/query split | Read paths are side-effect free; mutation paths are explicit, auditable, and permissioned. CLI/API/SDK tools share the same service contract. | A status endpoint mutates state, a CLI command bypasses the service layer, or an SDK tool writes state through a separate lane. |
| State machine integrity | Phase, board, approval, run, and blocked states move through canonical transitions with preserved recovery evidence. | Work appears shipped while blocked, starts twice, advances without approvals, or loses the resume/recover path. |
| Runtime boundaries | Claude SDK, Codex SDK, Realtime Voice, and deterministic tools are adapters around Builder state. Runtime-specific behavior stays out of product semantics. | Runtime strings leak into phase decisions, prompt policy owns lifecycle truth, or voice/delegation bypasses Agent-page evidence. |
| Boundary safety | File paths, repo roots, workspace identities, and generated-app targets are validated at the system boundary with structured parsers. | Raw path joins, broad filesystem reads, or generated-app operations can escape the controlled workspace. |
| Error and recovery | Failures produce structured evidence, stable operator messages, and a deterministic retry/recover path. | Exceptions surface as raw stack traces, block cards omit recovery state, or recovering a task requires manual DB/API surgery. |
| Observability | Logs, metrics, run events, tool events, token/cost evidence, and recommendations map back to canonical runs and tasks. | Observability invents recommendations without bounded evidence or cannot explain which task/run caused a product state. |
| Performance and context | Hot paths avoid repeated large context assembly, repeated full scans, unnecessary serialization, and N+1 service calls. Caching is explicit and invalidated by owner state. | Optimization trims tokens or CPU by dropping required evidence, hiding state, or adding stale caches without invalidation. |
| Test architecture | Unit tests cover service contracts and edge cases; API tests prove route/service integration; browser-visible regressions have static or end-to-end coverage. | Tests only check command success while lifecycle behavior, approvals, or recovery state can drift. |
| Product validation | Backend fixes are validated through Builder-owned surfaces: Agent, Board, Voice, approvals, Metrics, Observability, logs, and quality gates. | Raw API calls or database writes are used as proof for a lifecycle behavior the operator must perform through the dashboard. |
| File-size ratchet | New files stay at 500 lines or fewer. Existing over-500 files may only shrink or split, and the baseline must ratchet down after each reduction. | A change adds behavior to an over-500 file, creates a new over-500 file, or leaves a stale higher baseline after decomposition. |

## Current Regression Lens

Treat these as explicit review traps for this branch:

- Tool services must call stable public contracts, not private helpers removed
  from CLI modules.
- Builder state must keep Start Work, blocked state, phase dots, approvals, and
  recovery aligned across API, Board, and Agent views.
- A pending approval/question blocks the agent lane until resolved; backend
  status should not suggest active autonomous work while waiting on the
  operator.
- Imperative feature requests from Agent page and Voice must route through
  feature capture/planning instead of jumping directly to generated-app edits.
- Large route files should shed runtime loops or orchestration branches into
  named modules only when that simplifies ownership without changing behavior.
- Decomposition must preserve behavior first: move cohesive ownership, keep
  public contracts stable, run focused regression tests, and only then continue
  peeling down the next hotspot.

## Required Review Questions

- Which service owns the state transition or contract being changed?
- Is this code adapting Builder state, or silently redefining it?
- Is there one public function that both CLI and API can use?
- What happens after failure, and which evidence lets the operator recover?
- Does the performance improvement preserve the same evidence and user-visible
  lifecycle behavior?

## Useful Checks

```bash
builder quality-gate architecture-boundary --json
builder quality-gate state-integrity --json
builder lint --complexity-report --json
PYTHONPATH=src pytest tests/test_builder_tool_service.py tests/test_dashboard_api.py tests/test_embedded_agent_routes.py -q
```

Browser-visible backend proof should still follow lifecycle validation. Passing
service tests alone does not prove that Agent, Board, Voice, approvals, Metrics,
and Observability remain coherent.

## Related Docs

- `docs/quality-gate/architecture-boundary.md`
- `docs/quality-gate/state-integrity.md`
- `docs/references/phase-model.md`
- `docs/references/filesystem-boundaries.md`
- `docs/workflows/autonomous-lifecycle-validation.md`
- `docs/rubric/sdk-backed-agent-page-agent.md`
- `docs/rubric/realtime-voice-agent-page-agent.md`
