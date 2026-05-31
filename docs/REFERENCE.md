# Documentation Owner Map

## Control Owner

This file owns the repo documentation type taxonomy and the map from each
documentation concern to exactly one control owner doc.

## Purpose

Read this file before creating or materially changing documentation in this
repo. It maps each documentation concern to its owning surface so agents update
the existing owner instead of creating a parallel workflow, reference, rubric, or
analysis doc.

This file is an index and ownership router. It must not duplicate the detailed
policy owned by the mapped docs.

## Control Owner Rule

There must not be more than one control owner doc for the same concern.

- A control owner doc is the one place that defines current policy, contract,
  workflow, rubric, or pass/fail expectation for a concern.
- Supporting docs may provide rationale, history, examples, measurements, source
  notes, or secondary checks, but they must not redefine the control contract.
- If two docs appear to own the same behavior, merge the current rules into one
  owner and mark the other as supporting, historical, archive, or evidence-only.
- If a new doc would repeat an existing control owner, update the existing owner
  instead.
- If a concern truly needs a new owner, add that owner to this file in the same
  change.

## Documentation Types

Use one of these doc types before choosing or creating a doc:

| Type | Location | Owns | Does not own |
| --- | --- | --- | --- |
| `objective` | `docs/PROMPT.md` + `docs/goal/` | Active goal, execution instructions, proof checklist, and operator prompt scripts | Permanent product architecture, reusable workflow doctrine, or historical analysis |
| `reference` | `docs/references/` | Stable contracts, architecture facts, schemas, boundaries, and long-lived product semantics | Step-by-step runbooks, dated evidence dumps, or can/cannot behavior rubrics |
| `workflow` | `docs/workflows/` | Multi-step operating procedures and user-flow validation loops | Stable schema facts, pass/fail gates, or dated measurements |
| `quality-gate` | `docs/quality-gate/` | Deterministic pass/fail expectations and verification commands for a named surface | Workflow narration, design rationale, or implementation history |
| `rubric` | `docs/rubric/` | What an agent, runtime, or capability can do, cannot do, must ask for, and how it is evaluated | Runtime settings, persisted state schemas, or historical measurements |
| `design-doc` | `docs/design-docs/` | Rationale, options, tradeoffs, design language, and proposals | Current canonical runtime, workflow, or policy contracts unless promoted in this map |
| `analysis` | `docs/analysis/` | Dated findings, measurements, and evidence snapshots | Current policy, current pass/fail rules, or control-owner language |
| `changelog` | `CHANGELOG.md` | Compact chronological change history for future agents | Current product contracts, workflow rules, proof checklists, or release marketing copy |

## Update Rule

1. Search this map for the concern.
2. Pick the matching documentation type above.
3. If a control owner exists, update that owner doc and keep supporting docs
   subordinate.
4. If no owner exists, add one row here in the same change that introduces the
   new owner doc.
5. If a doc is superseded, mark it as historical, archive, or evidence-only and
   point to the active owner.
6. A trigger should usually require at most one owner doc plus one quality gate.

## Owner Map

