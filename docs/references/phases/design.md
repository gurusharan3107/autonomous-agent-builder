# Design Phase

Canonical owner contract for the `design` phase.

## Purpose

Turn a bounded backlog feature or task into implementation-ready technical
constraints, structure, and acceptance framing.

## Entry Conditions

Enter `design` when:
- planning has already produced a bounded backlog feature
- the next useful step is technical design rather than more product discovery
- implementation would otherwise be guessing about interfaces, architecture, or
  change boundaries

## Owner

Owner: the planner/designer runtime phase.

This is a background execution phase, not a chat-first phase. It may use
specialist runtime agents, but operator questioning still belongs to the
top-level Agent page.

## Auto-Allowed Tools

- read-only repo inspection
- bounded builder knowledge and memory reads
- bounded architecture and contract retrieval

These tools are allowed because design must ground itself in current repo
structure and prior decisions.

Design may use the main repo context for this read-only work. It does not need a
task worktree by default unless a non-standard flow mutates repo state during
design.

## Denied Tools

- implementation mutations by default
- direct code-writing or file mutation unless design output explicitly requires a
  separate implementation handoff
- direct operator questioning from hidden runtime lanes

## Operator Checkpoint Rules

If design cannot continue without an operator decision:
- do not improvise freeform chat inside the background runtime
- emit a bounded blocked handoff back to the Agent page
- include the exact missing decision and compact options where possible

The design phase should not own `AskUserQuestion` directly from subagents or
hidden specialist lanes.

## Output And Handoff Contract

Expected output:
- implementation-ready design constraints
- architecture and change boundaries
- task-ready acceptance framing
- clear handoff into `implementation`
- one bounded task packet that can enter a pre-provisioned workspace at the
  `design -> implementation` boundary

## Context-Efficiency Rules

- consume planning outputs first
- read only the code and docs necessary to define implementation boundaries
- prefer compact design artifacts over long narrative explanations
- avoid reopening requirement discovery unless a real operator decision blocks
  progress

## Current Repo Mapping

Current repo mapping: `design` plus the `design_review` checkpoint before
implementation continues.
