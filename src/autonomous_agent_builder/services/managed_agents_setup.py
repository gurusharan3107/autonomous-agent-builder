"""Provision Managed Agents resources for the claude_managed lane.

Phase B scope: provision the environment + all 11 builder roles (top-level
agents) + all 6 subagent roles, with multiagent rosters wired per
`_AGENT_POLICY.subagents`. Idempotent — re-running picks up existing IDs
from `.agent-builder/managed_agents.json` and only creates what's missing.

Provisioning order:
  1. Environment (single template)
  2. Subagents (no multiagent dependencies)
  3. Top-level agents with multiagent rosters referencing subagent IDs

Source of truth is `agents/definitions.py` + `_AGENT_POLICY`. Payload
shape is rendered by `services/managed_agents_specs.py` — no checked-in
YAML to drift against.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.runtime.managed_agents_runtime import _MA_CONFIG_PATH
from autonomous_agent_builder.services.managed_agents_specs import (
    ALL_AGENT_ROLES,
    ALL_SUBAGENT_ROLES,
    build_agent_payload,
    build_subagent_payload,
    expected_subagent_roster,
)

log = structlog.get_logger()

# Phase A used a planner-only constant. Phase B keeps it for backward
# compatibility with the Phase A test (planner-only smoke).
_PHASE_A_ROLES: tuple[str, ...] = ("planner",)


class ManagedAgentsSetupError(RuntimeError):
    """Raised when MA setup fails (missing config, API error, etc.)."""


def _config_path(project_root: Path) -> Path:
    return project_root / _MA_CONFIG_PATH


def _read_config(project_root: Path) -> dict[str, Any]:
    path = _config_path(project_root)
    if not path.exists():
        return {
            "agents": {},
            "subagents": {},
            "environment_id": None,
            "vaults": {},
        }
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ManagedAgentsSetupError(
            f"Existing config at {path} is invalid JSON: {exc}"
        ) from exc
    loaded.setdefault("agents", {})
    loaded.setdefault("subagents", {})
    loaded.setdefault("environment_id", None)
    loaded.setdefault("vaults", {})
    return loaded


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    path = _config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def _environment_payload() -> dict[str, Any]:
    """Single shared environment template for all builder MA sessions."""
    return {
        "name": "builder-default",
        "description": (
            "Default cloud environment for builder claude_managed sessions. "
            "Allows package-manager egress + GitHub + Anthropic API; "
            "everything else blocked at the network layer."
        ),
        "config": {
            "type": "cloud",
            "networking": {
                "type": "package_managers_and_custom",
                "allowed_hosts": [
                    "api.anthropic.com",
                    "api.githubcopilot.com",
                    "api.github.com",
                    "github.com",
                    "raw.githubusercontent.com",
                ],
            },
        },
        "metadata": {"builder_managed": "true"},
    }


async def _ensure_environment(*, client: Any, config: dict[str, Any]) -> str:
    if config.get("environment_id"):
        return str(config["environment_id"])
    payload = _environment_payload()
    log.info("managed_agents_setup_create_environment", name=payload["name"])
    env = await client.beta.environments.create(**payload)
    config["environment_id"] = env.id
    return env.id


async def _ensure_subagent(
    *, client: Any, config: dict[str, Any], role: str
) -> str:
    subagents = config.setdefault("subagents", {})
    if subagents.get(role):
        return str(subagents[role])
    payload = build_subagent_payload(role)
    log.info(
        "managed_agents_setup_create_subagent",
        role=role,
        name=payload["name"],
        model=payload["model"],
    )
    agent = await client.beta.agents.create(**payload)
    subagents[role] = agent.id
    return agent.id


async def _ensure_agent(
    *,
    client: Any,
    config: dict[str, Any],
    role: str,
    subagent_id_map: dict[str, str],
) -> str:
    agents = config.setdefault("agents", {})
    if agents.get(role):
        return str(agents[role])
    payload = build_agent_payload(role, subagent_id_map=subagent_id_map)
    log.info(
        "managed_agents_setup_create_agent",
        role=role,
        name=payload["name"],
        model=payload["model"],
        roster=[a for a in (payload.get("multiagent") or {}).get("agents", [])],
    )
    agent = await client.beta.agents.create(**payload)
    agents[role] = agent.id
    return agent.id


def _resolve_required_subagents(target_roles: tuple[str, ...]) -> tuple[str, ...]:
    """Return only the subagents actually needed by the target top-level roles."""
    needed: set[str] = set()
    for role in target_roles:
        for sub in expected_subagent_roster(role):
            needed.add(sub)
    # Preserve declared order from ALL_SUBAGENT_ROLES for deterministic logs
    return tuple(name for name in ALL_SUBAGENT_ROLES if name in needed)


async def setup_managed_agents(
    *,
    project_root: Path | None = None,
    client_factory: Callable[[], Any] | None = None,
    roles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Provision the MA environment + subagents + top-level agents.

    Args:
        project_root: project to write `.agent-builder/managed_agents.json`
            under. Defaults to CWD.
        client_factory: optional override (for tests). Default constructs
            an `anthropic.AsyncAnthropic()`.
        roles: subset of top-level roles to provision. Defaults to all 11
            roles in `AGENT_DEFINITIONS`. Subagents are provisioned only
            for the subset of subagents referenced by `roles`.

    Returns the persisted config dict (also written to disk):
        {
            "environment_id": "env_...",
            "agents": {"planner": "agent_...", ...},
            "subagents": {"repo-researcher": "agent_...", ...},
        }

    Idempotent — existing IDs are preserved.
    """
    root = project_root or Path.cwd()
    config = _read_config(root)
    target_roles = roles or ALL_AGENT_ROLES

    # Validate role names early — fail before any API calls
    unknown = [r for r in target_roles if r not in ALL_AGENT_ROLES]
    if unknown:
        raise ManagedAgentsSetupError(
            f"Unknown top-level agent role(s): {unknown}. "
            f"Available: {list(ALL_AGENT_ROLES)}"
        )

    if client_factory is None:
        import anthropic  # local import — only when running setup

        client = anthropic.AsyncAnthropic()
    else:
        client = client_factory()

    try:
        env_id = await _ensure_environment(client=client, config=config)

        # 1. Subagents first — only those referenced by the target roles
        required_subagents = _resolve_required_subagents(target_roles)
        subagent_id_map: dict[str, str] = dict(config.get("subagents") or {})
        for sub_role in required_subagents:
            sub_id = await _ensure_subagent(
                client=client, config=config, role=sub_role
            )
            subagent_id_map[sub_role] = sub_id

        # 2. Top-level agents with multiagent rosters
        for role in target_roles:
            await _ensure_agent(
                client=client,
                config=config,
                role=role,
                subagent_id_map=subagent_id_map,
            )

        _write_config(root, config)
        log.info(
            "managed_agents_setup_complete",
            environment_id=env_id,
            agents=sorted(config["agents"].keys()),
            subagents=sorted(config["subagents"].keys()),
        )
        return config
    finally:
        with contextlib.suppress(Exception):
            await client.close()