| Concern | Type | Control owner | Supporting docs | Update guidance |
| --- | --- | --- | --- | --- |
| Operator prompt scripts for Realtime voice and SDK-backed Agent page validation | `objective` | `docs/PROMPT.md` | `docs/rubric/realtime-voice-agent-page-agent.md`, `docs/rubric/sdk-backed-agent-page-agent.md` | Keep prompts phrased as operator product language, not implementation calls or agent instructions. |
| Operator capability limits | `rubric` | `docs/rubric/operator-limits.md` | `docs/rubric/realtime-voice-agent-page-agent.md`, `docs/rubric/sdk-backed-agent-page-agent.md`, `docs/PROMPT.md` | Keep only cannot-do, must-ask, decline, and delegation boundaries here. This rubric is normative; code divergence is a bug or explicit product-decision candidate. |
| Deterministic versus model-backed Agent behavior | `rubric` | `docs/rubric/deterministic-vs-model-backed-agent-behavior.md` | `docs/rubric/realtime-voice-agent-page-agent.md`, `docs/rubric/sdk-backed-agent-page-agent.md`, `docs/PROMPT.md` | Keep cross-runtime policy here for when Builder should use direct product-state/actions versus model-backed intent analysis. Runtime-specific rubrics may add examples but must not redefine the split. |
| Autonomous Builder agent catalog and responsibility-derived tool calls | `rubric` | `docs/rubric/autonomous-builder-agents.md` | `src/autonomous_agent_builder/agents/definitions.py`, `docs/rubric/sdk-backed-agent-page-agent.md`, `docs/rubric/realtime-voice-agent-page-agent.md`, `docs/quality-gate/agent-quality.md` | Define each Builder agent's responsibility first, then derive allowed tool calls and permission boundaries from that responsibility. |
| Compact project change history | `changelog` | `CHANGELOG.md` | git history, owner docs | Keep entries reverse chronological, compact, and evidence-linked. Do not define active contracts here. |
| Doc ownership and placement | `reference` | `docs/REFERENCE.md` | `workflow summary placement`, `workflow read principles --section Execution` | Update this map before adding a new doc type or owner surface. |
| Phase boundaries | `reference` | `docs/references/phase-model.md` | `docs/references/phases/*.md`, `docs/workflows/autonomous-lifecycle-validation.md` | Put phase semantics in references; keep lifecycle procedure in the workflow. |
| Autonomous lifecycle validation | `workflow` | `docs/workflows/autonomous-lifecycle-validation.md` | `docs/quality-gate/product-lifecycle.md`, `docs/quality-gate/state-integrity.md` | Keep visible product-flow steps in the workflow; keep pass/fail criteria in gates. |
| System improvement and real-user debugging | `workflow` | `docs/workflows/system-improvement-loop.md` | `docs/workflows/autonomous-lifecycle-validation.md` | Use for reproduce, trace owner, fix, retest loops. |
| Task workspace isolation | `workflow` | `docs/workflows/task-workspace-isolation.md` | `docs/references/phase-model.md` | Keep workspace identity and isolation procedure here. |
| Runtime settings and supported SDK lanes | `reference` | `docs/references/runtime-settings.md` | `docs/references/runtime-switch-dashboard-contract.md`, `docs/design-docs/modular-runtime-architecture.md` | `runtime-settings.md` owns stable keys and supported lanes. Architecture remains rationale. |
| Runtime switching dashboard behavior | `reference` | `docs/references/runtime-switch-dashboard-contract.md` | `docs/references/runtime-settings.md`, `docs/quality-gate/modular-runtime.md` | Keep future-run switching, historical attribution, and dashboard behavior here. |
| Modular runtime rationale | `design-doc` | `docs/design-docs/modular-runtime-architecture.md` | `docs/references/runtime-settings.md` | Use for rationale and boundary explanation, not the canonical settings schema. |
| Frontend React architecture | `rubric` | `docs/rubric/frontend-react-architecture.md` | `docs/design-docs/design-language.md`, `docs/quality-gate/dashboard-ux.md`, `docs/design-docs/agent-page-hierarchy.md` | Use as the review lens for React architecture, performance, context management, and design-system compliance. |
| Backend service architecture | `rubric` | `docs/rubric/backend-service-architecture.md` | `docs/quality-gate/architecture-boundary.md`, `docs/quality-gate/state-integrity.md`, `docs/references/phase-model.md` | Use as the review lens for service boundaries, runtime isolation, state ownership, and backend performance. |
| Claude Agent SDK runtime quality | `quality-gate` | `docs/quality-gate/claude-agent-sdk.md` | `CLAUDE.md`, `docs/workflows/agent-quality-tuning-loop.md` | Gate SDK runtime behavior here; keep Claude runtime contract in `CLAUDE.md`. |
| Claude SDK telemetry and observability policy | `reference` | `docs/references/claude-agent-sdk-telemetry-observability.md` | (none) | Use for telemetry split and content-safety policy. |
| Agent quality tuning | `workflow` | `docs/workflows/agent-quality-tuning-loop.md` | `docs/quality-gate/agent-quality.md`, `docs/references/agent-optimization-analysis.md` | Tuning loop in workflow; pass/fail in gate; **optimization-lane policy contract in `agent-optimization-analysis.md`** (the upstream contract both workflow and gate ground in). |
| Codex project subagents for repo optimization | `quality-gate` | `docs/quality-gate/codex-subagents.md` | `.codex/agents/`, `.codex/config.toml`, `AGENTS.md`, `docs/quality-gate/agent-quality.md` | Keep Codex-only subagent pass/fail expectations here; do not move them into Claude Agent SDK runtime docs. |
| SDK-backed Agent page behavior | `rubric` | `docs/rubric/sdk-backed-agent-page-agent.md` | `docs/quality-gate/agent-quality.md` | Rubric owns current can/cannot/must-ask behavior. |
| Builder CLI contract | `reference` | `docs/references/builder-cli.md` | `docs/quality-gate/builder-cli.md` | Stable command contracts live in the reference; gates own pass/fail checks. |
| Realtime voice integration | `reference` | `docs/references/realtime-voice-integration.md` | `docs/rubric/realtime-voice-agent-page-agent.md` | Integration policy lives in the reference; Realtime source docs are loaded only for prompt or cost changes. |
| Realtime voice agent evaluation | `rubric` | `docs/rubric/realtime-voice-agent-page-agent.md` | `docs/references/realtime-voice-integration.md` | Keep can/cannot/must-ask scenario rubric here, not in implementation docs. |
| Day-0 readiness | `reference` | `docs/references/day-0-readiness.md` | `docs/quality-gate/generated-app-acceptance.md` | Keep readiness contract here; product validation stays in gates/workflows. |
| Dashboard UX and design language | `design-doc` | `docs/design-docs/design-language.md` | `docs/quality-gate/dashboard-ux.md`, `docs/design-docs/agent-page-hierarchy.md` | Design language owns visual rules; UX gate owns pass/fail criteria. |
| Architecture boundary review | `workflow` | `docs/workflows/architecture-boundary-review.md` | `docs/quality-gate/architecture-boundary.md` | Use workflow for review process and the gate for owner boundaries and invariants. |
| Complexity and god-file ratchet | `quality-gate` | `docs/quality-gate/complexity.md` | `docs/quality-gate/complexity-baseline.json`, `builder lint --complexity-report --json` | Keep pass/fail thresholds and baseline ownership here; update the baseline only from a current scanner report. |
| Filesystem trust boundaries | `reference` | `docs/references/filesystem-boundaries.md` | `tests/test_path_containment.py`, `docs/quality-gate/architecture-boundary.md` | Keep root-plus-controlled-path containment policy here; tests own static regression checks. |
| State integrity | `quality-gate` | `docs/quality-gate/state-integrity.md` | `docs/quality-gate/architecture-boundary.md` | Gate canonical DB/artifact/projection behavior here. |
| Approval behavior | `quality-gate` | `docs/quality-gate/approval.md` | `docs/workflows/autonomous-lifecycle-validation.md` | Keep approval safety pass/fail rules in the gate. |
| Knowledge base (format, extraction, linting, retrieval) | `reference` | `docs/knowledge.md` | `docs/quality-gate/knowledge-base.md` | Single owner doc covering format contract, extraction, linting, retrieval; merged from former format/linting/extraction trio 2026-05-21. |
| Documentation agent behavior | `reference` | `docs/references/documentation-agent.md` | `docs/quality-gate/documentation-agent.md` | Reference owns role/contract; gate owns pass/fail expectations. |
| SDLC placement of documentation refresh | `reference` | `docs/references/autonomous-delivery-documentation-refresh.md` | `docs/references/documentation-agent.md`, `docs/references/main-commit-reference.md` | Owns where doc refresh sits in delivery flow, ownership split (builder/doc-agent/git lanes), primary vs post-main backstop role. |
| Memory retrieval workflow | `workflow` | `docs/workflows/memory-retrieval-guide.md` | `builder memory contract --json` | Keep repo memory procedure here; memories hold compact anecdotes only. |

