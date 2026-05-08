"""Tests for the in-process OTLP collector bundled with builder start."""

from __future__ import annotations

import base64
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest

from autonomous_agent_builder.observability.local_collector import (
    LocalOTLPCollector,
    parse_local_endpoint,
)


def _free_port() -> int:
    """Pick a free TCP port for the duration of the test."""
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("http://localhost:4318", ("localhost", 4318)),
        ("https://127.0.0.1:4318", ("127.0.0.1", 4318)),
        ("localhost:4318", ("localhost", 4318)),
        ("0.0.0.0:4318", ("0.0.0.0", 4318)),
        ("http://otel.example.com:4318", None),  # remote — refuse
        ("", None),
        ("not-a-url", None),
    ],
)
def test_parse_local_endpoint(endpoint, expected):
    assert parse_local_endpoint(endpoint) == expected


def _wait_for_listener(host: str, port: int, timeout: float = 2.0) -> bool:
    """Poll until the collector's TCP listener is accepting connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def test_local_collector_persists_traces_to_jsonl(tmp_path):
    port = _free_port()
    telemetry_root = tmp_path / "telemetry"
    collector = LocalOTLPCollector(telemetry_root, "127.0.0.1", port)
    started = collector.start()
    try:
        assert started.get("started") is True
        assert _wait_for_listener("127.0.0.1", port), "collector failed to bind"

        body = b'{"resourceSpans":[]}'
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/traces",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            assert resp.read() == b"{}"
    finally:
        collector.stop()

    files = sorted(telemetry_root.glob("traces-*.jsonl"))
    assert files, "no JSONL evidence file was created"
    line = files[0].read_text(encoding="utf-8").strip()
    envelope = json.loads(line)
    assert envelope["signal"] == "traces"
    assert envelope["content_type"] == "application/json"
    assert base64.b64decode(envelope["body_b64"]) == body


def test_local_collector_returns_404_for_unknown_path(tmp_path):
    port = _free_port()
    collector = LocalOTLPCollector(tmp_path / "tel", "127.0.0.1", port)
    collector.start()
    try:
        assert _wait_for_listener("127.0.0.1", port)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/unknown",
            data=b"x",
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req, timeout=2.0)
        assert excinfo.value.code == 404
    finally:
        collector.stop()


def test_local_collector_skips_when_port_already_in_use(tmp_path):
    port = _free_port()

    server_sock = socket.socket()
    server_sock.bind(("127.0.0.1", port))
    server_sock.listen(1)
    accept_thread = threading.Thread(
        target=lambda: server_sock.accept(), daemon=True
    )
    accept_thread.start()

    try:
        collector = LocalOTLPCollector(tmp_path / "tel", "127.0.0.1", port)
        result = collector.start()
        assert result == {"started": False, "reason": "port_in_use"}
    finally:
        server_sock.close()


def test_local_collector_traces_metrics_logs_paths(tmp_path):
    port = _free_port()
    collector = LocalOTLPCollector(tmp_path / "tel", "127.0.0.1", port)
    collector.start()
    try:
        assert _wait_for_listener("127.0.0.1", port)
        for signal in ("traces", "metrics", "logs"):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/{signal}",
                data=f'{{"signal":"{signal}"}}'.encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                assert resp.status == 200
    finally:
        collector.stop()

    for signal in ("traces", "metrics", "logs"):
        files = sorted((tmp_path / "tel").glob(f"{signal}-*.jsonl"))
        assert files, f"missing JSONL for {signal}"


def test_local_collector_stop_is_idempotent(tmp_path):
    port = _free_port()
    collector = LocalOTLPCollector(tmp_path / "tel", "127.0.0.1", port)
    collector.start()
    collector.stop()
    collector.stop()  # double-stop must not raise
