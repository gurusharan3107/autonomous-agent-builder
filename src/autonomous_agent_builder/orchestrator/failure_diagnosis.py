"""Runtime failure diagnosis for orchestrator agent runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CODEX_CHUNK_LIMIT_FRAGMENT = "separator is not found"
_CODEX_CHUNK_LIMIT_DETAIL = "chunk exceed"
_RUNTIME_IDLE_TIMEOUT_FRAGMENT = "claude runtime idle timeout"
_BUILDER_INTERNAL_PATHS = (
    ".agent-builder",
    ".agent-builder/dashboard",
    ".agent-builder/server",
    ".agent-builder/agent_builder.db",
    ".claude/progress",
    ".codex",
    ".playwright-cli",
)


def diagnose_task_failure(
    error: str,
    *,
    workspace_path: str = "",
    result: Any | None = None,
) -> str:
    issue = "agent_runtime_failure"
    detail = error
    if is_runtime_idle_timeout(error):
        issue = "runtime_idle_timeout"
        detail = "Claude SDK stream produced no event for the inactivity window; task may be retried."
    elif is_codex_chunk_limit_error(error):
        issue = "codex_transport_chunk_limit"
        detail = "Codex app-server failed while streaming/parsing a large tool or agent output."
        if workspace_contains_builder_internals(workspace_path):
            issue = "workspace_pollution_codex_chunk_limit"
            detail = (
                "Task workspace contains builder internals such as .agent-builder, "
                "dashboard bundles, copied server routes, or builder DB files; Codex "
                "hit a transport chunk limit while operating in that polluted workspace."
            )
    evidence = _observability_evidence(result)
    if workspace_path:
        evidence.append(f"workspace={workspace_path}")
    suffix = f" ({'; '.join(evidence)})" if evidence else ""
    return f"{issue}: {detail}{suffix}"


def is_runtime_idle_timeout(error: str) -> bool:
    return _RUNTIME_IDLE_TIMEOUT_FRAGMENT in error.lower()


def is_codex_chunk_limit_error(error: str) -> bool:
    lower = error.lower()
    return _CODEX_CHUNK_LIMIT_FRAGMENT in lower and _CODEX_CHUNK_LIMIT_DETAIL in lower


def workspace_contains_builder_internals(workspace_path: str) -> bool:
    if not workspace_path:
        return False
    workspace = Path(workspace_path)
    return any((workspace / path).exists() for path in _BUILDER_INTERNAL_PATHS)


def _observability_evidence(result: Any | None) -> list[str]:
    evidence: list[str] = []
    observability = result.observability if result else None
    if not isinstance(observability, dict):
        return evidence
    runtime_sdk = str(observability.get("runtime_sdk") or "").strip()
    raw_event_count = observability.get("raw_event_count")
    duration_ms = observability.get("duration_ms")
    if runtime_sdk:
        evidence.append(f"runtime={runtime_sdk}")
    if raw_event_count is not None:
        evidence.append(f"events={raw_event_count}")
    if duration_ms is not None:
        evidence.append(f"duration_ms={duration_ms}")
    return evidence