## Consolidation Candidates

When reducing duplicate context load, consolidate these clusters first:

| Cluster | Scaffold into | Keep as support | Demote or archive |
| --- | --- | --- | --- |
| Runtime and SDK ownership | `docs/references/runtime-settings.md` | `docs/design-docs/modular-runtime-architecture.md`, `docs/references/runtime-switch-dashboard-contract.md` | (none — historical spec removed 2026-05-21) |
| Agent quality and optimization | Three-way ownership: `docs/references/agent-optimization-analysis.md` (policy contract), `docs/workflows/agent-quality-tuning-loop.md` (procedure), `docs/quality-gate/agent-quality.md` (pass/fail). | none — confirmed three distinct concerns | none |
| Realtime voice integration and evaluation | Keep separate owners: `docs/references/realtime-voice-integration.md` for integration and `docs/rubric/realtime-voice-agent-page-agent.md` for behavior rubric | none | none unless source notes start redefining Builder policy |
| Phase and lifecycle | Keep separate owners: `docs/references/phase-model.md` for semantics and `docs/workflows/autonomous-lifecycle-validation.md` for procedure | `docs/references/phases/*.md` only when they add non-duplicative phase detail | Merge phase child docs into `phase-model.md` if they mostly repeat the same facts |

## Historical Or Evidence-Only Docs

None currently. (`docs/design-docs/modular-runtime-spec.md` and `docs/analysis/builder-cli-tool-signal-analysis.md` were removed 2026-05-21 as fully superseded by their active owners. `docs/references/agent-optimization-analysis.md` and `docs/references/autonomous-delivery-documentation-refresh.md` were re-evaluated 2026-05-21 and confirmed as canonical owners — promoted out of this list.)
