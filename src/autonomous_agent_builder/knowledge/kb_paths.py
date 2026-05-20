"""Helpers for repo-local knowledge-base path resolution."""

from __future__ import annotations

from pathlib import Path


def resolve_repo_local_kb_path(
    kb_dir: str | None,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, Path, Path]:
    resolved_project_root = (
        Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    )
    kb_root = (resolved_project_root / ".agent-builder" / "knowledge").resolve()
    normalized_kb_dir = str(kb_dir or "system-docs").strip() or "system-docs"
    kb_path = (kb_root / Path(normalized_kb_dir)).resolve()
    return normalized_kb_dir, kb_root, kb_path
