---
title: Telemetry and observability are core to the builder mission
type: pattern
date: 2026-05-07
phase: implementation
entity: observability
tags: [telemetry, observability, otel, mission-critical, readiness]
status: active
---

## Pattern

Telemetry and observability are core to the autonomous builder mission. They are not optional infra — they are the primary signal source for builder self-tuning, optimization, and the "builder just knows what to do when" promise in MISSION.md / GOAL.md.

## Agent Retrieval Summary

Retrieve this when an agent is about to disable telemetry, defer OTEL setup, or treat collector reachability as a nice-to-have. Operating rule: never disable telemetry as a workaround for a readiness bug or env friction. Fix the root cause (readiness logic, collector availability, endpoint config) instead. The optimization phase, recommendations, metrics, and observability surfaces all read from this telemetry — turning it off blinds the system.

## User-Facing Summary

Telemetry powers the builder's ability to learn what each specialist agent does well or poorly and tune itself. Disabling it makes the builder dumber over time.

## Reusable Guidance

- Default Claude SDK telemetry env in target `.env`: `AAB_CLAUDE_OTEL_ENABLED=1`, `AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318`, content-safety flags off (no raw prompts/tools/bodies by default).
- A reachable OTEL collector at the configured endpoint is part of the Day-0 expectation. Run a local OpenTelemetry Collector (Docker `otel/opentelemetry-collector-contrib` works) listening on 4318/HTTP for development, or wire to a hosted backend (Honeycomb, Grafana Cloud, etc.) for production.
- Optimization-agent (`agents/definitions.py`) and the metrics/observability/recommendations surfaces all consume normalized OTEL spans. Removing telemetry breaks the "builder owns its own optimization" loop the GOAL.md acceptance test requires.
- Readiness checks split telemetry into env-config (required), content-safety (required), and collector-reachable (optional). If a required check fails because of reachability, it is a readiness-rule bug — fix the rule or stand up the collector, never the env.
- Do not turn `AAB_CLAUDE_OTEL_ENABLED` off as a quick path. Same for the Codex lane: when Codex is the active runtime, its telemetry must be enabled and the Claude lane's telemetry disabled (mirror).
- For agents working on the builder: when proposing a workaround, prefer (a) running the collector, (b) fixing the readiness rule, (c) wiring to a remote backend — in that order. Skipping telemetry is not a valid workaround.

## When To Apply

Apply when:
- Auditing readiness failures that touch telemetry.
- Reviewing env templates in `services/runtime_guidance.py`.
- Resolving optimization-agent gaps or empty observability dashboards.
- Onboarding a new generated app — verify a collector is reachable before claiming Day-0 ready.
- A user proposes disabling OTEL "just to make it work."

## Retrieval Queries

- telemetry observability core mission
- otel collector reachable readiness
- disable AAB_CLAUDE_OTEL_ENABLED workaround
- builder optimization signal source
- claude sdk telemetry endpoint
