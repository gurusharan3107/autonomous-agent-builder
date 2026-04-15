"""Gate commands — list, show quality gate results."""

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

app = typer.Typer(help="Quality gate results.")


@app.command("list")
def list_gates(
    task: str = typer.Option(..., "--task", help="Task ID."),
    status: str | None = typer.Option(None, help="Filter by status (pass, fail, ...)."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List quality gate results for a task."""
    client = get_client()
    try:
        data = client.get(f"/tasks/{task}/gates")
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []
        if status:
            items = [g for g in items if g.get("status") == status]
        items = items[:limit]

        def fmt(items: list) -> str:
            headers = ["ID", "GATE", "STATUS", "FINDINGS", "ELAPSED", "CREATED"]
            rows = [
                [
                    str(g.get("id", ""))[:12],
                    g.get("gate_name", ""),
                    format_status(g.get("status", "")),
                    str(g.get("findings_count", 0)),
                    f"{g.get('elapsed_ms', 0)}ms",
                    str(g.get("created_at", ""))[:10],
                ]
                for g in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    gate_id: str = typer.Argument(help="Gate result ID."),
    full: bool = typer.Option(False, "--full", help="Include evidence JSON."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show gate result details. Use --full for evidence."""
    client = get_client()
    try:
        # Gate results are fetched via task, so we get individual by listing
        # For now, return the gate data from the list endpoint
        data = client.get(f"/tasks/{gate_id}/gates")
        if isinstance(data, list) and data:
            # If gate_id is actually a task_id, show first result
            data = data[0]
        elif not isinstance(data, dict):
            data = {"error": "gate not found"}
    except AabApiError as e:
        handle_api_error(e)
    else:
        if not full and "evidence" in data:
            data["evidence"] = truncate(str(data["evidence"]), 500)

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"gate_name: {d.get('gate_name', '')}",
                f"status: {format_status(d.get('status', ''))}",
                f"findings_count: {d.get('findings_count', 0)}",
                f"elapsed_ms: {d.get('elapsed_ms', 0)}",
                f"timeout: {d.get('timeout', False)}",
                f"remediation_attempted: {d.get('remediation_attempted', False)}",
                f"remediation_succeeded: {d.get('remediation_succeeded', False)}",
            ]
            if d.get("error_code"):
                lines.append(f"error_code: {d['error_code']}")
            if d.get("evidence"):
                lines.append(f"evidence: {d['evidence']}")
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
