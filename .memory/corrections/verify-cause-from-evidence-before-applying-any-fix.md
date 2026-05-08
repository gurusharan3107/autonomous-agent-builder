---
title: Verify cause from evidence before applying any fix
type: correction
date: 2026-05-08
phase: implementation
entity: fix-discipline
tags: [fix-discipline, debugging, tool-quirk]
status: active
---

## Correction

Before writing a fix for any reported symptom, prove the actual cause from observable evidence (network log, beforeunload trace, server log, repro in a clean environment). A theory that fits the symptom is not proof. Tooling artifacts have masqueraded as app bugs in this repo more than once — verify the artifact first.

## Agent Retrieval Summary

Retrieve before changing code in response to a reported UI/runtime symptom. Use this to gate the move from "I have a theory" to "I have evidence". When the symptom only appears under a specific tool (Chrome DevTools, MCP, automation), check whether the tool itself is the source before blaming the app.

## User-Facing Summary

This repo treats "matches the symptom" as a hypothesis, not a diagnosis. Code changes wait until the cause is reproduced from evidence — otherwise we patch phantoms.

## Reusable Guidance

- For any reported symptom, capture concrete evidence: network tab patterns, server logs, console errors, `beforeunload` traces. Without evidence, do not patch.
- Reproduce in a clean environment (different browser, no DevTools attached, headless) to confirm the symptom is real for end users — not a tooling artifact.
- "It looks like X" is not proof of X. Prefer no fix over a speculative fix.
- Examples seen here: a "scroll reset" theorized as a React re-render bug turned out to be Chrome DevTools MCP reloading the page periodically; a `useLayoutEffect` patch shipped against the wrong cause and had to be reverted.

## When To Apply

When a user reports a symptom, when a debug session shows unexpected behavior, when the temptation arises to add a defensive guard "to handle the case". Apply before opening the editor.

## Retrieval Queries

- verify cause before fix
- evidence before patch
- tooling artifact masquerading as bug
- reproduce in clean environment
- symptom vs root cause
