# Runtime Switch Dashboard Contract

Use this when changing dashboard tabs, runtime settings, board cards, metrics, observability, or backend logs. Runtime switching is deterministic: it selects the harness for future work only, while existing project state stays durable and attributed to the runtime that produced it.

## Decision

Changing runtime between any of the three user-facing lanes (`claude`,
`claude_managed`, `codex_sdk`) must not rewrite, hide, relabel, or re-score
already shipped work. The selected runtime controls the next Agent chat turn,
next dispatch, next onboarding run, and next backend runtime log. Historical
tasks, agent runs, metrics, observability, approvals, knowledge, memory, and
backlog items remain visible with their original runtime attribution.

## Invariants

| Surface | Must Change On Runtime Switch | Must Not Change On Runtime Switch |
|---|---|---|
| Agent | Selected runtime, new thread runtime, future prompt execution, runtime-specific guidance | Existing transcript, old thread runtime, old run events, pending user questions |
| Board | Dispatch target for the next task, current-runtime label | Shipped cards, sprint membership, task title, agent name, run runtime, cost/turn/duration history |
| Metrics | Current runtime selector/context, future run totals after new execution | Existing run rows, runtime aggregates, historical costs/tokens/gates |
| Observability | Selected-runtime readiness, selected-runtime capability guidance, and future-run telemetry guidance | Historical runtime telemetry, Codex evidence after switching to Claude, Claude evidence after switching to Codex, builder-product DB facts |
| Knowledge | Future extraction/runtime guidance if a run is started | Existing docs, validation results, document list, freshness evidence |
| Memory | Future memory writes from new runs | Existing memories, corrections, decisions, runtime-specific patterns |
| Backlog | Future dispatch/runtime choice | Backlog item identity, status, priority, sprint linkage, source/evidence |
| Inbox/Approvals | Future approval requests from new runs | Existing approval threads, run links, decision history |
| Compare | Future run candidates | Existing compared run payloads and attribution |
| Backend logs | A `runtime_settings_updated` event in the active DB | Reading from archived DBs at request time or treating runtime switch as data migration |

## Tab And Button Behavior

| Tab | User Action | Frontend Result | Backend Result | Log/Telemetry Result |
|---|---|---|---|---|
| Agent | Send prompt | Starts or continues the selected/new thread; shows selected runtime and thread runtime separately | Creates chat events and run status under selected runtime | `user_message`, runtime-specific `run_status`, tools/questions/errors |
| Agent | Resume old session | Opens the old transcript; if old runtime differs, it remains marked as that thread runtime | No runtime mutation | No new run unless user sends a prompt |
| Agent | Send prompt on cross-runtime thread | Starts a fresh runtime-native session for the new turn instead of resuming a prior runtime's `sdk_session_id` | Drops the stored SDK session id when its `run_status` runtime/provider differs from the active runtime | New `run_status` under the active runtime; old transcript stays attributed to its original runtime |
| Agent | Answer question / approval | Resolves the pending event on the same thread/runtime | Appends answer event and resumes run when applicable | `ask_user_question_answer` or `tool_approval_answer` |
| Settings | Change Runtime SDK | Updates global selected runtime for future runs only | Persists runtime settings and reconciles runtime-owned files | `runtime_settings_updated` event in active `.agent-builder/agent_builder.db` |
| Board | Dispatch task | Dispatches the selected queued task with current selected runtime | Creates/updates task run records | `agent_runs`/run events use selected runtime |
| Board | Select sprint | Filters visible lanes only | No mutation | No log event |
| Board | Click task card | Opens task detail with task runtime, model, effort, timeline, gates | No mutation | No log event |
| Board | Recover blocked task | Moves blocked/capability task back through deterministic recovery | Updates task status and recovery metadata | Recovery run/event if recovery executes |
| Metrics | Open/refresh | Shows all active DB runs grouped by runtime, cost/token/gate scores, top cost drivers, and the primary next optimization action | Read-only | No log event |
| Observability | Open/refresh | Shows selected runtime readiness, historical runtime aggregates, telemetry health, capability gaps, and one tabbed Recommendations panel | Read-only | No log event |
| Knowledge | Open/search/show doc | Reads repo-local KB only | Read-only | No log event |
| Memory | Open/search/show memory | Reads repo-local memory only | Read-only | No log event |
| Backlog | Create item | Adds a backlog item with source/evidence | Writes backlog/feature state | Creation event where implemented |
| Backlog | Filter/select item | Changes view only | No mutation | No log event |
| Inbox | Approve/reject/request changes | Resolves approval and resumes or blocks the owning run | Writes approval decision | Approval answer event |
| Compare | Select/open compare | Displays two immutable run payloads | Read-only | No log event |

## Runtime Agent Parity

Builder owns the SDLC agent roles. Claude Agent SDK and Codex SDK are
runtime lanes for executing those roles, not separate product workflows. A user
switching runtime should continue to see the same lifecycle concepts, phase
names, task cards, approval points, gates, telemetry history, and
recommendation categories.

