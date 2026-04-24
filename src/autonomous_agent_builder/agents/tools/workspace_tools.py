"""Custom workspace tools — @tool decorated functions for agent use.

These become MCP tools via create_sdk_mcp_server(). The agent runner
registers them as mcp__workspace__<tool_name>.

SECURITY: Bash tool must use subprocess with argv arrays, never shell=True.
This is non-negotiable per architecture decision.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


async def run_tests(workspace_path: str, test_pattern: str = "") -> dict:
    """Run pytest in the workspace directory.

    Args:
        workspace_path: Absolute path to workspace root.
        test_pattern: Optional pytest pattern to filter tests.
    """
    cmd = ["pytest", "--tb=short", "-q", "--no-header"]
    if test_pattern:
        cmd.append(test_pattern)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workspace_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    output = stdout.decode() + stderr.decode()
    passed = proc.returncode == 0

    return {
        "content": [{"type": "text", "text": output}],
        "metadata": {"passed": passed, "exit_code": proc.returncode},
    }


async def run_linter(workspace_path: str, fix: bool = False) -> dict:
    """Run ruff linter on workspace code.

    Args:
        workspace_path: Absolute path to workspace root.
        fix: If True, auto-fix issues.
    """
    cmd = ["ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.append(workspace_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    output = stdout.decode() + stderr.decode()
    clean = proc.returncode == 0

    return {
        "content": [{"type": "text", "text": output}],
        "metadata": {"clean": clean, "exit_code": proc.returncode},
    }


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

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout_sec,
        )
        stdout, stderr = await proc.communicate()
    except TimeoutError:
        return {
            "content": [{"type": "text", "text": f"Command timed out after {timeout_sec}s"}],
            "metadata": {"exit_code": -1, "timeout": True},
        }

    output = stdout.decode() + stderr.decode()
    return {
        "content": [{"type": "text", "text": output}],
        "metadata": {"exit_code": proc.returncode},
    }


async def read_file(workspace_path: str, file_path: str) -> dict:
    """Read a file within the workspace boundary.

    Args:
        workspace_path: Absolute path to workspace root.
        file_path: Relative path within workspace.
    """
    full_path = Path(workspace_path) / file_path
    resolved = full_path.resolve()

    # Enforce workspace boundary
    if not str(resolved).startswith(str(Path(workspace_path).resolve())):
        return {
            "content": [{"type": "text", "text": f"Error: path escapes workspace: {file_path}"}]
        }

    if not resolved.is_file():
        return {"content": [{"type": "text", "text": f"Error: file not found: {file_path}"}]}

    content = resolved.read_text(encoding="utf-8")
    return {"content": [{"type": "text", "text": content}]}


async def list_directory(workspace_path: str, relative_path: str = ".") -> dict:
    """List directory contents within workspace.

    Args:
        workspace_path: Absolute path to workspace root.
        relative_path: Relative path within workspace.
    """
    target = Path(workspace_path) / relative_path
    resolved = target.resolve()

    if not str(resolved).startswith(str(Path(workspace_path).resolve())):
        return {"content": [{"type": "text", "text": "Error: path escapes workspace"}]}

    if not resolved.is_dir():
        return {"content": [{"type": "text", "text": f"Error: not a directory: {relative_path}"}]}

    entries = []
    for entry in sorted(resolved.iterdir()):
        kind = "dir" if entry.is_dir() else "file"
        entries.append(f"[{kind}] {entry.name}")

    return {"content": [{"type": "text", "text": "\n".join(entries)}]}


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
