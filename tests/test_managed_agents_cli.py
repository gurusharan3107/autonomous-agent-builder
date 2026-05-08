"""Tests for `builder agent runtime managed-agents {setup,show}`."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner


def _mock_anthropic_client(env_id: str = "env_x") -> Any:
    """Build a fake AsyncAnthropic that hands out distinct IDs per create call."""
    counter = {"agents": 0}

    async def _create_agent(**kwargs: Any) -> SimpleNamespace:
        counter["agents"] += 1
        return SimpleNamespace(id=f"agent_{counter['agents']:03d}", version=1)

    async def _create_env(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=env_id)

    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.environments.create = AsyncMock(side_effect=_create_env)
    client.beta.agents.create = AsyncMock(side_effect=_create_agent)
    return client


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_setup_command_exits_when_api_key_missing(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    result = runner.invoke(managed_agents_app, ["setup", "--json"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.stdout or "ANTHROPIC_API_KEY" in result.stderr


def test_setup_command_provisions_subset_when_role_flag_used(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`--role planner` provisions only planner + its required subagents."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)

    fake_client = _mock_anthropic_client()
    monkeypatch.setattr(
        "autonomous_agent_builder.services.managed_agents_setup.anthropic",
        SimpleNamespace(AsyncAnthropic=lambda: fake_client),
        raising=False,
    )
    # Bypass the import-time fallback by patching the import lookup
    import autonomous_agent_builder.services.managed_agents_setup as setup_mod

    monkeypatch.setattr(
        setup_mod,
        "setup_managed_agents",
        _patched_setup_factory(fake_client),
    )

    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    result = runner.invoke(
        managed_agents_app,
        ["setup", "--role", "planner", "--json"],
    )
    assert result.exit_code == 0, result.output
    # structlog logs interleave stdout — extract the trailing JSON block
    # (logs use `key=value` format, no `{`, so first `{` starts our JSON)
    json_start = result.output.index("{")
    payload = json.loads(result.output[json_start:])
    assert "planner" in payload["agents"]
    # planner's subagents per _AGENT_POLICY include repo-researcher
    assert "repo-researcher" in payload["subagents"]


def _patched_setup_factory(client: Any):
    """Return a setup_managed_agents that uses the supplied client."""
    from autonomous_agent_builder.services.managed_agents_setup import (
        setup_managed_agents as real_setup,
    )

    async def _patched(**kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("client_factory", lambda: client)
        return await real_setup(**kwargs)

    return _patched


def test_show_command_reports_missing_setup(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    result = runner.invoke(managed_agents_app, ["show", "--json"])
    assert result.exit_code == 1


def test_show_command_renders_existing_config(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    cfg_dir.joinpath("managed_agents.json").write_text(
        json.dumps(
            {
                "environment_id": "env_existing",
                "agents": {"planner": "agent_pl"},
                "subagents": {"repo-researcher": "agent_rr"},
            }
        )
    )
    from autonomous_agent_builder.cli.commands.agent import managed_agents_app

    result = runner.invoke(managed_agents_app, ["show", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["environment_id"] == "env_existing"
    assert payload["agents"]["planner"] == "agent_pl"
    assert payload["subagents"]["repo-researcher"] == "agent_rr"
