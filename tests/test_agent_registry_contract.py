"""Contract test: every agent's allowed_tools must exist in _SDK_BUILTINS.

Catches contract drift between `agents/definitions.py` (which declares each
agent's tools tuple) and `agents/tool_registry.py` (which provides the
ToolSchema entries). Tools listed in an agent definition but missing from the
registry get silently dropped at runtime with a `tool_not_found_in_registry`
warning, then the agent's prompt template instructs the model to call them
anyway — which historically caused chat→chat lifecycle hangs (P19; autoresearch
INSIGHTS Run #10 / 2026-05-24).

If this test fails the fix is one of:
  - Add the missing ToolSchema to `_SDK_BUILTINS` in `tool_registry.py`
  - Or remove the tool from the agent's `allowed_tools` list
  - Or (for MCP custom tools provided at runtime) add the tool to the
    EXPECTED_RUNTIME_CUSTOM_TOOLS set below with a comment.

Runs in <1 second; wired into autoresearch preflight Recipe 1/2 so a single
catalog regression doesn't burn a $5 baseline run before it's caught.
"""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.definitions import AGENT_DEFINITIONS
from autonomous_agent_builder.agents.tool_registry import (
    _SDK_BUILTINS,
    ToolRegistry,
)

# Some tools are provided as MCP custom tools at runtime (via custom_tools dict
# passed to ToolRegistry.build). They're not in _SDK_BUILTINS but are valid in
# production. List them here so the contract test treats them as registered.
# As of 2026-05-24, all mcp__ tools used by Builder are declared statically in
# _SDK_BUILTINS, so this set is empty. Add an entry (with a comment naming the
# runtime provider) when a new MCP custom tool surfaces.
EXPECTED_RUNTIME_CUSTOM_TOOLS: set[str] = set()


def _resolve_tool(name: str) -> bool:
    """Return True iff `name` would resolve at registry build time."""
    if name in _SDK_BUILTINS:
        return True
    if name in EXPECTED_RUNTIME_CUSTOM_TOOLS:
        return True
    return False


@pytest.mark.parametrize("agent_name", sorted(AGENT_DEFINITIONS.keys()))
def test_every_agent_allowed_tool_has_a_schema(agent_name: str) -> None:
    """Every tool name in an agent's allowed_tools must resolve to a schema.

    Failure means the registry will silently drop the tool at runtime,
    leaving the agent's prompt template referencing a tool the model can't
    actually invoke. Symptom in production: P19-class lifecycle hang.
    """
    agent = AGENT_DEFINITIONS[agent_name]
    missing = [t for t in agent.tools if not _resolve_tool(t)]
    assert not missing, (
        f"Agent '{agent_name}' declares {len(missing)} tool(s) that are "
        f"missing from both _SDK_BUILTINS and EXPECTED_RUNTIME_CUSTOM_TOOLS: "
        f"{missing}. Fix by adding ToolSchema entries to "
        f"src/autonomous_agent_builder/agents/tool_registry.py:_SDK_BUILTINS, "
        f"OR removing the tools from allowed_tools in "
        f"src/autonomous_agent_builder/agents/definitions.py."
    )


@pytest.mark.parametrize("agent_name", sorted(AGENT_DEFINITIONS.keys()))
def test_registry_build_drops_zero_tools(agent_name: str) -> None:
    """Build each agent's registry; assert the resulting tool count equals
    the declared allowed_tools count (no silent drops).

    This is the runtime version of the test above: it actually invokes
    ToolRegistry.build (the same call path used by the orchestrator) and
    counts what survives. Pass means the registry is at parity with the
    declaration.
    """
    agent = AGENT_DEFINITIONS[agent_name]
    declared = list(dict.fromkeys(agent.tools))  # de-dupe defensively
    registry = ToolRegistry.build(declared, custom_tools=None)
    built = set(registry.tools.keys())
    expected = set(declared) & (set(_SDK_BUILTINS.keys())
                                  | EXPECTED_RUNTIME_CUSTOM_TOOLS)
    missing = expected - built
    extra = built - expected
    assert not missing, (
        f"Agent '{agent_name}': registry build dropped {len(missing)} "
        f"tool(s): {sorted(missing)}. Expected all {len(expected)} resolvable "
        f"declarations to survive."
    )
    assert not extra, (
        f"Agent '{agent_name}': registry built extras not in declaration: "
        f"{sorted(extra)}. Did ToolRegistry.build start auto-injecting?"
    )


def test_at_least_one_agent_exists() -> None:
    """Smoke check — keep the parameterize sets from silently zeroing out."""
    assert len(AGENT_DEFINITIONS) > 0, "AGENT_DEFINITIONS is empty"
