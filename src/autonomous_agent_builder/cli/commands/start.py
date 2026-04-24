"""Start command — build/publish the dashboard, then launch the local product.

Starts the FastAPI server from .agent-builder/server/, publishes the current
frontend bundle into .agent-builder/dashboard/, and serves the dashboard on
localhost.
"""

from __future__ import annotations

import sys

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
    port: int = typer.Option(None, "--port", help="Port (defaults to 9876 when omitted)."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with auto-reload."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Build/publish the dashboard, then start the embedded server.
    
    Launches the FastAPI server from .agent-builder/server/, rebuilds the
    current frontend when `frontend/` is present, and serves the dashboard on
    localhost. Automatically detects an available port if not specified.
    
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
                f"[OK] Server started on {d['url']}",
                f"  Port: {d['port']}",
                f"  Database: {d['database']}",
                "",
                "Dashboard: Open the URL above in your browser",
                "First run: the dashboard will enter onboarding mode until the repo is seeded",
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
