"""Tests for `builder agent runtime set|show` CLI surface."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import agent as agent_module
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


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
