"""Port management utilities for embedded server.

Handles automatic port detection, port file management, and port conflict resolution.
"""

from __future__ import annotations

import platform
import socket
import subprocess
from pathlib import Path


class PortNotAvailableError(Exception):
    """Raised when no ports are available in the specified range."""
    
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
        super().__init__(f"No available ports in range {start}-{end}")


def find_available_port(start: int = 9876, end: int = 9886) -> int:
    """Find an available port in the specified range.
    
    Tries each port in the range sequentially until an available one is found.
    
    Args:
        start: Starting port number (inclusive, default: 9876)
        end: Ending port number (inclusive, default: 9886)
        
    Returns:
        Available port number
        
    Raises:
        PortNotAvailableError: If no ports are available in the range
        
    Examples:
        >>> port = find_available_port()
        >>> print(f"Using port {port}")
    """
    for port in range(start, end + 1):
        if is_port_available(port):
            return port
    
    raise PortNotAvailableError(start, end)


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding.
    
    Args:
        port: Port number to check
        host: Host address to bind to
        
    Returns:
        True if port is available, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def write_port_file(port: int, agent_builder_dir: Path) -> None:
    """Write assigned port to .agent-builder/server.port file.
    
    Args:
        port: Port number to write
        agent_builder_dir: Path to .agent-builder/ directory
    """
    port_file = agent_builder_dir / "server.port"
    port_file.write_text(str(port))


def read_port_file(agent_builder_dir: Path) -> int | None:
    """Read port from .agent-builder/server.port file.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
        
    Returns:
        Port number if file exists and is valid, None otherwise
    """
    port_file = agent_builder_dir / "server.port"
    
    if not port_file.exists():
        return None
    
    try:
        port_str = port_file.read_text().strip()
        port = int(port_str)
        
        # Validate port range
        if 1 <= port <= 65535:
            return port
        else:
            return None
    except (ValueError, OSError):
        return None


def get_server_url(port: int, host: str = "127.0.0.1") -> str:
    """Get the server URL for the given port and host.
    
    Args:
        port: Port number
        host: Host address
        
    Returns:
        Server URL (e.g., "http://127.0.0.1:9876")
    """
    return f"http://{host}:{port}"


def kill_process_on_port(port: int) -> bool:
    """Kill any process using the specified port.
    
    Args:
        port: Port number to free up
        
    Returns:
        True if a process was killed, False if port was already free
    """
    system = platform.system()
    
    try:
        if system == "Windows":
            # Find process using the port
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=True,
            )
            
            # Parse netstat output to find PID
            pid = None
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    break
            
            if pid and pid != "0":
                # Kill the process
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    check=True,
                )
                print(f"✓ Killed existing process (PID {pid}) on port {port}")
                return True
                
        else:  # Linux/Mac
            # Find process using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            
            pid = result.stdout.strip()
            if pid:
                # Kill the process
                subprocess.run(
                    ["kill", "-9", pid],
                    capture_output=True,
                    check=True,
                )
                print(f"✓ Killed existing process (PID {pid}) on port {port}")
                return True
                
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Command failed or not available, port is likely free
        pass
    
    return False