| Builder role | Claude lane | Codex SDK lane | User-visible invariant |
|---|---|---|---|
| `planner` | Claude Agent SDK run with planning model, planning effort, Builder tools, and project settings | Codex runtime run using selected Codex model with the same Builder planning role policy | Backlog-to-plan behavior, plan artifact, and phase transition stay the same |
| `designer` | Claude Agent SDK run with design model, high effort, Builder knowledge/memory tools | Codex runtime run using selected Codex model with the same design role policy | Design handoff and blocked operator-decision semantics stay the same |
| `code-gen` | Claude Agent SDK run with implementation model, implementation tools, workspace cwd, and bounded turns | Codex runtime run using selected Codex model with scripted repeatable-work policy | Implementation task identity, changed-file evidence, run attribution, and Board movement stay the same |
| `integration-resolver` | Claude Agent SDK run with implementation model and bounded conflict-resolution policy | Codex runtime run using selected Codex model with the same conflict-resolution policy | Merge/conflict recovery stays a Builder-owned phase, not a user-managed runtime detail |
| `pr-creator` | Claude Agent SDK run with PR model and evidence-summary policy | Codex runtime run using selected Codex model with evidence-summary policy | PR creation remains a phase/gate outcome with stable task and artifact attribution |
| `build-verifier` | Claude Agent SDK run with PR model and scripted verification policy | Codex runtime run using selected Codex model with scripted verification policy | Build/test verification appears the same on Board, Metrics, Observability, and logs |
| `documentation-bridge` | Claude Agent SDK run with delegated documentation subagent when needed | Codex runtime run using selected Codex model with the same documentation-refresh role policy | Knowledge/docs freshness is maintained through Builder surfaces, not runtime-specific side channels |

Internal runtime mechanics may differ. Claude may use Claude Agent SDK options
such as project settings, Claude Code preset prompting, allowed tools, MCP
servers, SDK subagents, turns, budget, and effort. Codex uses the SDK/app-server
lane, Codex config, sandbox and approval policy, app-server events, native user
input, and Codex-native agent configuration. Codex CLI and other compatibility
adapters are not sprint validation lanes. Runtime differences must not change
historical state, phase ownership, or the user-facing meaning of an agent role.

## Runtime Attribution Rules

1. Current runtime labels must use language like `Current runtime ...`.
2. Historical task cards must show the run runtime that produced the card, for example `codex_sdk`.
3. A selected runtime must never be displayed as if it produced historical cards.
4. If a page shows both current and historical runtime state, the labels must be explicit:
   - `Current runtime`
   - `Thread runtime`
   - `Sprint runtime`
   - `Run runtime`
   - `Runtime history`
5. Active DB is the product source of truth. Archived `.agent-builder` DBs are migration sources only, never live dashboard data sources.

## Metrics And Observability Decision Rules

Metrics and Observability should let a user and an agent reach the same next
optimization decision without reading raw database rows:

- Metrics shows durable scores and aggregates: total runs, total tokens,
  estimated cost, Codex credits, gate pass rate, raw tokens, cache ratio,
  top cost drivers, benchmark status, and the primary next optimization action.
- Observability shows why the decision is valid: selected runtime,
  runtime-history rows, telemetry health for Claude native, Codex native, and
  Builder product lanes, capability gaps, phase decisions, tool-event coverage,
  and deterministic recommendations.
- Observability renders one `Recommendations` panel with `All`, `Optimization`,
  `Phase`, `Scripts`, and `Rules` tabs. Rule-backed recommendations must not be
  duplicated in a second recommendations panel.
- `builder logs analyze --json` mirrors the dashboard decision fields with
  `selected_runtime`, `runtime_native_telemetry_health`,
  `builder_product_telemetry_health`, `telemetry_health`, and
  `deterministic_recommendations`.

## Backend Log Contract

Runtime settings changes write one active-DB event:

```json
{
  "event_type": "runtime_settings_updated",
  "payload_json": {
    "previous_runtime_sdk": "codex_sdk",
    "selected_runtime_sdk": "claude",
    "scope": "future_runs_only",
    "state_policy": "preserve_existing_tasks_runs_metrics_observability_memory_knowledge_backlog"
  },
  "status": "completed"
}
```

Run logs must keep using the runtime that executed the run. Switching runtime after a run completed must not mutate that run's `runtime_sdk`.

## Regression Checklist

- Switch `codex_sdk -> claude -> claude_managed -> codex_sdk` through Settings.
- Verify Board shipped cards still show the same task titles, agent names, run runtime, costs, turns, and durations.
- Verify Metrics total run count does not decrease after switching.
- Verify Observability keeps historical runtime rows for both runtimes after at least one run exists for each.
- Verify Observability shows Claude native, Codex native, and Builder product
  telemetry health as separate areas, and never reports Builder product
  telemetry as `collector unknown`.
- Verify Observability has only one Recommendations panel and that deterministic
  rules appear under the tabbed Recommendations surface.
- Verify Agent shows selected runtime separately from thread runtime.
- Verify Knowledge, Memory, Backlog, Inbox, and Compare do not lose records after switching.
- Verify `builder logs --info --compact --json` or direct active DB inspection can see runtime-switch evidence without reading archive DBs.
