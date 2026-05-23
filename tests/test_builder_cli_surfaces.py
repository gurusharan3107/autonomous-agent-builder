"""Tests for builder retrieval and control-plane CLI surfaces."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from autonomous_agent_builder.agents.tool_registry import _SDK_BUILTINS
from autonomous_agent_builder.agents.tools.cli_tools import CLI_TOOLS
from autonomous_agent_builder.cli import main as main_module
from autonomous_agent_builder.cli.client import BuilderConnectivityError
from autonomous_agent_builder.cli.commands import agent as agent_module
from autonomous_agent_builder.cli.commands import logs as logs_module
from autonomous_agent_builder.cli.commands import map as map_module
from autonomous_agent_builder.cli.commands import memory as memory_module
from autonomous_agent_builder.cli.commands import start_impl as start_impl_module
from autonomous_agent_builder.cli.main import app
from tests.builder_cli_surface_helpers import (
    assert_agent_json_contract as _assert_agent_json_contract,
)
from tests.builder_cli_surface_helpers import (
    configure_local_kb as _configure_local_kb,
)
from tests.builder_cli_surface_helpers import (
    write_local_kb_doc as _write_local_kb_doc,
)

runner = CliRunner()


def test_builder_help_exposes_single_startup_owner():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "builder start --port 9876 Start the local dashboard and API" in result.stdout
    assert "Builder-owned local server lifecycle" in result.stdout


def test_publish_dashboard_assets_builds_frontend_and_copies_dist(monkeypatch, tmp_path: Path):
    project_root = tmp_path
    frontend_dir = project_root / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text('{"name":"frontend"}', encoding="utf-8")
    dist_dir = frontend_dir / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html>built</html>", encoding="utf-8")
    (dist_dir / "app.js").write_text("console.log('built')", encoding="utf-8")
    dashboard_dir = project_root / ".agent-builder" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "stale.txt").write_text("old", encoding="utf-8")

    calls: list[tuple[list[str], Path]] = []

    def fake_run(cmd, cwd=None, check=None):
        calls.append((cmd, Path(cwd)))
        return None

    monkeypatch.setattr(start_impl_module.shutil, "which", lambda name: name if name == "npm" else None)
    monkeypatch.setattr(start_impl_module.subprocess, "run", fake_run)

    result = start_impl_module._publish_dashboard_assets(project_root, dashboard_dir)

    assert result == {}
    assert calls == [(["npm", "run", "build"], frontend_dir)]
    assert not (dashboard_dir / "stale.txt").exists()
    assert (dashboard_dir / "index.html").read_text(encoding="utf-8") == "<html>built</html>"
    assert (dashboard_dir / "app.js").read_text(encoding="utf-8") == "console.log('built')"


def test_run_start_defaults_to_9876_and_reuses_that_port(monkeypatch, tmp_path: Path):
    agent_builder_dir = tmp_path / ".agent-builder"
    server_dir = agent_builder_dir / "server"
    dashboard_dir = agent_builder_dir / "dashboard"
    agent_builder_dir.mkdir()
    server_dir.mkdir()
    dashboard_dir.mkdir()
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")

    writes: list[int] = []
    checks: list[tuple[Path, int, bool]] = []
    starts: list[tuple[str, int]] = []

    def fake_write_port_file(port: int, _dir: Path) -> None:
        writes.append(port)

    def fake_ensure_builder_port_available(
        agent_builder_dir: Path,
        port: int,
        *,
        force: bool = False,
    ) -> None:
        checks.append((agent_builder_dir, port, force))

    def fake_publish_dashboard_assets(project_root: Path, dashboard_path: Path) -> dict[str, object]:
        assert project_root == tmp_path
        assert dashboard_path == dashboard_dir
        return {}

    expected_agent_builder_dir = agent_builder_dir

    def fake_start_uvicorn(
        *,
        agent_builder_dir: Path,
        server_path: Path,
        db_path: Path,
        dashboard_path: Path,
        host: str,
        port: int,
        debug: bool,
    ) -> None:
        assert agent_builder_dir == expected_agent_builder_dir
        starts.append((host, port))

    monkeypatch.setattr(start_impl_module, "_publish_dashboard_assets", fake_publish_dashboard_assets)
    monkeypatch.setattr(start_impl_module, "_start_uvicorn", fake_start_uvicorn)

    import autonomous_agent_builder.cli.port_manager as port_manager_module

    monkeypatch.setattr(port_manager_module, "write_port_file", fake_write_port_file)
    monkeypatch.setattr(
        port_manager_module,
        "ensure_builder_port_available",
        fake_ensure_builder_port_available,
    )

    result = start_impl_module.run_start(agent_builder_dir=agent_builder_dir, port=None, host="127.0.0.1", debug=False)

    assert result["status"] == "started"
    assert result["port"] == 9876
    assert writes == [9876]
    assert checks == [(agent_builder_dir, 9876, False)]
    assert starts == [("127.0.0.1", 9876)]


def test_kb_contract_defaults_to_system_docs():
    result = runner.invoke(app, ["knowledge", "contract", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["doc_type"] == "system-docs"
    assert payload["required_sections"] == [
        "# Title",
        "## Overview",
        "## Boundaries",
        "## Invariants",
        "## Evidence",
        "## Change guidance",
    ]


def test_context_json():
    result = runner.invoke(app, ["context", "verification", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task"] == "verification"
    assert "builder quality-gate quality-gates" in payload["commands"]


def test_map_json(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_dir = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_dir.mkdir(parents=True)
    (kb_dir / "project-overview.md").write_text("# Project Overview\n", encoding="utf-8")

    memory_dir = project_root / ".memory"
    memory_dir.mkdir()
    (memory_dir / "routing.json").write_text(
        json.dumps(
            {
                "memories": [
                    {"slug": "one", "type": "decision", "status": "active"},
                    {"slug": "two", "type": "correction", "status": "flagged"},
                ]
            }
        ),
        encoding="utf-8",
    )

    feature_list_dir = project_root / ".claude" / "progress"
    feature_list_dir.mkdir(parents=True)
    (feature_list_dir / "feature-list.json").write_text(
        json.dumps(
            {
                "features": [
                    {"status": "done"},
                    {"status": "pending"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AAB_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(project_root / ".agent-builder" / "knowledge"))
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_dir))
    monkeypatch.setattr(
        map_module,
        "_server_snapshot",
        lambda: {
            "reachable": True,
            "base_url": "http://localhost:8000",
            "projects": {"count": 1},
            "board": {"active": 2, "review": 1},
            "metrics": {"total_runs": 3, "total_cost": 1.25, "gate_pass_rate": 50.0},
        },
    )

    result = runner.invoke(app, ["map", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["knowledge_base"]["documents"] == 1
    assert payload["memory"]["flagged"] == 1
    assert payload["server"]["projects"]["count"] == 1


def test_agent_surfaces_expose_official_learning_mutation_tools():
    assert "builder_kb_extract" in CLI_TOOLS
    assert "builder_kb_add" in CLI_TOOLS
    assert "builder_kb_update" in CLI_TOOLS
    assert "builder_memory_add" in CLI_TOOLS
    assert "builder_backlog_item_list" in CLI_TOOLS
    assert "builder_backlog_item_show" in CLI_TOOLS
    assert "builder_task_list" in CLI_TOOLS
    assert "mcp__builder__backlog_item_list" in _SDK_BUILTINS
    assert "mcp__builder__backlog_item_show" in _SDK_BUILTINS
    assert "mcp__builder__kb_extract" in _SDK_BUILTINS
    assert "mcp__builder__kb_add" in _SDK_BUILTINS
    assert "mcp__builder__kb_update" in _SDK_BUILTINS
    assert "mcp__builder__memory_add" in _SDK_BUILTINS


def test_root_doctor_supports_global_json(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_doctor_payload",
        lambda: {
            "ok": True,
            "status": "ok",
            "exit_code": 0,
            "passed": True,
            "schema_version": "1",
            "tool": "builder",
            "checks": {
                "project": {
                    "initialized": True,
                    "cwd": "/tmp/project",
                    "project_root": "/tmp/project",
                    "agent_builder_dir": "/tmp/project/.agent-builder",
                    "hint": "",
                },
                "config": {
                    "api_base_url": "http://127.0.0.1:9876",
                    "api_base_url_source": "repo-port",
                    "auth_required": False,
                    "auth_source": "not_required",
                },
                "server": {
                    "reachable": True,
                    "healthy": True,
                    "status_code": 200,
                    "contract_ok": True,
                    "payload": {"status": "ok"},
                },
            },
            "next": "builder map",
            "next_step": "builder map",
        },
    )

    result = runner.invoke(app, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["tool"] == "builder"
    assert payload["next"] == "builder map"
    assert payload["checks"]["server"]["healthy"] is True


def test_root_invalid_command_emits_hint():
    result = runner.invoke(app, ["does-not-exist"])

    assert result.exit_code == 2
    assert "Error: No such command 'does-not-exist'." in result.output
    assert "Hint:" in result.output
    assert "builder --help" in result.output


def test_root_invalid_command_supports_global_json():
    result = runner.invoke(app, ["--json", "does-not-exist"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["error"]["message"] == "No such command 'does-not-exist'."
    assert payload["next"] == "builder --help"
    assert payload["error"]["hint"] == "builder --help"


def test_root_invalid_option_supports_global_json():
    result = runner.invoke(app, ["--json", "--badflag"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["error"]["message"] == "No such option: --badflag"
    assert payload["next"] == "builder --help"


def test_logs_command_reads_error_events_from_local_db(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-1", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-1",
            "sess-1",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--error", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["event_type"] == "tool_error"
    assert payload["results"][0]["tool_name"] == "mcp__builder__kb_add"


def test_logs_resolves_unique_session_prefix(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("2bbc4443-cc7a-42ab-8f6b-767967966ffe", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-1",
            "2bbc4443-cc7a-42ab-8f6b-767967966ffe",
            "run_status",
            json.dumps({"running": False, "tokens_used": 12, "stop_reason": "end_turn"}),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--session", "2bbc4443", "--info", "--compact", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["input_focus"] == "tokens_used=12; stop_reason=end_turn"


def test_script_list_includes_package_fallback_scripts(monkeypatch, tmp_path):
    scripts_dir = tmp_path / ".agent-builder" / "scripts"
    scripts_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["script", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = {item["name"] for item in payload["data"]}
    assert "build_verify" in names
    assert "change_evidence" in names


def test_build_verify_script_runs_node_workspace_checks(monkeypatch, tmp_path):
    scripts_dir = tmp_path / ".agent-builder" / "scripts"
    scripts_dir.mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "verify-fixture",
                "private": True,
                "scripts": {
                    "lint": "node -e \"console.log('lint passed')\"",
                    "build": "node -e \"console.log('build passed')\"",
                    "test": "node -e \"console.log('test passed')\"",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "script",
            "run",
            "build_verify",
            "--args",
            json.dumps({"project_root": str(tmp_path), "timeout": 20}),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    checks = payload["data"]["checks"]
    assert [check["code"] for check in checks] == [
        "npm_install",
        "npm_lint",
        "npm_build",
        "npm_test",
    ]
    assert all(check["status"] == "passed" for check in checks)


def test_change_evidence_script_reports_git_diff(monkeypatch, tmp_path):
    scripts_dir = tmp_path / ".agent-builder" / "scripts"
    scripts_dir.mkdir(parents=True)
    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    git_env = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        },
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, env=git_env)
    subprocess.run(
        ["git", "add", "tracked.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=git_env,
    )
    (tmp_path / "tracked.txt").write_text("before\nafter\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["script", "run", "change_evidence", "--args", "{}", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["has_changes"] is True
    assert payload["data"]["files_changed"] == 1
    assert payload["data"]["files"][0]["path"] == "tracked.txt"


def test_logs_analyze_returns_prompt_level_observability(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    session_id = "2bbc4443-cc7a-42ab-8f6b-767967966ffe"
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        (session_id, "sdk-1", "2026-04-22 10:00:00", "2026-04-22 10:00:03"),
    )
    events = [
        ("u1", "user_message", {"content": "which project is this?"}, "2026-04-22 10:00:00"),
        ("t1", "tool_result", {"tool_name": "Glob", "tool_input": {"pattern": "README*"}}, "2026-04-22 10:00:01"),
        ("a1", "assistant_message", {"content": "This is autonomous-agent-builder."}, "2026-04-22 10:00:02"),
        (
            "s1",
            "run_status",
            {
                "running": False,
                "tokens_used": 42,
                "tokens_input": 40,
                "tokens_output": 2,
                "tokens_cached": 30,
                "raw_tokens": 42,
                "noncached_plus_output_tokens": 12,
                "cost_usd": 0.01,
                "duration_ms": 1000,
                "stop_reason": "end_turn",
                "sdk_session_id": "sdk-1",
                "observability": {
                    "source": "runtime_env",
                    "enabled": True,
                    "metrics_exporter": "otlp",
                    "logs_exporter": "otlp",
                    "traces_exporter": "otlp",
                    "enhanced_tracing": True,
                    "detailed_beta_tracing": False,
                    "service_name": "autonomous-agent-builder",
                    "resource_attributes": "deployment.environment=test",
                    "headers_configured": False,
                    "endpoint_configured": True,
                    "export_intervals_ms": {"metrics": "2000", "logs": "1000", "traces": "1000"},
                    "sensitive_data_flags": [],
                    "signal_state": {"metrics": True, "logs": True, "traces": True},
                },
            },
            "2026-04-22 10:00:03",
        ),
    ]
    for event_id, event_type, payload, created_at in events:
        conn.execute(
            "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
            (event_id, session_id, event_type, json.dumps(payload), "completed", created_at),
        )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "analyze", "--session", "2bbc4443", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == session_id
    assert payload["sdk_session_id"] == "sdk-1"
    assert payload["prompt_count"] == 1
    assert payload["total_tokens"] == 42
    assert payload["raw_token_total"] == 42
    assert payload["input_tokens"] == 40
    assert payload["output_tokens"] == 2
    assert payload["cached_tokens"] == 30
    assert payload["noncached_plus_output_tokens"] == 12
    assert payload["cache_ratio"] == 0.75
    assert payload["analysis_mode"] == "summary"
    assert "prompts" not in payload
    assert payload["token_estimate"] < 2000
    assert payload["observability_coverage"]["source"] == "runtime_env"
    assert payload["observability_coverage"]["otel"]["enabled"] is True
    assert "otel_traces_exporter" not in payload["observability_coverage"]["missing_signals"]
    assert "llm_request_span_latency" not in payload["observability_coverage"]["missing_signals"]
    assert "hook_span_timeline" in payload["observability_coverage"]["missing_signals"]
    assert payload["observability_coverage"]["next"] == (
        "OTEL is configured for metrics, logs, and traces; hook span timeline is not "
        "captured in builder-local events yet."
    )
    assert payload["observability_coverage"]["counts"]["tools"] == 1
    prompt = payload["prompt_summaries"][0]
    assert prompt["tool_names"] == ["Glob"]
    assert prompt["telemetry"]["tokens_input"] == 40
    assert prompt["telemetry"]["tokens_output"] == 2
    assert prompt["telemetry"]["tokens_cached"] == 30
    assert prompt["telemetry"]["noncached_plus_output_tokens"] == 12
    assert prompt["token_accounting"] == {
        "raw_tokens": 42,
        "input_tokens": 40,
        "output_tokens": 2,
        "cached_tokens": 30,
        "noncached_plus_output_tokens": 12,
        "cache_ratio": 0.75,
    }
    assert prompt["context_efficiency"]["grade"] == "review"
    assert "broad_file_discovery" in prompt["context_efficiency"]["signals"]

    full_result = runner.invoke(
        app,
        ["logs", "analyze", "--session", "2bbc4443", "--full", "--json"],
    )

    assert full_result.exit_code == 0
    full_payload = json.loads(full_result.stdout)
    assert "prompts" in full_payload
    assert full_payload["observability_coverage"]["otel"]["service_name"] == (
        "autonomous-agent-builder"
    )
    assert full_payload["prompts"][0]["tools"][0]["tool_name"] == "Glob"


def test_logs_analyze_surfaces_task_dispatch_correlation(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    session_id = "dispatch-only-session"
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        (session_id, None, "2026-04-22 10:00:00", "2026-04-22 10:00:03"),
    )
    dispatch_payload = {
        "status": "dispatched",
        "task_id": "task-1",
        "current_status": "implementation",
    }
    events = [
        ("u1", "user_message", {"content": "Continue building my app."}, "2026-04-22 10:00:00"),
        (
            "t1",
            "tool_result",
            {
                "tool_name": "mcp__builder__task_dispatch",
                "content": json.dumps(dispatch_payload),
            },
            "2026-04-22 10:00:01",
        ),
        (
            "s1",
            "run_status",
            {
                "running": False,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "stop_reason": "task_dispatched",
                "dispatch": dispatch_payload,
            },
            "2026-04-22 10:00:02",
        ),
    ]
    for event_id, event_type, payload, created_at in events:
        conn.execute(
            "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
            (event_id, session_id, event_type, json.dumps(payload), "completed", created_at),
        )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "analyze", "--session", session_id, "--full", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    prompt = payload["prompts"][0]
    assert prompt["telemetry"]["running"] is False
    assert prompt["telemetry"]["stop_reason"] == "task_dispatched"
    assert prompt["telemetry"]["dispatch"] == dispatch_payload
    assert prompt["tools"][0]["dispatch"] == dispatch_payload


def test_logs_analyze_resolves_agent_run_prefix_without_chat_timeline(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table agent_runs (
            id varchar(36) primary key,
            task_id varchar(36),
            agent_name varchar(100),
            runtime_sdk varchar(50),
            provider varchar(100),
            model varchar(100),
            effort varchar(50),
            cost_usd real default 0,
            estimated_cost_usd real default 0,
            tokens_input integer default 0,
            tokens_output integer default 0,
            tokens_cached integer default 0,
            num_turns integer default 0,
            duration_ms integer default 0,
            stop_reason varchar(100),
            status varchar(50),
            observability json,
            started_at datetime default current_timestamp
        );
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        ("run-abcdef", None, "2026-05-13 10:00:00", "2026-05-13 10:00:00"),
    )
    conn.execute(
        """
        insert into agent_runs (
            id, task_id, agent_name, runtime_sdk, provider, model, effort,
            cost_usd, estimated_cost_usd, tokens_input, tokens_output, tokens_cached,
            num_turns, duration_ms, stop_reason, status, observability, started_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-abcdef",
            "task-1",
            "agent-chat",
            "codex_sdk",
            "codex_subscription",
            "gpt-5.5",
            "medium",
            0.0,
            1.25,
            1000,
            250,
            500,
            3,
            1200,
            "completed",
            "completed",
            json.dumps({"event_accounting": {"raw_event_count": 12}}),
            "2026-05-13 10:00:00",
        ),
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "analyze", "--session", "run-abc", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "run-abcdef"
    assert payload["analysis_target"] == "agent_run"
    assert payload["prompt_count"] == 0
    assert payload["total_tokens"] == 1250
    assert payload["total_cost_usd"] == 1.25
    assert payload["agent_run_evidence"]["agent_name"] == "agent-chat"
    assert payload["agent_run_evidence"]["observability_available"] is True
    assert payload["raw_evidence"]["available"] is True
    assert payload["raw_evidence"]["note"] == (
        "no chat timeline events resolved; using persisted AgentRun observability for this run"
    )


