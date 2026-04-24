"""Task commands — compact discovery, summary, and exact reads."""

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
from autonomous_agent_builder.cli.output import emit_error, format_status, render, table, truncate
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
        "Task lifecycle and dispatch.\n\n"
        "Start here:\n"
        "  builder backlog task list --json\n"
        "  builder backlog task search <query> --json\n"
        "  builder backlog task summary <query> --json\n"
    )
)


def _next_task_command(task_id: str, status: str | None) -> str:
    if status == "failed":
        return f"builder backlog task recover {task_id} --yes --json"
    return f"builder backlog task status {task_id} --json"


def _task_list(client, *, feature: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    if feature:
        data = client.get(f"/features/{feature}/tasks")
    else:
        data = client.get("/tasks")
    items = data if isinstance(data, list) else []
    return items[:limit] if limit else items


def _task_compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("title", "")),
        "doc_type": "task",
        "status": str(item.get("status", "")),
        "preview": make_preview(item, preview_keys=("description", "blocked_reason"), max_chars=120),
    }


def _task_resolution(query: str, client, *, feature: str | None = None) -> RetrievalResolution:
    items = _task_list(client, feature=feature)
    resolution = resolve_collection_item(
        query,
        items,
        id_keys=("id",),
        text_keys=("title", "description", "status"),
        suggestion_id_key="id",
        suggestion_label_key="title",
    )
    if resolution is None:
        return RetrievalResolution(item={}, matched_on="", suggestions=[])
    if resolution.item:
        return RetrievalResolution(
            item=client.get(f"/tasks/{resolution.item['id']}"),
            matched_on=resolution.matched_on,
            suggestions=resolution.suggestions,
        )
    return resolution


def _task_lookup_error(query: str, resolution: RetrievalResolution, *, use_json: bool) -> None:
    emit_error(
        f"Task not found: {query}",
        code="not_found",
        hint=not_found_hint(
            query,
            search_command=f'builder backlog task search "{query}" --json',
            suggestions=resolution.suggestions,
        ),
        detail={"query": query, "suggestions": resolution.suggestions},
        use_json=use_json,
    )
    sys.exit(1)


