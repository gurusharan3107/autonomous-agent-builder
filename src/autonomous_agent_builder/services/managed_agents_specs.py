"""Translate `agents/definitions.py` + `_AGENT_POLICY` → MA agents.create payloads.

Single source of truth for builder agents stays `agents/definitions.py`;
this module renders that source into the wire shape Anthropic's Managed
Agents API expects. The setup helper applies the rendered payloads via
`client.beta.agents.create` once per role.

Subagent provisioning runs before parent provisioning so the parent's
`multiagent.agents` roster can reference the freshly-created subagent IDs.

Phase B: top-level agents + subagents + multiagent rosters. mcp__* tools
beyond `builder_memory_search` are intentionally NOT wired here — Phase E
adds host-side custom-tool handlers for them. Until then, agents in the
claude_managed lane have read/write/edit/grep/glob/bash/web_search/
web_fetch + builder_memory_search; mcp__* tool calls in their templates
are surfaced as system-prompt context but not callable.
"""

from __future__ import annotations

import string
from typing import Any

from autonomous_agent_builder.agents.definitions import (
    AGENT_DEFINITIONS,
    SUBAGENT_DEFINITIONS,
    AgentDefinition,
    SubagentDefinition,
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.execution_policy import _AGENT_POLICY

# ── Public role rosters ──

# Top-level builder agent roles. Order matters for provisioning: parents
# referencing subagents are created AFTER subagents.
ALL_AGENT_ROLES: tuple[str, ...] = tuple(AGENT_DEFINITIONS.keys())

# Bounded specialist subagent roles per CLAUDE.md.
ALL_SUBAGENT_ROLES: tuple[str, ...] = tuple(SUBAGENT_DEFINITIONS.keys())


# ── Model resolution ──

# Per-role model fallback when settings doesn't drive it. Mirrors
# `_model_for_agent` in execution_policy.py without requiring Settings.
_ROLE_DEFAULT_MODEL: dict[str, str] = {
    "planner": "claude-opus-4-7",
    "designer": "claude-opus-4-7",
    "code-gen": "claude-sonnet-4-6",
    "init-project-chat": "claude-sonnet-4-6",
    "documentation-bridge": "claude-sonnet-4-6",
    "integration-resolver": "claude-sonnet-4-6",
    "optimization-agent": "claude-sonnet-4-6",
    "feature-verifier": "claude-sonnet-4-6",
    "pr-creator": "claude-sonnet-4-6",
    "build-verifier": "claude-sonnet-4-6",
    "chat": "claude-sonnet-4-6",
}

# Roles that need access to the GitHub MCP server (PR creation, issue
# management). Declared on agents.create as `mcp_servers=[...]`; the
# session attaches a vault containing the OAuth credential at run time.
_GITHUB_MCP_ROLES: frozenset[str] = frozenset({"pr-creator", "integration-resolver"})

_GITHUB_MCP_SERVER_NAME = "github"
_GITHUB_MCP_SERVER_URL = "https://api.githubcopilot.com/mcp/"


def _mcp_servers_for_role(role: str) -> tuple[str, ...]:
    """Return the MCP server names declared on an agent for the given role."""
    if role in _GITHUB_MCP_ROLES:
        return (_GITHUB_MCP_SERVER_NAME,)
    return ()


def _mcp_servers_block(role: str) -> list[dict[str, Any]]:
    """Build the agents.create `mcp_servers` block.

    Phase C declares only the GitHub Copilot MCP server. Adding more is a
    matter of extending `_GITHUB_MCP_ROLES`/registry. Auth lives in vaults
    attached to sessions — never inline on the agent.
    """
    if role not in _GITHUB_MCP_ROLES:
        return []
    return [
        {
            "type": "url",
            "name": _GITHUB_MCP_SERVER_NAME,
            "url": _GITHUB_MCP_SERVER_URL,
        }
    ]


# Subagents per CLAUDE.md "bounded specialist evidence lanes" — model
# choice mirrors `resolve_subagent_model` in execution_policy.py.
_SUBAGENT_DEFAULT_MODEL: dict[str, str] = {
    "repo-researcher": "claude-haiku-4-5",
    "browser-verifier": "claude-haiku-4-5",
    "build-verifier": "claude-haiku-4-5",
    "pr-reviewer": "claude-haiku-4-5",
    "documentation-agent": "claude-haiku-4-5",
    "security-reviewer": "claude-sonnet-4-6",
}


def resolve_agent_model(role: str) -> str:
    """Resolve the MA model ID for a top-level builder agent role."""
    return _ROLE_DEFAULT_MODEL.get(role, "claude-sonnet-4-6")


def resolve_subagent_model_for_ma(role: str) -> str:
    """Resolve the MA model ID for a builder subagent role."""
    return _SUBAGENT_DEFAULT_MODEL.get(role, "claude-haiku-4-5")


# ── Tool translation ──

# Builder uses Claude Agent SDK tool name conventions (PascalCase).
# Managed Agents' built-in toolset uses lowercase names. Keep the mapping
# explicit so the snapshot test catches additions/removals.
_BUILTIN_TOOL_MAP: dict[str, str] = {
    "Read": "read",
    "Glob": "glob",
    "Grep": "grep",
    "Bash": "bash",
    "Write": "write",
    "Edit": "edit",
    "WebFetch": "web_fetch",
    "WebSearch": "web_search",
}

# `builder_memory_search` is the one host-side custom tool wired in Phase A.
# Other mcp__* tools become Phase E work; including the schema here keeps
# the system prompt's references coherent without exposing a non-functional
# tool surface.
_MEMORY_SEARCH_CUSTOM_TOOL: dict[str, Any] = {
    "type": "custom",
    "name": "builder_memory_search",
    "description": (
        "Search builder memory (decisions, patterns, corrections) on the host "
        "filesystem for precedent relevant to this task. Returns matching "
        "memory entries as JSON."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Free-text search query (required).",
            },
            "tags": {
                "type": "string",
                "description": "Optional comma-separated tag filter.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 10, max 100).",
            },
        },
        "required": ["query"],
    },
}


