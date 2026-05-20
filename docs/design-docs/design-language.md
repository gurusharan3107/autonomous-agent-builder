# Dashboard Design Language

## Purpose

This document owns the durable visual and interaction rules for the Builder
dashboard. It is the design-language owner mapped in `docs/REFERENCE.md`.

Use this doc before changing dashboard routes, page hierarchy, visual density,
theme behavior, status language, motion, or the operator evidence surfaces.

## Product Frame

The dashboard is an operator console with editorial calm. It should make current
state, next action, and evidence easy to scan without asking the operator to
understand SDK internals.

The standing architecture is:

- Voice is the operator.
- Builder Agent is the brain and execution lane.
- Agent page is the audit transcript.
- Dashboard is the evidence plane.

## Visual Rules

- Use Builder design-system tokens and primitives from `frontend/src/design-system`.
- Do not introduce raw color values when an existing semantic token fits.
- Use compact, dense layouts for operational surfaces; avoid marketing-style
  hero sections, decorative cards, and large empty regions.
- Keep page intros calm and concise. The work surface should be visible in the
  first viewport.
- Use tabs for distinct modes, not duplicate panels.
- Use status strings and tones from the Builder status language. Unknown,
  blocked, loading, failed, success, and empty states must be explicit.
- Use Settings for operator appearance preferences. Do not reintroduce a global
  design drawer or a second appearance control surface.

## Page Patterns

### Board

- Board is the horizon and state scan surface.
- Board operator copy should describe work and improvements, not require
  sprint, task-dispatch, phase, or gate vocabulary for the happy path. Keep
  technical labels inside evidence/details when they are needed for proof.
- Cards should stay compact: id, status pill, title, short context, progress,
  and minimal footer evidence.
- Detailed task/run inspection belongs in Agent `Run trace`, reached by a
  direct link from the Board.
- Board density must follow the persisted `boardDensity` runtime preference.

### Agent

- Agent is split into `Conversation` and `Run trace`.
- `Conversation` owns operator chat, voice transcript rows, questions,
  approvals, and concise session context.
- Conversation and Voice empty states should use operator-facing work language
  such as Builder work, decisions, improvements, and voice turns. Avoid
  exposing tool-call, gate, Realtime, sprint-task, or dispatch vocabulary before
  the operator needs evidence details.
- `Run trace` owns task/run evidence, gates, cost, confidence, approvals, and
  compact logs. It must not duplicate the operator chat transcript.
- Questions and approvals should appear inline where the operator can answer
  without leaving the thread.

### Settings

- Settings owns runtime lane, voice transport, board density, default Agent
  mode, and appearance controls.
- Appearance controls should write one runtime preference object and apply theme
  state through root variables or attributes.
- Theme presets must remain compatible with calm, operator, sage, ember,
  midnight, and paper modes.

### Evidence Surfaces

- Metrics, Observability, Knowledge, Memory, Backlog, Inbox, Approvals, and
  Compare must render active project state with clear empty, blocked, loading,
  failed, and success states.
- Backlog and Approval happy paths should read as planned improvements and
  decisions. Use terms like work list, improvement, success checks,
  prerequisites, decision, and evidence before falling back to internal
  lifecycle terms.
- Backlog may preserve raw feature/work identifiers in APIs and traces, but the
  visible work list and detail metadata should display generated `feature-*`
  identifiers as neutral `item-*` labels and use human-readable item type
  labels such as `Improvement`.
- Evidence panes should be factual and compact. Do not turn diagnostic data into
  a second transcript or a full raw-log dump by default.

## Motion

- Motion should support orientation, not decoration.
- Use page-level entrance and inspector reveal patterns sparingly.
- Respect `prefers-reduced-motion`; reduced motion must disable entrance
  choreography and leave layout stable.

## Reference Validation

When checking visual parity, compare the live dashboard against the reference
bundle at:

`/Users/gurusharan/Documents/remote-claude/active/apps/apps-design-system/Autonomous-agent-builder`

Classify mismatches by true owner before fixing:

- design token
- primitive usage
- layout density
- route state
- runtime data
- transcript rendering
- Settings preference persistence

## Verification

Minimum deterministic checks for dashboard design changes:

- `python scripts/check_dashboard_design_tokens.py --json`
- `pytest tests/test_dashboard_design_system_contract.py tests/test_dashboard_api.py tests/test_embedded_dashboard_streams.py -q`
- `cd frontend && pnpm lint`
- `cd frontend && pnpm build`
- `builder quality-gate dashboard-ux --json`

Manual proof still matters. Start `builder start --port 9876`, capture the
relevant live screens in Chrome, and compare them with the reference bundle
before claiming visual convergence.
