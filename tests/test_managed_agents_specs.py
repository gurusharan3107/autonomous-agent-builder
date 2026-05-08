"""Tests for the spec translator (`agents/definitions.py` → MA payloads).

These are snapshot-style tests that pin the in-code rendering. If they
fail after edits to `agents/definitions.py` or `_AGENT_POLICY`, that's
the intended drift signal — review the diff and update the test.
"""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.definitions import (
    AGENT_DEFINITIONS,
    SUBAGENT_DEFINITIONS,
)
from autonomous_agent_builder.agents.execution_policy import _AGENT_POLICY
from autonomous_agent_builder.services.managed_agents_specs import (
    ALL_AGENT_ROLES,
    ALL_SUBAGENT_ROLES,
    build_agent_payload,
    build_subagent_payload,
    expected_subagent_roster,
    resolve_agent_model,
    resolve_subagent_model_for_ma,
)

# ── Roster constants reflect the source of truth ──


def test_all_agent_roles_matches_agent_definitions_keys() -> None:
    assert set(ALL_AGENT_ROLES) == set(AGENT_DEFINITIONS.keys())


def test_all_subagent_roles_matches_subagent_definitions_keys() -> None:
    assert set(ALL_SUBAGENT_ROLES) == set(SUBAGENT_DEFINITIONS.keys())


# ── Model resolution ──


@pytest.mark.parametrize(
    "role,expected_model",
    [
        ("planner", "claude-opus-4-7"),
        ("designer", "claude-opus-4-7"),
        ("code-gen", "claude-sonnet-4-6"),
        ("feature-verifier", "claude-sonnet-4-6"),
        ("optimization-agent", "claude-sonnet-4-6"),
        ("pr-creator", "claude-sonnet-4-6"),
        ("build-verifier", "claude-sonnet-4-6"),
    ],
)
def test_resolve_agent_model_for_known_roles(role: str, expected_model: str) -> None:
    assert resolve_agent_model(role) == expected_model


def test_resolve_agent_model_falls_back_to_sonnet_for_unknown() -> None:
    assert resolve_agent_model("unknown-role") == "claude-sonnet-4-6"


@pytest.mark.parametrize(
    "role,expected_model",
    [
        ("repo-researcher", "claude-haiku-4-5"),
        ("browser-verifier", "claude-haiku-4-5"),
        ("build-verifier", "claude-haiku-4-5"),
        ("pr-reviewer", "claude-haiku-4-5"),
        ("documentation-agent", "claude-haiku-4-5"),
        ("security-reviewer", "claude-sonnet-4-6"),
    ],
)
def test_resolve_subagent_model_for_known_roles(role: str, expected_model: str) -> None:
    assert resolve_subagent_model_for_ma(role) == expected_model


# ── Subagent payload shape ──


@pytest.mark.parametrize("role", list(ALL_SUBAGENT_ROLES))
def test_build_subagent_payload_renders_all_required_fields(role: str) -> None:
    payload = build_subagent_payload(role)
    assert payload["name"] == f"builder-subagent-{role}"
    assert isinstance(payload["model"], str) and payload["model"].startswith("claude-")
    assert isinstance(payload["system"], str) and payload["system"]
    assert isinstance(payload["tools"], list)
    assert payload["metadata"]["builder_role"] == role
    assert payload["metadata"]["builder_kind"] == "subagent"


def test_subagent_payload_has_no_multiagent_field() -> None:
    """Subagents do NOT have a multiagent roster — they ARE the leaves."""
    for role in ALL_SUBAGENT_ROLES:
        payload = build_subagent_payload(role)
        assert "multiagent" not in payload, role


# ── Top-level agent payload shape ──


@pytest.mark.parametrize("role", list(ALL_AGENT_ROLES))
def test_build_agent_payload_renders_all_required_fields(role: str) -> None:
    """Provide a full subagent_id_map so any role with subagents resolves cleanly."""
    sub_map = {sub: f"agent_sub_{sub}" for sub in ALL_SUBAGENT_ROLES}
    payload = build_agent_payload(role, subagent_id_map=sub_map)
    assert payload["name"] == f"builder-{role}"
    assert isinstance(payload["model"], str) and payload["model"].startswith("claude-")
    assert isinstance(payload["system"], str) and payload["system"]
    assert isinstance(payload["tools"], list)
    assert payload["metadata"]["builder_role"] == role
    assert payload["metadata"]["builder_kind"] == "agent"


def test_agent_payload_omits_multiagent_when_no_subagents() -> None:
    """code-gen, chat, init-project-chat, optimization-agent have no roster."""
    no_roster_roles = [
        role for role in ALL_AGENT_ROLES if not expected_subagent_roster(role)
    ]
    assert no_roster_roles, "expected at least one role with no subagents"
    for role in no_roster_roles:
        payload = build_agent_payload(role, subagent_id_map={})
        assert "multiagent" not in payload, role


