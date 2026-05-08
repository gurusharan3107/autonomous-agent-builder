"""Tests for vault provisioning + the `builder agent runtime managed-agents
vault-add` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from autonomous_agent_builder.services.managed_agents_setup import add_vault


def _make_client(*, vault_id: str = "vlt_001") -> Any:
    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.vaults.create = AsyncMock(return_value=SimpleNamespace(id=vault_id))
    client.beta.vaults.credentials.create = AsyncMock(
        return_value=SimpleNamespace(id="cred_001")
    )
    return client


def _github_credential() -> dict[str, Any]:
    return {
        "display_name": "GitHub (test)",
        "auth": {
            "type": "mcp_oauth",
            "mcp_server_url": "https://api.githubcopilot.com/mcp/",
            "access_token": "ghu_test_access",
            "refresh": {
                "refresh_token": "ghr_test_refresh",
                "client_id": "Iv1.test",
                "token_endpoint": "https://github.com/login/oauth/access_token",
                "token_endpoint_auth": {
                    "type": "client_secret_post",
                    "client_secret": "test-secret",
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_add_vault_creates_new_vault_and_credential(tmp_path: Path) -> None:
    client = _make_client()
    config = await add_vault(
        name="github",
        credential=_github_credential(),
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["vaults"]["github"] == "vlt_001"
    # Persisted to disk
    on_disk = json.loads((tmp_path / ".agent-builder" / "managed_agents.json").read_text())
    assert on_disk["vaults"]["github"] == "vlt_001"
    client.beta.vaults.create.assert_awaited_once()
    client.beta.vaults.credentials.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_vault_reuses_existing_vault(tmp_path: Path) -> None:
    """Re-running with an existing vault id adds another credential to it."""
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text(
        json.dumps(
            {
                "agents": {},
                "subagents": {},
                "environment_id": None,
                "vaults": {"github": "vlt_existing"},
            }
        )
    )
    client = _make_client()
    config = await add_vault(
        name="github",
        credential=_github_credential(),
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["vaults"]["github"] == "vlt_existing"
    client.beta.vaults.create.assert_not_awaited()
    client.beta.vaults.credentials.create.assert_awaited_once()
    create_call = client.beta.vaults.credentials.create.await_args
    assert create_call.kwargs["vault_id"] == "vlt_existing"


def test_vault_add_cli_rejects_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cred_file = tmp_path / "cred.json"
    cred_file.write_text(json.dumps(_github_credential()))

    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    runner = CliRunner()
    result = runner.invoke(
        managed_agents_app,
        ["vault-add", "--credential-file", str(cred_file), "--json"],
    )
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_vault_add_cli_rejects_invalid_json_credential(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    cred_file = tmp_path / "cred.json"
    cred_file.write_text("not json {")

    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    runner = CliRunner()
    result = runner.invoke(
        managed_agents_app,
        ["vault-add", "--credential-file", str(cred_file), "--json"],
    )
    assert result.exit_code == 1
    assert "JSON" in result.output


def test_vault_add_cli_provisions_with_real_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    cred_file = tmp_path / "cred.json"
    cred_file.write_text(json.dumps(_github_credential()))

    fake_client = _make_client(vault_id="vlt_cli")

    # Patch the add_vault used by the CLI (imported locally inside the
    # command) — patch on the module so the CLI's lookup picks up the wrap.
    import autonomous_agent_builder.services.managed_agents_setup as setup_mod
    from autonomous_agent_builder.services.managed_agents_setup import (
        add_vault as real_add_vault,
    )

    async def _wrapped(**kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("client_factory", lambda: fake_client)
        return await real_add_vault(**kwargs)

    monkeypatch.setattr(setup_mod, "add_vault", _wrapped)

    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    runner = CliRunner()
    result = runner.invoke(
        managed_agents_app,
        ["vault-add", "--credential-file", str(cred_file), "--json"],
    )
    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert payload["added"] == "github"
    assert payload["vaults"]["github"] == "vlt_cli"
