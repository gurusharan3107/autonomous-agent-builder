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
    """Render high-signal project-local Codex OTEL config."""
    return (
        _render_codex_otel_section(endpoint=endpoint, environment=environment) + "\n"
        "[feedback]\n"
        "enabled = true\n\n"
        "[analytics]\n"
        "enabled = true\n"
    )


def _render_codex_otel_section(*, endpoint: str, environment: str = "dev") -> str:
    return (
        "[otel]\n"
        f'environment = "{environment}"\n'
        "log_user_prompt = false\n"
        'exporter = { otlp-http = { endpoint = "'
        f"{_codex_logs_endpoint(endpoint)}"
        '", protocol = "binary" } }\n'
        'metrics_exporter = { otlp-http = { endpoint = "'
        f"{_codex_metrics_endpoint(endpoint)}"
        '", protocol = "binary" } }\n'
        'trace_exporter = { otlp-http = { endpoint = "'
        f"{_codex_traces_endpoint(endpoint)}"
        '", protocol = "binary" } }\n'
        'span_attributes = { "builder.product" = "autonomous-agent-builder", '
        '"builder.runtime" = "codex_sdk", '
        '"builder.goal" = "voice_first_delivery_os" }\n'
        'tracestate = { builder = { product = "autonomous-agent-builder", '
        'runtime = "codex_sdk", goal = "voice_first_delivery_os" } }\n'
    )


def ensure_project_codex_otel_config(
    project_root: Path,
    *,
    endpoint: str,
    environment: str = "dev",
) -> dict[str, Any]:
    """Create or extend project-local Codex OTEL config without touching globals."""
    path = codex_otel_config_path(project_root)
    if path.exists():
        status = codex_otel_status(project_root)
        if status.get("reason") == "otel_section_missing":
            _append_codex_otel_config(path, endpoint=endpoint, environment=environment)
            return {**codex_otel_status(project_root), "status": "updated", "changed": True}
        if _codex_otel_needs_signal_refresh(status):
            _upsert_codex_otel_signal_keys(path, endpoint=endpoint, environment=environment)
            return {**codex_otel_status(project_root), "status": "updated", "changed": True}
        return {**codex_otel_status(project_root), "status": "existing", "changed": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_codex_otel_config(endpoint=endpoint, environment=environment),
        encoding="utf-8",
    )
    return {**codex_otel_status(project_root), "status": "created", "changed": True}


def _append_codex_otel_config(path: Path, *, endpoint: str, environment: str) -> None:
    existing = path.read_text(encoding="utf-8").rstrip()
    rendered = _render_codex_otel_section(endpoint=endpoint, environment=environment).rstrip()
    path.write_text(f"{existing}\n\n{rendered}\n", encoding="utf-8")
    _upsert_boolean_section(path, section="feedback", key="enabled", value=True)
    _upsert_boolean_section(path, section="analytics", key="enabled", value=True)


def _codex_otel_needs_signal_refresh(status: dict[str, Any]) -> bool:
    signals = status.get("emitted_signals")
    if status.get("reason") == "otel_exporter_missing":
        return True
    return (
        bool(status.get("enabled"))
        and isinstance(signals, dict)
        and (
            not signals.get("logs")
            or not signals.get("metrics")
            or not signals.get("traces")
            or not status.get("span_attributes_configured")
            or not status.get("tracestate_configured")
            or not status.get("feedback_configured")
            or not status.get("analytics_configured")
        )
    )


def _upsert_codex_otel_signal_keys(path: Path, *, endpoint: str, environment: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "[otel]"), -1)
    if start < 0:
        _append_codex_otel_config(path, endpoint=endpoint, environment=environment)
        return

    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break

    desired = _codex_otel_desired_key_lines(endpoint=endpoint, environment=environment)
    existing_indexes: dict[str, int] = {}
    for index in range(start + 1, end):
        key = lines[index].split("=", 1)[0].strip()
        if key:
            existing_indexes[key] = index

    insert_at = end
    for key, line in desired.items():
        if key in existing_indexes:
            lines[existing_indexes[key]] = line
        else:
            lines.insert(insert_at, line)
            insert_at += 1

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _upsert_boolean_section(path, section="feedback", key="enabled", value=True)
    _upsert_boolean_section(path, section="analytics", key="enabled", value=True)