def _translate_tools(
    tool_names: tuple[str, ...],
    *,
    mcp_servers: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Translate AgentDefinition.tools to MA agents.create tools[].

    Args:
        tool_names: builder Claude-Agent-SDK tool names.
        mcp_servers: names of MCP servers declared on the same agent. For
            each declared server, an `mcp_toolset` entry is emitted so the
            agent can call its tools after the session attaches a vault.
    """
    enabled_builtins = sorted(
        _BUILTIN_TOOL_MAP[name] for name in tool_names if name in _BUILTIN_TOOL_MAP
    )
    out: list[dict[str, Any]] = []
    if enabled_builtins:
        out.append(
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [{"name": n, "enabled": True} for n in enabled_builtins],
            }
        )

    # builder_memory_search wired host-side (always available)
    needs_memory_search = (
        "mcp__builder__memory_search" in tool_names
        # Top-level agents that don't list memory_search but do reasoning over
        # precedent benefit from it too. For Phase B keep it conservative —
        # only roles that explicitly reference memory_search in their tools.
    )
    if needs_memory_search:
        out.append(_MEMORY_SEARCH_CUSTOM_TOOL)

    # mcp_toolset entries — one per declared MCP server. Per MA docs, the
    # toolset name references the server by `mcp_server_name` matching the
    # server's `name` field on the agent.
    for server_name in mcp_servers:
        out.append({"type": "mcp_toolset", "mcp_server_name": server_name})

    return out


# ── System-prompt extraction ──

# `prompt_template` mixes role description with per-task placeholders
# ({language}, {feature_description}, etc.). For MA, role description goes
# in agent.system; per-task data arrives via user.message. We render the
# template with placeholders replaced by `<name>` markers so the model
# sees them as variable references rather than literal `{name}` strings.

_TEMPLATE_FORMATTER = string.Formatter()


def _render_system_prompt(prompt_template: str) -> str:
    """Convert a per-task prompt template into a static role system prompt.

    Placeholders like `{language}` are rewritten as `<language>` so the
    agent reads them as variable hints and looks for them in user.message.
    Literal `{{` / `}}` escapes pass through as `{` / `}` per `string.Formatter`.
    """
    parts: list[str] = []
    for literal_text, field_name, _, _ in _TEMPLATE_FORMATTER.parse(prompt_template):
        parts.append(literal_text)
        if field_name:
            parts.append(f"<{field_name}>")
    return "".join(parts).strip()


# ── Payload builders ──


def build_subagent_payload(role: str) -> dict[str, Any]:
    """Render a SubagentDefinition into an MA agents.create payload."""
    sub_def: SubagentDefinition = get_subagent_definition(role)
    return {
        "name": f"builder-subagent-{role}",
        "description": sub_def.description,
        "model": resolve_subagent_model_for_ma(role),
        "system": sub_def.prompt.strip(),
        "tools": _translate_tools(sub_def.tools),
        "metadata": {
            "builder_role": role,
            "builder_kind": "subagent",
            "builder_source": "agents/definitions.py::SUBAGENT_DEFINITIONS",
        },
    }


def build_agent_payload(
    role: str,
    *,
    subagent_id_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render an AgentDefinition + _AGENT_POLICY into an MA agents.create payload.

    Args:
        role: top-level agent role name (e.g. "planner").
        subagent_id_map: maps subagent role name → freshly-provisioned MA
            agent_id. Required if the role has any subagents per
            `_AGENT_POLICY[role][3]`. Missing-id raises a KeyError.
    """
    agent_def: AgentDefinition = get_agent_definition(role)
    mcp_server_names = _mcp_servers_for_role(role)
    payload: dict[str, Any] = {
        "name": f"builder-{role}",
        "description": agent_def.description,
        "model": resolve_agent_model(role),
        "system": _render_system_prompt(agent_def.prompt_template),
        "tools": _translate_tools(agent_def.tools, mcp_servers=mcp_server_names),
        "metadata": {
            "builder_role": role,
            "builder_kind": "agent",
            "builder_source": "agents/definitions.py::AGENT_DEFINITIONS",
        },
    }
    mcp_block = _mcp_servers_block(role)
    if mcp_block:
        payload["mcp_servers"] = mcp_block

    policy = _AGENT_POLICY.get(role)
    subagent_names = policy[3] if policy else ()
    if subagent_names:
        if subagent_id_map is None:
            raise ValueError(
                f"Role '{role}' has subagents {subagent_names} but no "
                "subagent_id_map was supplied. Provision subagents first."
            )
        roster = []
        for name in subagent_names:
            if name not in subagent_id_map:
                raise KeyError(
                    f"Role '{role}' lists subagent '{name}' but no MA agent_id "
                    f"was provisioned for it. subagent_id_map keys: "
                    f"{sorted(subagent_id_map.keys())}"
                )
            roster.append(subagent_id_map[name])
        payload["multiagent"] = {
            "type": "coordinator",
            "agents": roster,
        }

    return payload


def expected_subagent_roster(role: str) -> tuple[str, ...]:
    """Return the subagent roster for a role per `_AGENT_POLICY`."""
    policy = _AGENT_POLICY.get(role)
    return tuple(policy[3]) if policy else ()
