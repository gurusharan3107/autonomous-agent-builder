"""Workspace and git-output policies used by orchestrator flows."""

from __future__ import annotations

from pathlib import Path

WORKSPACE_COPY_EXCLUDES = (
    ".agent-builder",
    ".claude",
    ".codex",
    ".git",
    ".env",
    ".env.*",
    ".playwright-cli",
    ".coverage",
    ".DS_Store",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "htmlcov",
    "node_modules",
    "dist",
    "build",
    "test-results",
)


def directory_workspace_is_stale(workspace_path: str, repo_url: str) -> bool:
    if not workspace_path or not repo_url:
        return False
    workspace = Path(workspace_path)
    repo_root = Path(repo_url).expanduser()
    return (repo_root / "package.json").exists() and not (workspace / "package.json").exists()


def is_builder_source_repo(path: Path) -> bool:
    """Return true when post-ship optimization can safely edit builder internals."""

    return (path / "src" / "autonomous_agent_builder").is_dir() and (
        path / "frontend" / "src"
    ).is_dir()


def next_clean_directory_workspace_path(base_path: Path) -> Path:
    for index in range(1, 100):
        candidate = base_path.with_name(f"{base_path.name}-clean-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate clean task workspace path near {base_path}")


def workspace_copy_excluded(path: Path) -> bool:
    for pattern in WORKSPACE_COPY_EXCLUDES:
        if pattern.endswith(".*"):
            prefix = pattern[:-1]
            if any(part.startswith(prefix) for part in path.parts):
                return True
            continue
        if pattern in path.parts:
            return True
    return False


def is_fast_forward_divergence(output: str) -> bool:
    lower = output.lower()
    return "not possible to fast-forward" in lower or "diverging branches" in lower


def untracked_overwrite_paths(output: str) -> list[str]:
    """Extract untracked target paths that Git says would be overwritten."""

    if "untracked working tree files would be overwritten" not in output.lower():
        return []
    return _overwrite_paths(output)


def tracked_overwrite_paths(output: str) -> list[str]:
    """Extract tracked target paths that Git says would be overwritten."""

    if "your local changes to the following files would be overwritten by merge" not in output.lower():
        return []
    return _overwrite_paths(output)


def _overwrite_paths(output: str) -> list[str]:
    paths: list[str] = []
    collecting = False
    for line in output.splitlines():
        stripped = line.strip()
        if not collecting:
            collecting = stripped.endswith("would be overwritten by merge:")
            continue
        if not stripped or stripped.startswith("Please ") or stripped == "Aborting":
            break
        path = stripped.strip('"')
        if path and not Path(path).is_absolute() and ".." not in Path(path).parts:
            paths.append(path)
    return paths
