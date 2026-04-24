# Implementation Phase

Canonical owner contract for the `implementation` phase.

## Purpose

Produce the code and local execution evidence required to realize a bounded
design or task.

## Entry Conditions

Enter `implementation` when:
- planning and design have already bounded the work
- the next useful step is to modify code in the task workspace
- a persisted task workspace already exists, created by the orchestrator at the
  `design -> implementation` handoff
- the agent can proceed without reopening product-definition questions

## Owner

Owner: the implementation agent.

This phase is execution-first. It should consume upstream context and produce
code plus evidence.

The implementation agent does not own workspace provisioning. It operates inside
the workspace path and branch chosen for the task.

## Auto-Allowed Tools

- `Read`
- `Edit`
- `Write`
- `TodoWrite` for bounded progress tracking inside the active implementation task
- bounded workspace execution such as test and lint tools
- targeted repo-local knowledge and memory reads needed for the task

These tools are auto-allowed because the phase is explicitly responsible for
changing code and producing local verification evidence.

## Denied Tools

- unrelated repo-wide exploration
- direct operator questioning
- non-essential web research
- reopening broad planning or requirements work

## Operator Checkpoint Rules

Implementation should not ask new product-requirement questions directly.

If blocked on a missing operator decision:
- stop implementation cleanly
- surface a bounded blocked handoff back to the Agent page
- do not continue by guessing a product decision

## Output And Handoff Contract

Expected output:
- code changes in the workspace
- local evidence such as tests, lint, or other task-level verification
- bounded progress updates that reflect the active implementation checklist when
  the task is multi-step
- a clean handoff into `verification`

Implementation must not start in the main repo checkout when a task workspace is
expected. Missing workspace provisioning is an orchestrator or workspace-owner
failure, not a reason for the implementation agent to improvise filesystem
state.

## Progress-Tracking Contract

Implementation should use `TodoWrite` to keep multi-step coding work organized
inside the active task session.

Use todo tracking when the implementation task benefits from an explicit working
checklist, such as:
- touching multiple files or subsystems
- applying code changes plus local verification
- sequencing a bounded set of implementation steps that the operator may want
  to monitor from the Agent page

Todo tracking in this phase is:
- session-scoped
- lightweight
- advisory progress state for the current implementation run

Todo tracking in this phase is not:
- the durable backlog owner
- a replacement for task, approval, or board state
- a substitute for verification evidence

Implementation should treat todos as the organized execution layer:
- create a small bounded checklist when the task is clearly multi-step
- keep one item `in_progress` at a time when practical
- complete items as real work finishes instead of leaving stale progress state
- avoid over-fragmenting simple work into excessive todo items

If the task is trivial or effectively one-step, implementation does not need to
force todo usage just to satisfy the contract.

## Context-Efficiency Rules

- consume design and planning outputs instead of rediscovering them
- retrieve only the repo context necessary to implement the task
- keep execution scoped to the workspace and the active task boundary
- prefer deterministic local evidence over conversational status text
- use reduced todo progress for organized execution instead of verbose
  conversational self-narration when the work is multi-step
- rely on the stable workspace `cwd` for session continuity instead of trying to
  reconstruct file state from transcript history

## Current Repo Mapping

Current repo mapping: `implementation`.