@app.command("list")
def list_tasks(
    feature: str | None = typer.Option(None, "--feature", help="Feature ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(50, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List tasks for a feature or the whole project."""
    client = get_client(use_json=json)
    try:
        items = _task_list(client, feature=feature)
        if status:
            items = [item for item in items if item.get("status") == status]
        items = items[:limit]
        compact = [_task_compact(item) for item in items]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "TITLE", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], format_status(row["status"]), row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload("list", compact, next_step="builder backlog task summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Task query."),
    feature: str | None = typer.Option(None, "--feature", help="Feature ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search tasks by ID, title, description, or status."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        items = _task_list(client, feature=feature)
        if status:
            items = [item for item in items if item.get("status") == status]
        matches = []
        for item in items:
            resolution = resolve_collection_item(
                query,
                [item],
                id_keys=("id",),
                text_keys=("title", "description", "status"),
                suggestion_id_key="id",
                suggestion_label_key="title",
            )
            if resolution and resolution.item:
                matches.append(item)
        compact = [_task_compact(item) for item in matches[:limit]]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "TITLE", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], format_status(row["status"]), row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload(query, compact, next_step="builder backlog task summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Task ID or natural-language query."),
    feature: str | None = typer.Option(None, "--feature", help="Feature ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded task overview before loading full details."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        resolution = _task_resolution(query, client, feature=feature)
        if not resolution.item:
            _task_lookup_error(query, resolution, use_json=json)
        item = resolution.item
        payload = {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "doc_type": "task",
            "matched_on": resolution.matched_on,
            "status": item.get("status", ""),
            "summary": "\n".join(
                [
                    f"description: {truncate(str(item.get('description', '') or ''), 220)}",
                    f"complexity: {item.get('complexity', '')}",
                    f"retry_count: {item.get('retry_count', 0)}",
                    f"blocked_reason: {item.get('blocked_reason', '') or ''}",
                ]
            ),
            "next_step": f"builder backlog task show {item.get('id', '')} --json",
        }

        def fmt(data: dict[str, Any]) -> str:
            return (
                f"{data['title']}\n"
                f"id: {data['id']}\n"
                f"status: {format_status(data['status'])}\n"
                f"matched_on: {data['matched_on']}\n\n"
                f"{data['summary']}\n\n"
                f"Next: {data['next_step']}"
            )

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    task_parts: list[str] = typer.Argument(help="Task ID or natural-language query."),
    full: bool = typer.Option(False, "--full", help="Include full details."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show task details. Use --full for gate results and agent runs."""
    query = join_query_parts(task_parts)
    client = get_client(use_json=json)
    try:
        resolution = _task_resolution(query, client)
        if not resolution.item:
            _task_lookup_error(query, resolution, use_json=json)
        data = resolution.item
        if full:
            data["gate_results"] = client.get(f"/tasks/{data['id']}/gates")
            data["agent_runs"] = client.get(f"/tasks/{data['id']}/runs")
        data["matched_on"] = resolution.matched_on
        data["next_step"] = _next_task_command(str(data["id"]), data.get("status"))

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"title: {d.get('title', '')}",
                f"status: {format_status(d.get('status', ''))}",
                f"description: {truncate(d.get('description', '') or '', 500)}",
                f"complexity: {d.get('complexity', '')}",
                f"retry_count: {d.get('retry_count', 0)}",
                f"blocked_reason: {d.get('blocked_reason', '') or ''}",
                f"matched_on: {d.get('matched_on', '')}",
            ]
            if full and d.get("gate_results"):
                lines.append(f"gate_results: {len(d['gate_results'])}")
            if full and d.get("agent_runs"):
                lines.append(f"agent_runs: {len(d['agent_runs'])}")
            lines.append(f"Next: {d.get('next_step', '')}")
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
    client = get_client(use_json=json)
    try:
        data = client.get(f"/tasks/{task_id}")
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        summary = {
            "id": data.get("id"),
            "status": data.get("status"),
            "retry_count": data.get("retry_count", 0),
            "blocked_reason": data.get("blocked_reason"),
            "capability_limit_reason": data.get("capability_limit_reason"),
            "next_step": (
                f"builder backlog task recover {task_id} --yes --json"
                if data.get("status") == "failed"
                else f"builder backlog task show {task_id} --json"
            ),
        }

        def fmt(d: dict) -> str:
            line = f"{d['id'][:12]}  {format_status(d.get('status', ''))}"
            if d.get("retry_count", 0) > 0:
                line += f"  retries={d['retry_count']}"
            if d.get("blocked_reason"):
                line += f"  blocked: {d['blocked_reason']}"
            line += f"\nNext: {d['next_step']}"
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
    """Dispatch a task through the SDLC pipeline."""
    if not yes:
        info = {"task_id": task_id, "action": "dispatch", "confirmed": False}
        render(
            info,
            lambda d: f"Would dispatch task {task_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client(use_json=json)
    try:
        data = client.post("/dispatch", {"task_id": task_id})
    except AabApiError as e:
        handle_api_error(e, use_json=json)
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


@app.command()
def recover(
    task_id: str = typer.Argument(help="Failed task ID to reset to pending."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation and recover the failed task."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Reset a failed task to pending so it can be dispatched again."""
    if not yes:
        info = {"task_id": task_id, "action": "recover", "confirmed": False}
        render(
            info,
            lambda d: f"Would recover failed task {task_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client(use_json=json)
    try:
        data = client.post(f"/tasks/{task_id}/recover")
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        def fmt(d: dict) -> str:
            return (
                f"recovered task {task_id}\n"
                f"status: {d.get('status', '')}\n"
                f"previous_status: {d.get('previous_status', '')}\n"
                f"current_status: {d.get('current_status', '')}\n"
                f"next_step: {d.get('next_step', '')}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
