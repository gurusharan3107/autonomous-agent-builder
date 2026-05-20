---
title: "Quality gate contract"
surface: "quality-gates"
summary: "Inspect task-scoped gate results through task detail views and keep pass/fail evidence machine-readable."
commands:
  - "builder backlog task status <task-id> --json"
  - "builder backlog task show <task-id> --full --json"
expectations:
  - "default verification output stays bounded until task detail expansion is requested"
  - "--json is the stable machine contract"
  - "use task-scoped gate retrieval through builder backlog task surfaces instead of scraping logs"
  - "follow-up action stays obvious when a gate fails"
---

# Quality gate contract

## Purpose

Use this gate when changing how task-scoped gate results are surfaced through
builder backlog task commands.

## When To Load

Load this gate before:

- changing task-status verification output
- changing gate result rendering in `builder backlog task show --full`
- changing JSON fields used to inspect pass/fail evidence

## Pass Signals

- verification remains task-scoped and bounded by default
- JSON stays the stable machine contract
- follow-up action is obvious when verification fails

## Fail Signals

- callers have to scrape logs to understand gate state
- gate details are no longer reachable through task surfaces

## Related Docs

- [verification.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/verification.md)

## Product Validation Taxonomy

Use this taxonomy when a review checklist spans the whole builder product. Do
not force every item into `verification`; route each concern to the gate that
owns the failure mode.

| Validation Check | Owning Gate | Notes |
|---|---|---|
| Use Case Fit | `agent-quality` | Mission fit: the product should remove manual tool/model/workflow/context management. |
| End-To-End Journey Completeness | `generated-app-acceptance` plus `verification` | Browser-visible journey from init/onboarding through execution, gates, review, and continuation. |
| Orchestration Ownership | `agent-quality` plus `architecture-boundary` | Builder owns phase routing, model/tool choice, retries, blocked state, and next action. |
| State Integrity | `state-integrity` | Canonical DB/project state must agree with artifacts, runs, gates, approvals, knowledge, and memory. |
| Backlog And Board Correctness | `verification` plus `product-lifecycle` | Planning must create real work items and board transitions must match the lifecycle. |
| Human Approval Semantics | `approval` | Approval points must be explicit, inspectable, enforced, and resumable. |
| Agent Execution Reliability | `agent-quality` plus `verification` | Tasks dispatch and progress through planning/design/implementation/gates/review/build verification. |
| Recovery And Blocked-State Handling | `architecture-boundary` plus `product-lifecycle` | Failures preserve state and expose deterministic restart/resume paths. |
| Knowledge And Memory Quality | `knowledge-base`, `documentation-agent`, `claude-md` | Repo-local knowledge and reusable memory must be useful, fresh, non-duplicative, and correctly owned. |
| Verification Strength | `verification`, `quality-gates`, generated-app-specific gates | Tests, lint, security, docs freshness, and gate evidence must be real controls. |
| Observability And Evidence | `agent-quality` plus runtime telemetry gates | Operators must see what happened, what failed, why, what changed, and what is next. |
| CLI Agent-Friendliness | `builder-cli` | Commands must be deterministic, bounded, JSON-stable, and product-concept aligned. |
| Dashboard UX Clarity | `dashboard-ux` | UI must make state, blocked approvals, active task, history, and evidence obvious. |
| Workspace And Session Continuity | `architecture-boundary` plus `state-integrity` | Resume must preserve repo/workspace/session identity and avoid project mixing. |
| Product Coherence | `agent-quality` plus `product-lifecycle` | The product must feel like one builder-owned operating system, not disconnected pages. |
| Domain Architecture | `architecture-boundary` | Core concepts such as project, feature, task, run, gate, approval, session, workspace, knowledge, and memory must stay stable. |
| Ownership Boundaries | `architecture-boundary`, `claude-md`, `builder-cli` | Product state, runtime execution, CLI, UI, tools, and docs need one owner each. |
| State Machine Design | `architecture-boundary` plus `product-lifecycle` | SDLC states/transitions must be explicit, not scattered across route assumptions and agent text. |
| Source Of Truth Design | `state-integrity` | DB state is canonical; artifacts, JSON files, transcripts, and dashboard responses are projections or migration inputs. |
| Layering | `architecture-boundary` | UI, CLI, routes, services, orchestrator, persistence, and runtime adapters stay separated. |
| Embedded Vs Main App Consistency | `architecture-boundary` plus `state-integrity` | Main and embedded servers expose the same product contract. |
| Orchestrator Pattern Quality | `architecture-boundary` plus `agent-quality` | Orchestrator remains deterministic owner of routing, retries, blocked states, approvals, and phase movement. |
| Adapter Design | `architecture-boundary` plus `builder-cli` | CLI, dashboard, SDK tools, and agents should adapt over shared services instead of inventing behavior. |
| Event And Streaming Model | `state-integrity` | SSE/log/session events are reliable projections of state, not competing truths. |
| Persistence Pattern | `state-integrity` | Repositories, transactions, migrations, and writes prevent partial/inconsistent state. |
| Command/Query Split | `builder-cli` plus `architecture-boundary` | Mutations are explicit/controlled; reads are bounded, stable, and inspectable. |
| Extensibility | `architecture-boundary` | New agents, gates, workflows, models, and surfaces should not duplicate lifecycle logic. |
| Testability | `verification` plus `architecture-boundary` | Service/API/CLI/browser tests should verify behavior without fragile mocks. |
| Failure Isolation | `architecture-boundary` plus `product-lifecycle` | Agent/model/tool/gate/approval failures preserve resumable state. |
| Pattern Discipline | `architecture-boundary` | Avoid mixing service logic, route logic, file writes, DB writes, and agent behavior in one place. |

### First-Class Product Gate Surfaces

The existing gates now cover agent quality, CLI quality, approval,
verification, knowledge, docs, runtime boundaries, and these first-class
product gates:

- `product-lifecycle`: end-to-end journey, backlog/board correctness,
  state-machine transitions, recovery, and product coherence.
- `state-integrity`: canonical source of truth, DB/artifact/event consistency,
  migrations, persistence, and embedded-vs-main parity.
- `dashboard-ux`: visible state clarity across Agent, Board, Metrics,
  Observability, Knowledge, Memory, Backlog, Inbox, and Compare.
- `architecture-invariants`: stricter architecture review for domain model,
  layering, adapter design, extensibility, failure isolation, and pattern
  discipline when `architecture-boundary` is too broad.
