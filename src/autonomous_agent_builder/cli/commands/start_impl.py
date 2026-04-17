"""Implementation logic for builder start command.

Handles server startup, port detection, and uvicorn configuration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def run_start(
    agent_builder_dir: Path,
    port: int | None,
    host: str,
    debug: bool,
) -> dict[str, Any]:
    """Start the embedded server.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
        port: Port number (None for auto-detect)
        host: Host address to bind
        debug: Enable debug mode with auto-reload
        
    Returns:
        Result dictionary with server information
    """
    from autonomous_agent_builder.cli.port_manager import (
        PortNotAvailableError,
        find_available_port,
        get_server_url,
        kill_process_on_port,
        write_port_file,
    )
    
    # Determine port
    if port is None:
        try:
            port = find_available_port()
        except PortNotAvailableError as e:
            return {
                "error": f"No available ports in range {e.start}-{e.end}",
                "hint": "Specify a port with --port option or stop other services",
            }
    
    # Kill any existing process on this port
    kill_process_on_port(port)
    
    # Write port file
    write_port_file(port, agent_builder_dir)
    
    # Get paths
    db_path = agent_builder_dir / "agent_builder.db"
    dashboard_path = agent_builder_dir / "dashboard"
    server_path = agent_builder_dir / "server"
    
    # Verify database exists
    if not db_path.exists():
        return {
            "error": "Database not found",
            "hint": "Run 'builder init --force' to reinitialize the project",
        }
    
    # Start server
    try:
        _start_uvicorn(
            server_path=server_path,
            db_path=db_path,
            dashboard_path=dashboard_path,
            host=host,
            port=port,
            debug=debug,
        )
        
        # This line is only reached if server fails to start
        return {
            "error": "Server failed to start",
            "hint": "Check that the port is not already in use",
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "hint": "Check server logs for details",
        }


def _start_uvicorn(
    server_path: Path,
    db_path: Path,
    dashboard_path: Path,
    host: str,
    port: int,
    debug: bool,
) -> None:
    """Start uvicorn server.
    
    Args:
        server_path: Path to server directory
        db_path: Path to database file
        dashboard_path: Path to dashboard assets
        host: Host address
        port: Port number
        debug: Enable debug mode
    """
    import uvicorn
    
    # Add server path to Python path so we can import the app
    sys.path.insert(0, str(server_path.parent))
    
    # Import the app factory
    from autonomous_agent_builder.embedded.server.app import create_app
    
    # Create app instance
    app = create_app(db_path=db_path, dashboard_path=dashboard_path)
    
    # Configure uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info" if not debug else "debug",
        reload=debug,
    )
    
    # Create and run server
    server = uvicorn.Server(config)
    
    # Print startup message
    url = f"http://{host}:{port}"
    print(f"\n✓ Server started on {url}")
    print(f"  Database: {db_path}")
    print(f"\nDashboard: Open {url} in your browser")
    print("Press Ctrl+C to stop the server\n")
    
    # Run server (blocks until Ctrl+C)
    server.run()
