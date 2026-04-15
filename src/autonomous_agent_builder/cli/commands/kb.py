"""Knowledge base commands — add, list, show, search, update."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import render, table, truncate

app = typer.Typer(help="Knowledge base — agent-written docs (ADRs, contracts, runbooks).")


def _read_content(content: str | None, content_file: str | None) -> str:
    """Resolve content from --content or --content-file (supports stdin via -)."""
    if content:
        return content
    if content_file:
        if content_file == "-":
            return sys.stdin.read()
        path = Path(content_file)
        if not path.exists():
            from autonomous_agent_builder.cli.output import error
            error(f"Error: file not found — {content_file}")
            sys.exit(2)
        return path.read_text(encoding="utf-8")
    from autonomous_agent_builder.cli.output import error
    error("Error: provide --content or --content-file")
    sys.exit(2)


@app.command()
def add(
    task: str = typer.Option(..., "--task", help="Task ID this doc belongs to."),
    doc_type: str = typer.Option(
        ..., "--type", help="Doc type: adr, api_contract, schema, runbook, context."
    ),
    title: str = typer.Option(..., help="Document title."),
    content: str | None = typer.Option(None, help="Document content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read content from (- for stdin)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a document to the knowledge base."""
    body = _read_content(content, content_file)
    payload = {
        "task_id": task,
        "doc_type": doc_type,
        "title": title,
        "content": body,
    }

    if dry_run:
        preview = {**payload, "content": truncate(body, 200)}
        render(
            {"dry_run": True, "would_create": preview},
            lambda d: f"Would create {doc_type} '{title}' for task {task}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.post("/kb/", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"created {d.get('doc_type', '')} document\n"
                f"id: {d.get('id', '')}\n"
                f"title: {d.get('title', '')}\n"
                f"version: {d.get('version', 1)}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("list")
def list_docs(
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List knowledge base documents."""
    client = get_client()
    params: dict = {}
    if task:
        params["task_id"] = task
    if doc_type:
        params["doc_type"] = doc_type
    params["limit"] = limit

    try:
        data = client.get("/kb/", **params)
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []

        def fmt(items: list) -> str:
            headers = ["ID", "TYPE", "TITLE", "VERSION", "CREATED"]
            rows = [
                [
                    str(d.get("id", ""))[:12],
                    d.get("doc_type", ""),
                    d.get("title", "")[:40],
                    f"v{d.get('version', 1)}",
                    str(d.get("created_at", ""))[:10],
                ]
                for d in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    doc_id: str = typer.Argument(help="Document ID."),
    full: bool = typer.Option(False, "--full", help="Show full content."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a KB document. Default truncates content; use --full for complete."""
    client = get_client()
    try:
        data = client.get(f"/kb/{doc_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        if not full and isinstance(data.get("content"), str):
            data["content"] = truncate(data["content"])

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"type: {d.get('doc_type', '')}",
                f"title: {d.get('title', '')}",
                f"version: v{d.get('version', 1)}",
                f"task_id: {d.get('task_id', '')}",
                f"created: {d.get('created_at', '')}",
                "",
                d.get("content", ""),
            ]
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def search(
    query: str = typer.Argument(help="Search query."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search knowledge base documents by title and content."""
    client = get_client()
    params: dict = {"q": query, "limit": limit}
    if doc_type:
        params["doc_type"] = doc_type
    if task:
        params["task_id"] = task

    try:
        data = client.get("/kb/search", **params)
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []

        def fmt(items: list) -> str:
            headers = ["ID", "TYPE", "TITLE", "VERSION"]
            rows = [
                [
                    str(d.get("id", ""))[:12],
                    d.get("doc_type", ""),
                    d.get("title", "")[:45],
                    f"v{d.get('version', 1)}",
                ]
                for d in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def update(
    doc_id: str = typer.Argument(help="Document ID to update."),
    title: str | None = typer.Option(None, help="New title."),
    content: str | None = typer.Option(None, help="New content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read new content from (- for stdin)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Update a KB document. Bumps version on content change."""
    payload: dict = {}
    if title:
        payload["title"] = title
    if content or content_file:
        payload["content"] = _read_content(content, content_file)

    if not payload:
        from autonomous_agent_builder.cli.output import error
        error("Error: provide --title, --content, or --content-file")
        sys.exit(2)

    if dry_run:
        render(
            {"dry_run": True, "doc_id": doc_id, "would_update": payload},
            lambda d: f"Would update document {doc_id}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.put(f"/kb/{doc_id}", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"updated document {doc_id}\n"
                f"title: {d.get('title', '')}\n"
                f"version: v{d.get('version', 1)}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
