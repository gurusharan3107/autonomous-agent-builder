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
async def test_prepare_onecli_runtime_env_fails_closed_by_default_when_enabled(
    monkeypatch,
):
    """Council 2026-05-08 — Item 2: when OneCLI is enabled, default is fail-closed."""

    async def fake_fetch_onecli_container_config(**_kwargs):
        raise RuntimeError("onecli unavailable")

    monkeypatch.setenv("AAB_ONECLI_ENABLED", "true")
    monkeypatch.delenv("AAB_ONECLI_FAIL_CLOSED", raising=False)
    monkeypatch.setattr(
        onecli_runtime,
        "_fetch_onecli_container_config",
        fake_fetch_onecli_container_config,
    )

    with pytest.raises(RuntimeError, match="OneCLI runtime bootstrap failed"):
        await onecli_runtime.prepare_onecli_runtime_env()


@pytest.mark.asyncio
async def test_prepare_onecli_runtime_env_explicit_fail_open_still_honored(
    monkeypatch,
):
    """Operators can still opt in to legacy fail-open with AAB_ONECLI_FAIL_CLOSED=0."""

    async def fake_fetch_onecli_container_config(**_kwargs):
        raise RuntimeError("onecli unavailable")

    monkeypatch.setenv("AAB_ONECLI_ENABLED", "true")
    monkeypatch.setenv("AAB_ONECLI_FAIL_CLOSED", "0")
    monkeypatch.setattr(
        onecli_runtime,
        "_fetch_onecli_container_config",
        fake_fetch_onecli_container_config,
    )

    result = await onecli_runtime.prepare_onecli_runtime_env()

    assert result.active is False
    assert result.message == "onecli unavailable"


def test_scrub_provider_env_suppresses_api_key_and_preserves_oauth_token():
    env = {
        "ANTHROPIC_API_KEY": "sk-real",
        "CLAUDE_CODE_OAUTH_TOKEN": "real-oauth",
        "OTHER_VAR": "keep-me",
        "PATH": "/usr/bin",
    }
    scrubbed = onecli_runtime.scrub_provider_env(env)
    assert scrubbed["ANTHROPIC_API_KEY"] == "placeholder"
    assert scrubbed["CLAUDE_CODE_OAUTH_TOKEN"] == "real-oauth"
    assert scrubbed["OTHER_VAR"] == "keep-me"
    assert scrubbed["PATH"] == "/usr/bin"
    # input must not be mutated
    assert env["ANTHROPIC_API_KEY"] == "sk-real"


def test_scrub_provider_env_handles_empty_input():
    assert onecli_runtime.scrub_provider_env({}) == {}


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
