from __future__ import annotations

import os
import sys

import pytest

from autonomous_agent_builder.agents.tools.workspace_tools import (
    compact_workspace_map,
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
async def test_run_linter_node_workspace_routes_to_npm_lint(tmp_path, monkeypatch) -> None:
    # Node workspace with a lint script: run_linter must call npm run lint, not ruff.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_npm = bin_dir / "npm"
    fake_npm.write_text(
        f"#!{sys.executable}\nimport sys\nprint('npm lint ok')\nsys.exit(0)\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    (tmp_path / "package.json").write_text(
        '{"scripts": {"lint": "eslint ."}, "devDependencies": {}}',
        encoding="utf-8",
    )

    result = await run_linter(str(tmp_path))

    assert result["metadata"]["clean"] is True
    assert "npm lint ok" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_run_linter_node_workspace_no_lint_script_falls_back_to_ruff(
    tmp_path, monkeypatch
) -> None:
    # Node workspace without a lint script falls back to ruff (Python linter).
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ruff = bin_dir / "ruff"
    fake_ruff.write_text(
        f"#!{sys.executable}\nprint('ruff ok')\nimport sys\nsys.exit(0)\n",
        encoding="utf-8",
    )
    fake_ruff.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    (tmp_path / "package.json").write_text(
        '{"scripts": {}, "devDependencies": {}}',
        encoding="utf-8",
    )

    result = await run_linter(str(tmp_path))

    assert result["metadata"]["clean"] is True
    assert "ruff ok" in result["content"][0]["text"]


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


def test_compact_workspace_map_lists_source_and_skips_noise(tmp_path) -> None:
    # IMP-027 context follow-up: the map gives code-gen the file tree upfront so
    # it does not spend turns rediscovering it. Must skip dependency/build/VCS
    # noise and hidden files, and emit relative paths.
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "src" / "app.js").write_text("x")
    (tmp_path / "node_modules" / "pkg" / "junk.js").write_text("x")
    (tmp_path / ".git" / "HEAD").write_text("x")
    (tmp_path / ".env").write_text("secret")

    result = compact_workspace_map(str(tmp_path))
    lines = result.splitlines()
    assert "index.html" in lines
    assert "src/app.js" in lines
    assert not any("node_modules" in line for line in lines)
    assert not any(line.startswith(".git") for line in lines)
    assert ".env" not in lines  # hidden files excluded


def test_compact_workspace_map_handles_missing_and_empty(tmp_path) -> None:
    assert compact_workspace_map(str(tmp_path / "does-not-exist")) == ""
    assert compact_workspace_map(str(tmp_path)) == ""  # empty workspace


def test_compact_workspace_map_caps_file_count(tmp_path) -> None:
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x")
    result = compact_workspace_map(str(tmp_path), max_files=4)
    assert "truncated at 4 files" in result
    assert len([line for line in result.splitlines() if line.endswith(".txt")]) == 4


@pytest.mark.asyncio
async def test_run_linter_installs_deps_when_node_modules_absent(
    tmp_path, monkeypatch
) -> None:
    # scaffold writes package.json but does not run npm install;
    # run_linter must install deps before invoking npm run lint.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "npm_calls.txt"

    fake_npm = bin_dir / "npm"
    fake_npm.write_text(
        f"#!{sys.executable}\n"
        "import sys, os\n"
        f"open(r'{calls_file}', 'a').write(sys.argv[1] + '\\n')\n"
        "print('ok')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    (tmp_path / "package.json").write_text(
        '{"scripts": {"lint": "eslint ."}}', encoding="utf-8"
    )
    # node_modules deliberately absent — no package-lock.json → npm install path
    assert not (tmp_path / "node_modules").exists()

    await run_linter(str(tmp_path))

    logged = calls_file.read_text().splitlines()
    assert "install" in logged, "npm install must be called before npm run lint"
    assert "run" in logged, "npm run lint must be called after install"
    assert logged.index("install") < logged.index("run"), "install before run"


@pytest.mark.asyncio
async def test_run_linter_skips_install_when_node_modules_present(
    tmp_path, monkeypatch
) -> None:
    # When node_modules already exists, run_linter must NOT call npm install.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_file = tmp_path / "npm_calls.txt"

    fake_npm = bin_dir / "npm"
    fake_npm.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"open(r'{calls_file}', 'a').write(sys.argv[1] + '\\n')\n"
        "print('ok')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    (tmp_path / "package.json").write_text(
        '{"scripts": {"lint": "eslint ."}}', encoding="utf-8"
    )
    (tmp_path / "node_modules").mkdir()  # already present

    await run_linter(str(tmp_path))

    logged = calls_file.read_text().splitlines()
    assert "install" not in logged, "npm install must NOT be called when node_modules exists"
    assert "run" in logged
