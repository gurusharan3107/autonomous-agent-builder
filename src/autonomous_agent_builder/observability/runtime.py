"""Repo-owned Claude runtime observability wiring and summaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.collector import otel_collector_reachability

_BASE_ENV_KEYS = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_LOGS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_METRIC_EXPORT_INTERVAL",
    "OTEL_LOGS_EXPORT_INTERVAL",
    "OTEL_TRACES_EXPORT_INTERVAL",
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_METRICS_INCLUDE_SESSION_ID",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
    "OTEL_LOG_RAW_API_BODIES",
    "ENABLE_BETA_TRACING_DETAILED",
    "BETA_TRACING_ENDPOINT",
)

_CONTENT_FLAGS = (
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
    "OTEL_LOG_RAW_API_BODIES",
)

_PLACEHOLDER_ENDPOINT_MARKERS = ("your-collector", "replace-me", "changeme")


@dataclass(frozen=True)
class ClaudeObservabilityConfig:
    """Resolved Claude child-process OTEL environment and safe summary."""

    env: dict[str, str]
    summary: dict[str, Any]


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_falsey(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"", "0", "false", "no", "off"}


def _is_placeholder_endpoint(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return bool(normalized) and any(
        marker in normalized for marker in _PLACEHOLDER_ENDPOINT_MARKERS
    )


def _repo_owned_env() -> dict[str, str]:
    settings = get_settings()
    enabled = _env_truthy(os.environ.get("AAB_CLAUDE_OTEL_ENABLED"))
    endpoint = (os.environ.get("AAB_CLAUDE_OTEL_ENDPOINT") or "").strip()
    if not enabled or not endpoint:
        return {}

    env = {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": os.environ.get("AAB_CLAUDE_OTEL_TRACES_EXPORTER", "otlp"),
        "OTEL_METRICS_EXPORTER": os.environ.get("AAB_CLAUDE_OTEL_METRICS_EXPORTER", "otlp"),
        "OTEL_LOGS_EXPORTER": os.environ.get("AAB_CLAUDE_OTEL_LOGS_EXPORTER", "otlp"),
        "OTEL_EXPORTER_OTLP_PROTOCOL": os.environ.get("AAB_CLAUDE_OTEL_PROTOCOL", "http/protobuf"),
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_METRIC_EXPORT_INTERVAL": os.environ.get(
            "AAB_CLAUDE_OTEL_METRIC_EXPORT_INTERVAL", "2000"
        ),
        "OTEL_LOGS_EXPORT_INTERVAL": os.environ.get("AAB_CLAUDE_OTEL_LOGS_EXPORT_INTERVAL", "1000"),
        "OTEL_TRACES_EXPORT_INTERVAL": os.environ.get(
            "AAB_CLAUDE_OTEL_TRACES_EXPORT_INTERVAL", "1000"
        ),
        "OTEL_SERVICE_NAME": os.environ.get(
            "AAB_CLAUDE_OTEL_SERVICE_NAME", "autonomous-agent-builder"
        ),
    }

    headers = (os.environ.get("AAB_CLAUDE_OTEL_HEADERS") or "").strip()
    if headers:
        env["OTEL_EXPORTER_OTLP_HEADERS"] = headers
    resource_attributes = (os.environ.get("AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES") or "").strip()
    if resource_attributes:
        env["OTEL_RESOURCE_ATTRIBUTES"] = resource_attributes
    include_session_id = os.environ.get("AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID")
    if include_session_id is not None:
        env["OTEL_METRICS_INCLUDE_SESSION_ID"] = include_session_id
    if _env_truthy(os.environ.get("AAB_CLAUDE_OTEL_LOG_USER_PROMPTS")):
        env["OTEL_LOG_USER_PROMPTS"] = "1"
    if _env_truthy(os.environ.get("AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS")):
        env["OTEL_LOG_TOOL_DETAILS"] = "1"
    if _env_truthy(os.environ.get("AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT")):
        env["OTEL_LOG_TOOL_CONTENT"] = "1"
    raw_api_bodies = (os.environ.get("AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES") or "").strip()
    if raw_api_bodies and not _env_falsey(raw_api_bodies):
        env["OTEL_LOG_RAW_API_BODIES"] = raw_api_bodies
    if _env_truthy(os.environ.get("AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING")):
        env["ENABLE_BETA_TRACING_DETAILED"] = "1"
        beta_endpoint = (os.environ.get("AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT") or "").strip()
        if beta_endpoint:
            env["BETA_TRACING_ENDPOINT"] = beta_endpoint

    _ = settings.app_name
    return env


def resolve_claude_observability(
    extra_env: dict[str, str] | None = None,
) -> ClaudeObservabilityConfig:
    """Return effective OTEL env for a Claude child process plus a safe summary."""

    effective: dict[str, str] = {}
    for key in _BASE_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            effective[key] = value

    for key, value in _repo_owned_env().items():
        effective.setdefault(key, value)

    for key, value in (extra_env or {}).items():
        if key in _BASE_ENV_KEYS:
            effective[key] = value

    enabled = effective.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1"
    traces_enabled = bool(effective.get("OTEL_TRACES_EXPORTER"))
    metrics_enabled = bool(effective.get("OTEL_METRICS_EXPORTER"))
    logs_enabled = bool(effective.get("OTEL_LOGS_EXPORTER"))
    detailed_tracing = _env_truthy(effective.get("ENABLE_BETA_TRACING_DETAILED")) and bool(
        effective.get("BETA_TRACING_ENDPOINT")
    )
    sensitive_flags = [
        key
        for key in _CONTENT_FLAGS
        if (
            not _env_falsey(effective.get(key))
            if key == "OTEL_LOG_RAW_API_BODIES"
            else _env_truthy(effective.get(key))
        )
    ]
    otlp_endpoint = effective.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    endpoint_placeholder = _is_placeholder_endpoint(otlp_endpoint)
    collector = otel_collector_reachability(otlp_endpoint)

    return ClaudeObservabilityConfig(
        env=effective,
        summary={
            "source": "runtime_env",
            "enabled": enabled,
            "metrics_exporter": effective.get("OTEL_METRICS_EXPORTER", ""),
            "logs_exporter": effective.get("OTEL_LOGS_EXPORTER", ""),
            "traces_exporter": effective.get("OTEL_TRACES_EXPORTER", ""),
            "enhanced_tracing": effective.get("CLAUDE_CODE_ENHANCED_TELEMETRY_BETA") == "1",
            "detailed_beta_tracing": detailed_tracing,
            "service_name": effective.get("OTEL_SERVICE_NAME", ""),
            "resource_attributes": effective.get("OTEL_RESOURCE_ATTRIBUTES", ""),
            "headers_configured": bool(effective.get("OTEL_EXPORTER_OTLP_HEADERS")),
            "endpoint_configured": bool(otlp_endpoint) and not endpoint_placeholder,
            "endpoint_placeholder": endpoint_placeholder,
            "collector": collector,
            "collector_reachable": collector.get("reachable"),
            "export_intervals_ms": {
                "metrics": effective.get("OTEL_METRIC_EXPORT_INTERVAL", ""),
                "logs": effective.get("OTEL_LOGS_EXPORT_INTERVAL", ""),
                "traces": effective.get("OTEL_TRACES_EXPORT_INTERVAL", ""),
            },
            "sensitive_data_flags": sensitive_flags,
            "signal_state": {
                "metrics": metrics_enabled,
                "logs": logs_enabled,
                "traces": traces_enabled,
            },
        },
    )
