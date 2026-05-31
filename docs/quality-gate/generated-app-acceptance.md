---
title: "Generated app acceptance gate"
surface: "generated-app-acceptance"
summary: "Validate generated-app features through the same visible browser path a real user would use."
commands:
  - "builder quality-gate generated-app-acceptance --json"
  - "builder logs analyze --session <id-or-prefix> --json"
expectations:
  - "the generated app runs from the disposable target repo, not host builder state"
  - "the feature is reachable through visible navigation without typing a guessed route"
  - "the user can operate the feature through visible forms, buttons, links, or controls"
  - "state persists after navigation or reload when persistence is expected"
  - "Chrome proof records the visible URL, path, controls, and post-reload state; an app-local script may validate that artifact"
  - "browser evidence is attached to the responsible task or batch"
  - "quality gates use the generated app's own scripts and do not report unsupported language for Node/React/Vite apps"
related_docs:
  - "docs/workflows/autonomous-lifecycle-validation.md"
---

# Generated App Acceptance Gate

## Purpose

Use this gate before accepting a forward-engineering feature in a generated app.
The check proves the shipped behavior through the generated app itself, not by
inspecting host builder state or manually entering hidden routes. Drive the
proof with the Chrome plugin against the generated app's localhost URL.

## When To Load

Load this gate when:

- changing forward-engineering verification behavior
- accepting task or batch work that modifies generated-app UX
- diagnosing whether a feature was actually shipped or only implemented behind
  an undiscoverable route
- adding Chrome automation for generated-app validation

## Pass Signals

- the app starts from the disposable generated repo
- Chrome reaches the feature through visible navigation
- primary user actions work through visible controls
- expected state survives navigation or reload
- a compact Chrome proof artifact is available when the browser proof lane
  uses Chrome plugin instead of local Chrome headless automation
- screenshots, console/network findings, or run notes are attached to the task
  or dependency batch that introduced the feature

## Fail Signals

- validation depends on typing a route the user could not discover
- the app being tested is the host builder instead of the generated repo
- the feature only exists in code or tests, with no visible user path
- browser evidence is detached from the task or batch that caused the change
- a failing or crashing local headless browser script is treated as equivalent
  to a passing Chrome proof
- the sprint is marked shipped without generated-app Chrome acceptance
  evidence for the approved feature
- generated app verification stops at `UNSUPPORTED_LANGUAGE` instead of running
  the target app's available lint, build, or test scripts
