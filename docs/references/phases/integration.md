# Integration Phase

Canonical owner contract for the `integration` phase.

## Purpose

Turn a verified change into a reviewable integration artifact and confirm the
post-review or post-merge state.

## Entry Conditions

Enter `integration` when:
- verification has produced sufficient readiness evidence
- the next useful step is PR creation, review handling, or post-merge/build
  verification

## Owner

Owner: the PR/review/build-verification flow.

This phase owns integration readiness and finalization, not product-definition
interviewing.

## Auto-Allowed Tools

- PR creation surfaces
- merge-readiness evidence gathering
- post-merge verification tools
- bounded integration validation that confirms the change is ready or complete

## Denied Tools

- requirement interviews
- broad replanning
- unrelated implementation work outside a defined remediation feedback loop

## Operator Checkpoint Rules

Approval and review checkpoints are explicit here, but they are not requirement
interviews.

If human review or approval is needed:
- present it as a review or approval checkpoint
- keep the decision scoped to integration readiness or requested changes
- do not repurpose the checkpoint into feature-clarification chat

## Output And Handoff Contract

Expected output:
- reviewable change artifact
- explicit review or approval state
- final integrated verification state after review or merge
- for forward-engineering sprints, shipped-state mutation: all generated sprint
  tasks `done`, sprint phase `shipped`, verification status `passed`, and the
  approved backlog feature `done`

## Context-Efficiency Rules

- carry forward verification evidence instead of reconstructing it
- keep PR and review context concise and evidence-backed
- use explicit checkpoint state instead of narrative chat to represent human
  review
- do not rerun requirement or sprint planning because a post-verifier
  finalization step failed. Recovery should restart from `build_verify` when a
  completed verifier run already exists.
- in non-git disposable directory workspaces, keep `git status` failures as
  advisory metadata evidence unless the workflow explicitly required a git-backed
  integration artifact.

## Current Repo Mapping

Current repo mapping: `pr_creation`, `review_pending`, and `build_verify`.

`build_verify` is also the final sprint-shipping boundary for the current
forward-engineering flow. It must parse verifier output honestly: real failed
checks keep the task failed, advisory non-git metadata does not, and successful
final verification advances the visible Board strip to `Shipped`.

In multi-sprint runs, finalization applies only to the selected/current sprint:
its generated task IDs become `done`, its approved backlog items become `done`,
and older shipped sprint tasks stay available through the Board sprint selector
rather than appearing in the current sprint lanes.
