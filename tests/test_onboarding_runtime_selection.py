from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.api.routes import onboarding as onboarding_routes


@pytest.mark.asyncio
async def test_onboarding_start_persists_selected_runtime(monkeypatch, tmp_path):
    async def fake_start(project_root, _factory):
        assert project_root == tmp_path
        return {
            "repo": {
                "root": str(project_root),
                "name": project_root.name,
                "language": "python",
                "framework": "fastapi",
                "branch": "",
                "dirty": False,
                "status_lines": 0,
            },
            "onboarding_mode": "forward_engineering",
            "current_phase": "ready",
            "ready": True,
            "started_at": None,
            "updated_at": "2026-05-01T00:00:00Z",
            "phases": [],
            "entity_counts": {},
            "kb_status": {},
            "scan_summary": {},
            "archives": [],
            "errors": [],
        }

    monkeypatch.setattr(onboarding_routes, "start_onboarding", fake_start)
    app = FastAPI()
    app.state.project_root = tmp_path
    app.include_router(onboarding_routes.router, prefix="/api")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/onboarding/start", json={"runtime_sdk": "codex_sdk"})

    assert response.status_code == 200
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="codex_sdk"' in env_text
    assert 'RUNTIME_PROVIDER="codex_subscription"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text
    assert 'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"' in env_text
    assert "AAB_CODEX_JSONL_TELEMETRY_ENABLED" not in env_text
