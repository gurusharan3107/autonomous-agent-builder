# Requirements Phase

Canonical owner contract for the `requirements` phase.

## Purpose

Turn a raw product idea into a scoped product brief, initial feature direction,
and major constraints before repo execution begins.

This phase exists for forward engineering only. It is not the default lane for
adding a feature to an already-existing product.

## Entry Conditions

Enter `requirements` when:
- the product is not yet defined well enough for backlog planning
- the repo or project is effectively starting from an idea
- the agent must shape the initial feature set, stack direction, or major
  constraints before delivery work can begin

Do not enter `requirements` for an existing repo feature request. That belongs
in `planning`.

## Owner

Owner: the top-level interactive Agent-page lane.

This is not a subagent-owned phase. Operator answers belong in the visible Agent
page because the phase is fundamentally about product direction and missing
requirements.

## Auto-Allowed Tools

- `AskUserQuestion`
- bounded read-only retrieval from repo-owned `builder` and `workflow` surfaces
- read-only repo inspection when a starting codebase exists and context matters
- bounded web research when product-shaping context is missing and current
  external facts matter

Preferred order:
1. repo-owned bounded retrieval
2. read-only repo inspection if needed
3. web research only when product shaping depends on external context

## Denied Tools

- `Edit`
- `Write`
- `Bash`
- task creation, dispatch, or implementation mutation tools
- broad repo mutation or execution surfaces

## Operator Checkpoint Rules

Use `AskUserQuestion` when the next blocker is a product decision the system
cannot derive from repo context or bounded research.

Questioning rules:
- ask only high-leverage questions
- present exactly three suggested options when a structured choice is useful;
  put the recommended choice first, and rely on the Agent page's fourth inline
  custom-answer text box for operators who have something else in mind
- keep the questioning in the main Agent page
- keep answered question cards visible with the selected or custom answer so the
  operator can revisit the requirements trail
- do not ask the user for technical details the repo or research can answer
- for the first product-specific prompt in a clean-slate forward-engineering
  workspace, use model-backed judgment to decide whether to answer directly,
  ask product-tailoring questions, or capture the scope; do not make every
  first-product prompt take the same tool path
- for broad first-product prompts, gather enough user-specific requirements
  before backlog capture so the first backlog reflects the user's actual
  product, not a generic MVP for that product category
- tailor the first scope around user-visible product decisions such as target
  user, primary workflow, important data, first-screen outcome, privacy or
  persistence expectations, and product tone or interaction style
- use runtime-native structured questions when the product idea is still broad;
  ask as many product-shaping questions or follow-up rounds as the
  specification needs; ask one question when the answer changes the next
  follow-up, and batch independent questions when that reduces back-and-forth
  without overloading the user
- skip extra questions when the user has already provided enough specific
  audience, workflow, data, success criteria, and product-tone constraints to
  make the first version genuinely tailored
- do not jump from a first product idea directly to approval; approval comes
  after the requirements are tailored enough to describe the first shippable
  scope in user terms

## Output And Handoff Contract

Expected output:
- scoped product brief
- initial feature list or feature candidates
- chosen product boundaries and major constraints
- enough clarity to hand off into `planning`

Handoff:
- once the product is bounded enough to define one concrete backlog item or an
  initial feature set, move into `planning`

## Context-Efficiency Rules

- prefer bounded retrieval over broad repo walking
- prefer a few decisive operator questions over long exploratory chat
- avoid implementation detail gathering before product direction is stable
- keep external research targeted to decisions that actually shape the product

## Current Repo Mapping

Current repo mapping: forward-engineering interactive intake before normal task
status dispatch begins.
