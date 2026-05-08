"""In-process OTLP/HTTP receiver bundled with ``builder start``.

Replaces the chicken-and-egg situation where Day-0 readiness requires a
reachable OTel collector but a fresh ``builder init`` ships nothing on
``127.0.0.1:4318``. Now ``builder start`` itself listens on the configured
local OTLP endpoint so the readiness contract is satisfied out of the box,
and incoming OTLP exports are appended to ``.agent-builder/telemetry/``
JSONL files for ``builder logs analyze`` to consume later.

Design choices:

* **In-process, threaded ``http.server``** — no extra runtime dependency,
  no separate uvicorn binding, no docker. Builds atop stdlib only.
* **No protobuf decoding** — OTLP requests come in two content-types
  (``application/json`` and ``application/x-protobuf``). We store the raw
  body base64-encoded with the content-type so downstream tooling can
  decode it on demand. The collector contract is "received & persisted",
  not "fully parsed" — that's what real OTel Collector pipelines do.
* **Port-conflict policy** — when something is already bound to the local
  endpoint we log and skip. This lets operators run a real OTel collector
  alongside builder without breakage.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

log = structlog.get_logger(__name__)

_OTLP_SIGNAL_PATHS = {
    "/v1/traces": "traces",
    "/v1/metrics": "metrics",
    "/v1/logs": "logs",
}


class _LocalOTLPHandler(BaseHTTPRequestHandler):
    """Persist OTLP/HTTP exports to a local JSONL evidence store."""

    telemetry_root: Path = Path()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Silence stdlib's default per-request stderr logs; we use structlog.
        return

    def do_POST(self) -> None:  # noqa: N802
        signal = _OTLP_SIGNAL_PATHS.get(self.path.split("?", 1)[0])
        if signal is None:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        content_type = self.headers.get("Content-Type", "").strip()

        try:
            self._persist(signal, body, content_type)
        except OSError as exc:  # pragma: no cover - defensive
            log.warning(
                "local_otlp_persist_failed",
                signal=signal,
                error=str(exc),
            )

        # OTel Collector returns 200 + empty `ExportPartialSuccess` body. We
        # mirror that contract loosely — empty body is acceptable.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def _persist(self, signal: str, body: bytes, content_type: str) -> None:
        if not body:
            return
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self.telemetry_root / f"{signal}-{date}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "ts": datetime.now(UTC).isoformat(),
            "signal": signal,
            "content_type": content_type,
            "length": len(body),
            "body_b64": base64.b64encode(body).decode("ascii"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope) + "\n")


class LocalOTLPCollector:
    """Thin wrapper that owns the receiver thread lifecycle."""

    def __init__(self, telemetry_root: Path, host: str, port: int) -> None:
        self.telemetry_root = telemetry_root
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> dict[str, Any]:
        if _port_in_use(self.host, self.port):
            log.info(
                "local_otlp_collector_skipped_port_in_use",
                host=self.host,
                port=self.port,
            )
            return {"started": False, "reason": "port_in_use"}

        # Bind a fresh handler subclass so each collector instance writes to
        # its own telemetry root. ``BaseHTTPRequestHandler`` is class-level,
        # which is why we generate a per-instance subclass here.
        telemetry_root = self.telemetry_root
        handler_cls = type(
            "_BoundLocalOTLPHandler",
            (_LocalOTLPHandler,),
            {"telemetry_root": telemetry_root},
        )
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler_cls)
        except OSError as exc:
            log.warning(
                "local_otlp_collector_bind_failed",
                host=self.host,
                port=self.port,
                error=str(exc),
            )
            return {"started": False, "reason": "bind_failed", "error": str(exc)}

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="local-otlp-collector",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "local_otlp_collector_started",
            host=self.host,
            port=self.port,
            telemetry_root=str(self.telemetry_root),
        )
        return {"started": True, "host": self.host, "port": self.port}

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None


def _port_in_use(host: str, port: int, timeout: float = 0.2) -> bool:
    """Return True when ``host:port`` already has a TCP listener."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_local_endpoint(endpoint: str) -> tuple[str, int] | None:
    """Return ``(host, port)`` for a local OTLP HTTP endpoint or ``None``."""
    raw = (endpoint or "").strip()
    if not raw:
        return None
    parseable = raw if "://" in raw else f"http://{raw}"
    parsed = urlparse(parseable)
    host = (parsed.hostname or "").strip().lower()
    port = parsed.port
    if not host or port is None:
        return None
    if host not in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return None
    return host, int(port)