def test_logs_ndjson_emits_line_delimited_compact_events(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-ndjson", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-ndjson",
            "sess-ndjson",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--session", "sess-ndjson", "--error", "--compact", "--ndjson", "--no-follow"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "tool_error"
    assert payload["tool_name"] == "mcp__builder__kb_add"
    assert payload["outcome"] == "error"
    assert payload["error_message"] == "Missing required sections for feature: Current behavior"


def test_logs_follow_ndjson_uses_info_selector_without_signature_errors(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_load_rows(**kwargs):
        calls.append(kwargs)
        if len(calls) > 1:
            raise KeyboardInterrupt()
        return []

    monkeypatch.setattr(logs_module, "_load_rows", fake_load_rows)
    monkeypatch.setattr(logs_module.time, "sleep", lambda _: None)

    result = runner.invoke(app, ["logs", "--info", "--follow", "--ndjson"])

    assert result.exit_code == 0
    assert len(calls) == 2
    assert calls[0]["info_only"] is True
    assert calls[1]["info_only"] is True


def test_logs_info_ndjson_auto_compacts_filtered_lane(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-ndjson-info", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-ndjson-info",
            "sess-ndjson-info",
            "run_status",
            json.dumps(
                {
                    "running": False,
                    "current_turn": 1,
                    "max_turns": 15,
                    "tokens_used": 164,
                    "cost_usd": 0.0307,
                    "duration_ms": 3216,
                    "stop_reason": "end_turn",
                    "sdk_session_id": "sdk-sess-info",
                }
            ),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--session", "sess-ndjson-info", "--info", "--ndjson", "--no-follow"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "run_status"
    assert payload["tool_name"] == "Agent"
    assert payload["summary"] == "Agent run completed"
    assert "current_turn=1" in payload["input_focus"]


def test_logs_rejects_json_and_ndjson_together():
    result = runner.invoke(app, ["logs", "--json", "--ndjson"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_usage"


def test_logs_help_includes_raw_mode():
    result = runner.invoke(app, ["logs", "--help"])

    assert result.exit_code == 0
    assert "--raw" in result.stdout
    assert "Emit exact stored event" in result.stdout


def test_logs_rejects_raw_and_compact_together():
    result = runner.invoke(app, ["logs", "--raw", "--compact", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_usage"


def test_logs_raw_json_returns_exact_event_rows(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-raw", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, tool_use_id, response_to_event_id, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "evt-raw",
            "sess-raw",
            "tool_result",
            json.dumps(
                {
                    "tool_name": "mcp__builder__board",
                    "content": "{\"status\":\"ok\"}",
                }
            ),
            "completed",
            "toolu_123",
            "evt-parent",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--session", "sess-raw", "--raw", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    event = payload["results"][0]
    assert event == {
        "id": "evt-raw",
        "session_id": "sess-raw",
        "event_type": "tool_result",
        "status": "completed",
        "payload": {
            "tool_name": "mcp__builder__board",
            "content": "{\"status\":\"ok\"}",
        },
        "tool_use_id": "toolu_123",
        "response_to_event_id": "evt-parent",
        "created_at": "2026-04-22 10:00:01",
    }
    assert payload["next_step"] == "builder logs --session <id> --raw --json"


def test_logs_raw_ndjson_emits_line_delimited_event_rows(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-raw-ndjson", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, tool_use_id, response_to_event_id, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "evt-raw-ndjson",
            "sess-raw-ndjson",
            "tool_error",
            json.dumps({"tool_name": "mcp__builder__kb_show", "content": "not found"}),
            "completed",
            "toolu_ndjson",
            None,
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "--session", "sess-raw-ndjson", "--raw", "--ndjson", "--no-follow"],
    )

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "tool_error"
    assert payload["tool_use_id"] == "toolu_ndjson"
    assert payload["response_to_event_id"] is None
    assert payload["payload"]["tool_name"] == "mcp__builder__kb_show"


def test_logs_raw_json_respects_type_and_limit_filters(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-raw-filters", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    rows = [
        (
            "evt-tool-1",
            "sess-raw-filters",
            "tool_result",
            json.dumps({"tool_name": "mcp__builder__board", "content": "first"}),
            "completed",
            "toolu_1",
            None,
            "2026-04-22 10:00:01",
        ),
        (
            "evt-run",
            "sess-raw-filters",
            "run_status",
            json.dumps({"running": False}),
            "completed",
            None,
            None,
            "2026-04-22 10:00:02",
        ),
        (
            "evt-tool-2",
            "sess-raw-filters",
            "tool_result",
            json.dumps({"tool_name": "mcp__builder__board", "content": "second"}),
            "completed",
            "toolu_2",
            "evt-tool-1",
            "2026-04-22 10:00:03",
        ),
    ]
    conn.executemany(
        "insert into chat_events (id, session_id, event_type, payload_json, status, tool_use_id, response_to_event_id, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "logs",
            "--session",
            "sess-raw-filters",
            "--raw",
            "--type",
            "tool_result",
            "--tool",
            "mcp__builder__board",
            "--limit",
            "1",
            "--json",
            "--no-follow",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "evt-tool-2"


def test_logs_raw_json_regression_surface_shows_board_and_kb_without_backlog_tools(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("2bbc4443-cc7a-42ab-8f6b-767967966ffe", "2026-04-25 16:49:54", "2026-04-25 16:55:26"),
    )
    rows = [
        (
            "evt-board",
            "2bbc4443-cc7a-42ab-8f6b-767967966ffe",
            "tool_result",
            json.dumps({"tool_name": "mcp__builder__board", "content": "{\"pending\":[]}"}),
            "completed",
            "toolu_board",
            None,
            "2026-04-25 16:50:03",
        ),
        (
            "evt-kb",
            "2bbc4443-cc7a-42ab-8f6b-767967966ffe",
            "tool_result",
            json.dumps({"tool_name": "mcp__builder__kb_show", "content": "{\"id\":\"system-docs/project-overview.md\"}"}),
            "completed",
            "toolu_kb",
            None,
            "2026-04-25 16:54:49",
        ),
    ]
    conn.executemany(
        "insert into chat_events (id, session_id, event_type, payload_json, status, tool_use_id, response_to_event_id, created_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "--session", "2bbc4443", "--raw", "--json", "--no-follow"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    tool_names = [event["payload"].get("tool_name", "") for event in payload["results"]]
    assert "mcp__builder__board" in tool_names
    assert "mcp__builder__kb_show" in tool_names
    assert "mcp__builder__backlog_item_list" not in tool_names


def test_logs_command_supports_info_compact(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-2", "2026-04-22 11:00:00", "2026-04-22 11:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-2",
            "sess-2",
            "tool_result",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "tool_input": {"doc_type": "feature"},
                    "content": "{\"status\":\"ok\",\"id\":\"feature/doc.md\"}",
                }
            ),
            "completed",
            "2026-04-22 11:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--info", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["next_step"] == "builder logs --session <id> --compact --json"
    event = payload["results"][0]
    assert event["event_type"] == "tool_result"
    assert event["tool_name"] == "mcp__builder__kb_add"
    assert event["outcome"] == "ok"
    assert event["input_focus"] == "doc_type=feature"
    assert event["summary"] == "mcp__builder__kb_add: feature/doc.md"
    assert "error_message" not in event
    assert event["next_action"] == "Expand raw output only if the compact digest is insufficient."


def test_logs_error_json_includes_failed_realtime_voice_tool_output(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-voice", "2026-05-10 07:54:00", "2026-05-10 07:54:00"),
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-latest", "2026-05-10 08:00:00", "2026-05-10 08:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-voice-failed",
            "sess-voice",
            "voice_tool_output",
            json.dumps(
                {
                    "tool_name": "delegate_to_builder_agent",
                    "tool_call_id": "call_123",
                    "ok": False,
                    "error": "This chat session is already running",
                }
            ),
            "failed",
            "2026-05-10 07:54:01",
        ),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-latest-ok",
            "sess-latest",
            "assistant_message",
            json.dumps({"content": "latest session has no errors"}),
            "completed",
            "2026-05-10 08:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--error", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    event = payload["results"][0]
    assert event["event_type"] == "voice_tool_output"
    assert event["tool_name"] == "delegate_to_builder_agent"
    assert event["outcome"] == "error"
    assert event["error_message"] == "This chat session is already running"
    assert event["next_action"] == "Inspect Realtime function-call arguments and sideband concurrency."


def test_logs_info_json_summarizes_realtime_voice_tool_output_result(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-voice", "2026-05-10 07:54:00", "2026-05-10 07:54:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-voice-ok",
            "sess-voice",
            "voice_tool_output",
            json.dumps(
                {
                    "tool_name": "delegate_to_builder_agent",
                    "tool_call_id": "call_123",
                    "ok": True,
                    "result_status": "not_recoverable",
                    "completion_status": "not_recoverable",
                    "capability_decision": "not_recoverable",
                    "recommended_tool": "open_run_trace",
                    "result_message": "No recoverable Board task is currently blocked.",
                }
            ),
            "completed",
            "2026-05-10 07:54:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--info", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    event = payload["results"][0]
    assert event["event_type"] == "voice_tool_output"
    assert event["tool_name"] == "delegate_to_builder_agent"
    assert event["outcome"] == "ok"
    assert event["summary"] == "Realtime voice delegate_to_builder_agent ok (not_recoverable)"
    assert event["input_focus"] == "call_id=call_123; result=not_recoverable"


def test_logs_run_status_json_compacts_sdk_telemetry(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-run", "2026-04-22 11:00:00", "2026-04-22 11:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-run",
            "sess-run",
            "run_status",
            json.dumps(
                {
                    "running": False,
                    "current_turn": 2,
                    "max_turns": 15,
                    "tokens_used": 42,
                    "cost_usd": 0.03,
                    "duration_ms": 1234,
                    "stop_reason": "end_turn",
                    "sdk_session_id": "sdk-sess-run",
                }
            ),
            "completed",
            "2026-04-22 11:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "--session", "sess-run", "--type", "run_status", "--compact", "--json", "--no-follow"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    event = payload["results"][0]
    assert event["event_type"] == "run_status"
    assert event["tool_name"] == "Agent"
    assert event["outcome"] == "completed"
    assert event["summary"] == "Agent run completed"
    assert "duration_ms=1234" in event["input_focus"]
    assert "stop_reason=end_turn" in event["input_focus"]
    assert "sdk_session_id=sdk-sess-run" in event["input_focus"]


def test_logs_run_status_marks_provider_limit_blocked(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        ("sess-limit", "sdk-sess-limit", "2026-04-22 11:00:00", "2026-04-22 11:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-limit",
            "sess-limit",
            "run_status",
            json.dumps(
                {
                    "running": False,
                    "current_turn": 0,
                    "max_turns": 20,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                    "duration_ms": 0,
                    "stop_reason": "provider_limit",
                    "provider_limit": {
                        "code": "provider_limit",
                        "reset_hint": "resets 11:10pm",
                        "source": "claude_agent_sdk",
                    },
                    "sdk_session_id": "sdk-sess-limit",
                }
            ),
            "blocked",
            "2026-04-22 11:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "--session", "sess-limit", "--type", "run_status", "--compact", "--json", "--no-follow"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    event = payload["results"][0]
    assert event["outcome"] == "blocked"
    assert event["summary"] == "Agent run blocked"
    assert "stop_reason=provider_limit" in event["input_focus"]


def test_logs_info_includes_run_status_when_no_tool_results_exist(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        ("sess-info", "sdk-sess-info", "2026-04-22 11:30:00", "2026-04-22 11:30:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-info",
            "sess-info",
            "run_status",
            json.dumps(
                {
                    "running": False,
                    "current_turn": 1,
                    "max_turns": 15,
                    "tokens_used": 164,
                    "cost_usd": 0.0307,
                    "duration_ms": 3216,
                    "stop_reason": "end_turn",
                    "sdk_session_id": "sdk-sess-info",
                }
            ),
            "completed",
            "2026-04-22 11:30:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--info", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    event = payload["results"][0]
    assert event["event_type"] == "run_status"
    assert event["summary"] == "Agent run completed"


def test_logs_analyze_includes_runtime_aggregates(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        create table agent_runs (
            id varchar(36) primary key,
            task_id varchar(36) not null,
            agent_name varchar(50) not null,
            cost_usd float not null default 0,
            tokens_input integer not null default 0,
            tokens_output integer not null default 0,
            tokens_cached integer not null default 0,
            num_turns integer not null default 0,
            duration_ms integer not null default 0,
            stop_reason varchar(50),
            status varchar(20) not null default 'completed'
        );
        create table approval_gates (
            id varchar(36) primary key,
            task_id varchar(36) not null,
            gate_type varchar(50) not null,
            status varchar(20) not null,
            created_at datetime not null,
            resolved_at datetime
        );
        create table tasks (
            id varchar(36) primary key,
            status varchar(50) not null,
            depends_on json
        );
        create table agent_run_events (
            id varchar(36) primary key,
            run_id varchar(36) not null,
            event_type varchar(50) not null,
            tool_name varchar(100)
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        ("sess-analyze", "sdk-analyze", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-user",
            "sess-analyze",
            "user_message",
            json.dumps({"content": "Continue building my app."}),
            "completed",
            "2026-04-22 12:00:01",
        ),
    )
    conn.executemany(
        "insert into agent_runs (id, task_id, agent_name, cost_usd, tokens_output, num_turns, duration_ms, stop_reason, status) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("run-plan", "task-1", "planner", 0.4, 4000, 20, 1000, "end_turn", "completed"),
            ("run-design", "task-1", "designer", 0.6, 6000, 15, 2000, "end_turn", "completed"),
            ("run-code", "task-1", "code-gen", 0.5, 7000, 25, 3000, "end_turn", "completed"),
        ],
    )
    conn.execute(
        "insert into approval_gates (id, task_id, gate_type, status, created_at, resolved_at) values (?, ?, ?, ?, ?, ?)",
        (
            "gate-1",
            "task-1",
            "planning",
            "approve",
            "2026-04-22 12:00:00",
            "2026-04-22 12:01:00",
        ),
    )
    conn.execute(
        "insert into tasks (id, status, depends_on) values (?, ?, ?)",
        (
            "task-limit",
            "capability_limit",
            json.dumps({"provider_limit": {"reset_at": "2026-04-22T12:30:00+00:00"}}),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "analyze", "--session", "sess-analyze", "--full", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    aggregates = payload["runtime_aggregates"]
    assert aggregates["available"] is True
    assert aggregates["totals"]["runs"] == 3
    assert aggregates["phase_ceremony"]["flag"] == "planning_design_exceeds_implementation"
    assert aggregates["approval_wait"]["total"] == 1
    assert aggregates["provider_limits"]["count"] == 1
    assert aggregates["tool_observability"]["missing_tool_events"] is True
    assert payload["raw_token_total"] == 17000
    assert payload["phase_ceremony_tokens"] == 10000
    assert payload["top_cost_drivers"][0]["agent_name"] == "code-gen"
    assert payload["recommended_next_change"]
    assert payload["raw_evidence"]["available"] is True
    assert payload["raw_evidence"]["event_count"] == 1


def test_logs_analyze_scopes_runtime_aggregates_to_chat_session(monkeypatch, tmp_path):
    """`analyze --session <id>` must not bleed other sessions' agent_runs.

    Two chat sessions each drive their own task with disjoint agent runs.
    Aggregates (totals, by_agent, top_cost_drivers, raw_token_total) must
    surface only the targeted session's numbers — the M2.3 contract.
    """
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        create table tasks (
            id varchar(36) primary key,
            chat_session_id varchar(36),
            status varchar(50) not null,
            depends_on json
        );
        create table agent_runs (
            id varchar(36) primary key,
            task_id varchar(36) not null,
            agent_name varchar(50) not null,
            cost_usd float not null default 0,
            tokens_input integer not null default 0,
            tokens_output integer not null default 0,
            tokens_cached integer not null default 0,
            num_turns integer not null default 0,
            duration_ms integer not null default 0,
            stop_reason varchar(50),
            status varchar(20) not null default 'completed'
        );
        create table approval_gates (
            id varchar(36) primary key,
            task_id varchar(36) not null,
            gate_type varchar(50) not null,
            status varchar(20) not null,
            created_at datetime not null,
            resolved_at datetime
        );
        create table agent_run_events (
            id varchar(36) primary key,
            run_id varchar(36) not null,
            event_type varchar(50) not null,
            tool_name varchar(100)
        );
        """
    )
    conn.executemany(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        [
            ("sess-A", "sdk-A", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
            ("sess-B", "sdk-B", "2026-04-22 12:05:00", "2026-04-22 12:05:00"),
        ],
    )
    conn.executemany(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        [
            (
                "evt-A",
                "sess-A",
                "user_message",
                json.dumps({"content": "Build feature A."}),
                "completed",
                "2026-04-22 12:00:01",
            ),
            (
                "evt-B",
                "sess-B",
                "user_message",
                json.dumps({"content": "Build feature B."}),
                "completed",
                "2026-04-22 12:05:01",
            ),
        ],
    )
    conn.executemany(
        "insert into tasks (id, chat_session_id, status, depends_on) values (?, ?, ?, ?)",
        [
            ("task-A", "sess-A", "running", None),
            ("task-B", "sess-B", "running", None),
        ],
    )
    conn.executemany(
        "insert into agent_runs (id, task_id, agent_name, cost_usd, tokens_input, tokens_output, num_turns, duration_ms, stop_reason, status) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("run-A1", "task-A", "code-gen", 0.5, 1000, 500, 10, 1000, "end_turn", "completed"),
            ("run-A2", "task-A", "scaffold", 0.2, 400, 200, 5, 500, "end_turn", "completed"),
            ("run-B1", "task-B", "feature-verifier", 0.9, 9000, 4500, 30, 5000, "end_turn", "completed"),
            ("run-B2", "task-B", "build-verifier", 0.7, 6000, 3000, 20, 3000, "end_turn", "completed"),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result_a = runner.invoke(
        app, ["logs", "analyze", "--session", "sess-A", "--full", "--json"]
    )
    assert result_a.exit_code == 0, result_a.stdout
    payload_a = json.loads(result_a.stdout)
    aggs_a = payload_a["runtime_aggregates"]
    assert aggs_a["session_scoped"] is True
    assert aggs_a["totals"]["runs"] == 2
    agent_names_a = sorted(row["agent_name"] for row in aggs_a["by_agent"])
    assert agent_names_a == ["code-gen", "scaffold"]
    assert "feature-verifier" not in agent_names_a
    assert "build-verifier" not in agent_names_a
    assert payload_a["raw_token_total"] == 2100  # (1000+500) + (400+200)

    result_b = runner.invoke(
        app, ["logs", "analyze", "--session", "sess-B", "--full", "--json"]
    )
    assert result_b.exit_code == 0, result_b.stdout
    payload_b = json.loads(result_b.stdout)
    aggs_b = payload_b["runtime_aggregates"]
    assert aggs_b["session_scoped"] is True
    assert aggs_b["totals"]["runs"] == 2
    agent_names_b = sorted(row["agent_name"] for row in aggs_b["by_agent"])
    assert agent_names_b == ["build-verifier", "feature-verifier"]
    assert "code-gen" not in agent_names_b
    assert payload_b["raw_token_total"] == 22500  # (9000+4500) + (6000+3000)


def test_logs_analyze_does_not_flag_tool_events_before_first_run(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            sdk_session_id varchar(255),
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        create table agent_runs (
            id varchar(36) primary key,
            task_id varchar(36) not null,
            agent_name varchar(50) not null,
            cost_usd float not null default 0,
            tokens_input integer not null default 0,
            tokens_output integer not null default 0,
            tokens_cached integer not null default 0,
            num_turns integer not null default 0,
            duration_ms integer not null default 0,
            stop_reason varchar(50),
            status varchar(20) not null default 'completed'
        );
        create table agent_run_events (
            id varchar(36) primary key,
            run_id varchar(36) not null,
            event_type varchar(50) not null,
            tool_name varchar(100)
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, sdk_session_id, created_at, updated_at) values (?, ?, ?, ?)",
        ("sess-empty", "sdk-empty", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-empty",
            "sess-empty",
            "assistant_message",
            json.dumps({"content": "What do you want to build?"}),
            "completed",
            "2026-04-22 12:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "analyze", "--session", "sess-empty", "--full", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    aggregates = payload["runtime_aggregates"]
    assert aggregates["totals"]["runs"] == 0
    assert aggregates["tool_observability"]["agent_run_events_available"] is True
    assert aggregates["tool_observability"]["agent_run_event_count"] == 0
    assert aggregates["tool_observability"]["missing_tool_events"] is False


def test_logs_default_lane_includes_specialist_status(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-specialist", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-specialist",
            "sess-specialist",
            "specialist_status",
            json.dumps(
                {
                    "specialist": "documentation-agent",
                    "phase": "discovering",
                    "content": "Scanning maintained docs.",
                }
            ),
            "completed",
            "2026-04-22 12:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["event_type"] == "specialist_status"


def test_logs_error_json_auto_compacts_filtered_lane(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-3", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-3",
            "sess-3",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 12:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--error", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    event = payload["results"][0]
    assert event["event_type"] == "tool_error"
    assert event["tool_name"] == "mcp__builder__kb_add"
    assert event["outcome"] == "error"
    assert event["error_message"] == "Missing required sections for feature: Current behavior"


def test_kb_summary_json_stays_triage_sized(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/builder-cli-surface.md",
        (
            "---\n"
            "title: Builder CLI Surface\n"
            "tags: [feature, cli, builder, commands, operator]\n"
            "version: 7\n"
            "card_summary: The builder CLI is the repo-local operator and agent interface.\n"
            "detail_summary: Start with doctor and map, then use page-aligned commands for targeted retrieval.\n"
            "---\n\n"
            "# Builder CLI Surface\n\n"
            "## Change guidance\n\n"
            "Keep JSON compact by default and expand only behind explicit full reads.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "builder", "cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "system-docs/builder-cli-surface.md"
    assert payload["preview"] == "The builder CLI is the repo-local operator and agent interface."
    assert payload["detail"] == "Start with doctor and map, then use page-aligned commands for targeted retrieval."
    assert payload["change_guidance"] == "Keep JSON compact by default and expand only behind explicit full reads."
    assert payload["next_step"] == "builder knowledge show system-docs/builder-cli-surface.md --section 'Change guidance' --json"


def test_root_help_exposes_page_aligned_surfaces():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "agent" in result.output
    assert "board" in result.output
    assert "backlog" in result.output
    assert "knowledge" in result.output
    assert "memory" in result.output
    assert "metrics" in result.output
    assert "│ project" not in result.output
    assert "│ feature" not in result.output
    assert "│ approval" not in result.output
    assert "run           " not in result.output
    assert "kb            " not in result.output


def test_legacy_top_level_commands_are_removed():
    for command in ("project", "feature", "task", "approval", "run", "kb"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 2
        assert f"No such command '{command}'." in result.output


def test_backlog_and_knowledge_surfaces_are_registered():
    backlog_result = runner.invoke(app, ["backlog", "--help"])
    knowledge_result = runner.invoke(app, ["knowledge", "--help"])
    agent_result = runner.invoke(app, ["agent", "--help"])
    board_result = runner.invoke(app, ["board", "--help"])
    metrics_result = runner.invoke(app, ["metrics", "--help"])
    map_result = runner.invoke(app, ["map", "--help"])
    context_result = runner.invoke(app, ["context", "--help"])
    item_result = runner.invoke(app, ["backlog", "item", "--help"])
    feature_result = runner.invoke(app, ["backlog", "feature", "--help"])

    assert backlog_result.exit_code == 0
    assert "Backlog planning and execution surfaces." in backlog_result.output
    assert "project" in backlog_result.output
    assert "item" in backlog_result.output
    assert "feature" not in backlog_result.output
    assert "task" in backlog_result.output
    assert "approval" in backlog_result.output
    assert "run" in backlog_result.output
    assert item_result.exit_code == 0
    assert feature_result.exit_code == 2

    assert knowledge_result.exit_code == 0
    assert "search" in knowledge_result.output
    assert "extract" in knowledge_result.output

    assert agent_result.exit_code == 0
    assert "Agent chat sessions and runtime metadata." in agent_result.output
    assert "sessions" in agent_result.output
    assert "history" in agent_result.output
    assert "meta" in agent_result.output
    assert "runtime" in agent_result.output

    assert board_result.exit_code == 0
    assert "active-work routing" in board_result.output
    assert "show" in board_result.output

    assert metrics_result.exit_code == 0
    assert "Cost and verification metrics." in metrics_result.output
    assert "show" in metrics_result.output

    assert map_result.exit_code == 0
    assert "startup orientation" in map_result.output

    assert context_result.exit_code == 0
    assert "named profiles" in context_result.output


def test_agent_runtime_set_rejects_codex_cli_user_facing_lane(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "agent",
            "runtime",
            "set",
            "--sdk",
            "codex_cli",
            "--provider",
            "codex_subscription",
            "--model",
            "gpt-5.5",
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["sdk"] == "codex_cli"
    assert payload["status"] == "error"
    assert payload["code"] == "invalid_sdk"
    assert not Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).exists()


def test_agent_runtime_set_persists_claude_env_and_disables_codex(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(
        'AAB_CLAUDE_OTEL_ENABLED="0"\nAAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "agent",
            "runtime",
            "set",
            "--sdk",
            "claude",
            "--provider",
            "claude_agent_sdk",
            "--model",
            "sonnet",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sdk"] == "claude"
    assert payload["provider"] == "claude_agent_sdk"
    assert payload["auth"]["method"] == "claude_code_oauth_token"
    assert payload["auth"]["api_key_used"] is False
    assert payload["telemetry"]["active_lane"] == "claude"
    env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="claude"' in env_text
    assert 'RUNTIME_PROVIDER="claude_agent_sdk"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="1"' in env_text
    assert 'AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING="1"' in env_text
    assert 'AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES="0"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"' in env_text


def test_agent_runtime_set_persists_codex_sdk_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "agent",
            "runtime",
            "set",
            "--sdk",
            "codex_sdk",
            "--provider",
            "codex_subscription",
            "--model",
            "gpt-5.5",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sdk"] == "codex_sdk"
    assert payload["provider"] == "codex_subscription"
    env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="codex_sdk"' in env_text
    assert 'RUNTIME_PROVIDER="codex_subscription"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text
    assert 'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"' in env_text
    assert "AAB_CODEX_JSONL_TELEMETRY_ENABLED" not in env_text
    assert payload["telemetry"]["active_lane"] == "codex"
    assert "RUNTIME_API_KEY_ENV" not in env_text


def test_agent_runtime_show_reports_codex_cli_as_invalid_user_facing_lane(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: SimpleNamespace(
            runtime=SimpleNamespace(
                sdk="codex_cli",
                provider="codex_subscription",
                model="gpt-5.5",
                api_base_url=None,
                api_key_env=None,
                codex_profile=None,
                sandbox_mode="workspace-write",
                approval_policy="never",
                tracing="builder",
            )
        ),
    )

    result = runner.invoke(app, ["agent", "runtime", "show", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["sdk"] == "codex_cli"
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid_sdk"
    assert "capabilities" not in payload


def test_agent_runtime_show_reports_codex_sdk_capabilities(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: SimpleNamespace(
            runtime=SimpleNamespace(
                sdk="codex_sdk",
                provider="codex_subscription",
                model="gpt-5.5",
                api_base_url=None,
                api_key_env=None,
                codex_profile=None,
                sandbox_mode="workspace-write",
                approval_policy="never",
                tracing="builder",
            )
        ),
    )

    result = runner.invoke(app, ["agent", "runtime", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sdk"] == "codex_sdk"
    assert payload["capabilities"]["subscription_auth"] is True
    assert payload["capabilities"]["tools"] is True
    assert payload["capabilities"]["app_server_events"] is True
    assert payload["capabilities"]["native_user_input"] is True


def test_memory_summary_resolves_natural_query(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decisions = memory_root / "decisions"
    decisions.mkdir(parents=True)
    body = "## Summary\n\nUse the builder retrieval surface.\n"
    payload = {
        "slug": "decision-builder-cli",
        "title": "Builder CLI retrieval precedent",
        "type": "decision",
        "date": "2026-01-01",
        "phase": "implementation",
        "entity": "builder-cli",
        "tags": ["cli", "retrieval"],
        "status": "active",
    }
    decisions.joinpath("decision-builder-cli.md").write_text(
        memory_module._build_memory_markdown(payload, body),
        encoding="utf-8",
    )
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "summary", "builder", "retrieval", "--json"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["id"] == "decision-builder-cli"
    assert response["matched_on"] in {"search", "name", "prefix"}


def test_agent_sessions_json_is_agent_friendly(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: {
            "sessions": [
                {
                    "id": "sess-1",
                    "sdk_session_id": "sdk-sess-1",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "message_count": 3,
                    "preview": "Latest agent turn",
                }
            ]
        },
    )

    result = runner.invoke(app, ["agent", "sessions", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "sess-1"
    assert payload["results"][0]["sdk_session_id"] == "sdk-sess-1"
    assert payload["next_step"] == "builder agent history --session sess-1 --json"
    assert payload["progressive_disclosure"][2]["command"] == "builder agent sessions --json --full"


def test_agent_history_json_exposes_sdk_result_telemetry(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: {
            "session_id": "sess-1",
            "sdk_session_id": "sdk-sess-1",
            "model": "haiku",
            "repo_identity": "/repo",
            "workspace_cwd": "/repo",
            "messages": [{"role": "assistant", "content": "done"}],
            "status": {
                "running": False,
                "current_turn": 2,
                "max_turns": 15,
                "tokens_used": 42,
                "cost_usd": 0.03,
                "duration_ms": 1234,
                "stop_reason": "end_turn",
                "sdk_session_id": "sdk-sess-1",
            },
        },
    )

    result = runner.invoke(app, ["agent", "history", "--session", "sess-1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "sess-1"
    assert payload["sdk_session_id"] == "sdk-sess-1"
    assert payload["status"]["duration_ms"] == 1234
    assert payload["status"]["stop_reason"] == "end_turn"
    assert payload["status"]["sdk_session_id"] == "sdk-sess-1"


def test_agent_sessions_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(BuilderConnectivityError("http://127.0.0.1:9876")),
    )
    monkeypatch.setattr(
        agent_module,
        "load_local_agent_sessions",
        lambda limit: {
            "status": "ok",
            "count": 1,
            "results": [{"id": "sess-local", "updated_at": "2026-01-01T00:00:00Z", "message_count": 2, "preview": "Local session"}],
            "schema_version": "1",
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder agent history --session <id> --json",
        },
    )

    result = runner.invoke(app, ["agent", "sessions", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["results"][0]["id"] == "sess-local"
    assert payload["results"][0]["preview"] == "Local session"
    assert payload["actionable_next"] == "builder agent history --session sess-local --json"
    assert payload["progressive_disclosure"][2]["command"] == "builder agent sessions --json --full"


def test_map_json_includes_next_step(monkeypatch, tmp_path):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(map_module, "_server_snapshot", lambda: {"reachable": False, "base_url": "http://127.0.0.1:9876"})

    result = runner.invoke(app, ["map", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder --json doctor"


def test_context_json_includes_next_step():
    result = runner.invoke(app, ["context", "verification", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder quality-gate quality-gates"


def test_context_readiness_profile_points_to_status_first():
    result = runner.invoke(app, ["context", "readiness", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder readiness status --json"
    assert "builder readiness assess --json" in payload["commands"]


def test_context_unknown_profile_json_returns_deterministic_guidance():
    result = runner.invoke(app, ["context", "unknown", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_context_profile"
    assert payload["next"] == "builder context --help"
    assert "verification" in payload["error"]["detail"]["valid_profiles"]


def test_invalid_builder_command_json_uses_contract_without_raw_leak():
    result = runner.invoke(app, ["--json", "does-not-exist"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    _assert_agent_json_contract(payload, ok=False)
    assert payload["code"] == "invalid_usage"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["next"] in {"builder --help", "builder doctor --json"}
    assert "Traceback" not in result.stdout
    assert "<html" not in result.stdout.lower()


def test_core_builder_json_commands_have_agent_contract(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "card_summary: Local builder project overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder local context.\n"
        ),
    )
    monkeypatch.setattr(map_module, "_server_snapshot", lambda: {"reachable": False, "base_url": "http://127.0.0.1:9876"})

    commands = [
        ["context", "verification", "--json"],
        ["map", "--json"],
        ["knowledge", "list", "--json"],
        ["knowledge", "search", "overview", "--json"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout
        _assert_agent_json_contract(json.loads(result.stdout), ok=True)


def test_memory_summary_resolves_body_text(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decisions = memory_root / "decisions"
    decisions.mkdir(parents=True)
    body = (
        "## Summary\n\n"
        "Use builder and workflow CLIs for memory and knowledge operations.\n"
    )
    payload = {
        "slug": "workflow-and-memory-creation-only-via-clis",
        "title": "Workflow and memory creation ONLY via CLIs",
        "type": "decision",
        "date": "2026-01-01",
        "phase": "implementation",
        "entity": "builder-cli",
        "tags": ["cli", "knowledge"],
        "status": "active",
    }
    decisions.joinpath("workflow-and-memory-creation-only-via-clis.md").write_text(
        memory_module._build_memory_markdown(payload, body),
        encoding="utf-8",
    )
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "summary", "workflow", "knowledge", "operations", "--json"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["id"] == "workflow-and-memory-creation-only-via-clis"
    assert response["matched_on"] in {"search", "prefix", "name"}


def test_logs_analyze_selected_runtime_prefers_observed_codex_coverage():
    from autonomous_agent_builder.cli.commands.logs import _selected_runtime_from_coverage

    assert _selected_runtime_from_coverage({"runtime_sdk": "codex_sdk"}) == "codex_sdk"
    assert _selected_runtime_from_coverage({"runtime_sdk": "claude"}) == "claude_agent_sdk"
