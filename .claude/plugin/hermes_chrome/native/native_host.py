#!/usr/bin/env python3
"""Native messaging host for the Hermes Chrome Bridge extension.

Runs inside WSL2 (Chrome's native manifest launches it via a Windows `.bat`
that shells in with `wsl python3 <this file>`). Chrome talks to it over stdin/
stdout native messaging; the bridge client (also WSL2) talks to it over an
AF_UNIX socket at HERMES_CHROME_BRIDGE_SOCKET. The Unix socket only works
because both ends live in WSL2 — see scripts/install_hermes_chrome_bridge.py.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import queue
import socket
import struct
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

# Bind on all interfaces so WSL2 can reach this process running on Windows.
SOCKET_PATH = Path(os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
    str(Path.home() / ".hermes" / "run" / "chrome-bridge.sock")))

pending: dict[str, queue.Queue[dict[str, Any]]] = {}
pending_lock = threading.Lock()
out_lock = threading.Lock()


def _screenshot_dir() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "cache" / "hermes-chrome"


# ── Native messaging (Chrome ↔ this process via stdin/stdout) ────────────────

def read_native_message() -> dict[str, Any] | None:
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    length = struct.unpack("<I", raw_len)[0]
    data = sys.stdin.buffer.read(length)
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def write_native_message(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    with out_lock:
        sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


# ── Unix socket server (this process ↔ WSL2 tools.py) ───────────────────────

def socket_server() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        SOCKET_PATH.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(10)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


def handle_client(conn: socket.socket) -> None:
    with conn:
        chunks: list[bytes] = []
        request: dict[str, Any] = {}
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            try:
                request = json.loads(b"".join(chunks).decode("utf-8"))
                break
            except json.JSONDecodeError:
                continue

        request_id = str(uuid.uuid4())
        response_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with pending_lock:
            pending[request_id] = response_q
        write_native_message({"id": request_id, **request})
        try:
            response = response_q.get(timeout=float(request.get("timeoutSeconds", 45)))
            response = _materialize_response(response)
        except queue.Empty:
            response = {"id": request_id, "success": False, "error": "Hermes Chrome extension timed out"}
        finally:
            with pending_lock:
                pending.pop(request_id, None)
        conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))


def _materialize_response(response: dict[str, Any]) -> dict[str, Any]:
    results = response.get("results")
    if not isinstance(results, list):
        return response
    screenshot_dir = _screenshot_dir()
    for index, item in enumerate(results):
        if not isinstance(item, dict) or item.get("type") != "screenshot":
            continue
        data = item.pop("base64", None)
        if not isinstance(data, str):
            continue
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        ext = item.get("format", "png")
        path = screenshot_dir / f"{response.get('id') or 'capture'}-{index}.{ext}"
        path.write_bytes(base64.b64decode(data))
        item["screenshot_path"] = str(path)

    return response


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    threading.Thread(target=socket_server, daemon=True).start()
    while True:
        message = read_native_message()
        if message is None:
            return 0
        request_id = str(message.get("id") or "")
        with pending_lock:
            response_q = pending.get(request_id)
        if response_q is not None:
            response_q.put(message)


if __name__ == "__main__":
    raise SystemExit(main())
