from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder.services.runtime_settings import (
    ensure_runtime_env,
    runtime_settings_payload,
    telemetry_state,
)


@pytest.fixture(autouse=True)
def builder_source_env(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path / "builder-source.env"
    monkeypatch.setenv("AAB_BUILDER_SOURCE_ENV", str(path))
    return path


def test_codex_runtime_env_creates_project_local_otel_config(tmp_path: Path) -> None:
    result = ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config={
            "sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "codex_profile": None,
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": None,
        },
        endpoint="http://localhost:4318",
    )

    config_path = tmp_path / ".codex" / "config.toml"
    assert "CODEX_OTEL_CONFIG" in result["changed_keys"]
    assert config_path.exists()
    text = config_path.read_text(encoding="utf-8")
    assert "[otel]" in text
    assert "otlp-http" in text
    assert "http://localhost:4318/v1/logs" in text
    assert "http://localhost:4318/v1/metrics" in text
    assert "http://localhost:4318/v1/traces" in text
    assert "span_attributes" in text
    assert "tracestate" in text
    assert "[feedback]" in text
    assert "enabled = true" in text
    assert "[analytics]" in text


def test_telemetry_state_reports_project_local_codex_otel(tmp_path: Path) -> None:
    ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config={
            "sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "codex_profile": None,
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": None,
        },
        endpoint="http://collector.example.com:4318",
    )

    state = telemetry_state(tmp_path)

    assert state["active_lane"] == "codex"
    assert state["historical_access"]["available"] is True
    assert state["historical_access"]["applies_to_inactive_lanes"] is True
    assert state["codex"]["history_accessible"] is True
    assert state["codex"]["otel"]["configured"] is True
    assert state["codex"]["otel"]["project_local"] is True
    assert state["codex"]["otel"]["exporter"] == "otlp-http"
    assert state["codex"]["otel"]["emitted_signals"]["metrics"] is True
    assert state["codex"]["otel"]["emitted_signals"]["traces"] is True
    assert state["codex"]["otel"]["emitted_signals"]["trace_metadata"] is True
    assert state["codex"]["otel"]["emitted_signals"]["review_feedback"] is True
    assert state["codex"]["otel"]["emitted_signals"]["analytics"] is True
    assert state["codex"]["otel"]["span_attributes_configured"] is True
    assert state["codex"]["otel"]["tracestate_configured"] is True
    assert state["codex"]["otel"]["trace_metadata_configured"] is True
    assert state["codex"]["otel"]["feedback_configured"] is True
    assert state["codex"]["otel"]["analytics_configured"] is True


def test_codex_runtime_env_updates_existing_project_config_without_otel(tmp_path: Path) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[feedback]\n"
        "enabled = false\n\n"
        '[agents.architecture_reviewer]\nconfig_file = "agents/architecture-reviewer.toml"\n',
        encoding="utf-8",
    )

    result = ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config={
            "sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "codex_profile": None,
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": None,
        },
        endpoint="http://localhost:4318",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "CODEX_OTEL_CONFIG" in result["changed_keys"]
    assert "[agents.architecture_reviewer]" in text
    assert "[otel]" in text
    assert "metrics_exporter" in text
    assert "trace_exporter" in text
    assert "tracestate" in text
    assert "[feedback]" in text
    assert "[feedback]\nenabled = true" in text
    assert text.count("[feedback]") == 1
    assert "[analytics]" in text


def test_codex_runtime_env_refreshes_existing_logs_only_otel_config(tmp_path: Path) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[otel]\n"
        'environment = "dev"\n'
        "log_user_prompt = true\n"
        'exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", '
        'protocol = "binary" } }\n',
        encoding="utf-8",
    )

    result = ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config={
            "sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "codex_profile": None,
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": None,
        },
        endpoint="http://localhost:4318",
    )

    text = config_path.read_text(encoding="utf-8")
    assert "CODEX_OTEL_CONFIG" in result["changed_keys"]
    assert "log_user_prompt = false" in text
    assert "metrics_exporter" in text
    assert "trace_exporter" in text
    assert "span_attributes" in text
    assert "tracestate" in text
    assert "[feedback]" in text
    assert "[analytics]" in text


