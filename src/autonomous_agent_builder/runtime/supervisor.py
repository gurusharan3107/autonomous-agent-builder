"""Runtime ownership and process hygiene helpers for local builder processes."""

from __future__ import annotations

import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OWNER = "autonomous-agent-builder"
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class PortProcess:
    pid: int
    command: str = ""


class RuntimeSupervisorError(Exception):
    """Runtime supervisor failure with an agent-facing code."""

    def __init__(self, message: str, *, code: str = "runtime_error", exit_code: int = 1):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def runtime_dir(agent_builder_dir: Path) -> Path:
    return agent_builder_dir / "runtime"


def servers_dir(agent_builder_dir: Path) -> Path:
    return runtime_dir(agent_builder_dir) / "servers"


def server_metadata_path(agent_builder_dir: Path, port: int) -> Path:
    return servers_dir(agent_builder_dir) / f"{port}.json"


def builder_version() -> str:
    try:
        return importlib.metadata.version("autonomous-agent-builder")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+local"


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_command(pid: int) -> str:
    if pid <= 0 or sys.platform == "win32":
        return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    return result.stdout.strip()


def listening_processes(port: int) -> list[PortProcess]:
    if sys.platform == "win32":
        return _windows_listening_processes(port)
    try:
        result = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    processes = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        processes.append(PortProcess(pid=pid, command=process_command(pid)))
    return processes


def _windows_listening_processes(port: int) -> list[PortProcess]:
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.append(int(parts[-1]))
    return [PortProcess(pid=pid, command="") for pid in dict.fromkeys(pids)]


def read_server_metadata(agent_builder_dir: Path, port: int) -> dict[str, Any] | None:
    path = server_metadata_path(agent_builder_dir, port)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_server_metadata(
    agent_builder_dir: Path,
    *,
    host: str,
    port: int,
    command: list[str] | None = None,
) -> dict[str, Any]:
    path = server_metadata_path(agent_builder_dir, port)
    path.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "owner": OWNER,
        "kind": "server",
        "pid": pid,
        "process_group_id": os.getpgrp() if hasattr(os, "getpgrp") else pid,
        "host": host,
        "port": port,
        "cwd": str(agent_builder_dir.parent.resolve()),
        "command": command or [sys.executable, *sys.argv],
        "started_at": utc_now(),
        "last_seen_at": utc_now(),
        "builder_version": builder_version(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def clear_server_metadata(agent_builder_dir: Path, port: int) -> None:
    try:
        server_metadata_path(agent_builder_dir, port).unlink()
    except FileNotFoundError:
        return


def server_status(agent_builder_dir: Path, port: int | None = None) -> dict[str, Any]:
    ports = [port] if port is not None else _known_ports(agent_builder_dir)
    servers = [_server_status_for_port(agent_builder_dir, item) for item in ports]
    stale = [
        server for server in servers if server["metadata_present"] and not server["owned_live"]
    ]
    unknown = [
        server for server in servers if server["listener_present"] and not server["owned_live"]
    ]
    return {
        "status": "ok",
        "servers": servers,
        "stale_count": len(stale),
        "unknown_listener_count": len(unknown),
        "next_step": "builder server stop --port <port> --json",
    }


def _known_ports(agent_builder_dir: Path) -> list[int]:
    ports: set[int] = set()
    for path in servers_dir(agent_builder_dir).glob("*.json"):
        if path.stem.isdigit():
            ports.add(int(path.stem))
    port_file = agent_builder_dir / "server.port"
    if port_file.exists():
        with suppress(OSError, ValueError):
            ports.add(int(port_file.read_text(encoding="utf-8").strip()))
    return sorted(ports)


def _server_status_for_port(agent_builder_dir: Path, port: int) -> dict[str, Any]:
    metadata = read_server_metadata(agent_builder_dir, port)
    listeners = listening_processes(port)
    metadata_pid = int(metadata.get("pid", 0)) if metadata else 0
    owned_live = bool(metadata and any(proc.pid == metadata_pid for proc in listeners))
    return {
        "port": port,
        "metadata_present": metadata is not None,
        "listener_present": bool(listeners),
        "owned_live": owned_live,
        "pids": [proc.pid for proc in listeners],
        "metadata": metadata or {},
        "classification": _classify(metadata, listeners, metadata_pid, owned_live),
    }


def _classify(
    metadata: dict[str, Any] | None,
    listeners: list[PortProcess],
    metadata_pid: int,
    owned_live: bool,
) -> str:
    if owned_live:
        return "owned_live"
    if metadata and not listeners:
        return "stale_metadata"
    if metadata and listeners and all(proc.pid != metadata_pid for proc in listeners):
        return "metadata_pid_mismatch"
    if listeners:
        return "unknown_listener"
    return "free"


def ensure_port_available(agent_builder_dir: Path, port: int, *, force: bool = False) -> None:
    listeners = listening_processes(port)
    if not listeners:
        return
    metadata = read_server_metadata(agent_builder_dir, port)
    metadata_pid = int(metadata.get("pid", 0)) if metadata else 0
    owned = metadata and metadata.get("owner") == OWNER
    if owned and any(proc.pid == metadata_pid for proc in listeners):
        stop_server(agent_builder_dir, port=port, force=False)
        wait_for_port_free(port)
        return
    if not force:
        pids = ", ".join(str(proc.pid) for proc in listeners)
        raise RuntimeSupervisorError(
            f"Port {port} is already in use by non-builder process(es): {pids}.",
            code="port_in_use_unknown_owner",
            exit_code=3,
        )
    for proc in listeners:
        terminate_pid(proc.pid)
    wait_for_port_free(port)


def stop_server(agent_builder_dir: Path, *, port: int, force: bool = False) -> dict[str, Any]:
    metadata = read_server_metadata(agent_builder_dir, port)
    listeners = listening_processes(port)
    metadata_pid = int(metadata.get("pid", 0)) if metadata else 0
    owned = metadata and metadata.get("owner") == OWNER
    target_pids = [proc.pid for proc in listeners if owned and proc.pid == metadata_pid]
    if not target_pids and force:
        target_pids = [proc.pid for proc in listeners]
    if listeners and not target_pids:
        raise RuntimeSupervisorError(
            f"Port {port} has listener(s), but none are proven builder-owned.",
            code="unknown_listener_not_stopped",
            exit_code=3,
        )
    stopped: list[int] = []
    for pid in target_pids:
        terminate_pid(pid)
        stopped.append(pid)
    wait_for_port_free(port)
    clear_server_metadata(agent_builder_dir, port)
    return {
        "status": "ok",
        "port": port,
        "stopped_pids": stopped,
        "metadata_removed": metadata is not None,
        "next_step": "builder server status --json",
    }


def terminate_pid(pid: int, *, process_group_id: int = 0, grace_seconds: float = 2.0) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
        return
    target = -process_group_id if process_group_id > 0 else pid
    try:
        os.kill(target, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(target, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def wait_for_port_free(port: int, *, timeout_seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not listening_processes(port):
            return True
        time.sleep(0.05)
    return not listening_processes(port)
