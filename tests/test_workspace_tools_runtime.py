from __future__ import annotations

import os
import sys

import pytest

from autonomous_agent_builder.agents.tools.workspace_tools import (
    list_directory,
    read_file,
    run_command,
    run_linter,
    run_tests,
)


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


@pytest.mark.asyncio
async def test_run_tests_timeout_kills_process(tmp_path) -> None:
    test_file = tmp_path / "test_sleep.py"
    test_file.write_text(
        "import time\n\n\ndef test_sleep():\n    time.sleep(10)\n",
        encoding="utf-8",
    )

    result = await run_tests(str(tmp_path), timeout_sec=0.1)

    assert result["metadata"]["timeout"] is True
    assert result["metadata"]["killed"] is True
    assert result["metadata"]["passed"] is False
    assert result["metadata"]["exit_code"] == 124
    assert result["metadata"]["code"] == "command_timeout"


@pytest.mark.asyncio
async def test_run_linter_timeout_kills_process(tmp_path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ruff = bin_dir / "ruff"
    fake_ruff.write_text(
        f"#!{sys.executable}\nimport time\ntime.sleep(10)\n",
        encoding="utf-8",
    )
    fake_ruff.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    result = await run_linter(str(tmp_path), timeout_sec=0.1)

    assert result["metadata"]["timeout"] is True
    assert result["metadata"]["killed"] is True
    assert result["metadata"]["clean"] is False
    assert result["metadata"]["exit_code"] == 124
    assert result["metadata"]["code"] == "command_timeout"


@pytest.mark.asyncio
async def test_run_command_bounds_large_output(tmp_path) -> None:
    result = await run_command(
        str(tmp_path),
        [sys.executable, "-c", "print('x' * 20000)"],
        timeout_sec=5,
    )

    text = result["content"][0]["text"]
    assert len(text) <= result["metadata"]["max_output_chars"]
    assert result["metadata"]["truncated"] is True
    assert result["metadata"]["output_chars"] > result["metadata"]["max_output_chars"]


@pytest.mark.asyncio
async def test_read_file_returns_bounded_slice_by_default(tmp_path) -> None:
    path = tmp_path / "large.txt"
    path.write_text("\n".join(f"line-{index}" for index in range(300)), encoding="utf-8")

    result = await read_file(str(tmp_path), "large.txt")

    assert result["metadata"]["total_lines"] == 300
    assert result["metadata"]["returned_lines"] == 200
    assert result["metadata"]["omitted_lines"] == 100
    assert "line-199" in result["content"][0]["text"]
    assert "line-250" not in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_read_file_rejects_sibling_prefix_escape(tmp_path) -> None:
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-secret"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("outside", encoding="utf-8")

    result = await read_file(str(workspace), "../work-secret/secret.txt")

    assert result["content"][0]["text"] == (
        "Error: path escapes workspace: ../work-secret/secret.txt"
    )


@pytest.mark.asyncio
async def test_read_file_rejects_symlink_escape(tmp_path) -> None:
    workspace = tmp_path / "work"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    (workspace / "linked.txt").symlink_to(outside / "secret.txt")

    result = await read_file(str(workspace), "linked.txt")

    assert result["content"][0]["text"] == "Error: path escapes workspace: linked.txt"


@pytest.mark.asyncio
async def test_list_directory_limits_large_directories(tmp_path) -> None:
    for index in range(250):
        (tmp_path / f"file-{index:03d}.txt").write_text("x", encoding="utf-8")

    result = await list_directory(str(tmp_path))

    assert result["metadata"]["entry_count"] == 250
    assert result["metadata"]["returned_entries"] == 200
    assert result["metadata"]["omitted_entries"] == 50
    assert "entries omitted" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_list_directory_rejects_sibling_prefix_escape(tmp_path) -> None:
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-secret"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("outside", encoding="utf-8")

    result = await list_directory(str(workspace), "../work-secret")

    assert result["content"][0]["text"] == "Error: path escapes workspace"


@pytest.mark.asyncio
async def test_list_directory_rejects_symlink_escape(tmp_path) -> None:
    workspace = tmp_path / "work"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    (workspace / "linked-dir").symlink_to(outside, target_is_directory=True)

    result = await list_directory(str(workspace), "linked-dir")

    assert result["content"][0]["text"] == "Error: path escapes workspace"
