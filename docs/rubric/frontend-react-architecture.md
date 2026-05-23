---
title: "Frontend React architecture rubric"
tags: ["frontend", "react", "architecture", "dashboard", "rubric"]
doc_type: "rubric"
created: "2026-05-18"
---

# Frontend React Architecture Rubric

## Purpose

Use this rubric to review Builder frontend changes for architecture,
performance, state ownership, and design-system alignment. It is the lens for
React review before optimizing dashboard code.

This rubric complements the dashboard UX gate. The UX gate decides whether the
operator can see coherent state, action, evidence, and runtime effects. This
rubric decides whether the React implementation keeps that behavior durable,
efficient, and easy to reason about.

## Grounding

- The Builder design system owns primitives, tokens, motion hooks, status
  language, and page-level visual patterns.
- React performance review should prioritize waterfalls, bundle size,
  server/client data flow, rerenders, rendering cost, and JavaScript hot paths.
- Dashboard lifecycle semantics come from Builder state, lifecycle workflows,
  and API responses. React components project that state; they do not invent a
  second lifecycle model.
- Frontend source files target 500 lines or fewer. Existing files above that
  limit are historical debt; new work should move owner-specific logic into
  focused components, hooks, selectors, presenters, or API modules without
  changing visible behavior.

## Decomposition Architecture

Use a feature-sliced React architecture:

- Pages are route adapters. They assemble data loading, layout, and feature
  regions, but they do not own detailed business rules, duplicate lifecycle
  semantics, or long inline render branches.
- Feature components own one visible workflow or region, such as Agent timeline,
  pending decision actions, Board phase rail, lane cards, Voice transcript,
  Metrics panels, or Observability command evidence.
- Static contract tests should follow the same owner split. When a page has
  been decomposed, scan the route adapter plus its feature modules rather than
  forcing feature-owned strings or controls back into the page file.
- Hooks own side effects and runtime subscriptions. They expose typed state and
  commands, avoid hidden global mutation, and keep reconnect/polling behavior
  outside presentational components.
- Selectors and presenters own derived labels, counts, disabled reasons, phase
  status, and display grouping. Components should render those projections
  rather than recompute lifecycle truth inline.
- Design-system primitives own shared visual semantics: buttons, tabs, status
  dots, pills, cards, drawers, motion hooks, and decision actions. Product pages
  should compose primitives, not fork local visual systems.
- API clients and shared types own transport shape. Pages and components should
  consume typed responses and avoid ad hoc parsing of backend payloads.
- Tests follow the same boundaries. Static tests cover selectors, ownership
  rules, and design-system usage; browser tests prove the operator flow remains
  intact.

## Placement Principles

Place code by its reason to change:

- Shared system modules are for stable UI primitives and contracts used by
  multiple features. Examples: design-system components, status tokens, typed
  API clients, shared response types, accessibility helpers, and pure formatting
  primitives. They must not know Agent, Board, Voice, Metrics, or Observability
  workflow policy.
- Focused feature modules are for one visible workflow or invariant family.
  Examples: Agent timeline, pending decision composer, Voice transcript,
  Board phase rail, Board lane projection, phase drawer evidence, Metrics
  recommendation panels, and Observability command timeline.
- Page modules are route adapters. They load data, choose feature regions, and
  preserve URL/layout state. They do not own selectors, lifecycle policy,
  transport parsing, or bespoke primitives.
- Hooks own effects and subscriptions. They should be shared only when the
  effect contract is independent of the page workflow; otherwise keep them under
  the focused feature that owns the behavior.
- Selectors/presenters own derived view data. They are pure, testable, and named
  after the state they project, such as phase status, disabled start reason,
  pending decision view model, or transcript label.
- Tests mirror ownership. Pure selector tests live beside selectors; feature
  tests cover one workflow; page/browser tests prove the assembled operator path.

Do not promote code to shared UI because it appears twice visually. Promote only
when the semantics are the same, the API is stable, and the component belongs in
the Builder design system. If the component encodes Agent-page, Board, Voice, or
approval policy, it remains a focused feature module.

Preferred extraction patterns:

- Container/presenter split for large page regions with data and view logic.
- Custom hook for subscriptions, polling, realtime connection state, keyboard
  shortcuts, or optimistic UI rollback.
- Pure selector for phase dots, lane counts, disabled states, transcript labels,
  and drawer summaries.
- Single owner component for each blocking action surface, especially approval
  decisions and Start Work state.
- Design-system wrapper only when it becomes a reusable primitive with one
  documented contract.

Avoid extraction that creates generic `utils`, duplicate local UI kits, parallel
action owners, or wrappers that only hide the original complexity under another
name.

## Scoring

Use the same scale for every category:

| Score | Meaning |
| --- | --- |
| 0 | Violates the product contract or creates a user-visible regression. |
| 1 | Works only through duplicated state, duplicated UI, or fragile special cases. |
| 2 | Functionally correct but leaves unclear ownership, weak tests, or avoidable performance cost. |
| 3 | Aligned with the product contract, design system, and focused evidence. |
| 4 | Aligned and actively reduces future drift through simpler ownership or stronger checks. |

