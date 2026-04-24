---
title: Use builder CLI telemetry before reopening broad code context
type: pattern
date: 2026-04-24
phase: testing
entity: builder-cli-telemetry
tags: [builder-logs, claude-agent-sdk, agent-debugging, context-efficiency]
status: active
---

For Agent-page or autonomous-run debugging, start with builder CLI surfaces as the agent-efficient evidence path: builder --json doctor, builder map, builder logs --error, builder logs --info --compact --json, and session-scoped builder logs --session <id> --type <event> --json. The working directory matters because builder logs reads the repo-local .agent-builder/agent_builder.db; for external target runs such as /private/tmp/aab-reverse-flasky-..., run builder logs from the target workspace, not only from the source repo. If a needed SDK telemetry field is not available through builder CLI, report the gap explicitly instead of silently scraping internals.
