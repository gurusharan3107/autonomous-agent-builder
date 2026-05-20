"""Server lifecycle commands for builder-owned local processes."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
    handle_project_not_found,
    require_project,
)
from autonomous_agent_builder.runtime.supervisor import (
    RuntimeSupervisorError,
    server_status,
    stop_server,
)

app = typer.Typer(
    help=(
        "Builder server lifecycle — inspect and stop builder-owned local servers.\n\n"
        "Start here:\n"
        "  builder server status --json\n"
        "  builder server doctor --json\n"
        "  builder server stop --port 9876 --json"
    )
)


@app.command()
def status(
    port: int | None = typer.Option(None, "--port", help="Limit status to one port."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show builder-owned server metadata and live listener status."""
    try:
        agent_builder_dir = find_agent_builder_dir()
    except ProjectNotFoundError as exc:
        handle_project_not_found(exc, use_json=json)
        return
    payload = server_status(agent_builder_dir, port)
    render(payload, _format_status, use_json=json)
    sys.exit(0)


@app.command()
def stop(
    port: int = typer.Option(..., "--port", help="Port to stop."),
    force: bool = typer.Option(
        False,
        "--force",
        help=(
            "Stop an unknown listener. Without this, only proven builder-owned "
            "listeners are stopped."
        ),
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Stop a builder-owned server by port."""
    agent_builder_dir = require_project()
    try:
        payload = stop_server(agent_builder_dir, port=port, force=force)
    except RuntimeSupervisorError as exc:
        payload = {
            "status": "error",
            "error": str(exc),
            "code": exc.code,
            "exit_code": exc.exit_code,
            "next_step": f"builder server status --port {port} --json",
        }
        render(payload, lambda data: f"Error: {data['error']}", use_json=json)
        sys.exit(exc.exit_code)
    render(payload, lambda data: f"stopped port {data['port']}", use_json=json)
    sys.exit(0)


@app.command()
def doctor(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Diagnose stale server metadata and unknown listeners."""
    try:
        agent_builder_dir = find_agent_builder_dir()
    except ProjectNotFoundError as exc:
        handle_project_not_found(exc, use_json=json)
        return
    payload = server_status(agent_builder_dir)
    failed = payload.get("unknown_listener_count", 0) > 0
    payload.update(
        {
            "passed": not failed,
            "status": "error" if failed else "ok",
            "code": "unknown_server_listener" if failed else "ok",
            "next_step": (
                "builder server status --json" if failed else "builder start --port <port>"
            ),
        }
    )
    render(payload, _format_doctor, use_json=json)
    sys.exit(1 if failed else 0)


def _format_status(data: dict) -> str:
    servers = data.get("servers", [])
    if not servers:
        return "no builder server metadata found"
    lines = []
    for server in servers:
        lines.append(
            f"port {server['port']}: {server['classification']} "
            f"pids={','.join(str(pid) for pid in server.get('pids', [])) or '-'}"
        )
    return "\n".join(lines)


def _format_doctor(data: dict) -> str:
    state = "passed" if data.get("passed") else "failed"
    return f"server doctor {state}\n{_format_status(data)}"
