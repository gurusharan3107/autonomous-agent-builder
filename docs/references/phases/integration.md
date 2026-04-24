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

## Context-Efficiency Rules

- carry forward verification evidence instead of reconstructing it
- keep PR and review context concise and evidence-backed
- use explicit checkpoint state instead of narrative chat to represent human
  review

## Current Repo Mapping

Current repo mapping: `pr_creation`, `review_pending`, and `build_verify`.
