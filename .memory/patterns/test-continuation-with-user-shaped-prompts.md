---
title: Test continuation with user-shaped prompts
type: pattern
date: 2026-04-29
phase: testing
entity: forward-engineering-autonomous-lifecycle-validation
tags: [forward-engineering, agent-page, dispatch, approval, context-efficiency]
status: graduated
preserve_as_precedent: true
graduated_into: docs/workflows/forward-engineering-autonomous-lifecycle-validation.md
---

When validating forward-engineering from the Agent page, use realistic user prompts such as 'Continue building my app.' A passing run should make the builder inspect board/backlog state, choose the deterministic next task by status and priority, auto-allow safe read-only inspection and builder-owned dispatch in that continuation lane, and surface only real blockers such as approval gates, missing prerequisites, or provider limits. If the run asks the user to choose from a feature menu or approve internal MCP tool names, fix the product orchestration surface rather than writing a more internal prompt.
