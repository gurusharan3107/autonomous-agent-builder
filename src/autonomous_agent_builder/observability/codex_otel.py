"""Project-local Codex OTEL configuration helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from autonomous_agent_builder.observability.collector import otel_collector_reachability


def codex_otel_config_path(project_root: Path) -> Path:
    """Return the project-local Codex config path; never points at global config."""
    return project_root.resolve() / ".codex" / "config.toml"


def render_codex_otel_config(*, endpoint: str, environment: str = "dev") -> str:
    """Render the minimal project-local Codex OTEL config."""
    return (
        "[otel]\n"
        f'environment = "{environment}"\n'
        "log_user_prompt = false\n"
        'exporter = { otlp-http = { endpoint = "'
        f"{_codex_logs_endpoint(endpoint)}"
        '", protocol = "binary" } }\n'
    )


def ensure_project_codex_otel_config(
    project_root: Path,
    *,
    endpoint: str,
    environment: str = "dev",
) -> dict[str, Any]:
    """Create a project-local Codex OTEL config if no project config exists."""
    path = codex_otel_config_path(project_root)
    if path.exists():
        return {**codex_otel_status(project_root), "status": "existing", "changed": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_codex_otel_config(endpoint=endpoint, environment=environment),
        encoding="utf-8",
    )
    return {**codex_otel_status(project_root), "status": "created", "changed": True}


def codex_otel_status(project_root: Path) -> dict[str, Any]:
    """Return safe health information for project-local Codex OTEL config."""
    path = codex_otel_config_path(project_root)
    if not path.exists():
        return _status(
            configured=False,
            enabled=False,
            exporter="missing",
            endpoint="",
            path=path,
            reason="project_codex_config_missing",
        )
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return _status(
            configured=True,
            enabled=False,
            exporter="invalid",
            endpoint="",
            path=path,
            reason=exc.__class__.__name__,
        )
    otel = parsed.get("otel") if isinstance(parsed, dict) else None
    if not isinstance(otel, dict):
        return _status(
            configured=True,
            enabled=False,
            exporter="missing",
            endpoint="",
            path=path,
            reason="otel_section_missing",
        )
    exporter = otel.get("exporter")
    if exporter in (None, "", "none"):
        return _status(
            configured=True,
            enabled=False,
            exporter=str(exporter or "none"),
            endpoint="",
            path=path,
            reason="otel_exporter_disabled",
        )
    exporter_name, endpoint = _exporter_endpoint(exporter)
    return _status(
        configured=True,
        enabled=bool(endpoint),
        exporter=exporter_name,
        endpoint=endpoint,
        path=path,
        reason="" if endpoint else "otel_exporter_endpoint_missing",
    )


def _status(
    *,
    configured: bool,
    enabled: bool,
    exporter: str,
    endpoint: str,
    path: Path,
    reason: str,
) -> dict[str, Any]:
    collector = otel_collector_reachability(endpoint)
    return {
        "configured": configured,
        "enabled": enabled,
        "exporter": exporter,
        "endpoint": endpoint,
        "collector": collector,
        "collector_status": collector.get("status"),
        "collector_reachable": collector.get("reachable"),
        "emitted_signals": {
            "logs": enabled,
            "metrics": enabled,
            "traces": False,
            "native_event_names": enabled,
        },
        "config_path": str(path),
        "project_local": True,
        "reason": reason,
    }


def _exporter_endpoint(exporter: Any) -> tuple[str, str]:
    if isinstance(exporter, str):
        return exporter, ""
    if not isinstance(exporter, dict):
        return "invalid", ""
    for key in ("otlp-http", "otlp-grpc"):
        value = exporter.get(key)
        if isinstance(value, dict):
            return key, str(value.get("endpoint") or "")
    return "unsupported", ""


def _codex_logs_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    if not value:
        return "http://localhost:4318/v1/logs"
    parsed = urlparse(value)
    if parsed.path and parsed.path != "/":
        return value
    return value.rstrip("/") + "/v1/logs"
