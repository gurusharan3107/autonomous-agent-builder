"""Project commands — list, create, show."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import render, table

app = typer.Typer(help="Project CRUD.")


@app.command("list")
def list_projects(
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all projects."""
    client = get_client()
    try:
        data = client.get("/projects/")
    except AabApiError as e:
        handle_api_error(e)
    else:
        # Apply client-side limit
        items = data[:limit] if isinstance(data, list) else data

        def fmt(items: list) -> str:
            headers = ["ID", "NAME", "LANGUAGE", "CREATED"]
            rows = [
                [
                    str(p.get("id", ""))[:12],
                    p.get("name", ""),
                    p.get("language", ""),
                    str(p.get("created_at", ""))[:10],
                ]
                for p in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def create(
    name: str = typer.Option(..., help="Project name."),
    language: str = typer.Option("python", help="Language (python, java, node)."),
    description: str = typer.Option("", help="Project description."),
    repo_url: str = typer.Option("", "--repo-url", help="Repository URL."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Create a new project."""
    payload = {
        "name": name,
        "language": language,
        "description": description,
        "repo_url": repo_url,
    }

    if dry_run:
        render({"dry_run": True, "would_create": payload}, lambda d: str(d), use_json=json)
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.post("/projects/", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"created project {d.get('id', '')[:12]}\n"
                f"name: {d.get('name', '')}\n"
                f"language: {d.get('language', '')}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    project_id: str = typer.Argument(help="Project ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show project details."""
    client = get_client()
    try:
        data = client.get(f"/projects/{project_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"name: {d.get('name', '')}",
                f"description: {d.get('description', '')}",
                f"language: {d.get('language', '')}",
                f"repo_url: {d.get('repo_url', '')}",
                f"created: {d.get('created_at', '')}",
            ]
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