## Rubric

| Category | Pass Standard | Fail Signals |
| --- | --- | --- |
| Surface ownership | Each page has one owner for a user action, state banner, modal, or inline decision. Shared controls are extracted only when they remove real duplication. | The same approval, question, recommendation, or lifecycle action renders from two independent code paths. |
| State truth | UI state is derived from canonical API/session data and stable local view state. Derived labels, disabled states, counts, and phase dots agree with backend state. | Components infer lifecycle truth from unrelated ids, tab state, stale arrays, or optimistic flags that can outlive the backend state. |
| Decision controls | Blocking questions and approvals use the current design-system decision card/action pattern exactly once, keep the agent blocked, and suppress conflicting composer prompts. | Inline approval controls appear twice, the generic composer remains active during a blocking decision, or the agent looks like it is still working while waiting for approval. |
| Lifecycle actions | Buttons and controls reflect whether work can currently start, resume, recover, hold, or open evidence. Disabled reasons are deterministic and visible through accessible labels. | A start/recover/approve action stays enabled after the work already started, is blocked, or is waiting on an operator decision. |
| Data loading | Data fetches are page-scoped, cancellable where needed, and avoid request waterfalls for independent data. Polling preserves mounted user context. | Polling clears visible transcripts, request chains serialize independent calls, or loading states hide durable product evidence. |
| Component boundaries | Components have domain names and small responsibilities. Hooks own reusable state transitions; presentational components receive already-shaped props. | Large page files mix data fetching, lifecycle policy, rendering variants, and event formatting without an owner boundary. |
| Performance and context | Expensive derivations are memoized only when they are genuinely expensive or preserve stable props. Lists use Set/Map lookups for repeated membership checks. Heavy code is loaded only when the surface needs it. | Memoization hides stale dependencies, inline component definitions cause avoidable rerenders, or large optional surfaces enter the main path unnecessarily. |
| Accessibility and keyboard flow | All stateful controls have accessible labels, disabled reasons, focusable action paths, and no visual-only status meaning. | Icons or color dots are the only status signal, disabled controls lack explanation, or pending decisions cannot be answered by keyboard. |
| Design-system compliance | Colors, spacing, status dots, buttons, empty states, tabs, and decision cards use Builder primitives/tokens/status language. | New raw colors, bespoke approval boxes, duplicate card shells, or page-specific status language bypass the design system. |
| File-size and component boundaries | New frontend files stay at 500 lines or fewer, and edits to historical over-500 files extract cohesive ownership instead of adding more branches. | A change grows a large page file, creates a new over-500 file, or moves code into a generic bucket with no clear owner. |
| Tests and browser proof | Static tests cover contract-sensitive UI code; browser tests cover Agent, Board, Voice, Inbox, Metrics, and Observability paths that can regress together. | Only snapshots or lint pass while the actual lifecycle path has not been exercised in the browser. |

## Current Regression Lens

Treat these as explicit review traps for this branch:

- Board phase dots must represent phase completion, active work, and blocked
  state. The Done dot is green only when the selected feature or sprint is
  shipped.
- Start Work is disabled after work has started, is in review, or is blocked.
- Agent-page questions and approvals render once, through the current
  design-system decision actions.
- While an approval or question is pending, the generic prompt composer is
  blocked and the agent does not display a conflicting active-work state.
- Feature creation must be tested from both typed Agent-page input and Voice
  delegation before the app is considered complete for optimization work.
- Large page files such as Agent and Board should shed drawers, selectors,
  pending-decision controls, lane/phase presenters, and realtime transcript
  pieces into named owner modules without changing the operator workflow.

## Required Review Questions

- What is the canonical data source for this UI state?
- Which component owns the visible action, and is there another component
  rendering the same action?
- Did this change add to a file above 500 lines, and if so which owner module
  should absorb that behavior instead?
- Can the operator explain the current state without reading logs?
- Does disabling or hiding a control preserve functionality, or does it remove
  the only path to continue?
- Does the change reduce context load for future agents, or add another branch
  they must keep in sync?

## Useful Checks

```bash
builder quality-gate dashboard-ux --json
npm run lint
npm run build
find frontend/src -type f \( -name '*.tsx' -o -name '*.ts' \) -print0 | xargs -0 wc -l | sort -nr | head -30
PYTHONPATH=src pytest tests/test_dashboard_design_system_contract.py tests/test_realtime_voice_frontend_static.py -q
```

Browser proof should follow the lifecycle validation
workflow, including end-to-end feature creation through the Agent page and
through Voice.

## Related Docs

- `docs/design-docs/design-language.md`
- `docs/design-docs/agent-page-hierarchy.md`
- `docs/quality-gate/dashboard-ux.md`
- `docs/workflows/autonomous-lifecycle-validation.md`
- `docs/rubric/sdk-backed-agent-page-agent.md`
- `docs/rubric/realtime-voice-agent-page-agent.md`
