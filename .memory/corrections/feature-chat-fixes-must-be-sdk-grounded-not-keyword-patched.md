---
title: Feature chat fixes must be SDK-grounded, not keyword patched
type: correction
date: 2026-04-24
phase: design
entity: embedded-agent-chat
tags: [claude-agent-sdk, feature-spec, routing, telemetry]
status: active
---

When natural Agent-page feature requests misroute or stall, do not solve it by adding more common words to the intent matcher alone. First inspect the live SDK behavior through builder-owned telemetry, then choose the smallest runtime surface that preserves the Claude Agent SDK contract: the parent chat agent should gather the minimum missing intent, preserve session continuity with the SDK session id, and emit a durable builder state transition only after the user's clarification resolves scope. Keyword routing is only an entry filter; convergence should be owned by prompt contract, tool context, session continuation, and ResultMessage/run telemetry evidence.
