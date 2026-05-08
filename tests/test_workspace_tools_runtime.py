from __future__ import annotations

import sys

import pytest

from autonomous_agent_builder.agents.tools.workspace_tools import run_command


@pytest.mark.asyncio
async def test_run_command_timeout_kills_process(tmp_path) -> None:
    result = await run_command(
        str(tmp_path),
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout_sec=0.1,
    )

    assert result["metadata"]["timeout"] is True
    assert result["metadata"]["killed"] is True
    assert result["metadata"]["exit_code"] == 124
    assert result["metadata"]["code"] == "command_timeout"
