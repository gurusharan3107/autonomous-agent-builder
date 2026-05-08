"""Provision Managed Agents resources for the claude_managed lane.

Phase A scope: provision exactly one agent (`planner`) + one environment,
persisting their IDs in `.agent-builder/managed_agents.json`. Phase B
extends this to all 11 builder roles with multiagent rosters derived
from `_AGENT_POLICY.subagents`.

This module reads the YAML specs in `runtime/managed_agents_specs/`,
calls `client.beta.{agents,environments}.create`, and writes the
resulting IDs back to the project config. Idempotent — re-running picks
up existing IDs from the config and only creates what's missing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
import yaml

from autonomous_agent_builder.runtime.managed_agents_runtime import _MA_CONFIG_PATH

log = structlog.get_logger()

_SPECS_DIR = (
    Path(__file__).resolve().parent.parent / "runtime" / "managed_agents_specs"
)

# Phase A: planner only. Phase B will expand this to all 11 roles, each
# with a multiagent roster derived from `_AGENT_POLICY.subagents`.
_PHASE_A_ROLES: tuple[str, ...] = ("planner",)


class ManagedAgentsSetupError(RuntimeError):
    """Raised when MA setup fails (missing YAML, API error, etc.)."""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ManagedAgentsSetupError(f"Spec file not found: {path}")
    return yaml.safe_load(path.read_text())


def _spec_path(role: str) -> Path:
    return _SPECS_DIR / f"{role}.agent.yaml"


def _environment_spec_path() -> Path:
    return _SPECS_DIR / "environment.yaml"


def _config_path(project_root: Path) -> Path:
    return project_root / _MA_CONFIG_PATH


def _read_config(project_root: Path) -> dict[str, Any]:
    path = _config_path(project_root)
    if not path.exists():
        return {"agents": {}, "environment_id": None}
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ManagedAgentsSetupError(
            f"Existing config at {path} is invalid JSON: {exc}"
        ) from exc
    loaded.setdefault("agents", {})
    loaded.setdefault("environment_id", None)
    return loaded


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    path = _config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


async def _ensure_environment(
    *,
    client: Any,
    config: dict[str, Any],
) -> str:
    """Create the environment from environment.yaml if not already provisioned."""
    if config.get("environment_id"):
        return str(config["environment_id"])

    spec = _load_yaml(_environment_spec_path())
    log.info("managed_agents_setup_create_environment", name=spec.get("name"))
    env = await client.beta.environments.create(**spec)
    config["environment_id"] = env.id
    return env.id


async def _ensure_agent(
    *,
    client: Any,
    config: dict[str, Any],
    role: str,
) -> str:
    """Create the agent from <role>.agent.yaml if not already provisioned."""
    agents = config.setdefault("agents", {})
    if agents.get(role):
        return str(agents[role])

    spec = _load_yaml(_spec_path(role))
    log.info("managed_agents_setup_create_agent", role=role, name=spec.get("name"))
    agent = await client.beta.agents.create(**spec)
    agents[role] = agent.id
    return agent.id


async def setup_phase_a(
    *,
    project_root: Path | None = None,
    client_factory: Callable[[], Any] | None = None,
    roles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Provision Phase A resources (environment + planner agent).

    Idempotent: existing IDs in `.agent-builder/managed_agents.json` are
    preserved. Returns the final config dict (also written to disk).

    Args:
        project_root: project to write the config under. Defaults to CWD.
        client_factory: optional override (for tests). Default constructs
            an `anthropic.AsyncAnthropic()`.
        roles: subset of roles to provision. Defaults to Phase A scope.
    """
    root = project_root or Path.cwd()
    config = _read_config(root)
    target_roles = roles or _PHASE_A_ROLES

    if client_factory is None:
        import anthropic  # local import — only when running setup

        client = anthropic.AsyncAnthropic()
    else:
        client = client_factory()

    try:
        env_id = await _ensure_environment(client=client, config=config)
        for role in target_roles:
            await _ensure_agent(client=client, config=config, role=role)
        _write_config(root, config)
        log.info(
            "managed_agents_setup_complete",
            environment_id=env_id,
            agents=list(config["agents"].keys()),
        )
        return config
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await client.close()
