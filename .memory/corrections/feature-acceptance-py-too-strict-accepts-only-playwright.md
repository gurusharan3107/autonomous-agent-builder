---
title: feature_acceptance.py too strict — accepts only Playwright
type: correction
date: 2026-05-08
phase: verification
entity: feature-acceptance-script
tags: [feature-verifier, playwright, jsdom, verify-phase, deterministic-script]
status: active
---

## Correction

The deterministic ``feature_acceptance.py`` script only accepted Playwright as proof-of-acceptance, returning ``missing_playwright`` for any project that used a different test runner. This blocked Sprint 1 verify tasks for HTML/CSS/JS apps where the feature-verifier agent (correctly) created JSDOM-based tests.

## Agent Retrieval Summary

Retrieve when triaging ``feature_acceptance_failed: missing_playwright`` blockers, when working on the verify phase for vanilla-HTML/JS workspaces, or when adjusting acceptable test-runner commands.

Operating rule: Playwright is preferred for UI-heavy / multi-page apps, but a passing JSDOM/jest/mocha/custom-node test in a single-file vanilla workspace is still valid acceptance proof for the agreed scope. The deterministic verifier should accept any test runner the feature-verifier agent legitimately set up.

## User-Facing Summary

Sprint 1 task #3 (Verify) blocked because the script only accepted Playwright. The agent had built JSDOM-based tests and a ``run-tests.js`` runner — both reasonable for a single-file todo app — but the deterministic check rejected them. Patch P10 adds fallback paths so generic test scripts and ``run-tests.js`` are accepted when no Playwright is configured.

## Reusable Guidance

- ``src/autonomous_agent_builder/embedded/scripts/feature_acceptance.py:_select_playwright_command`` now falls back to:
  1. ``_FALLBACK_SCRIPT_PRIORITY``: ``test:acceptance``, ``test:feature``, ``test:integration``, ``test:smoke``, ``test:run``, ``test``
  2. Direct ``node run-tests.js`` if the file exists at workspace root
- The status code returned when no command is found changed from ``missing_playwright`` to ``missing_test_command`` (more honest about the scope of the check). The error message now lists what was tried (Playwright + generic + run-tests.js).
- The fallback is *additive* — Playwright is still preferred when present; this just removes the hard-block when it isn't.
- Pre-existing block in target workspace ``/tmp/aab-workspaces/33f0a54e-d506-...`` (Sprint 1, task 33F0A54E) was the trigger for this fix. Verified with isolated unit test that the fallback finds ``npm test`` and would have run the JSDOM suite.
- The orchestrator's two-step ``_record_feature_acceptance_tests`` flow still runs the model-backed feature-verifier agent first to create tests — only the deterministic re-check after the agent now has more permissive command discovery.

## When To Apply

Apply when:
- A target workspace blocks at the verify phase with ``missing_playwright`` or ``missing_test_command``.
- A new test runner is added to the supported set (e.g. vitest, web-test-runner).
- The feature-verifier agent prompt is changed in a way that affects what test files / commands it produces.
- A workspace is HTML-only / no-build-step and Playwright would be overkill.

## Retrieval Queries

- missing_playwright feature_acceptance
- feature_acceptance_failed verify task blocked
- jsdom test runner accepted
- run-tests.js fallback acceptance
- vanilla html acceptance test runner
- Playwright not required deterministic verify
