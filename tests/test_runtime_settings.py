from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.services.runtime_settings import (
    ensure_runtime_env,
    telemetry_state,
)


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
    assert state["codex"]["otel"]["configured"] is True
    assert state["codex"]["otel"]["project_local"] is True
    assert state["codex"]["otel"]["exporter"] == "otlp-http"
