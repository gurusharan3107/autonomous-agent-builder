"""Phase context persistence helpers for orchestrator transitions."""

from __future__ import annotations

from typing import Any


def phase_context(task: Any, key: str) -> str:
    """Return a compact stored phase context value."""
    if not isinstance(task.depends_on, dict):
        return ""
    stored_context = task.depends_on.get("phase_context")
    if not isinstance(stored_context, dict):
        return ""
    value = stored_context.get(key)
    return str(value or "").strip()


def store_phase_context(task: Any, key: str, value: str) -> None:
    """Persist non-empty phase context without disturbing other dependency data."""
    if not value:
        return
    depends_on = dict(task.depends_on or {})
    stored_context = dict(depends_on.get("phase_context") or {})
    stored_context[key] = value
    depends_on["phase_context"] = stored_context
    task.depends_on = depends_on


def compact_phase_output(output_text: str, max_chars: int = 2000) -> str:
    """Normalize agent phase output for cross-phase prompt context."""
    compact = " ".join(str(output_text or "").split()).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
