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

Browser validation and builder CLI telemetry should be the default proof lane
for operator-visible runtime behavior. Reach for lower-level DB or server
inspection only when the builder-owned evidence is insufficient.

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

## Context-Efficiency Rules

- run the smallest verification set that proves readiness
- keep evidence compact and structured
- use specialist verification only when the evidence class requires it, such as
  browser or API validation
- avoid reloading broad repo context that is irrelevant to the check
- prefer browser-visible behavior plus `builder logs` and related builder
  telemetry over static code inspection when validating a live runtime claim

## Current Repo Mapping

Current repo mapping: `quality_gates`.
