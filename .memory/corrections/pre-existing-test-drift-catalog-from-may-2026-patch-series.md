---
title: Pre-existing test drift catalog from May 2026 patch series
type: correction
date: 2026-05-07
phase: testing
entity: test-suite
tags: [tests, conftest, legacy-ids, drift, verification]
status: active
---

## Correction

During the May 2026 plan-mode patch series, several pre-existing test failures surfaced when the conftest's legacy ``RUNTIME_MODEL=anthropic/claude-sonnet-4-5`` was canonicalized to ``claude-sonnet-4-6``. Cataloguing the patterns so future maintainers don't waste time re-diagnosing the same drift.

## Agent Retrieval Summary

Retrieve when modifying ``tests/conftest.py``, the chat-history API shape, or any code that emits the ``"I want to do sprint planning."`` / ``"I can plan and start the next sprint for this now"`` operator-handoff phrasing.

## User-Facing Summary

The test suite had three classes of stale expectations: hardcoded legacy model IDs, stale agent-message text, and lambda mocks that don't accept the kwargs the real factory now passes. Patches in this series corrected the model IDs and the mocks; some unrelated KeyError / CLI tests remain pre-existing.

## Reusable Guidance

- ``tests/conftest.py:23`` autouse-monkeypatches ``RUNTIME_MODEL``. Updating that value (e.g. canonicalizing legacy IDs) cascades into every test that asserts ``payload["model"] == ...``. Follow up with grep + bulk update of the literal expected value.
- The chat agent's natural-language handoff phrase is ``"I can plan and start the next sprint for this now, or keep it in the backlog."`` (in ``embedded/server/routes/agent.py``). Several older tests asserted the long-removed phrase ``"I want to do sprint planning"`` — those need updating to match the live string.
- ``create_runtime`` accepts ``**kwargs`` (sdk, model, etc.). Test mocks must be ``lambda **_kwargs: FakeRuntime()``, not ``lambda: FakeRuntime()``. The bare-arg form was a subtle pre-existing test bug surfaced when any new code path called ``create_runtime`` with kwargs.
- Pre-existing failures NOT addressed (out of scope for the patch series): ``test_chat_post_starts_background_run_and_persists_timeline`` (KeyError ``sdk_session_id`` — API response shape drift), ``test_continue_building_records_terminal_dispatch_status`` (KeyError ``dispatch``), ``test_embedded_kb_routes_parse_multiline_frontmatter_tags`` (ordering), ``test_builder_verify_execute_runs_command_proof`` and ``test_server_start_uses_repo_local_port_when_flag_omitted`` (CLI exit-code drift), ``test_parse_reset_hint_absolute_time_with_timezone`` (datetime/timezone parsing).
- Real bug fixed in ``services/runtime_guidance.py:_discover_commands``: the npm/pnpm scripts branch entered for non-Node workspaces because ``_read_json`` returns ``{}`` for missing ``package.json``, and ``isinstance({}, dict)`` was the only guard. This synthesized ``Setup: \`unknown install\``` for Python projects. Now gated on ``package_json_path.exists()``.

## When To Apply

Apply when:
- A PR touches the chat-history API response shape, ``_runtime_metadata_for_agent``, or runtime config resolution.
- A model-ID canonicalization sweep is undertaken (legacy → 4.6/4.7).
- New ``create_runtime`` callers are added.
- Tests fail with assertions like ``"haiku" == "anthropic/claude-sonnet-4-6"`` — that's the conftest's RUNTIME_MODEL leaking into a test that didn't expect it.

## Retrieval Queries

- runtime_model conftest legacy
- haiku assertion test
- create_runtime kwargs lambda
- I want to do sprint planning legacy text
- npm scripts branch unknown install python
- discover_commands package_json missing
