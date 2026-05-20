"""Port management utilities for the embedded server."""

from __future__ import annotations

import socket
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
    """Compatibility wrapper that force-stops a listener on the specified port."""
    from autonomous_agent_builder.runtime.supervisor import listening_processes, stop_server

    processes = listening_processes(port)
    if not processes:
        return False
    stop_server(Path(".agent-builder"), port=port, force=True)
    return True


def ensure_builder_port_available(
    agent_builder_dir: Path,
    port: int,
    *,
    force: bool = False,
) -> None:
    """Ensure a port is free, stopping only builder-owned listeners by default."""
    from autonomous_agent_builder.runtime.supervisor import ensure_port_available

    ensure_port_available(agent_builder_dir, port, force=force)
