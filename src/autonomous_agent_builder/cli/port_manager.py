"""Port management utilities for the embedded server."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path


DEFAULT_PORT = 9876


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
            return True
    except OSError:
        return False


def write_port_file(port: int, agent_builder_dir: Path) -> None:
    """Write assigned port to .agent-builder/server.port file."""
    port_file = agent_builder_dir / "server.port"
    port_file.write_text(str(port))


def read_port_file(agent_builder_dir: Path) -> int | None:
    """Read port from .agent-builder/server.port file."""
    port_file = agent_builder_dir / "server.port"

    if not port_file.exists():
        return None

    try:
        port = int(port_file.read_text().strip())
        return port if 1 <= port <= 65535 else None
    except (ValueError, OSError):
        return None


def get_server_url(port: int, host: str = "127.0.0.1") -> str:
    """Get the server URL for the given port and host."""
    return f"http://{host}:{port}"


def kill_process_on_port(port: int) -> bool:
    """Kill any listening process using the specified port."""
    try:
        pids: list[str] = []

        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pids.append(parts[-1])
            pids = list(dict.fromkeys(pids))  # deduplicate, preserve order
        else:
            result = subprocess.run(
                ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
            )
            pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip()]

        if not pids:
            return False

        for pid in pids:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            else:
                try:
                    subprocess.run(["kill", pid], capture_output=True, check=True)
                except subprocess.CalledProcessError:
                    subprocess.run(["kill", "-9", pid], capture_output=True, check=True)

        print(f"[OK] Killed existing process(es) ({', '.join(pids)}) on port {port}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
