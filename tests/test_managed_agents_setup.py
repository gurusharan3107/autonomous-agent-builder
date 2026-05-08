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
    """Phase A provisions planner + its subagents (repo-researcher) per
    `_AGENT_POLICY['planner'][3]`."""
    client = _make_client()
    config = await setup_phase_a(
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["environment_id"] == "env_001"
    assert "planner" in config["agents"]
    assert "repo-researcher" in config["subagents"]
    # File written
    cfg_path = tmp_path / ".agent-builder" / "managed_agents.json"
    assert cfg_path.exists()
    on_disk = json.loads(cfg_path.read_text())
    assert on_disk["environment_id"] == "env_001"
    assert "planner" in on_disk["agents"]
    assert "repo-researcher" in on_disk["subagents"]
    # API: 1 environment create + 2 agent creates (subagent + planner)
    client.beta.environments.create.assert_awaited_once()
    assert client.beta.agents.create.await_count == 2


@pytest.mark.asyncio
async def test_setup_phase_a_is_idempotent(tmp_path: Path) -> None:
    """Re-running with existing IDs (incl. subagents) does NOT recreate."""
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text(
        json.dumps(
            {
                "environment_id": "env_existing",
                "agents": {"planner": "agent_existing"},
                "subagents": {"repo-researcher": "agent_rr_existing"},
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
    assert config["subagents"]["repo-researcher"] == "agent_rr_existing"
    client.beta.environments.create.assert_not_awaited()
    client.beta.agents.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_setup_phase_a_partial_existing_only_creates_missing(tmp_path: Path) -> None:
    """Env already provisioned but no planner/subagents — both get created."""
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text(
        json.dumps(
            {
                "environment_id": "env_existing",
                "agents": {},
                "subagents": {},
            }
        )
    )
    client = _make_client()
    config = await setup_phase_a(
        project_root=tmp_path,
        client_factory=lambda: client,
    )
    assert config["environment_id"] == "env_existing"
    assert "planner" in config["agents"]
    assert "repo-researcher" in config["subagents"]
    client.beta.environments.create.assert_not_awaited()
    # Two agent creates: subagent + planner
    assert client.beta.agents.create.await_count == 2


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
