---
title: First dashboard run findings: sidebar metrics, tool registry warning, OTEL bundling
type: correction
date: 2026-05-07
phase: testing
entity: dashboard-run
tags: [dashboard, ui-bug, otel, tool-registry, init-project-chat, validation]
status: active
---

## Correction

First end-to-end Claude Agent SDK dashboard turn (forward-engineering, target=todo-app, 2026-05-07) succeeded but surfaced three issues. Future runs should expect these unless graduated into deterministic fixes or quality-gate checks.

## Agent Retrieval Summary

Retrieve when validating a fresh init-project-chat dashboard run, reviewing the dashboard sidebar metrics widget, debugging tool-registry warnings, or auditing OTEL collector setup expectations.

Operating rules:
- The init-project-chat phase asks 4 focused AskUserQuestion cards (Interface, Persistence, Fields, Confirm Scope), then writes `.claude/progress/feature-list.json` and stops. End-to-end works.
- Sidebar Cost/Tokens/Turns widget does NOT track real run data — trust OTEL telemetry, `agent_phase_complete` log lines, and `builder metrics show --json` instead. Filing this as a UI binding bug is correct.
- A `tool_not_found_in_registry tool=AskUserQuestion` warning fires near the start of every run, then the same tool name shows up successfully in `tool_use` logs. Treat as spurious until proven otherwise — do not chase as a real failure unless question cards stop rendering.

## User-Facing Summary

The agent successfully generated a 5-feature backlog from "Build a simple todo app" through 4 Q&A cards. The agent's sidebar metrics didn't update during the run — telemetry and logs are correct, only the UI widget is off.

## Reusable Guidance

### Confirmed working
- Day-0 forward-engineering onboarding via dashboard advances all 4 pending phases (`repo_detect`, `project_seed`, `repo_scan`, `work_item_seed`) once the agent run completes.
- Per-task model routing fires correctly: `claude-haiku-4-5-20251001` for `query_source=generate_session_title` (cheap auxiliary), `claude-sonnet-4-6` with `effort=medium` for the main `init-project-chat` agent run.
- OTEL spans cleanly emit `claude_code.llm_request`, `claude_code.api_request`, `claude_code.user_prompt`, `claude_code.hook_execution_start/complete`, plus token usage metrics with proper `query_source` and `effort` attribution.
- `AskUserQuestion` tool flow: model fires the tool, dashboard renders an "AGENT QUESTION" card with select buttons + Submit answer button + free-text "OTHER" textbox. User clicks an option then Submit answer; selecting alone does NOT dispatch.
- Generated `feature-list.json` includes `metadata` (project, done, pending counts), `features[]` with `id`, `title`, `description`, `status`, numeric-string `priority`, `acceptance_criteria[]`, `dependencies[]`. Backlog page renders them sorted by priority.

### Findings

1. **Dashboard sidebar Cost/Tokens/Turns widget is stuck at zero** during and after a run that actually consumed $0.091, 1713 output tokens, 5 turns. OTEL captured the run correctly. The Agent page sidebar reads from a different source that isn't bound to live run state. Likely fix: the `CURRENT RUN` panel should subscribe to the same stream that updates `agent_phase_complete` and pull cost/tokens/turns into the displayed values. Reproduces deterministically — UI bug, not flaky.

2. **`tool_not_found_in_registry tool=AskUserQuestion` warning** fires before the agent's first turn, after `tool_registry_built tool_count=8` (the registry built from agent_def.tools is `['Read','Glob','Grep','Bash','mcp__builder__kb_search','mcp__builder__memory_search','mcp__builder__task_list','mcp__builder__task_show']` — no `AskUserQuestion`). The agent then successfully uses `AskUserQuestion` and tool_use logs show it landing. The warning is misleading because `AskUserQuestion` is a built-in Claude Agent SDK tool, not a builder-managed one — it shouldn't be expected in the registry. Either suppress the warning for known SDK tools or extend the registry to include built-ins so the warning means something actionable.

3. **OTEL collector is not bundled.** A fresh `builder init` writes `AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318` but provides no collector. Required readiness checks `telemetry_env_config` and `telemetry_content_safe` fail because the collector is unreachable, even though env shape is correct. Manual workaround: install `otelcol-contrib` (Go binary, ~150 MB) and run with a config exporting to debug + JSONL. Right fix per `telemetry-and-observability-are-core-to-the-builder-mission` memory: ship a builder-managed local collector or split required env-shape checks from optional reachability checks. Reachability already has its own optional check; the required ones should ignore it.

## When To Apply

Apply when:
- Driving any fresh forward-engineering Day-0 dashboard run (Browser Use, Chrome DevTools MCP, Computer Use, or human).
- Reviewing PRs that touch the Agent page sidebar, the tool registry build path, or the readiness telemetry checks.
- Triaging a "$0.0000 cost" report from a real user — most likely the same UI bug, not an actual zero-cost run; confirm against `builder metrics show` and OTEL.
- A `tool_not_found_in_registry` warning is reported — check whether the missing tool is `AskUserQuestion` or another Claude Agent SDK built-in before treating it as a real registry gap.

## Retrieval Queries

- dashboard sidebar cost zero
- AskUserQuestion tool not found warning
- otel collector not bundled builder
- init-project-chat 4 questions
- forward engineering day 0 dashboard run
- per task model routing haiku sonnet evidence
- feature-list.json schema
