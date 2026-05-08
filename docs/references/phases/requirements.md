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
- prefer concise options with the recommended choice first
- keep the questioning in the main Agent page
- do not ask the user for technical details the repo or research can answer

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

