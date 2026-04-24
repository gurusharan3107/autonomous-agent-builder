---
title: Reverse-engineering validation must use an external repo
type: decision
date: 2026-04-24
phase: planning
entity: validation
tags: [reverse-engineering, testing, external-repo]
status: active
---

Use a disposable external repo clone for reverse-engineering validation. Do not use autonomous-agent-builder itself as the validation subject because self-hosting hides planning, retrieval, and implementation-boundary defects that the workflow is meant to expose.
