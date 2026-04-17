"""Start command — launch embedded server and dashboard.

Starts the FastAPI server from .agent-builder/server/ with automatic
port detection and serves the dashboard on localhost.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    handle_project_not_found,
    require_project,
)

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def start_command(
    port: int = typer.Option(None, "--port", help="Port (auto-detect if not specified)."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with auto-reload."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Start the embedded server and dashboard.
    
    Launches the FastAPI server from .agent-builder/server/ and serves
    the dashboard on localhost. Automatically detects an available port
    if not specified.
    
    Examples:
        builder start
        builder start --port 8001
        builder start --debug
    """
    try:
        # Require initialized project
        agent_builder_dir = require_project()
        
        # Import here to avoid circular dependencies
        from autonomous_agent_builder.cli.commands.start_impl import run_start
        
        result = run_start(
            agent_builder_dir=agent_builder_dir,
            port=port,
            host=host,
            debug=debug,
        )
        
        def fmt(d: dict) -> str:
            if d.get("error"):
                return f"Error: {d['error']}\n\nHint: {d.get('hint', '')}"
            
            lines = [
                f"✓ Server started on {d['url']}",
                f"  Port: {d['port']}",
                f"  Database: {d['database']}",
                "",
                "Dashboard: Open the URL above in your browser",
                "Press Ctrl+C to stop the server",
            ]
            return "\n".join(lines)
        
        render(result, fmt, use_json=json)
        
        if result.get("error"):
            sys.exit(EXIT_FAILURE)
        else:
            # Server is running - this blocks until Ctrl+C
            pass
            
    except ProjectNotFoundError as e:
        handle_project_not_found(e, use_json=json)
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        if not json:
            print("\n\nServer stopped")
        sys.exit(EXIT_SUCCESS)
    except Exception as e:
        error_result = {
            "error": str(e),
            "hint": "Check server logs for details",
        }
        
        def fmt(d: dict) -> str:
            return f"Error: {d['error']}\n\nHint: {d['hint']}"
        
        render(error_result, fmt, use_json=json)
        sys.exit(EXIT_FAILURE)
