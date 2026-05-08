from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder import onecli_runtime


@pytest.mark.asyncio
async def test_prepare_onecli_runtime_env_disabled_without_opt_in(monkeypatch):
    for key in (
        "AAB_ONECLI_ENABLED",
        "ONECLI_API_KEY",
        "ONECLI_URL",
        "AAB_ONECLI_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    result = await onecli_runtime.prepare_onecli_runtime_env()

    assert result.active is False
    assert result.env == {}


@pytest.mark.asyncio
async def test_prepare_onecli_runtime_env_fetches_config_and_sanitizes_provider_env(
    monkeypatch,
    tmp_path: Path,
):
    ca_path = tmp_path / "onecli-ca.pem"
    captured: dict[str, object] = {}

    async def fake_fetch_onecli_container_config(*, url, api_key, agent_identifier):
        captured["url"] = url
        captured["api_key"] = api_key
        captured["agent_identifier"] = agent_identifier
        return {
            "env": {
                "CLAUDE_CODE_OAUTH_TOKEN": "placeholder",
                "HTTPS_PROXY": "http://x:aoc_token@localhost:10255",
            },
            "caCertificate": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n",
            "caCertificateContainerPath": str(ca_path),
        }

    monkeypatch.setenv("AAB_ONECLI_ENABLED", "true")
    monkeypatch.setenv("ONECLI_URL", "http://127.0.0.1:10254")
    monkeypatch.setenv("ONECLI_API_KEY", "oc_test")
    monkeypatch.setenv("ONECLI_AGENT", "builder-agent")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-key-from-env")
    monkeypatch.setattr(
        onecli_runtime,
        "_fetch_onecli_container_config",
        fake_fetch_onecli_container_config,
    )

    result = await onecli_runtime.prepare_onecli_runtime_env()

    assert result.active is True
    assert captured == {
        "url": "http://127.0.0.1:10254",
        "api_key": "oc_test",
        "agent_identifier": "builder-agent",
    }
    assert result.env["CLAUDE_CODE_OAUTH_TOKEN"] == "placeholder"
    assert result.env["ANTHROPIC_API_KEY"] == "placeholder"
    assert result.env["HTTPS_PROXY"] == "http://x:aoc_token@localhost:10255"
    assert ca_path.read_text(encoding="utf-8").startswith("-----BEGIN CERTIFICATE-----")


@pytest.mark.asyncio
async def test_prepare_onecli_runtime_env_fails_open_by_default(monkeypatch):
    async def fake_fetch_onecli_container_config(**_kwargs):
        raise RuntimeError("onecli unavailable")

    monkeypatch.setenv("AAB_ONECLI_ENABLED", "true")
    monkeypatch.delenv("AAB_ONECLI_FAIL_CLOSED", raising=False)
    monkeypatch.setattr(
        onecli_runtime,
        "_fetch_onecli_container_config",
        fake_fetch_onecli_container_config,
    )

    result = await onecli_runtime.prepare_onecli_runtime_env()

    assert result.active is False
    assert result.message == "onecli unavailable"


@pytest.mark.asyncio
async def test_prepare_onecli_runtime_env_can_fail_closed(monkeypatch):
    async def fake_fetch_onecli_container_config(**_kwargs):
        raise RuntimeError("onecli unavailable")

    monkeypatch.setenv("AAB_ONECLI_ENABLED", "true")
    monkeypatch.setenv("AAB_ONECLI_FAIL_CLOSED", "true")
    monkeypatch.setattr(
        onecli_runtime,
        "_fetch_onecli_container_config",
        fake_fetch_onecli_container_config,
    )

    with pytest.raises(RuntimeError, match="OneCLI runtime bootstrap failed"):
        await onecli_runtime.prepare_onecli_runtime_env()