def test_agent_payload_includes_multiagent_when_role_has_subagents() -> None:
    sub_map = {sub: f"agent_sub_{sub}" for sub in ALL_SUBAGENT_ROLES}
    roles_with_roster = [
        role for role in ALL_AGENT_ROLES if expected_subagent_roster(role)
    ]
    assert roles_with_roster, "expected at least one role with subagents"
    for role in roles_with_roster:
        payload = build_agent_payload(role, subagent_id_map=sub_map)
        assert "multiagent" in payload, role
        assert payload["multiagent"]["type"] == "coordinator"
        # Roster matches `_AGENT_POLICY[role][3]`
        expected_names = expected_subagent_roster(role)
        expected_ids = [sub_map[name] for name in expected_names]
        assert payload["multiagent"]["agents"] == expected_ids, role


def test_agent_payload_raises_when_subagent_id_missing() -> None:
    """Roles with a roster but no id-map provided fail loudly."""
    role_with_subs = next(
        role for role in ALL_AGENT_ROLES if expected_subagent_roster(role)
    )
    with pytest.raises(ValueError, match="no subagent_id_map"):
        build_agent_payload(role_with_subs, subagent_id_map=None)


def test_agent_payload_raises_on_partial_subagent_id_map() -> None:
    """Roles whose roster references a subagent absent from the map raise KeyError."""
    role_with_subs = next(
        role for role in ALL_AGENT_ROLES if expected_subagent_roster(role)
    )
    # Empty map — all roster names will be missing
    with pytest.raises(KeyError, match="no MA agent_id"):
        build_agent_payload(role_with_subs, subagent_id_map={})


# ── Tool translation ──


def test_tool_translation_maps_pascal_case_to_lowercase() -> None:
    """Read/Glob/Grep/Bash/Write/Edit/WebFetch/WebSearch get enabled in agent_toolset.

    Asserts only against tools the role actually declares — `code-gen`'s tools
    tuple is read directly so this stays robust against future tool changes.
    """
    payload = build_agent_payload("code-gen", subagent_id_map={})
    tools = payload["tools"]
    toolset = next(t for t in tools if t.get("type") == "agent_toolset_20260401")
    enabled = sorted(c["name"] for c in toolset["configs"] if c.get("enabled"))

    builtin_map = {
        "Read": "read",
        "Glob": "glob",
        "Grep": "grep",
        "Bash": "bash",
        "Write": "write",
        "Edit": "edit",
        "WebFetch": "web_fetch",
        "WebSearch": "web_search",
    }
    expected = sorted(
        builtin_map[t]
        for t in AGENT_DEFINITIONS["code-gen"].tools
        if t in builtin_map
    )
    assert enabled == expected, (enabled, expected)


def test_planner_tools_include_builder_memory_search_when_explicit() -> None:
    """If the role's tools tuple lists mcp__builder__memory_search, the host-side
    custom tool is included; otherwise it isn't."""
    sub_map = {sub: f"agent_sub_{sub}" for sub in ALL_SUBAGENT_ROLES}
    planner = build_agent_payload("planner", subagent_id_map=sub_map)
    custom_tools = [t for t in planner["tools"] if t.get("type") == "custom"]
    custom_names = [t["name"] for t in custom_tools]
    # planner's AgentDefinition.tools includes mcp__builder__memory_search per
    # current source of truth — verify by checking AGENT_DEFINITIONS directly
    if "mcp__builder__memory_search" in AGENT_DEFINITIONS["planner"].tools:
        assert "builder_memory_search" in custom_names
    else:
        assert "builder_memory_search" not in custom_names


# ── Multiagent roster matches _AGENT_POLICY snapshot ──


def test_expected_subagent_roster_mirrors_policy() -> None:
    """Catch any drift between `_AGENT_POLICY[role][3]` and what we read."""
    for role, policy in _AGENT_POLICY.items():
        if role not in ALL_AGENT_ROLES:
            continue
        assert expected_subagent_roster(role) == policy[3], role


def test_system_prompt_replaces_placeholders_with_angle_markers() -> None:
    """`{language}` → `<language>` so per-task data references are visible."""
    payload = build_agent_payload("planner", subagent_id_map={
        sub: f"agent_sub_{sub}" for sub in ALL_SUBAGENT_ROLES
    })
    system = payload["system"]
    # planner's prompt_template references {language} and {feature_description}
    assert "<language>" in system or "<feature_description>" in system
    # No raw `{name}` placeholders should leak through
    assert "{language}" not in system
    assert "{feature_description}" not in system
