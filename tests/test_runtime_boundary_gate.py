from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder.quality_gates.runtime_boundary import (
    assert_runtime_boundary_clean,
    scan_runtime_boundary,
)


def test_runtime_boundary_gate_passes_for_repo():
    assert_runtime_boundary_clean()


def test_runtime_boundary_gate_blocks_cli_bridge_import(tmp_path: Path):
    protected = tmp_path / "src" / "autonomous_agent_builder" / "agents" / "runtime.py"
    protected.parent.mkdir(parents=True)
    protected.write_text(
        (
            "from autonomous_agent_builder.agents.tools import cli_tools\n\n"
            "async def run():\n"
            "    return await cli_tools.builder_board()\n"
        ),
        encoding="utf-8",
    )

    violations = scan_runtime_boundary(repo_root=tmp_path)

    assert [item.rule for item in violations] == ["runtime_cli_bridge_import"]
    assert "owning service layer" in violations[0].remediation


def test_runtime_boundary_gate_blocks_direct_builder_shellout(tmp_path: Path):
    runtime_file = tmp_path / "src" / "autonomous_agent_builder" / "claude_runtime.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text(
        (
            "import asyncio\n\n"
            "async def run():\n"
            "    command = [\"builder\", \"task\", \"show\", \"T-1\"]\n"
            "    return await asyncio.create_subprocess_exec(*command)\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError) as excinfo:
        assert_runtime_boundary_clean(repo_root=tmp_path)

    message = str(excinfo.value)
    assert "runtime_builder_shellout" in message
    assert "builder_tool_service" in message


def test_runtime_boundary_gate_allows_service_layer_shellout(tmp_path: Path):
    service_file = (
        tmp_path
        / "src"
        / "autonomous_agent_builder"
        / "services"
        / "builder_tool_service.py"
    )
    service_file.parent.mkdir(parents=True)
    service_file.write_text(
        (
            "import asyncio\n\n"
            "async def run():\n"
            "    command = [\"builder\", \"task\", \"show\", \"T-1\"]\n"
            "    return await asyncio.create_subprocess_exec(*command)\n"
        ),
        encoding="utf-8",
    )
    protected = tmp_path / "src" / "autonomous_agent_builder" / "agents" / "runtime.py"
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text(
        (
            "from autonomous_agent_builder.services import builder_tool_service\n\n"
            "async def run():\n"
            "    return await builder_tool_service.run()\n"
        ),
        encoding="utf-8",
    )

    assert scan_runtime_boundary(repo_root=tmp_path) == []
