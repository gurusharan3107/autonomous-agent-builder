from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from autonomous_agent_builder.observability.summary import dashboard_observability_summary


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table agent_runs (
            id text primary key,
            task_id text,
            agent_name text,
            runtime_sdk text,
            provider text,
            model text,
            effort text,
            cost_usd real,
            tokens_input integer,
            tokens_output integer,
            tokens_cached integer,
            num_turns integer,
            duration_ms integer,
            stop_reason text,
            observability text
        );
        create table agent_run_events (
            id text primary key,
            run_id text,
            event_type text,
            tool_name text
        );
        create table approval_gates (
            id text primary key,
            task_id text,
            gate_type text,
            status text,
            created_at text,
            resolved_at text
        );
        create table tasks (
            id text primary key,
            status text,
            depends_on text
        );
        create table chat_events (
            id text primary key,
            session_id text,
            event_type text,
            status text,
            content text,
            payload_json text
        );
        """
    )
    conn.commit()
    conn.close()


def test_codex_observability_summary_reports_app_server_coverage(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_MODEL", "gpt-5.5")
    codex_config = tmp_path / ".codex" / "config.toml"
    codex_config.parent.mkdir()
    codex_config.write_text(
        """
[otel]
environment = "test"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", protocol = "binary" } }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    optimization = {
        "optimization_summary": {
            "token_accounting": {
                "raw_total_tokens": 10_500,
                "noncached_plus_output_tokens": 2_500,
                "cached_input_tokens": 8_000,
                "output_tokens": 500,
            },
            "avoidable_cost_flags": ["prompt_over_phase_budget"],
            "avoidable_token_estimate": 1_000,
        }
    }
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        insert into agent_runs
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            "task-1",
            "code-gen",
            "codex_sdk",
            "codex_subscription",
            "gpt-5.5",
            "medium",
            0.0,
            10_000,
            500,
            8_000,
            1,
            1000,
            "completed",
            json.dumps(optimization),
        ),
    )
    conn.execute(
        "insert into agent_run_events values (?, ?, ?, ?)",
        ("event-1", "run-1", "command", "Bash"),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)

    assert payload["runtime"]["selected_runtime_sdk"] == "codex_sdk"
    assert payload["observability_coverage"]["mode"] == "codex_app_server"
    assert "codex_token_usage" not in payload["observability_coverage"]["missing_signals"]
    assert payload["runtime_aggregates"]["totals"]["estimated_cost_usd"] == pytest.approx(0.029)
    assert payload["runtime_aggregates"]["by_model_effort"][0]["model"] == "gpt-5.5"
    assert payload["optimization_summary"]["raw_token_total"] == 10_500
    assert payload["runtime_capability_matrix"]["runtime"] == "codex_sdk"
    assert payload["phase_runtime_decisions"][0]["phase"] == "requirements"
    assert payload["runtime_decision_summary"]["runtime"] == "codex_sdk"
    health = payload["observability_coverage"]["telemetry_health"]
    assert health["codex_native"]["configured"] is True
    assert health["codex_native"]["exporter"] == "otlp-http"
    assert health["builder_product"]["source"] == "active_db"
    assert payload["deterministic_recommendations"]
    assert payload["recommendations"]


def test_claude_observability_summary_reports_otel_gaps(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    monkeypatch.delenv("CLAUDE_CODE_ENABLE_TELEMETRY", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_LOGS_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)

    payload = dashboard_observability_summary(db_path)

    assert payload["runtime"]["selected_runtime_sdk"] == "claude_agent_sdk"
    assert payload["observability_coverage"]["mode"] == "claude_otel"
    assert "otel_metrics_exporter" in payload["observability_coverage"]["missing_signals"]
    assert payload["optimization_summary"]["available"] is True
    assert payload["runtime_capability_matrix"]["runtime"] == "claude_agent_sdk"
    assert any(
        item["id"] == "hooks" and item["native"]
        for item in payload["runtime_capability_matrix"]["capabilities"]
    )


def test_claude_observability_summary_projects_reachable_collector_status(
    monkeypatch, tmp_path
):
    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def connect(*_args, **_kwargs):
        return ConnectedSocket()

    monkeypatch.setenv("RUNTIME_SDK", "claude")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_SERVICE_NAME", "test")
    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        connect,
    )
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)

    payload = dashboard_observability_summary(db_path)
    otel = payload["observability_coverage"]["otel"]

    assert otel["collector"]["status"] == "reachable"
    assert otel["collector_status"] == "reachable"
    assert otel["collector_reachable"] is True
    assert "otel_collector_unreachable" not in payload["observability_coverage"]["missing_signals"]


