"""Task commands — list, show, status, dispatch."""

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

app = typer.Typer(help="Task lifecycle and dispatch.")


@app.command("list")
def list_tasks(
    feature: str = typer.Option(..., "--feature", help="Feature ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(50, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List tasks for a feature."""
    client = get_client()
    try:
        data = client.get(f"/features/{feature}/tasks")
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []
        if status:
            items = [t for t in items if t.get("status") == status]
        items = items[:limit]

        def fmt(items: list) -> str:
            headers = ["ID", "TITLE", "STATUS", "RETRIES", "CREATED"]
            rows = [
                [
                    str(t.get("id", ""))[:12],
                    t.get("title", "")[:35],
                    format_status(t.get("status", "")),
                    str(t.get("retry_count", 0)),
                    str(t.get("created_at", ""))[:10],
                ]
                for t in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    task_id: str = typer.Argument(help="Task ID."),
    full: bool = typer.Option(False, "--full", help="Include full details."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show task details. Use --full for gate results and agent runs."""
    client = get_client()
    try:
        data = client.get(f"/tasks/{task_id}")
        if full:
            data["gate_results"] = client.get(f"/tasks/{task_id}/gates")
            data["agent_runs"] = client.get(f"/tasks/{task_id}/runs")
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"title: {d.get('title', '')}",
                f"status: {format_status(d.get('status', ''))}",
                f"description: {truncate(d.get('description', '') or '', 500)}",
                f"complexity: {d.get('complexity', '')}",
                f"retry_count: {d.get('retry_count', 0)}",
            ]
            if d.get("blocked_reason"):
                lines.append(f"blocked_reason: {d['blocked_reason']}")
            if d.get("capability_limit_reason"):
                lines.append(
                    f"capability_limit: {truncate(d['capability_limit_reason'], 300)}"
                )
            if d.get("gate_results"):
                lines.append(f"\ngate_results: {len(d['gate_results'])} results")
                for g in d["gate_results"][:5]:
                    lines.append(
                        f"  {g.get('gate_name', '')}: "
                        f"{format_status(g.get('status', ''))} "
                        f"({g.get('findings_count', 0)} findings)"
                    )
            if d.get("agent_runs"):
                lines.append(f"\nagent_runs: {len(d['agent_runs'])} runs")
                for r in d["agent_runs"][:5]:
                    lines.append(
                        f"  {r.get('agent_name', '')}: "
                        f"${r.get('cost_usd', 0):.2f} "
                        f"{r.get('duration_ms', 0)}ms "
                        f"{r.get('stop_reason', '')}"
                    )
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def status(
    task_id: str = typer.Argument(help="Task ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Quick status check — current phase, retry count, blocked reason."""
    client = get_client()
    try:
        data = client.get(f"/tasks/{task_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        summary = {
            "id": data.get("id"),
            "status": data.get("status"),
            "retry_count": data.get("retry_count", 0),
            "blocked_reason": data.get("blocked_reason"),
            "capability_limit_reason": data.get("capability_limit_reason"),
        }

        def fmt(d: dict) -> str:
            line = f"{d['id'][:12]}  {format_status(d.get('status', ''))}"
            if d.get("retry_count", 0) > 0:
                line += f"  retries={d['retry_count']}"
            if d.get("blocked_reason"):
                line += f"  blocked: {d['blocked_reason']}"
            return line

        render(summary, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def dispatch(
    task_id: str = typer.Argument(help="Task ID to dispatch."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation and dispatch."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Dispatch a task through the SDLC pipeline.

    Without --yes, shows what would happen. With --yes, dispatches.
    """
    if not yes:
        info = {"task_id": task_id, "action": "dispatch", "confirmed": False}
        render(
            info,
            lambda d: f"Would dispatch task {task_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.post("/dispatch", {"task_id": task_id})
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"dispatched task {task_id}\n"
                f"status: {d.get('status', '')}\n"
                f"current_status: {d.get('current_status', '')}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
