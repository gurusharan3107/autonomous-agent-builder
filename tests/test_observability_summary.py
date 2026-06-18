from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.services.context_budget import build_agent_context_budget


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


def test_codex_observability_summary_keeps_chunk_pressure_as_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    optimization = {
        "optimization_summary": {
            "token_accounting": {
                "raw_total_tokens": 45_500,
                "input_tokens": 44_000,
                "noncached_plus_output_tokens": 5_500,
                "cached_input_tokens": 39_000,
                "output_tokens": 1_500,
            },
            "event_accounting": {
                "raw_event_count": 7,
                "largest_event_bytes": 125_000,
                "largest_command_output_bytes": 45_000,
                "chunk_pressure_risk": True,
            },
            "avoidable_cost_flags": ["large_command_output", "chunk_pressure_large_event"],
            "avoidable_token_estimate": 5_500,
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
            "agent-chat",
            "codex_sdk",
            "codex_subscription",
            "gpt-5.5",
            "medium",
            0.0,
            44_000,
            1_500,
            39_000,
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

    coverage = payload["observability_coverage"]
    assert "chunk_pressure" not in coverage["missing_signals"]
    assert "chunk_pressure" in coverage["available_signals"]
    assert coverage["codex"]["chunk_pressure"]["available"] is True
    assert coverage["codex"]["chunk_pressure"]["risky_runs"] == 1
    assert coverage["codex"]["chunk_pressure"]["largest_command_output_bytes"] == 45_000
    assert any(
        item["code"] == "script_candidate_output_truncation_artifact"
        for item in payload["deterministic_recommendations"]
    )


def test_codex_observability_summary_reports_context_budget_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_MODEL", "gpt-5.5")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    budget = build_agent_context_budget(
        agent_name="agent-chat",
        prompt="final SDK-backed prompt",
        user_message="what is the current context budget?",
        recent_context="recent transcript digest",
        documentation_context=None,
        observability_context="builder observability facts",
        runtime_metadata={
            "runtime_sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "effort": "medium",
        },
        resume_session=None,
        specialist_active=False,
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into chat_events values (?, ?, ?, ?, ?, ?)",
        ("budget-1", "session-1", "context_budget", "completed", "", json.dumps(budget)),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    summary = payload["runtime_aggregates"]["context_budget"]
    coverage = payload["observability_coverage"]

    assert summary["available"] is True
    assert summary["event_count"] == 1
    assert summary["total_estimated_tokens"] == budget["total_estimated_tokens"]
    assert summary["latest"]["lane"] == "sdk_agent"
    assert "context_budget" in coverage["available_signals"]
    assert "context_budget" not in coverage["missing_signals"]
    assert coverage["codex"]["context_budget"]["event_count"] == 1


def test_observability_recommendations_cover_budget_top_driver_and_app_lane(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)

    rows = [
        (
            "run-agent-chat",
            "agent-chat",
            {
                "raw_total_tokens": 210_000,
                "input_tokens": 170_000,
                "output_tokens": 40_000,
                "cached_input_tokens": 30_000,
                "noncached_plus_output_tokens": 180_000,
            },
            42_000,
        ),
        (
            "run-code-gen",
            "code-gen",
            {
                "raw_total_tokens": 55_000,
                "input_tokens": 45_000,
                "output_tokens": 10_000,
                "cached_input_tokens": 5_000,
                "noncached_plus_output_tokens": 50_000,
            },
            7_500,
        ),
    ]
    for run_id, agent_name, token_accounting, avoidable in rows:
        observability = {
            "optimization_summary": {
                "token_accounting": token_accounting,
                "avoidable_cost_flags": [],
                "avoidable_token_estimate": avoidable,
            }
        }
        conn.execute(
            """
            insert into agent_runs (
                id, task_id, agent_name, runtime_sdk, provider, model, effort,
                cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
                duration_ms, stop_reason, observability
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "task-1",
                agent_name,
                "codex_sdk",
                "codex_subscription",
                "gpt-5.5",
                "medium",
                0.0,
                token_accounting["input_tokens"],
                token_accounting["output_tokens"],
                token_accounting["cached_input_tokens"],
                1,
                1000,
                "end_turn",
                json.dumps(observability),
            ),
        )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    by_code = {item["code"]: item for item in payload["deterministic_recommendations"]}

    assert "runtime_token_budget_over_target" in by_code
    assert by_code["runtime_token_budget_over_target"]["owner_lane"] == "builder_source"
    assert "agent_chat_readonly_intent_budget" in by_code
    assert by_code["agent_chat_readonly_intent_budget"]["next_actor"] == "builder"
    assert "managed_repo_codegen_context_pack" in by_code
    assert by_code["managed_repo_codegen_context_pack"]["owner_lane"] == "managed_repo_environment"
    assert by_code["managed_repo_codegen_context_pack"]["next_actor"] == "optimization_agent"
    assert by_code["runtime_token_budget_over_target"]["priority_rank"] < by_code[
        "managed_repo_codegen_context_pack"
    ]["priority_rank"]
    assert by_code["agent_chat_readonly_intent_budget"]["evidence_source"] == "metrics top driver"


def test_observability_readonly_intent_recommendation_uses_active_driver(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)

    def insert_agent_chat_run(run_id: str, raw_tokens: int, avoidable: int) -> None:
        observability = {
            "optimization_summary": {
                "token_accounting": {
                    "raw_total_tokens": raw_tokens,
                    "input_tokens": raw_tokens,
                    "output_tokens": 0,
                    "cached_input_tokens": 0,
                    "noncached_plus_output_tokens": raw_tokens,
                },
                "avoidable_cost_flags": [],
                "avoidable_token_estimate": avoidable,
            }
        }
        conn.execute(
            """
            insert into agent_runs (
                id, task_id, agent_name, runtime_sdk, provider, model, effort,
                cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
                duration_ms, stop_reason, observability
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "task-1",
                "agent-chat",
                "codex_sdk",
                "codex_subscription",
                "gpt-5.5",
                "medium",
                0.0,
                raw_tokens,
                0,
                0,
                0,
                100,
                "deterministic_status_check" if raw_tokens == 0 else "completed",
                json.dumps(observability),
            ),
        )

    for index in range(5):
        insert_agent_chat_run(f"recent-clean-{index}", 0, 0)
    insert_agent_chat_run("historical-expensive", 60_000, 30_000)
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    by_code = {item["code"]: item for item in payload["deterministic_recommendations"]}

    assert "agent_chat_readonly_intent_budget" not in by_code
    assert payload["optimization_summary"]["top_cost_drivers"][0]["avoidable_token_estimate"] == 30_000
    assert payload["optimization_summary"]["active_top_cost_drivers"][0][
        "avoidable_token_estimate"
    ] == 0


def test_observability_recommendations_surface_errors_with_provenance(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into chat_events values (?, ?, ?, ?, ?, ?)",
        (
            "evt-error",
            "sess-error",
            "run_error",
            "error",
            "",
            json.dumps(
                {
                    "summary": "Agent run failed",
                    "error_message": "Error: Separator is not found, and chunk exceed the limit",
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    by_code = {item["code"]: item for item in payload["deterministic_recommendations"]}

    assert payload["runtime_aggregates"]["error_summary"]["count"] == 1
    assert payload["runtime_aggregates"]["error_summary"]["total_count"] == 1
    assert payload["runtime_aggregates"]["error_summary"]["recent_count"] == 1
    assert "Separator is not found" in payload["runtime_aggregates"]["error_summary"]["recent"][0]["summary"]
    assert by_code["runtime_error_trend"]["evidence_source"] == "builder logs"
    assert by_code["runtime_error_trend"]["evidence_command"] == "builder logs --error --json --limit 10"
    assert by_code["runtime_error_trend"]["validation_status"] == "validated"
    assert by_code["runtime_error_trend"]["priority_rank"] == 1


def test_observability_resolves_error_recommendation_after_same_prompt_succeeds(
    monkeypatch, tmp_path
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("alter table chat_events add column created_at text")
    prompt = "what can you tell me from observability data, what should i fix next?"
    # Use recent dates (within the 7-day retention window) so resolution tracking applies
    now = datetime.now(UTC)
    t_error = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    t_error_status = (now - timedelta(hours=2, seconds=-30)).strftime("%Y-%m-%d %H:%M:%S")
    t_user_before = (now - timedelta(hours=2, minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_user_after = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_status_after = (now - timedelta(minutes=59)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "user-before",
            "failed-session",
            "user_message",
            "completed",
            "",
            json.dumps({"content": prompt}),
            t_user_before,
        ),
    )
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "error-before",
            "failed-session",
            "run_error",
            "completed",
            "",
            json.dumps({"content": "Error: Separator is found, but chunk is longer than limit"}),
            t_error,
        ),
    )
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "failed-status",
            "failed-session",
            "run_status",
            "completed",
            "",
            json.dumps(
                {
                    "running": False,
                    "runtime_sdk": "codex_sdk",
                    "error": "Separator is found, but chunk is longer than limit",
                    "stop_reason": "runtime_error",
                }
            ),
            t_error_status,
        ),
    )
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "user-after",
            "fixed-session",
            "user_message",
            "completed",
            "",
            json.dumps({"content": prompt}),
            t_user_after,
        ),
    )
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "status-after",
            "fixed-session",
            "run_status",
            "completed",
            "",
            json.dumps({"running": False, "runtime_sdk": "codex_sdk", "stop_reason": "end_turn"}),
            t_status_after,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    codes = {item["code"] for item in payload["deterministic_recommendations"]}
    completed_codes = {
        item["code"]
        for item in payload["observability_coverage"]["resolved_recommendations"]
        if item.get("lifecycle_status") == "applied"
    }

    assert payload["runtime_aggregates"]["error_summary"]["total_count"] == 1
    assert payload["runtime_aggregates"]["error_summary"]["resolved_count"] == 1
    assert payload["runtime_aggregates"]["error_summary"]["active_count"] == 0
    assert "runtime_error_trend" not in codes
    assert "runtime_error_trend" in completed_codes


def test_observability_keeps_codex_error_active_until_codex_prompt_succeeds(
    monkeypatch, tmp_path
):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("alter table chat_events add column created_at text")
    prompt = "what can you tell me from observability data, what should i fix next?"
    # Use recent dates (within the 7-day retention window) so the error is processed
    now = datetime.now(UTC)
    t_user_before = (now - timedelta(hours=2, minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_error = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    t_error_status = (now - timedelta(hours=1, minutes=59, seconds=49)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    t_user_after = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_status_after = (now - timedelta(minutes=59)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (
            "user-before",
            "failed-session",
            "user_message",
            "completed",
            "",
            json.dumps({"content": prompt}),
            t_user_before,
        ),
        (
            "error-before",
            "failed-session",
            "run_error",
            "completed",
            "",
            json.dumps({"content": "Error: Separator is found, but chunk is longer than limit"}),
            t_error,
        ),
        (
            "failed-status",
            "failed-session",
            "run_status",
            "completed",
            "",
            json.dumps(
                {
                    "running": False,
                    "runtime_sdk": "codex_sdk",
                    "error": "Separator is found, but chunk is longer than limit",
                    "stop_reason": "runtime_error",
                }
            ),
            t_error_status,
        ),
        (
            "user-after",
            "claude-session",
            "user_message",
            "completed",
            "",
            json.dumps({"content": prompt}),
            t_user_after,
        ),
        (
            "status-after",
            "claude-session",
            "run_status",
            "completed",
            "",
            json.dumps({"running": False, "runtime_sdk": "claude", "stop_reason": "end_turn"}),
            t_status_after,
        ),
    ]
    conn.executemany(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    codes = {item["code"] for item in payload["deterministic_recommendations"]}

    assert payload["runtime_aggregates"]["error_summary"]["resolved_count"] == 0
    assert payload["runtime_aggregates"]["error_summary"]["active_count"] == 1
    assert "runtime_error_trend" in codes


def test_stale_errors_older_than_retention_window_do_not_trigger_dispatch_blocking_rec(
    monkeypatch, tmp_path
):
    """Errors older than 7 days must NOT cause runtime_error_trend (IMP-014)."""
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("alter table chat_events add column created_at text")
    # Insert 9 tool_errors all dated more than 7 days ago (simulating 2026-05-20 errors
    # still visible on 2026-06-02 — 13 days stale).
    stale_date = "2026-05-20 10:00:00"
    for i in range(9):
        conn.execute(
            """
            insert into chat_events
                (id, session_id, event_type, status, content, payload_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"stale-err-{i}",
                f"stale-session-{i}",
                "tool_error",
                "error",
                "",
                json.dumps({"error_message": f"Tool failure {i}"}),
                stale_date,
            ),
        )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    codes = {item["code"] for item in payload["deterministic_recommendations"]}

    # total_count still reflects all historical errors
    assert payload["runtime_aggregates"]["error_summary"]["total_count"] == 9
    # active_count must be 0 because all errors are outside the retention window
    assert payload["runtime_aggregates"]["error_summary"]["active_count"] == 0
    # The dispatch-blocking recommendation must NOT fire
    assert "runtime_error_trend" not in codes


def test_recent_errors_within_retention_window_do_trigger_dispatch_blocking_rec(
    monkeypatch, tmp_path
):
    """Errors within the 7-day window MUST still trigger runtime_error_trend (IMP-014)."""
    from datetime import timedelta

    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("alter table chat_events add column created_at text")
    # Insert a tool_error dated 1 day ago (well within the 7-day window)
    from datetime import UTC, datetime

    recent_date = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        insert into chat_events
            (id, session_id, event_type, status, content, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "recent-err-1",
            "recent-session-1",
            "tool_error",
            "error",
            "",
            json.dumps({"error_message": "Recent tool failure"}),
            recent_date,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    codes = {item["code"] for item in payload["deterministic_recommendations"]}

    assert payload["runtime_aggregates"]["error_summary"]["total_count"] == 1
    assert payload["runtime_aggregates"]["error_summary"]["active_count"] == 1
    # The dispatch-blocking recommendation MUST fire for recent errors
    assert "runtime_error_trend" in codes


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
                "sonnet",
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
    assert [
        item["priority_rank"] for item in payload["deterministic_recommendations"]
    ] == list(range(1, len(payload["deterministic_recommendations"]) + 1))


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


def test_observability_approval_stalled_is_operator_recommendation(
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
    assert "approval_action_waiting" in open_codes
    assert "approval_stalled" in summary_codes


def test_recommendations_never_emit_phantom_blank_row(monkeypatch, tmp_path):
    """No summary recommendation may have a None category / blank detail (phantom card bug)."""
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    # Insert a minimal run so we are past the missing-db early return.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into agent_runs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "task-1", "code-gen", "codex_sdk", "codex_subscription",
         "gpt-5.5", "medium", 0.0, 1000, 100, 500, 1, 500, "completed", None),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    recs = payload["recommendations"]

    # No row with blank/None content may appear — the phantom card is gone.
    for item in recs:
        assert item.get("code"), f"recommendation has empty code: {item}"
        assert item.get("detail") or item.get("title"), (
            f"recommendation has no content (phantom row): {item}"
        )

    # The summary baseline_ready duplicate must not appear; the deterministic
    # surface owns baseline-ready signalling.
    assert all(item.get("code") != "baseline_ready" for item in recs), (
        "baseline_ready must not appear in summary recommendations"
    )


def test_recommendations_non_empty_in_active_case(monkeypatch, tmp_path):
    """Summary recommendations remain non-empty when there is genuine signal."""
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    db_path = tmp_path / "agent_builder.db"
    _init_db(db_path)
    import json as _json
    optimization = {
        "optimization_summary": {
            "token_accounting": {
                "raw_total_tokens": 10_000,
                "noncached_plus_output_tokens": 2_000,
                "cached_input_tokens": 8_000,
                "output_tokens": 500,
            },
            "avoidable_cost_flags": ["prompt_over_phase_budget"],
            "avoidable_token_estimate": 500,
        }
    }
    conn = sqlite3.connect(db_path)
    conn.execute(
        "insert into agent_runs values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "task-1", "code-gen", "codex_sdk", "codex_subscription",
         "gpt-5.5", "medium", 0.0, 9_000, 500, 8_000, 1, 1000, "completed",
         _json.dumps(optimization)),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    assert payload["recommendations"], (
        "summary recommendations must be non-empty when avoidable_cost_flags are present"
    )
    codes = {item["code"] for item in payload["recommendations"]}
    assert "prompt_over_phase_budget" in codes


# ---------------------------------------------------------------------------
# Loop-4 outcome attribution tests
# ---------------------------------------------------------------------------


def _init_db_with_outcome_columns(path):
    """Create a DB with status/output_text/started_at/completed_at columns."""
    _init_db(path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        alter table agent_runs add column status text;
        alter table agent_runs add column output_text text;
        alter table agent_runs add column completed_at text;
        alter table agent_runs add column started_at text;
        """
    )
    conn.commit()
    conn.close()


def test_recommendation_lifecycle_outcome_token_code(monkeypatch, tmp_path):
    """Applied record with a token-typed code gets a measured outcome verdict.

    Fixture:
    - 4 delivery runs BEFORE the optimization timestamp  (2 each agent)
    - optimization-agent run at 2026-05-06T00:00:00+00:00 with
      selected_recommendation='reduce_code-gen_raw_tokens', status='implemented'
    - 4 delivery runs AFTER the optimization timestamp
    The before window has higher tokens → expected verdict = 'improved'.
    """
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    db_path = tmp_path / "agent_builder.db"
    _init_db_with_outcome_columns(db_path)
    conn = sqlite3.connect(db_path)

    opt_ts = "2026-05-06T00:00:00+00:00"
    code = "reduce_code-gen_raw_tokens"

    # Before: 4 delivery runs with noncached+output = max(2000-500,0)+200 = 1700 each
    before_timestamps = [
        "2026-05-05T08:00:00+00:00",
        "2026-05-05T12:00:00+00:00",
        "2026-05-05T16:00:00+00:00",
        "2026-05-05T20:00:00+00:00",
    ]
    for i, ts in enumerate(before_timestamps):
        conn.execute(
            """
            insert into agent_runs (
                id, task_id, agent_name, runtime_sdk, provider, model, effort,
                cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
                duration_ms, stop_reason, observability, status, started_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"before-{i}", "task-1", "code-gen", "claude_agent_sdk", "anthropic",
                "sonnet", "medium", 0.0, 2000, 200, 500, 1, 1000, "end_turn", "{}", "completed", ts,
            ),
        )

    # After: 4 delivery runs with lower tokens: noncached+output = max(800-100,0)+80 = 780
    after_timestamps = [
        "2026-05-06T08:00:00+00:00",
        "2026-05-06T12:00:00+00:00",
        "2026-05-06T16:00:00+00:00",
        "2026-05-06T20:00:00+00:00",
    ]
    for i, ts in enumerate(after_timestamps):
        conn.execute(
            """
            insert into agent_runs (
                id, task_id, agent_name, runtime_sdk, provider, model, effort,
                cost_usd, tokens_input, tokens_output, tokens_cached, num_turns,
                duration_ms, stop_reason, observability, status, started_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"after-{i}", "task-1", "code-gen", "claude_agent_sdk", "anthropic",
                "sonnet", "medium", 0.0, 800, 80, 100, 1, 500, "end_turn", "{}", "completed", ts,
            ),
        )

    # Optimization run
    opt_payload = {
        "agent_name": "optimization-agent",
        "status": "implemented",
        "selected_recommendation": code,
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
            "opt-1", "task-1", "optimization-agent", "deterministic", "builder",
            "none", "none", 0.0, 0, 0, 0, 0, 1,
            "deterministic_post_ship_optimization", "{}", "completed",
            json.dumps(opt_payload), opt_ts,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    lifecycle = payload["observability_coverage"]["recommendation_lifecycle"]

    # by_code and applied list must both carry outcome
    by_code_record = lifecycle["by_code"].get(code)
    assert by_code_record is not None, f"code {code!r} not in by_code"
    outcome = by_code_record.get("outcome")
    assert outcome is not None, "outcome must be set on applied record"
    assert outcome["verdict"] == "improved", (
        f"expected 'improved' but got {outcome['verdict']!r}; outcome={outcome}"
    )
    assert outcome["metric"] == "noncached_plus_output_tokens"

    # The applied list entry must carry the same outcome object (shared reference)
    applied_entries = [e for e in lifecycle["applied"] if e.get("code") == code]
    assert applied_entries, f"code {code!r} not found in applied list"
    assert applied_entries[0]["outcome"] is by_code_record["outcome"], (
        "applied list entry and by_code entry must share the same outcome dict"
    )


def test_recommendation_lifecycle_outcome_not_measurable(monkeypatch, tmp_path):
    """Applied record with maintain_current_flow gets verdict='not_measurable'."""
    monkeypatch.setenv("RUNTIME_SDK", "claude")
    db_path = tmp_path / "agent_builder.db"
    _init_db_with_outcome_columns(db_path)
    conn = sqlite3.connect(db_path)

    opt_ts = "2026-05-06T00:00:00+00:00"
    code = "maintain_current_flow"

    opt_payload = {
        "agent_name": "optimization-agent",
        "status": "implemented",
        "selected_recommendation": code,
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
            "opt-2", "task-1", "optimization-agent", "deterministic", "builder",
            "none", "none", 0.0, 0, 0, 0, 0, 1,
            "deterministic_post_ship_optimization", "{}", "completed",
            json.dumps(opt_payload), opt_ts,
        ),
    )
    conn.commit()
    conn.close()

    payload = dashboard_observability_summary(db_path)
    lifecycle = payload["observability_coverage"]["recommendation_lifecycle"]

    by_code_record = lifecycle["by_code"].get(code)
    assert by_code_record is not None
    outcome = by_code_record.get("outcome")
    assert outcome is not None, "outcome must be set even for non-measurable codes"
    assert outcome["verdict"] == "not_measurable"
    assert outcome["metric"] is None