async def add_vault(
    *,
    name: str,
    credential: dict[str, Any],
    project_root: Path | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Provision a vault + credential and persist its ID under config.vaults[name].

    Phase C: only `name="github"` is wired through to runtime sessions
    (pr-creator, integration-resolver), but the helper is generic so
    Phase D+ can add additional vault names without changing call sites.

    Args:
        name: short vault key under `config["vaults"]` (e.g. "github").
            Sessions attach all configured vault IDs by default.
        credential: full credential payload per MA docs §Vaults — must
            include `display_name` and `auth` (for `mcp_oauth` shape:
            mcp_server_url, access_token, refresh.{refresh_token,
            client_id, token_endpoint, token_endpoint_auth}).
        project_root: project to write `.agent-builder/managed_agents.json`
            under. Defaults to CWD.
        client_factory: optional override (for tests).

    Returns:
        Updated config dict.

    Idempotent: if a vault with the same name already exists in config,
    this re-uses the existing vault and ADDS the new credential to it
    (per MA's vaults model — one vault holds multiple credentials).
    """
    root = project_root or Path.cwd()
    config = _read_config(root)
    vaults = config.setdefault("vaults", {})

    if client_factory is None:
        import anthropic  # local import — only when running setup

        client = anthropic.AsyncAnthropic()
    else:
        client = client_factory()

    try:
        vault_id = vaults.get(name)
        if not vault_id:
            log.info("managed_agents_setup_create_vault", name=name)
            vault = await client.beta.vaults.create(
                name=f"builder-vault-{name}",
                description=f"Builder vault for the '{name}' MCP credential set.",
            )
            vault_id = vault.id
            vaults[name] = vault_id

        log.info(
            "managed_agents_setup_create_credential",
            vault=name,
            display_name=credential.get("display_name"),
        )
        await client.beta.vaults.credentials.create(
            vault_id=vault_id,
            **credential,
        )

        _write_config(root, config)
        return config
    finally:
        with contextlib.suppress(Exception):
            await client.close()


# Phase A backward-compatible alias used by the Phase A tests.
async def setup_phase_a(
    *,
    project_root: Path | None = None,
    client_factory: Callable[[], Any] | None = None,
    roles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Phase A wrapper — provisions only the planner role by default.

    Retained so the original Phase A smoke test keeps passing. New code
    should call `setup_managed_agents` directly.
    """
    return await setup_managed_agents(
        project_root=project_root,
        client_factory=client_factory,
        roles=roles or _PHASE_A_ROLES,
    )
