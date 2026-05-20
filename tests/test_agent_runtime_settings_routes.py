"""Agent runtime-settings route regressions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    assess_readiness,
    load_readiness_status,
)
from autonomous_agent_builder.services.runtime_guidance import render_project_runtime_guidance
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_runtime_settings_route_toggles_telemetry_lanes(test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/runtime", json={"sdk": "codex_sdk"})
        payload = response.json()

        assert response.status_code == 200
        assert payload["sdk"] == "codex_sdk"
        assert payload["telemetry"]["active_lane"] == "codex"

        env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
        assert 'RUNTIME_SDK="codex_sdk"' in env_text
        assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
        assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text
        assert 'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"' in env_text
        assert "AAB_CODEX_JSONL_TELEMETRY_ENABLED" not in env_text

        get_response = await client.get("/api/agent/runtime")
        get_payload = get_response.json()
        assert get_response.status_code == 200
        assert get_payload["sdk"] == "codex_sdk"
        assert get_payload["telemetry"]["active_lane"] == "codex"

        meta_response = await client.get("/api/agent/chat/meta")
        meta_payload = meta_response.json()
        assert meta_response.status_code == 200
        assert meta_payload["runtime_sdk"] == "codex_sdk"
        assert meta_payload["provider"] == "codex_subscription"
        assert meta_payload["model"] == "gpt-5.5"

        history_response = await client.get("/api/agent/chat/history", params={"fresh": "1"})
        history_payload = history_response.json()
        assert history_response.status_code == 200
        assert history_payload["runtime_sdk"] == "codex_sdk"
        assert history_payload["provider"] == "codex_subscription"
        assert history_payload["model"] == "gpt-5.5"

@pytest.mark.asyncio
async def test_runtime_settings_route_repairs_ready_state_without_onboarding(test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    (tmp_path / "AGENTS.md").write_text(
        render_project_runtime_guidance(
            project_name="runtime-switch",
            sdk="codex_sdk",
            language="unknown",
            mode="forward_engineering",
        ),
        encoding="utf-8",
    )
    Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n'
        'AAB_CLAUDE_OTEL_ENABLED="0"\n'
        'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"\n'
        'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n'
        'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"\n'
        'AAB_CODEX_TELEMETRY_COST_SOURCE="subscription_unmetered"\n',
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)
    Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n'
        'AAB_CLAUDE_OTEL_ENABLED="0"\n'
        'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"\n'
        'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n'
        'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"\n'
        'AAB_CODEX_TELEMETRY_COST_SOURCE="subscription_unmetered"\n',
        encoding="utf-8",
    )
    assess_readiness(tmp_path, write=True)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/runtime", json={"sdk": "claude"})
        payload = response.json()

        assert response.status_code == 200
        assert payload["sdk"] == "claude"
        assert payload["telemetry"]["active_lane"] == "claude"
        assert payload["runtime_repair"]["status"] == "ready"

        status_response = await client.get("/api/onboarding/status")
        status = status_response.json()

    assert status["ready"] is True
    assert status["current_phase"] == "ready"
    env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="claude"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="1"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"' in env_text
    assert (tmp_path / "CLAUDE.md").exists()
    readiness = load_readiness_status(tmp_path)
    assert readiness["state"] == READY_STATE
    assert readiness["can_continue"] is True
    assert readiness.get("invalidated_by", []) == []
