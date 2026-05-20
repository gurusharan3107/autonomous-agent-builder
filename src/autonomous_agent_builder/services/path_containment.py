"""Resolved filesystem containment checks for Builder trust boundaries."""

from __future__ import annotations

from pathlib import Path


def resolve_contained_path(root: Path | str, child: Path | str) -> Path | None:
    """Resolve child under root, returning None when it escapes the root."""
    resolved_root = Path(root).resolve()
    resolved_child = (resolved_root / child).resolve()
    if not resolved_child.is_relative_to(resolved_root):
        return None
    return resolved_child
