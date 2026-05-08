"""Project commands — compact discovery, summary, and exact reads."""

from __future__ import annotations

import sys
from typing import Any

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate
from autonomous_agent_builder.cli.retrieval import (
    RetrievalResolution,
    compact_results_payload,
    join_query_parts,
    make_preview,
    not_found_hint,
    resolve_collection_item,
)

app = typer.Typer(
    help=(
        "Project scope and discovery.\n\n"
        "Start here:\n"
        "  builder backlog project list --json\n"
        "  builder backlog project search <query> --json\n"
        "  builder backlog project summary <query> --json\n"
    )
)


def _project_compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("name", "")),
        "doc_type": "project",
        "status": str(item.get("language", "")),
        "preview": make_preview(item, preview_keys=("description", "repo_url"), max_chars=120),
    }


def _project_list(client, *, limit: int | None = None) -> list[dict[str, Any]]:
    data = client.get("/projects/")
    items = data if isinstance(data, list) else []
    return items[:limit] if limit else items


def _resolve_project(query: str, client) -> RetrievalResolution:
    items = _project_list(client)
    resolution = resolve_collection_item(
        query,
        items,
        id_keys=("id",),
        text_keys=("name", "description", "repo_url", "language"),
        suggestion_id_key="id",
        suggestion_label_key="name",
    )
    if resolution is None:
        return RetrievalResolution(item={}, matched_on="", suggestions=[])
    if resolution.item:
        return RetrievalResolution(
            item=client.get(f"/projects/{resolution.item['id']}"),
            matched_on=resolution.matched_on,
            suggestions=resolution.suggestions,
        )
    return resolution


def _handle_project_lookup_error(query: str, resolution: RetrievalResolution, *, use_json: bool) -> None:
    hint = not_found_hint(
        query,
        search_command=f'builder backlog project search "{query}" --json',
        suggestions=resolution.suggestions,
    )
    emit_error(
        f"Project not found: {query}",
        code="not_found",
        hint=hint,
        detail={"query": query, "suggestions": resolution.suggestions},
        use_json=use_json,
    )
    sys.exit(1)


@app.command("list")
def list_projects(
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all projects."""
    client = get_client(use_json=json)
    try:
        items = _project_list(client, limit=limit)
        compact = [_project_compact(item) for item in items]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "NAME", "LANGUAGE", "PREVIEW"]
            table_rows = [
                [row["id"], row["title"], row["status"], row["preview"]]
                for row in rows
            ]
            return table(headers, table_rows)

        render(
            compact_results_payload("list", compact, next_step="builder backlog project summary <query> --json")
            if json
            else compact,
            fmt,
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    finally:
        client.close()


@app.command()
def search(
    query_parts: list[str] = typer.Argument(help="Project query."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search projects by name, description, repo URL, or language."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        items = _project_list(client)
        resolution_items = []
        for item in items:
            resolution = resolve_collection_item(
                query,
                [item],
                id_keys=("id",),
                text_keys=("name", "description", "repo_url", "language"),
                suggestion_id_key="id",
                suggestion_label_key="name",
            )
            if resolution and resolution.item:
                resolution_items.append(item)
        compact = [_project_compact(item) for item in resolution_items[:limit]]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "NAME", "LANGUAGE", "PREVIEW"]
            table_rows = [[row["id"], row["title"], row["status"], row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload(query, compact, next_step="builder backlog project summary <query> --json")
            if json
            else compact,
            fmt,
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def summary(
    query_parts: list[str] = typer.Argument(help="Project ID or natural-language query."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded project overview before loading full details."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        resolution = _resolve_project(query, client)
        if not resolution.item:
            _handle_project_lookup_error(query, resolution, use_json=json)

        payload = {
            "id": resolution.item.get("id", ""),
            "title": resolution.item.get("name", ""),
            "doc_type": "project",
            "matched_on": resolution.matched_on,
            "summary": "\n".join(
                line
                for line in [
                    f"language: {resolution.item.get('language', '')}",
                    f"repo_url: {resolution.item.get('repo_url', '')}",
                    f"description: {truncate(str(resolution.item.get('description', '') or ''), 220)}",
                ]
                if line.strip().split(": ", 1)[1]
            ),
            "next_step": f"builder backlog project show {resolution.item.get('id', '')} --json",
        }

        def fmt(data: dict[str, Any]) -> str:
            return (
                f"{data['title']}\n"
                f"id: {data['id']}\n"
                f"matched_on: {data['matched_on']}\n\n"
                f"{data['summary']}\n\n"
                f"Next: {data['next_step']}"
            )

        render(payload, fmt, use_json=json)
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

    client = get_client(use_json=json)
    try:
        data = client.post("/projects/", payload)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
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
    project_parts: list[str] = typer.Argument(help="Project ID or natural-language query."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show project details."""
    query = join_query_parts(project_parts)
    client = get_client(use_json=json)
    try:
        resolution = _resolve_project(query, client)
        if not resolution.item:
            _handle_project_lookup_error(query, resolution, use_json=json)
        data = {
            **resolution.item,
            "matched_on": resolution.matched_on,
            "next_step": f"builder backlog project summary {resolution.item.get('id', '')} --json",
        }

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"name: {d.get('name', '')}",
                f"description: {d.get('description', '')}",
                f"language: {d.get('language', '')}",
                f"repo_url: {d.get('repo_url', '')}",
                f"created: {d.get('created_at', '')}",
                f"matched_on: {d.get('matched_on', '')}",
                f"Next: {d.get('next_step', '')}",
            ]
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
