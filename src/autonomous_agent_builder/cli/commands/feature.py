"""Feature commands — list, create, show."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import format_status, render, table

app = typer.Typer(help="Feature CRUD.")


@app.command("list")
def list_features(
    project: str = typer.Option(..., "--project", help="Project ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List features for a project."""
    client = get_client()
    try:
        data = client.get(f"/projects/{project}/features")
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []
        if status:
            items = [f for f in items if f.get("status") == status]
        items = items[:limit]

        def fmt(items: list) -> str:
            headers = ["ID", "TITLE", "STATUS", "PRIORITY", "CREATED"]
            rows = [
                [
                    str(f.get("id", ""))[:12],
                    f.get("title", "")[:40],
                    format_status(f.get("status", "")),
                    str(f.get("priority", "")),
                    str(f.get("created_at", ""))[:10],
                ]
                for f in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def create(
    project: str = typer.Option(..., "--project", help="Project ID."),
    title: str = typer.Option(..., help="Feature title."),
    description: str = typer.Option("", help="Feature description."),
    priority: int = typer.Option(0, help="Priority (0=highest)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Create a feature under a project."""
    payload = {"title": title, "description": description, "priority": priority}

    if dry_run:
        render(
            {"dry_run": True, "project_id": project, "would_create": payload},
            lambda d: str(d),
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.post(f"/projects/{project}/features", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"created feature {d.get('id', '')[:12]}\n"
                f"title: {d.get('title', '')}\n"
                f"status: {format_status(d.get('status', ''))}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    feature_id: str = typer.Argument(help="Feature ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show feature details."""
    client = get_client()
    try:
        data = client.get(f"/features/{feature_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"title: {d.get('title', '')}",
                f"description: {d.get('description', '')}",
                f"status: {format_status(d.get('status', ''))}",
                f"priority: {d.get('priority', '')}",
                f"project_id: {d.get('project_id', '')}",
                f"created: {d.get('created_at', '')}",
            ]
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
