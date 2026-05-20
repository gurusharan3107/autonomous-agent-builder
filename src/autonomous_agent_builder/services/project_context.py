"""Request-scoped project context helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def request_project_root(request: Any) -> Path:
    """Return the app-scoped project root, falling back only at this boundary."""
    return Path(getattr(request.app.state, "project_root", Path.cwd())).resolve()
