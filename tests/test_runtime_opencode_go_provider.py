from __future__ import annotations

import pytest

from autonomous_agent_builder.runtime.openai_runtime import OpenAIAgentsRuntime


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_opencode_go_model_discovery_uses_zen_go_models_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, *, headers):
            captured["url"] = url
            captured["headers"] = headers
            return _FakeResponse({"data": [{"id": "kimi-k2.6"}, {"id": "minimax-m2.7"}]})

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.openai_runtime.httpx.AsyncClient",
        FakeAsyncClient,
    )

    runtime = OpenAIAgentsRuntime()
    result = await runtime.list_models(api_key="provider-key")

    assert result["ok"] is True
    assert captured["url"] == "https://opencode.ai/zen/go/v1/models"
    assert captured["headers"] == {"Authorization": "Bearer provider-key"}
    assert [model["id"] for model in result["models"]] == ["kimi-k2.6", "minimax-m2.7"]


@pytest.mark.asyncio
async def test_opencode_go_probe_fails_clearly_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)

    runtime = OpenAIAgentsRuntime()
    result = await runtime.probe()

    assert result.ok is False
    assert result.code == "missing_api_key_env"
    assert "OPENCODE_GO_API_KEY" in result.message
    assert result.capabilities is not None
    assert result.capabilities.api_key_auth is True