def test_claude_runtime_env_does_not_create_or_report_codex_otel(tmp_path: Path) -> None:
    config = {
        "sdk": "claude",
        "provider": "claude_agent_sdk",
        "model": "sonnet",
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "tracing": "builder",
    }

    result = ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config=config,
        endpoint="http://localhost:4318",
    )

    state = telemetry_state(tmp_path, config)
    assert "CODEX_OTEL_CONFIG" not in result["changed_keys"]
    assert not (tmp_path / ".codex" / "config.toml").exists()
    assert result["active_telemetry"] == "claude"
    assert state["active_lane"] == "claude"
    assert state["codex"]["enabled"] is False
    assert state["codex"]["history_accessible"] is True
    assert state["codex"]["otel"]["enabled"] is False
    assert state["codex"]["otel"]["reason"] == "inactive_runtime"
    assert state["codex"]["otel"]["historical_accessible"] is True
    assert state["codex"]["otel"]["emitted_signals"]["logs"] is False
    assert state["codex"]["otel"]["emitted_signals"]["trace_metadata"] is False


def test_claude_runtime_reports_existing_codex_otel_as_inactive(tmp_path: Path) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[otel]\n"
        'environment = "dev"\n'
        "log_user_prompt = false\n"
        'exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", '
        'protocol = "binary" } }\n'
        'metrics_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/metrics", '
        'protocol = "binary" } }\n'
        'trace_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/traces", '
        'protocol = "binary" } }\n'
        'span_attributes = { "builder.product" = "autonomous-agent-builder" }\n'
        'tracestate = { builder = { product = "autonomous-agent-builder" } }\n\n'
        "[feedback]\n"
        "enabled = true\n\n"
        "[analytics]\n"
        "enabled = true\n",
        encoding="utf-8",
    )
    config = {
        "sdk": "claude",
        "provider": "claude_agent_sdk",
        "model": "sonnet",
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "tracing": "builder",
    }

    result = ensure_runtime_env(
        tmp_path,
        project_name="Test App",
        config=config,
        endpoint="http://localhost:4318",
    )

    state = telemetry_state(tmp_path, config)
    assert "CODEX_OTEL_CONFIG" not in result["changed_keys"]
    assert result["active_telemetry"] == "claude"
    assert state["codex"]["otel"]["configured"] is True
    assert state["codex"]["otel"]["enabled"] is False
    assert state["codex"]["otel"]["collector_status"] == "inactive"
    assert state["codex"]["otel"]["historical_accessible"] is True
    assert state["codex"]["otel"]["trace_metadata_configured"] is True
    assert state["codex"]["otel"]["feedback_configured"] is True
    assert state["codex"]["otel"]["analytics_configured"] is True
    assert state["codex"]["otel"]["emitted_signals"]["logs"] is False
    assert state["codex"]["otel"]["emitted_signals"]["metrics"] is False
    assert state["codex"]["otel"]["emitted_signals"]["traces"] is False


def test_claude_auth_state_uses_builder_source_env_only(
    monkeypatch,
    tmp_path: Path,
    builder_source_env: Path,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    (tmp_path / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=generated-token\n", encoding="utf-8")
    builder_source_env.write_text("CLAUDE_CODE_OAUTH_TOKEN=builder-token\n", encoding="utf-8")

    payload = runtime_settings_payload(
        tmp_path,
        {
            "sdk": "claude",
            "provider": "claude_agent_sdk",
            "model": "sonnet",
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": "builder",
        },
        include_capabilities=False,
    )

    assert payload["auth"]["configured"] is True
    assert payload["auth"]["api_key_used"] is False
    assert payload["auth"]["source"] == "builder_source_env"


def test_claude_auth_state_ignores_generated_project_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=generated-token\n", encoding="utf-8")

    payload = runtime_settings_payload(
        tmp_path,
        {
            "sdk": "claude",
            "provider": "claude_agent_sdk",
            "model": "sonnet",
            "sandbox_mode": "workspace-write",
            "approval_policy": "never",
            "tracing": "builder",
        },
        include_capabilities=False,
    )

    assert payload["auth"]["configured"] is False
    assert payload["auth"]["source"] == "builder_source_env_missing"
