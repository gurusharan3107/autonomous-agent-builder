"""Implementation logic for builder start command.

Handles dashboard publication, server startup, fixed-port reuse, and uvicorn
configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


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
    # Mirror the main app entrypoint so embedded Claude SDK/CLI calls inherit
    # repo-local auth and runtime settings when the dashboard is launched via
    # `builder start`.
    load_dotenv(agent_builder_dir.parent / ".env")

    from autonomous_agent_builder.cli.port_manager import (
        DEFAULT_PORT,
        kill_process_on_port,
        write_port_file,
    )
    
    # Default to the canonical local product port.
    if port is None:
        port = DEFAULT_PORT
    
    # Kill any existing process on this port
    kill_process_on_port(port)
    
    # Write port file
    write_port_file(port, agent_builder_dir)
    
    # Get paths
    project_root = agent_builder_dir.parent
    db_path = agent_builder_dir / "agent_builder.db"
    dashboard_path = agent_builder_dir / "dashboard"
    server_path = agent_builder_dir / "server"
    
    # Verify database exists
    if not db_path.exists():
        return {
            "error": "Database not found",
            "hint": "Run 'builder init --force' to reinitialize the project",
        }

    dashboard_result = _publish_dashboard_assets(project_root, dashboard_path)
    if dashboard_result.get("error"):
        return dashboard_result
    
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


def _publish_dashboard_assets(project_root: Path, dashboard_path: Path) -> dict[str, Any]:
    """Build and publish the current frontend into .agent-builder/dashboard."""
    frontend_dir = project_root / "frontend"
    package_json = frontend_dir / "package.json"

    if not package_json.exists():
        return {}

    npm_exe = shutil.which("npm")
    if npm_exe is None:
        return {
            "error": "npm is not installed or not available in PATH",
            "hint": "Install Node.js/npm so 'builder start' can build the dashboard before launch",
        }

    print("Building dashboard from frontend/ ...")
    try:
        subprocess.run([npm_exe, "run", "build"], cwd=frontend_dir, check=True)
    except FileNotFoundError:
        return {
            "error": "npm is not installed or not available in PATH",
            "hint": "Install Node.js/npm so 'builder start' can build the dashboard before launch",
        }
    except subprocess.CalledProcessError as exc:
        return {
            "error": f"Dashboard build failed with exit code {exc.returncode}",
            "hint": "Fix the frontend build errors, then rerun 'builder start'",
        }

    dist_dir = frontend_dir / "dist"
    if not dist_dir.exists() or not any(dist_dir.iterdir()):
        return {
            "error": f"Dashboard build output missing at {dist_dir}",
            "hint": "Check the frontend build configuration and rerun 'builder start'",
        }

    if dashboard_path.exists():
        shutil.rmtree(dashboard_path)
    shutil.copytree(dist_dir, dashboard_path)
    print(f"Published dashboard to {dashboard_path}")
    return {}


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
    print(f"\n[OK] Server started on {url}")
    print(f"  Database: {db_path}")
    print(f"\nDashboard: Open {url} in your browser")
    print("Press Ctrl+C to stop the server\n")
    
    # Run server (blocks until Ctrl+C)
    server.run()
