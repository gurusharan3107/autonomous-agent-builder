---
title: Knowledge tag filtering must align frontend and API intersection semantics
type: correction
date: 2026-04-18
phase: implementation
entity: knowledge-api
tags: [knowledge, api, tags, filtering, frontend]
status: active
---

## Constraint

Knowledge and memory tag clouds rely on the filtered result set, not the unfiltered index, to decide which cards remain visible and which tags stay selectable.

## What Went Wrong

The knowledge UI was changed to use intersection semantics and disabled non-matching tags, but the live FastAPI route in src/autonomous_agent_builder/api/routes/knowledge.py still returned union-style document filtering and marked every tag as available. The browser looked partially correct while the API kept feeding it stale tag counts and selectable tags.

## What To Do Instead

When changing tag-cloud behavior, update the frontend and the backing API in the same pass. /api/kb/ must require all selected tags, and /api/kb/tags must compute counts from the filtered intersection while only keeping tags selectable if adding them still leaves at least one matching document. Verify the browser against the live endpoint after redeploy.
