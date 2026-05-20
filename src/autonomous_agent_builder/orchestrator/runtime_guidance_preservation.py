"""Preserve Builder-owned runtime guidance during task workspace git operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from autonomous_agent_builder.db.models import Task

log = structlog.get_logger()

PROJECT_RUNTIME_GUIDANCE_PATHS = (
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path(".claude") / "CLAUDE.md",
)
GitRunner = Callable[..., Awaitable[tuple[int, str]]]


def tracked_modified_paths(status_output: str, paths: list[str]) -> list[str]:
    """Filter paths to tracked-modified entries from ``git status --short``."""
    requested = set(paths)
    tracked: list[str] = []
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        xy, rest = line[:2], line[3:].strip()
        if xy == "??":
            continue
        path = rest.split(" -> ")[-1].strip().strip('"')
        if path in requested and path not in tracked:
            tracked.append(path)
    return tracked


def untracked_paths(status_output: str, paths: list[str]) -> list[str]:
    """Filter paths to untracked entries from ``git status --short``."""
    requested = set(paths)
    untracked: list[str] = []
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        xy, rest = line[:2], line[3:].strip()
        if xy != "??":
            continue
        path = rest.strip().strip('"')
        if path in requested and path not in untracked:
            untracked.append(path)
    return untracked


def _status_path(line: str) -> str:
    if len(line) < 4:
        return ""
    rest = line[3:].strip()
    return rest.split(" -> ")[-1].strip().strip('"')


def non_guidance_status_lines(status_output: str) -> list[str]:
    """Return tracked status lines that are not Builder runtime guidance."""
    guidance_paths = {str(path) for path in PROJECT_RUNTIME_GUIDANCE_PATHS}
    lines: list[str] = []
    for line in status_output.splitlines():
        path = _status_path(line)
        if path and path not in guidance_paths:
            lines.append(line)
    return lines


def project_runtime_guidance_snapshot(repo_root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for relative_path in PROJECT_RUNTIME_GUIDANCE_PATHS:
        path = repo_root / relative_path
        if path.is_file():
            snapshot[str(relative_path)] = path.read_bytes()
    return snapshot


async def clean_project_runtime_guidance_for_git_operation(
    run_git: GitRunner,
    snapshot: dict[str, bytes],
) -> str | None:
    paths = list(snapshot)
    if not paths:
        return None
    head_code, _ = await run_git("rev-parse", "--verify", "HEAD")
    if head_code != 0:
        return None
    status_code, status_output = await run_git("status", "--short", "--", *paths)
    if status_code != 0:
        return (
            "Integration failed: could not inspect runtime guidance before merge: "
            f"{status_output.strip()}"
        )
    if not status_output.strip():
        return None

    untracked = untracked_paths(status_output, paths)
    if untracked:
        clean_code, clean_output = await run_git("clean", "-f", "--", *untracked)
        if clean_code != 0:
            return (
                "Integration failed: could not prepare untracked runtime guidance "
                f"before merge: {clean_output.strip()}"
            )

    tracked_modified = tracked_modified_paths(status_output, paths)
    if not tracked_modified:
        return None
    checkout_code, checkout_output = await run_git("checkout", "--", *tracked_modified)
    if checkout_code != 0:
        return (
            "Integration failed: could not prepare runtime guidance before merge: "
            f"{checkout_output.strip()}"
        )
    return None


async def restore_project_runtime_guidance_snapshot(
    repo_root: Path,
    snapshot: dict[str, bytes],
    run_git: GitRunner,
) -> str | None:
    restored: list[str] = []
    for relative_path, expected in snapshot.items():
        path = repo_root / relative_path
        current = path.read_bytes() if path.is_file() else None
        if current == expected:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected)
        restored.append(relative_path)
    if not restored:
        return None
    add_code, add_output = await run_git("add", "--", *restored)
    if add_code != 0:
        return (
            "Integration failed: could not restore runtime guidance after merge: "
            f"{add_output.strip()}"
        )
    diff_code, diff_output = await run_git("diff", "--cached", "--name-only", "--", *restored)
    if diff_code != 0:
        return (
            "Integration failed: could not inspect restored runtime guidance: "
            f"{diff_output.strip()}"
        )
    if not diff_output.strip():
        return None
    commit_code, commit_output = await run_git(
        "-c",
        "user.name=Autonomous Builder",
        "-c",
        "user.email=builder@example.local",
        "commit",
        "-m",
        "chore: restore builder runtime guidance",
        "--",
        *restored,
    )
    if commit_code != 0:
        return (
            "Integration failed: could not commit restored runtime guidance: "
            f"{commit_output.strip()}"
        )
    return None


async def preserve_project_runtime_guidance(task: Task, workspace_path: str) -> str | None:
    """Keep builder runtime guidance from being replaced by generated app docs."""
    if not workspace_path:
        return None

    repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
    if not repo_url:
        return None
    repo_root = Path(repo_url).expanduser()
    workspace = Path(workspace_path).expanduser()
    if not repo_root.exists() or not workspace.exists():
        return None

    restored: list[str] = []
    for relative_path in PROJECT_RUNTIME_GUIDANCE_PATHS:
        source = repo_root / relative_path
        target = workspace / relative_path
        if not source.is_file():
            continue
        source_bytes = source.read_bytes()
        target_bytes = target.read_bytes() if target.is_file() else None
        if target_bytes == source_bytes:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_bytes)
        restored.append(str(relative_path))

    if not restored:
        return None

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(errors="replace") + stderr.decode(errors="replace")

    add_code, add_output = await run_git("add", "--", *restored)
    if add_code != 0:
        return f"Owner surface protection failed: could not stage runtime guidance: {add_output.strip()}"

    diff_code, diff_output = await run_git("diff", "--cached", "--name-only", "--", *restored)
    if diff_code != 0:
        return f"Owner surface protection failed: could not inspect runtime guidance: {diff_output.strip()}"
    if not diff_output.strip():
        return None

    commit_code, commit_output = await run_git(
        "-c",
        "user.name=Autonomous Builder",
        "-c",
        "user.email=builder@example.local",
        "commit",
        "-m",
        "chore: preserve builder runtime guidance",
        "--",
        *restored,
    )
    if commit_code != 0:
        return f"Owner surface protection failed: could not commit runtime guidance: {commit_output.strip()}"

    log.info(
        "project_runtime_guidance_preserved",
        task_id=task.id,
        paths=restored,
    )
    return None
