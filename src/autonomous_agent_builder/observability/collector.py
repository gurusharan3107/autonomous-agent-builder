"""OTEL collector endpoint classification for repo-owned telemetry status."""

from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlparse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_LOCAL_PREFIXES = ("127.",)
_DEFAULT_PORT_BY_SCHEME = {"http": 80, "https": 443}


def otel_collector_reachability(endpoint: str | None, *, timeout: float = 0.2) -> dict[str, Any]:
    """Return configured-vs-reachable state for a local OTEL collector endpoint."""
    raw_endpoint = (endpoint or "").strip()
    if not raw_endpoint:
        return {
            "configured": False,
            "local": False,
            "checked": False,
            "reachable": False,
            "status": "missing",
            "endpoint": "",
            "error": "",
        }

    parseable_endpoint = raw_endpoint if "://" in raw_endpoint else f"http://{raw_endpoint}"
    parsed = urlparse(parseable_endpoint)
    hostname = parsed.hostname or ""
    port = parsed.port or _DEFAULT_PORT_BY_SCHEME.get(parsed.scheme)
    local = _is_local_hostname(hostname)
    if not local:
        return {
            "configured": True,
            "local": False,
            "checked": False,
            "reachable": None,
            "status": "configured_not_checked",
            "endpoint": raw_endpoint,
            "error": "",
        }
    if not port:
        return {
            "configured": True,
            "local": True,
            "checked": True,
            "reachable": False,
            "status": "invalid_endpoint",
            "endpoint": raw_endpoint,
            "error": "missing_port",
        }
    try:
        with socket.create_connection((hostname, int(port)), timeout=timeout):
            pass
    except OSError as exc:
        return {
            "configured": True,
            "local": True,
            "checked": True,
            "reachable": False,
            "status": "configured_unreachable",
            "endpoint": raw_endpoint,
            "error": exc.__class__.__name__,
        }
    return {
        "configured": True,
        "local": True,
        "checked": True,
        "reachable": True,
        "status": "reachable",
        "endpoint": raw_endpoint,
        "error": "",
    }


def _is_local_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    return normalized in _LOCAL_HOSTS or normalized.startswith(_LOCAL_PREFIXES)