def _codex_otel_desired_key_lines(*, endpoint: str, environment: str) -> dict[str, str]:
    return {
        "environment": f'environment = "{environment}"',
        "log_user_prompt": "log_user_prompt = false",
        "exporter": (
            'exporter = { otlp-http = { endpoint = "'
            f"{_codex_logs_endpoint(endpoint)}"
            '", protocol = "binary" } }'
        ),
        "metrics_exporter": (
            'metrics_exporter = { otlp-http = { endpoint = "'
            f"{_codex_metrics_endpoint(endpoint)}"
            '", protocol = "binary" } }'
        ),
        "trace_exporter": (
            'trace_exporter = { otlp-http = { endpoint = "'
            f"{_codex_traces_endpoint(endpoint)}"
            '", protocol = "binary" } }'
        ),
        "span_attributes": (
            'span_attributes = { "builder.product" = "autonomous-agent-builder", '
            '"builder.runtime" = "codex_sdk", '
            '"builder.goal" = "voice_first_delivery_os" }'
        ),
        "tracestate": (
            'tracestate = { builder = { product = "autonomous-agent-builder", '
            'runtime = "codex_sdk", goal = "voice_first_delivery_os" } }'
        ),
    }


def _upsert_boolean_section(path: Path, *, section: str, key: str, value: bool) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = f"[{section}]"
    desired_line = f"{key} = {'true' if value else 'false'}"
    start = next((index for index, line in enumerate(lines) if line.strip() == header), -1)
    if start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([header, desired_line])
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return

    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break

    for index in range(start + 1, end):
        existing_key = lines[index].split("=", 1)[0].strip()
        if existing_key == key:
            lines[index] = desired_line
            path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            return

    lines.insert(end, desired_line)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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
            configured=False,
            enabled=False,
            exporter="missing",
            endpoint="",
            path=path,
            parsed_config=parsed,
            reason="otel_section_missing",
        )
    exporter = otel.get("exporter")
    if exporter is None:
        return _status(
            configured=True,
            enabled=False,
            exporter="missing",
            endpoint="",
            path=path,
            parsed_config=parsed,
            parsed_otel=otel,
            reason="otel_exporter_missing",
        )
    if exporter in ("", "none"):
        return _status(
            configured=True,
            enabled=False,
            exporter=str(exporter or "none"),
            endpoint="",
            path=path,
            parsed_config=parsed,
            parsed_otel=otel,
            reason="otel_exporter_disabled",
        )
    exporter_name, endpoint = _exporter_endpoint(exporter)
    return _status(
        configured=True,
        enabled=bool(endpoint),
        exporter=exporter_name,
        endpoint=endpoint,
        path=path,
        parsed_config=parsed,
        parsed_otel=otel,
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
    parsed_config: dict[str, Any] | None = None,
    parsed_otel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collector = otel_collector_reachability(endpoint)
    parsed_config = parsed_config or {}
    parsed_otel = parsed_otel or {}
    feedback = parsed_config.get("feedback") if isinstance(parsed_config, dict) else None
    analytics = parsed_config.get("analytics") if isinstance(parsed_config, dict) else None
    config_loaded = bool(parsed_config)
    feedback_configured = bool(isinstance(feedback, dict) and feedback.get("enabled") is True)
    analytics_configured = bool(isinstance(analytics, dict) and analytics.get("enabled") is True)
    feedback_enabled = config_loaded and not (
        isinstance(feedback, dict) and feedback.get("enabled") is False
    )
    analytics_enabled = config_loaded and not (
        isinstance(analytics, dict) and analytics.get("enabled") is False
    )
    span_attributes_configured = bool(parsed_otel.get("span_attributes"))
    tracestate_configured = bool(parsed_otel.get("tracestate"))
    trace_metadata_configured = span_attributes_configured and tracestate_configured
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
            "metrics": enabled and bool(parsed_otel.get("metrics_exporter")),
            "traces": enabled and bool(parsed_otel.get("trace_exporter")),
            "trace_metadata": enabled and trace_metadata_configured,
            "review_feedback": feedback_enabled,
            "analytics": analytics_enabled,
            "native_event_names": enabled,
        },
        "span_attributes_configured": span_attributes_configured,
        "tracestate_configured": tracestate_configured,
        "trace_metadata_configured": trace_metadata_configured,
        "feedback_configured": feedback_configured,
        "feedback_enabled": feedback_enabled,
        "analytics_configured": analytics_configured,
        "analytics_enabled": analytics_enabled,
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


def _codex_metrics_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    if not value:
        return "http://localhost:4318/v1/metrics"
    parsed = urlparse(value)
    if parsed.path and parsed.path != "/":
        return value
    return value.rstrip("/") + "/v1/metrics"


def _codex_traces_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    if not value:
        return "http://localhost:4318/v1/traces"
    parsed = urlparse(value)
    if parsed.path and parsed.path != "/":
        return value
    return value.rstrip("/") + "/v1/traces"
