"""Server management commands — start, health check."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import render

app = typer.Typer(help="Server management.")


@app.command()
def start(
    port: int = typer.Option(8000, help="Port to listen on."),
    host: str = typer.Option("0.0.0.0", help="Host to bind to."),
    debug: bool = typer.Option(False, help="Enable debug mode with auto-reload."),
) -> None:
    """Start the builder API server."""
    import uvicorn

    uvicorn.run(
        "autonomous_agent_builder.api.app:app",
        host=host,
        port=port,
        reload=debug,
    )


@app.command()
def health(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Check if the server is running and healthy."""
    client = get_client()
    try:
        data = client.health()
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return f"status: {d.get('status', 'unknown')}\nversion: {d.get('version', 'unknown')}"

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
