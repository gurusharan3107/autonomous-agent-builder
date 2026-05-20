"""Custom workspace tools — @tool decorated functions for agent use.

These become MCP tools via create_sdk_mcp_server(). The agent runner
registers them as mcp__workspace__<tool_name>.

SECURITY: Bash tool must use subprocess with argv arrays, never shell=True.
This is non-negotiable per architecture decision.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from autonomous_agent_builder.services.path_containment import resolve_contained_path

MAX_COMMAND_OUTPUT_CHARS = 6000
MAX_FILE_CHARS = 12000
MAX_DIRECTORY_ENTRIES = 200
DEFAULT_TEST_TIMEOUT_SEC = 300
DEFAULT_LINTER_TIMEOUT_SEC = 120
MAX_TOOL_TIMEOUT_SEC = 900


def _bounded_text(text: str, *, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    marker = "\n... (truncated; rerun with a narrower command, file slice, or directory)\n"
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars - len(marker)
    return text[:head_chars] + marker + text[-max(tail_chars, 0) :], True


def _text_payload(
    text: str,
    *,
    metadata: dict | None = None,
    max_chars: int = MAX_COMMAND_OUTPUT_CHARS,
) -> dict:
    bounded, truncated = _bounded_text(text, max_chars=max_chars)
    return {
        "content": [{"type": "text", "text": bounded}],
        "metadata": {
            **(metadata or {}),
            "output_chars": len(text),
            "truncated": truncated,
            "max_output_chars": max_chars,
        },
    }


def _resolve_workspace_member(workspace_path: str, relative_path: str) -> Path | None:
    return resolve_contained_path(workspace_path, relative_path)


def _bounded_timeout(value: int | float | None, *, default: int) -> float:
    try:
        timeout = float(value if value is not None else default)
    except (TypeError, ValueError):
        timeout = float(default)
    return max(min(timeout, float(MAX_TOOL_TIMEOUT_SEC)), 0.1)


def _process_kwargs() -> dict:
    if sys.platform == "win32":
        return {}
    return {"start_new_session": True}


async def _communicate_with_timeout(
    proc: asyncio.subprocess.Process,
    *,
    timeout_sec: float,
) -> tuple[bytes, bytes, bool]:
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        return stdout, stderr, False
    except TimeoutError:
        await _terminate_process_tree(proc)
        return b"", b"", True


def _timeout_payload(timeout_sec: float, proc: asyncio.subprocess.Process) -> dict:
    return {
        "content": [{"type": "text", "text": f"Command timed out after {timeout_sec:g}s"}],
        "metadata": {
            "exit_code": 124,
            "timeout": True,
            "killed": True,
            "pid": proc.pid,
            "code": "command_timeout",
        },
    }


async def run_tests(
    workspace_path: str,
    test_pattern: str = "",
    timeout_sec: int | float = DEFAULT_TEST_TIMEOUT_SEC,
) -> dict:
    """Run pytest in the workspace directory.

    Args:
        workspace_path: Absolute path to workspace root.
        test_pattern: Optional pytest pattern to filter tests.
    """
    cmd = ["pytest", "--tb=short", "-q", "--no-header"]
    if test_pattern:
        cmd.append(test_pattern)

    safe_timeout = _bounded_timeout(timeout_sec, default=DEFAULT_TEST_TIMEOUT_SEC)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_process_kwargs(),
    )
    stdout, stderr, timed_out = await _communicate_with_timeout(proc, timeout_sec=safe_timeout)
    if timed_out:
        payload = _timeout_payload(safe_timeout, proc)
        payload["metadata"]["passed"] = False
        return payload

    output = stdout.decode() + stderr.decode()
    passed = proc.returncode == 0

    return _text_payload(
        output,
        metadata={"passed": passed, "exit_code": proc.returncode, "timeout": False},
    )


async def run_linter(
    workspace_path: str,
    fix: bool = False,
    timeout_sec: int | float = DEFAULT_LINTER_TIMEOUT_SEC,
) -> dict:
    """Run ruff linter on workspace code.

    Args:
        workspace_path: Absolute path to workspace root.
        fix: If True, auto-fix issues.
    """
    cmd = ["ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.append(workspace_path)

    safe_timeout = _bounded_timeout(timeout_sec, default=DEFAULT_LINTER_TIMEOUT_SEC)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_process_kwargs(),
    )
    stdout, stderr, timed_out = await _communicate_with_timeout(proc, timeout_sec=safe_timeout)
    if timed_out:
        payload = _timeout_payload(safe_timeout, proc)
        payload["metadata"]["clean"] = False
        return payload

    output = stdout.decode() + stderr.decode()
    clean = proc.returncode == 0

    return _text_payload(
        output,
        metadata={"clean": clean, "exit_code": proc.returncode, "timeout": False},
    )


async def run_command(workspace_path: str, argv: list[str], timeout_sec: int = 60) -> dict:
    """Run an arbitrary command in the workspace using argv array.

    SECURITY: This always uses subprocess with argv, never shell=True.
    The PreToolUse hook validates workspace boundary before execution.

    Args:
        workspace_path: Absolute path to workspace root.
        argv: Command as array of arguments (e.g. ["npm", "test"]).
        timeout_sec: Timeout in seconds.
    """
    if not argv:
        return {"content": [{"type": "text", "text": "Error: empty argv"}]}

    safe_timeout = _bounded_timeout(timeout_sec, default=60)
    process_kwargs = _process_kwargs()

    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **process_kwargs,
    )
    stdout, stderr, timed_out = await _communicate_with_timeout(proc, timeout_sec=safe_timeout)
    if timed_out:
        return _timeout_payload(safe_timeout, proc)

    output = stdout.decode() + stderr.decode()
    return _text_payload(
        output,
        metadata={
            "exit_code": proc.returncode,
            "argv": argv,
        },
    )


async def _terminate_process_tree(
    proc: asyncio.subprocess.Process,
    *,
    grace_seconds: float = 2.0,
) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        proc.kill()
        await proc.wait()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.kill()
    await proc.wait()


async def read_file(
    workspace_path: str,
    file_path: str,
    start_line: int = 1,
    max_lines: int = 200,
) -> dict:
    """Read a file within the workspace boundary.

    Args:
        workspace_path: Absolute path to workspace root.
        file_path: Relative path within workspace.
    """
    resolved = _resolve_workspace_member(workspace_path, file_path)

    # Enforce workspace boundary
    if resolved is None:
        return {
            "content": [{"type": "text", "text": f"Error: path escapes workspace: {file_path}"}]
        }

    if not resolved.is_file():
        return {"content": [{"type": "text", "text": f"Error: file not found: {file_path}"}]}

    content = resolved.read_text(encoding="utf-8")
    lines = content.splitlines()
    safe_start = max(int(start_line or 1), 1)
    safe_max_lines = max(int(max_lines or 200), 1)
    start_index = min(safe_start - 1, len(lines))
    end_index = min(start_index + safe_max_lines, len(lines))
    selected = "\n".join(lines[start_index:end_index])
    if content.endswith("\n") and selected:
        selected += "\n"
    return _text_payload(
        selected,
        metadata={
            "file_path": file_path,
            "start_line": safe_start,
            "max_lines": safe_max_lines,
            "total_lines": len(lines),
            "returned_lines": end_index - start_index,
            "omitted_lines": max(len(lines) - end_index, 0),
            "file_chars": len(content),
        },
        max_chars=MAX_FILE_CHARS,
    )


async def list_directory(workspace_path: str, relative_path: str = ".") -> dict:
    """List directory contents within workspace.

    Args:
        workspace_path: Absolute path to workspace root.
        relative_path: Relative path within workspace.
    """
    resolved = _resolve_workspace_member(workspace_path, relative_path)

    if resolved is None:
        return {"content": [{"type": "text", "text": "Error: path escapes workspace"}]}

    if not resolved.is_dir():
        return {"content": [{"type": "text", "text": f"Error: not a directory: {relative_path}"}]}

    all_entries = sorted(resolved.iterdir())
    entries = []
    for entry in all_entries[:MAX_DIRECTORY_ENTRIES]:
        kind = "dir" if entry.is_dir() else "file"
        entries.append(f"[{kind}] {entry.name}")

    omitted = max(len(all_entries) - len(entries), 0)
    text = "\n".join(entries)
    if omitted:
        text += f"\n... ({omitted} entries omitted; inspect a narrower directory)"
    return _text_payload(
        text,
        metadata={
            "relative_path": relative_path,
            "entry_count": len(all_entries),
            "returned_entries": len(entries),
            "omitted_entries": omitted,
        },
    )


async def get_project_info(workspace_path: str) -> dict:
    """Detect project language and structure.

    Args:
        workspace_path: Absolute path to workspace root.
    """
    wp = Path(workspace_path)
    info: dict = {"path": workspace_path, "language": "unknown", "build_files": []}

    # Detect language from build files
    detectors = {
        "pyproject.toml": "python",
        "setup.py": "python",
        "requirements.txt": "python",
        "package.json": "node",
        "pom.xml": "java",
        "build.gradle": "java",
        "Cargo.toml": "rust",
        "go.mod": "go",
    }

    for filename, lang in detectors.items():
        if (wp / filename).exists():
            info["language"] = lang
            info["build_files"].append(filename)

    # Read package manager config if available
    if (wp / "package.json").exists():
        try:
            pkg = json.loads((wp / "package.json").read_text())
            info["name"] = pkg.get("name", "")
            info["scripts"] = list(pkg.get("scripts", {}).keys())
        except json.JSONDecodeError:
            pass
    elif (wp / "pyproject.toml").exists():
        info["name"] = wp.name

    return {"content": [{"type": "text", "text": json.dumps(info, indent=2)}]}


# Registry of all workspace tools — used by the MCP server builder
WORKSPACE_TOOLS = {
    "run_tests": run_tests,
    "run_linter": run_linter,
    "run_command": run_command,
    "read_file": read_file,
    "list_directory": list_directory,
    "get_project_info": get_project_info,
}
