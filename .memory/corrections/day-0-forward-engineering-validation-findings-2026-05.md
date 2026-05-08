---
title: Day-0 forward-engineering validation findings (2026-05)
type: correction
date: 2026-05-07
phase: testing
entity: day0-validation
tags: [validation, readiness, otel, model-ids, aiosqlite]
status: active
---

## Correction

During clean-slate forward-engineering validation in 2026-05 (target workspace `/home/gurusharangupta/Workspace/todo-app`), the following builder gaps were observed and partially fixed. Future validators should expect these recurrences if not graduated.

## Agent Retrieval Summary

Retrieve when running a fresh `builder init` on a clean target, validating Day-0 readiness, or auditing telemetry/runtime defaults. Use this list to skip rediscovery.

## User-Facing Summary

A clean-slate Day-0 validation surfaced five findings: a missing Python dep (`aiosqlite`), onboarding phases not auto-advancing from CLI init, four legacy Claude model IDs across runtime defaults (now fixed), the OTEL collector being required but not bundled, and confirmation that bare model aliases work correctly with the Claude Agent SDK. Future fresh-install runs should expect these unless graduated to deterministic fixes.

## Reusable Guidance

### Findings (active as of 2026-05-07)

1. **`aiosqlite` was missing from the pipx-installed builder venv.** `builder init` reported `ok: true` but with `error: "Database initialization failed: No module named 'aiosqlite'"`. Bug: the JSON envelope's `ok` field doesn't reflect the inner error. Fix applied: `pipx inject autonomous-agent-builder aiosqlite`. Build/release should add `aiosqlite` to project dependencies so fresh installs succeed without manual injection. Bug to fix: `services/init_impl.py` (or wherever the init JSON is assembled) returns `ok=true` even when an error is set — these should be aligned.

2. **`builder init` does not advance Day-0 onboarding phases.** After init, `repo_detect`, `project_seed`, `repo_scan`, `work_item_seed` stay `pending` in `.agent-builder/onboarding-state.json`. Init's CLI hint says "Begin first-run onboarding from the UI" so this is by design — but readiness assess returns `blocked` until the dashboard interview runs. Document this clearly in the init output (the current "Next steps" already mentions it but the `--no-input` headless flow has no way to advance phases without `builder start`). Consider adding `builder onboarding run --no-input` to support headless progression.

3. **Legacy model IDs in 4 source paths (FIXED 2026-05-07).** Updated:
   - `src/autonomous_agent_builder/runtime/factory.py:18` claude default → `anthropic/claude-sonnet-4-6`
   - `src/autonomous_agent_builder/services/runtime_guidance.py:335` written-to-target `.env` → `anthropic/claude-sonnet-4-6`
   - `src/autonomous_agent_builder/embedded/server/routes/knowledge_extraction.py:32` route default → `claude-haiku-4-5` (KB extraction is classification work; matches `kb_extraction_model` in config.py)
   - `src/autonomous_agent_builder/config.py:113` runtime model field default → `anthropic/claude-sonnet-4-6` (and the comment on line 111).
   - Add a CI lint that flags any new occurrence of retired/deprecated Claude IDs (`claude-sonnet-4-5`, date-suffixed IDs like `claude-sonnet-4-20250514`, `claude-3-7-*`, `claude-3-5-*`, `claude-opus-4-1`, `claude-opus-4-5` outside legacy-pinning contexts). Config canonicalizes on `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`.

4. **OTEL collector required for Day-0 readiness; no setup help shipped.** `telemetry_collector_reachable` is optional but `telemetry_env_config` and `telemetry_content_safe` are required and currently roll up the `configured_unreachable` collector status into a fail. Workaround used: install `otelcol-contrib` v0.151.0 as a static binary at `~/.local/opt/otelcol/`, run with a config that exports to debug + JSONL file. Real fix: ship a builder-managed local collector (sidecar binary, downloaded on first init), or split the required env-config check from collector reachability so env-shape passes regardless of reachability. **Do not turn off telemetry — it powers the optimization phase.** See memory `telemetry-and-observability-are-core-to-the-builder-mission`.

5. **Bare model aliases pass through SDK correctly.** Verified at `claude_agent_sdk/types.py:89` — `# Model alias ("sonnet", "opus", "haiku", "inherit") or a full model ID.` Builder's use of bare `"opus"`/`"sonnet"`/`"haiku"` in `agents/definitions.py` and `agents/execution_policy.py` is correct; the alias is forwarded to `claude` CLI which resolves to current default. No fix required.

## When To Apply

Apply when:
- Running validation against a fresh builder install.
- Reviewing PRs that touch model IDs, runtime defaults, telemetry env templates, or readiness rules.
- Triaging an "init succeeded but readiness blocked" report from a user.

## Retrieval Queries

- aiosqlite missing builder install
- onboarding phases pending after init
- legacy model id audit
- otel collector setup builder
- claude agent sdk alias support
- builder validation findings 2026-05
