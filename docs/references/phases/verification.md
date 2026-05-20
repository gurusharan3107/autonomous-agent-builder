# Verification Phase

Canonical owner contract for the `verification` phase.

## Purpose

Validate that implementation meets the expected quality bar through automated
checks and targeted verification specialists when needed.

## Entry Conditions

Enter `verification` when:
- implementation has produced code and local evidence
- the next useful step is to validate correctness and regressions
- the system needs explicit pass, warn, or fail evidence before integration

## Owner

Owner: quality gates plus verification specialists when needed.

Verification is not a requirement-gathering lane. It exists to test and confirm
behavior.

## Auto-Allowed Tools

- test runners
- lint and code-quality checks
- API validation surfaces
- browser verification surfaces
- other bounded verification tools that inspect results without redefining
  requirements

Sub-lanes may include:
- automated code and test verification
- API validation
- browser validation

Chrome-visible browser validation and builder CLI telemetry should be the
default proof lane for operator-visible runtime behavior. Reach for lower-level
DB or server inspection only when the builder-owned evidence is insufficient.

For sprint feature verification, the first proof must be agentic acceptance
through `feature-verifier`: inspect the implemented feature against the
approved acceptance criteria, exercise the product like a user, and fix genuine
product defects before treating the feature as ready. Only after the verifier is
satisfied should it create or update durable browser acceptance tests. On later
verification runs for the same feature, run the deterministic browser feature
tests first; if they are missing, stale, or failing, wake
`feature-verifier` to inspect whether the product or the test is wrong and then
rerun the deterministic acceptance check.

For forward-engineering generated apps, Chrome is the preferred acceptance proof
for user-visible behavior. The proof should exercise visible navigation,
forms, buttons, route changes, and reload or persistence behavior. If a
generated-app `browser-proof` script exists, it may validate a compact
Chrome proof artifact, but it must not hide a failed or missing browser
proof behind a passing unit-test-only result.

For sprint-generated work, `queued` is a valid pre-dispatch state. Verification
must prove that queued sprint tasks can actually enter the orchestrator rather
than remaining as visible but inert Board cards.

## Denied Tools

- new product-definition interviews
- broad implementation mutation outside the defined remediation loop
- unrelated exploratory research

## Operator Checkpoint Rules

Verification can produce operator-visible evidence, but it should not ask new
product-requirement questions.

If verification exposes a genuine product ambiguity, hand the decision back to
the Agent page as a bounded blocked state rather than continuing the interview
inside verification.

## Output And Handoff Contract

Expected output:
- pass, warn, or fail evidence
- remediation feedback when checks fail
- readiness decision for `integration`
- for generated apps, the exact browser URL/path tested, the visible controls
  used, and the post-navigation or post-reload state that proves acceptance
- for multi-sprint Boards, evidence must name the selected sprint; do not mix
  tasks from earlier shipped sprints into current-sprint verification.

## Context-Efficiency Rules

- run the smallest verification set that proves readiness
- keep evidence compact and structured
- use specialist verification only when the evidence class requires it, such as
  browser or API validation
- avoid reloading broad repo context that is irrelevant to the check
- prefer browser-visible behavior plus `builder logs` and related builder
  telemetry over static code inspection when validating a live runtime claim
- treat an explicit `FAIL` from build, test, lint, browser proof, or acceptance
  checks as blocking. Treat non-git metadata failures as advisory only when the
  disposable workspace is intentionally not a git repository.

## Current Repo Mapping

Current repo mapping: `quality_gates`.