def test_claude_observability_does_not_flag_tool_events_before_first_run(
    monkeypatch, tmp_path
):
    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def connect(*_args, **_kwargs):
        return ConnectedSocket()

    monkeypatch.setenv("RUNTIME_SDK", "claude")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_SERVICE_NAME", "test")
    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        connect,
    )
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)

    payload = dashboard_observability_summary(db_path)

    tool_state = payload["runtime_aggregates"]["tool_observability"]
    assert tool_state["agent_run_events_available"] is True
    assert tool_state["agent_run_event_count"] == 0
    assert tool_state["missing_tool_events"] is False
    assert "tool_events" not in payload["observability_coverage"]["missing_signals"]
    assert not any(
        item["code"] == "tool_events_missing"
        for item in payload["deterministic_recommendations"]
    )


def test_claude_observability_does_not_flag_tool_events_for_provider_limit_only(
    monkeypatch, tmp_path
):
    class ConnectedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def connect(*_args, **_kwargs):
        return ConnectedSocket()

    monkeypatch.setenv("RUNTIME_SDK", "claude")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_SERVICE_NAME", "test")
    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        connect,
    )
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into chat_events values (?, ?, ?, ?, ?, ?)",
        (
            "evt-provider-limit",
            "sess-provider-limit",
            "run_status",
            "blocked",
            "",
            json.dumps(
                {
                    "running": False,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                    "stop_reason": "provider_limit",
                    "provider_limit": {
                        "code": "provider_limit",
                        "reset_hint": "resets 11:10pm",
                        "source": "claude_agent_sdk",
                    },
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)

    tool_state = payload["runtime_aggregates"]["tool_observability"]
    assert payload["runtime_aggregates"]["totals"]["runs"] == 1
    assert tool_state["missing_tool_events"] is False
    assert "tool_events" not in payload["observability_coverage"]["missing_signals"]
    assert payload["runtime_aggregates"]["provider_limits"]["count"] == 1
    assert any(
        item["code"] == "provider_limits_present"
        for item in payload["recommendations"]
    )


def test_claude_observability_summary_flags_unreachable_local_collector(
    monkeypatch, tmp_path
):
    def refuse_connection(*_args, **_kwargs):
        raise ConnectionRefusedError("collector not listening")

    monkeypatch.setenv("RUNTIME_SDK", "claude")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_SERVICE_NAME", "test")
    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        refuse_connection,
    )
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)

    payload = dashboard_observability_summary(db_path)
    otel = payload["observability_coverage"]["otel"]

    assert otel["collector"]["status"] == "configured_unreachable"
    assert otel["collector_status"] == "configured_unreachable"
    assert otel["collector_reachable"] is False
    assert "otel_collector_unreachable" in payload["observability_coverage"]["missing_signals"]


