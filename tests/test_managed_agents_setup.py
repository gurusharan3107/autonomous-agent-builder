"""Tests for the Phase A managed-agents setup helper."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.services.managed_agents_setup import (
    ManagedAgentsSetupError,
    setup_phase_a,
)


def _make_client(*, env_id: str = "env_001", agent_id: str = "agent_planner_001") -> Any:
    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.environments.create = AsyncMock(
        return_value=SimpleNamespace(id=env_id)
    )
    client.beta.agents.create = AsyncMock(
        return_value=SimpleNamespace(id=agent_id, version=1)
    )
    return client


@pytest.mark.asyncio
async def test_setup_phase_a_provisions_environment_and_planner(tmp_path: Path) -> None:
    client = _make_client()
    config = await setup_phase_a(
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["environment_id"] == "env_001"
    assert config["agents"]["planner"] == "agent_planner_001"
    # File written
    cfg_path = tmp_path / ".agent-builder" / "managed_agents.json"
    assert cfg_path.exists()
    on_disk = json.loads(cfg_path.read_text())
    assert on_disk["environment_id"] == "env_001"
    assert on_disk["agents"]["planner"] == "agent_planner_001"
    # API was called exactly once each
    client.beta.environments.create.assert_awaited_once()
    client.beta.agents.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_phase_a_is_idempotent(tmp_path: Path) -> None:
    """Re-running with existing IDs in config does NOT recreate."""
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text(
        json.dumps(
            {
                "environment_id": "env_existing",
                "agents": {"planner": "agent_existing"},
            }
        )
    )
    client = _make_client()
    config = await setup_phase_a(
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["environment_id"] == "env_existing"
    assert config["agents"]["planner"] == "agent_existing"
    # Neither create method was called
    client.beta.environments.create.assert_not_awaited()
    client.beta.agents.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_phase_a_partial_existing_only_creates_missing(tmp_path: Path) -> None:
    """Env already provisioned but no planner — only agent gets created."""
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text(
        json.dumps({"environment_id": "env_existing", "agents": {}})
    )
    client = _make_client()
    config = await setup_phase_a(
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["environment_id"] == "env_existing"
    assert config["agents"]["planner"] == "agent_planner_001"
    client.beta.environments.create.assert_not_awaited()
    client.beta.agents.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_phase_a_raises_on_invalid_existing_config(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text("not json {")
    with pytest.raises(ManagedAgentsSetupError, match="invalid JSON"):
        await setup_phase_a(
            project_root=tmp_path,
            client_factory=lambda: _make_client(),
        )
