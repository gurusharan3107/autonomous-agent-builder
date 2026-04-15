"""Run commands — list, show agent run history."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import format_status, render, table, truncate

app = typer.Typer(help="Agent run history.")


@app.command("list")
def list_runs(
    task: str = typer.Option(..., "--task", help="Task ID."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List agent runs for a task."""
    client = get_client()
    try:
        data = client.get(f"/tasks/{task}/runs")
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []
        items = items[:limit]

        def fmt(items: list) -> str:
            headers = ["ID", "AGENT", "COST", "TOKENS", "TURNS", "DURATION", "STATUS"]
            rows = [
                [
                    str(r.get("id", ""))[:12],
                    r.get("agent_name", "")[:12],
                    f"${r.get('cost_usd', 0):.2f}",
                    str(r.get("tokens_input", 0) + r.get("tokens_output", 0)),
                    str(r.get("num_turns", 0)),
                    f"{r.get('duration_ms', 0)}ms",
                    r.get("status", ""),
                ]
                for r in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    run_id: str = typer.Argument(help="Agent run ID."),
    full: bool = typer.Option(False, "--full", help="Include events timeline."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show agent run details. Use --full for events."""
    client = get_client()
    try:
        # Runs are fetched via task list; show individual run details
        data = client.get(f"/tasks/{run_id}/runs")
        if isinstance(data, list) and data:
            data = data[0]
        elif not isinstance(data, dict):
            data = {"error": "run not found"}
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"agent_name: {d.get('agent_name', '')}",
                f"status: {format_status(d.get('status', ''))}",
                f"cost_usd: ${d.get('cost_usd', 0):.2f}",
                f"tokens_input: {d.get('tokens_input', 0):,}",
                f"tokens_output: {d.get('tokens_output', 0):,}",
                f"tokens_cached: {d.get('tokens_cached', 0):,}",
                f"num_turns: {d.get('num_turns', 0)}",
                f"duration_ms: {d.get('duration_ms', 0)}",
                f"stop_reason: {d.get('stop_reason', '')}",
                f"session_id: {d.get('session_id', '')}",
            ]
            if d.get("error"):
                lines.append(f"error: {truncate(d['error'], 500)}")
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
