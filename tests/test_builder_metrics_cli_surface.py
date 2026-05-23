"""Tests for builder metrics and local fallback CLI surfaces."""

from __future__ import annotations

import json
import sqlite3

from typer.testing import CliRunner

from autonomous_agent_builder.cli import local_fallback as local_fallback_module
from autonomous_agent_builder.cli.client import BuilderConnectivityError
from autonomous_agent_builder.cli.commands import metrics as metrics_module
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_metrics_show_json_includes_summary_and_next_step(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(metrics_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        metrics_module,
        "request_json",
        lambda *args, **kwargs: {
            "total_cost": 1.25,
            "total_tokens": 500,
            "total_runs": 4,
            "gate_pass_rate": 0.75,
            "runs": [
                {
                    "id": "run-planner-1",
                    "agent_name": "planner",
                    "cost_usd": 0.25,
                    "tokens_input": 100,
                    "tokens_output": 50,
                    "duration_ms": 123,
                    "status": "completed",
                    "diff_summary": {
                        "files": [
                            {"path": "src/app.js", "status": "M"},
                            {"path": "node_modules/playwright-core/index.js", "status": "A"},
                        ],
                        "hunks": [
                            {"path": "dist/assets/index.js", "added_lines": 200},
                            {"path": "src/app.js", "added_lines": 2},
                        ],
                    },
                    "observability": {
                        "command": "builder script run build_verify --json",
                        "data": {
                            "command": [
                                "/tmp/aab-workspaces/demo/node_modules/.bin/playwright",
                                "test",
                            ],
                            "checks": [
                                {
                                    "command": [
                                        "/tmp/aab-workspaces/demo/node_modules/.bin/playwright",
                                        "test",
                                    ],
                                    "status": "passed",
                                    "preview": "large package-lock preview with node_modules",
                                    "stdout": "verbose raw output",
                                }
                            ],
                            "raw": "raw forensic payload",
                        },
                    },
                },
                {
                    "agent_name": "verifier",
                    "cost_usd": 0.10,
                    "tokens_input": 20,
                    "tokens_output": 10,
                    "duration_ms": 50,
                    "status": "completed",
                },
            ],
            "voice_ledger": {
                "tool_outputs": [
                    {
                        "event_id": "evt-voice-failed",
                        "tool_name": "delegate_to_builder_agent",
                        "tool_call_id": "call_123",
                        "ok": False,
                        "error": "message is required",
                    }
                ],
                "usage": [{"voice_call_id": "rtc_123", "total_tokens": 100}],
                "totals": {
                    "responses": 1,
                    "total_tokens": 100,
                    "input_text_tokens": 20,
                    "input_audio_tokens": 30,
                    "output_text_tokens": 10,
                    "output_audio_tokens": 40,
                    "cached_tokens": 5,
                    "estimated_cost_usd": None,
                    "cost_source": "usage_without_realtime_rate_card",
                    "delegated_messages": 1,
                    "voice_digests": 2,
                    "tool_calls": 1,
                    "tool_outputs": 1,
                    "failed_tool_outputs": 1,
                    "wait_events": 0,
                    "prepared_actions": 0,
                    "confirmed_actions": 0,
                    "delegation_ratio": 1.0,
                },
            },
        },
    )

    result = runner.invoke(app, ["metrics", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["total_cost"] == 1.25
    assert payload["summary"]["total_runs"] == 4
    assert "runs" not in payload
    assert payload["run_count"] == 2
    assert payload["recent_runs"][0]["agent_name"] == "planner"
    assert payload["recent_runs"][0]["analysis_id"] == "run-planner-1"
    assert payload["recent_runs"][0]["analysis_command"] == (
        "builder logs analyze --session run-planner-1 --json"
    )
    assert payload["voice_ledger"]["totals"]["failed_tool_outputs"] == 1
    assert payload["voice_ledger"]["recent_failures"] == [
        {
            "tool_name": "delegate_to_builder_agent",
            "tool_call_id": "call_123",
            "error": "message is required",
            "event_id": "evt-voice-failed",
        }
    ]
    assert "tool_outputs" not in payload["voice_ledger"]
    assert "usage" not in payload["voice_ledger"]
    assert payload["raw_evidence"]["command"] == "builder metrics show --json --full --limit 10"
    assert payload["next_step"] == "builder logs analyze --session run-planner-1 --json"
    assert payload["actionable_next"] == "builder logs analyze --session run-planner-1 --json"
    assert payload["progressive_disclosure"][0]["command"] == (
        "builder logs analyze --session run-planner-1 --json"
    )

    full_result = runner.invoke(app, ["metrics", "show", "--json", "--full"])
    assert full_result.exit_code == 0
    full_payload = json.loads(full_result.stdout)
    assert "runs" in full_payload
    assert full_payload["run_count"] == 2
    assert full_payload["runs_returned"] == 2
    assert full_payload["runs"][0]["agent_name"] == "planner"
    assert "tool_outputs" not in full_payload["voice_ledger"]
    assert "usage" not in full_payload["voice_ledger"]
    diff_summary = full_payload["runs"][0]["diff_summary"]
    assert diff_summary["bounded"] is True
    assert diff_summary["omitted_generated_paths"] == 2
    assert diff_summary["files"] == [{"path": "src/app.js", "status": "M"}]
    assert diff_summary["hunks"] == [{"path": "src/app.js", "added_lines": 2}]
    observability = full_payload["runs"][0]["observability"]
    assert observability["command"] == "builder script run build_verify --json"
    assert observability["data"]["command"] == ["test"]
    assert observability["data"]["checks"] == [{"command": ["test"], "status": "passed"}]
    serialized_observability = json.dumps(observability)
    assert "node_modules" not in serialized_observability
    assert "preview" not in serialized_observability
    assert "stdout" not in serialized_observability
    assert "raw forensic payload" not in serialized_observability

    limited_result = runner.invoke(app, ["metrics", "show", "--json", "--full", "--limit", "1"])
    assert limited_result.exit_code == 0
    limited_payload = json.loads(limited_result.stdout)
    assert limited_payload["run_count"] == 2
    assert limited_payload["runs_returned"] == 1
    assert limited_payload["truncated"] is True
    assert limited_payload["next_step"] == "builder metrics show --json --full --limit 2"


def test_metrics_show_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(metrics_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        metrics_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(BuilderConnectivityError("http://127.0.0.1:9876")),
    )
    monkeypatch.setattr(
        metrics_module,
        "load_local_metrics",
        lambda: {
            "total_cost": 0.5,
            "total_tokens": 200,
            "total_runs": 2,
            "gate_pass_rate": 50.0,
            "runs": [],
            "summary": {"total_cost": 0.5, "total_tokens": 200, "total_runs": 2, "gate_pass_rate": 50.0},
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder backlog run summary <query> --json",
        },
    )

    result = runner.invoke(app, ["metrics", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["fallback_reason"] == "connectivity_error"
    assert payload["fallback_base_url"] == "http://127.0.0.1:9876"
    assert payload["summary"]["total_runs"] == 2


def test_metrics_compact_run_points_agent_chat_to_session_task_id():
    row = metrics_module._compact_run(
        {
            "id": "event-1",
            "task_id": "chat-session-1",
            "agent_name": "agent-chat",
            "tokens_input": 0,
            "tokens_output": 0,
        }
    )

    assert row["analysis_id"] == "chat-session-1"
    assert row["analysis_command"] == (
        "builder logs analyze --session chat-session-1 --json"
    )


def test_load_local_agent_history_filters_runtime_transport_noise(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        local_fallback_module,
        "_local_chat_runtime_metadata",
        lambda _project_root: {
            "model": "gpt-5.5",
            "effort": "medium",
            "runtime_sdk": "codex_sdk",
            "provider": "codex_subscription",
        },
    )
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir()
    db_path = agent_builder_dir / "agent_builder.db"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            create table chat_sessions (
                id text primary key,
                sdk_session_id text,
                created_at text,
                updated_at text
            )
            """
        )
        conn.execute(
            """
            create table chat_events (
                id text primary key,
                session_id text,
                event_type text,
                status text,
                payload_json text,
                created_at text
            )
            """
        )
        conn.execute(
            "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
            ("sess-1", "sdk-sess-1", "2026-05-13T10:00:00Z", "2026-05-13T10:00:10Z"),
        )
        conn.executemany(
            """
            insert into chat_events (id, session_id, event_type, status, payload_json, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "event-user",
                    "sess-1",
                    "user_message",
                    "completed",
                    json.dumps({"content": "what should I do next?"}),
                    "2026-05-13T10:00:01Z",
                ),
                (
                    "event-runtime",
                    "sess-1",
                    "runtime_item_started",
                    "completed",
                    json.dumps({"content": "item/started"}),
                    "2026-05-13T10:00:02Z",
                ),
                (
                    "event-assistant",
                    "sess-1",
                    "assistant_message",
                    "completed",
                    json.dumps({"content": "Do shipping/state reconciliation next.", "final": True}),
                    "2026-05-13T10:00:03Z",
                ),
                (
                    "event-status",
                    "sess-1",
                    "run_status",
                    "completed",
                    json.dumps(
                        {
                            "running": False,
                            "runtime_sdk": "codex_sdk",
                            "provider": "codex_subscription",
                            "model": "gpt-5.5",
                            "stop_reason": "completed",
                        }
                    ),
                    "2026-05-13T10:00:04Z",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    payload = local_fallback_module.load_local_agent_history("sess-1", full=True)

    assert payload["model"] == "gpt-5.5"
    assert payload["runtime_sdk"] == "codex_sdk"
    assert payload["provider"] == "codex_subscription"
    assert [message["content"] for message in payload["messages"]] == [
        "what should I do next?",
        "Do shipping/state reconciliation next.",
    ]
    assert [item["type"] for item in payload["items"]] == [
        "user_message",
        "assistant_message",
    ]
    assert payload["status"]["stop_reason"] == "completed"


def test_local_session_factory_targets_repo_agent_builder_db(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agent-builder").mkdir()
    monkeypatch.delenv("DB_NAME", raising=False)

    local_fallback_module._local_session_factory()

    assert (
        local_fallback_module.os.environ["DB_NAME"]
        == str((tmp_path / ".agent-builder" / "agent_builder").resolve())
    )


def test_load_local_metrics_uses_standalone_loader(monkeypatch):
    """Regression: load_local_metrics must call load_metrics_response(session),
    NOT metrics_json(session, ...). metrics_json is a FastAPI route handler that
    expects (request: Request, db: AsyncSession); passing an AsyncSession as
    the first arg raises AttributeError: 'AsyncSession' object has no attribute
    'app'. Caught 2026-05-23 via smoke-A-v2 evidence: metrics.json had
    ok=False, error.type=AttributeError, blocking chunk_pressure_risk gate.
    """
    calls = []

    async def _fake_load_metrics_response(session, project_root=None):
        calls.append(session)

        class _FakeMetrics:
            def model_dump(self, **_kwargs):
                return {
                    "total_cost": 0.5,
                    "total_tokens": 1000,
                    "total_runs": 2,
                    "gate_pass_rate": 1.0,
                    "optimization": {"chunk_pressure": {"risk": False}},
                }

        return _FakeMetrics()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _Factory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(local_fallback_module, "_local_session_factory", lambda: _Factory())
    monkeypatch.setattr(local_fallback_module, "load_metrics_response", _fake_load_metrics_response)

    payload = local_fallback_module.load_local_metrics()

    assert len(calls) == 1, "load_metrics_response must be called exactly once"
    assert isinstance(calls[0], _Session), "session object must be passed to standalone loader"
    assert payload["total_runs"] == 2
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