def test_empty_observability_summary_reports_explicit_gap(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "missing.db"

    payload = dashboard_observability_summary(db_path)

    assert payload["runtime_aggregates"]["available"] is False
    assert payload["runtime_aggregates"]["reason"] == "agent_builder_db_missing"
    assert "codex_token_usage" in payload["observability_coverage"]["missing_signals"]
    assert payload["deterministic_script_candidates"] == []


def test_codex_observability_summary_reports_missing_project_otel_config(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)

    payload = dashboard_observability_summary(db_path)
    health = payload["observability_coverage"]["telemetry_health"]

    assert health["codex_native"]["status"] == "missing"
    assert health["codex_native"]["project_local"] is True
    assert health["codex_native"]["reason"] == "project_codex_config_missing"
    assert any(
        item["code"] == "telemetry_collector_blocked"
        for item in payload["deterministic_recommendations"]
    )


def test_observability_filters_recommendations_handled_by_optimizer(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        alter table agent_runs add column status text;
        alter table agent_runs add column output_text text;
        alter table agent_runs add column completed_at text;
        alter table agent_runs add column started_at text;
        """
    )
    for index in range(2):
        conn.execute(
            """
            insert into agent_runs (
                id, task_id, agent_name, runtime_sdk, provider, model, effort,
                cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
                duration_ms, stop_reason, observability, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"build-{index}",
                "task-1",
                "build-verifier",
                "claude_agent_sdk",
                "anthropic",
                "claude-sonnet-4-6",
                "medium",
                0.0,
                1000,
                200,
                0,
                1,
                1000,
                "end_turn",
                "{}",
                "completed",
            ),
        )
    for index in range(5):
        conn.execute(
            "insert into agent_run_events values (?, ?, ?, ?)",
            (f"event-{index}", "build-0", "tool_use", "command"),
        )
    optimization_payload = {
        "agent_name": "optimization-agent",
        "status": "implemented",
        "selected_recommendations": ["script_candidate_build_verify_script"],
        "post_preflight_decision": {
            "deterministic_actions_applied": ["script_candidate_build_verify_script"],
            "recommendation_decisions": [
                {
                    "code": "script_candidate_command_sequence_wrapper",
                    "lifecycle_status": "applied",
                    "reason": "covered by build_verify script",
                }
            ],
        },
    }
    conn.execute(
        """
        insert into agent_runs (
            id, task_id, agent_name, runtime_sdk, provider, model, effort,
            cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
            duration_ms, stop_reason, observability, status, output_text, completed_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "optimization-1",
            "task-1",
            "optimization-agent",
            "deterministic",
            "builder",
            "none",
            "none",
            0.0,
            0,
            0,
            0,
            0,
            1,
            "deterministic_post_ship_optimization",
            "{}",
            "completed",
            json.dumps(optimization_payload),
            "2026-05-06T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    open_codes = {item["code"] for item in payload["deterministic_recommendations"]}
    resolved_codes = {
        item["code"] for item in payload["observability_coverage"]["resolved_recommendations"]
    }

    assert "script_candidate_build_verify_script" not in open_codes
    assert "script_candidate_command_sequence_wrapper" not in open_codes
    assert "script_candidate_build_verify_script" in resolved_codes
    assert "script_candidate_command_sequence_wrapper" in resolved_codes


def test_observability_approval_stalled_ignores_terminal_task_gates(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("insert into tasks values (?, ?, ?)", ("task-1", "done", "{}"))
    conn.execute(
        "insert into approval_gates values (?, ?, ?, ?, ?, ?)",
        (
            "gate-1",
            "task-1",
            "planning",
            "pending",
            "2026-05-06T00:00:00+00:00",
            None,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    open_codes = {item["code"] for item in payload["deterministic_recommendations"]}

    assert payload["runtime_aggregates"]["approval_wait"]["active_unresolved"] == 0
    assert "approval_stalled" not in open_codes


def test_observability_approval_stalled_is_summary_warning_not_rule(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("insert into tasks values (?, ?, ?)", ("task-1", "design_review", "{}"))
    conn.execute(
        "insert into approval_gates values (?, ?, ?, ?, ?, ?)",
        (
            "gate-1",
            "task-1",
            "planning",
            "pending",
            "2026-05-06T00:00:00+00:00",
            None,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    open_codes = {item["code"] for item in payload["deterministic_recommendations"]}
    summary_codes = {item["code"] for item in payload["recommendations"]}

    assert payload["runtime_aggregates"]["approval_wait"]["active_unresolved"] == 1
    assert "approval_stalled" not in open_codes
    assert "approval_stalled" in summary_codes
