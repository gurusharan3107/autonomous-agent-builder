"""Approval commands — compact discovery, summary, and exact reads."""

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
        "Approval gates and decisions.\n\n"
        "Start here:\n"
        "  builder backlog approval list --json\n"
        "  builder backlog approval search <query> --json\n"
        "  builder backlog approval summary <query> --json\n"
    )
)


def _approval_list(client, *, task: str | None = None) -> list[dict[str, Any]]:
    data = client.get(f"/tasks/{task}/approvals") if task else client.get("/approval-gates")
    return data if isinstance(data, list) else []


def _approval_compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("gate_type", "")),
        "doc_type": "approval",
        "status": str(item.get("status", "")),
        "preview": make_preview(item, preview_keys=("task_id",), max_chars=90),
    }


def _approval_resolution(query: str, client, *, task: str | None = None) -> RetrievalResolution:
    items = _approval_list(client, task=task)
    resolution = resolve_collection_item(
        query,
        items,
        id_keys=("id", "task_id"),
        text_keys=("gate_type", "status"),
        suggestion_id_key="id",
        suggestion_label_key="gate_type",
    )
    if resolution is None:
        return RetrievalResolution(item={}, matched_on="", suggestions=[])
    if resolution.item:
        return RetrievalResolution(
            item=client.get(f"/dashboard/approvals/{resolution.item['id']}"),
            matched_on=resolution.matched_on,
            suggestions=resolution.suggestions,
        )
    return resolution


def _approval_lookup_error(query: str, resolution: RetrievalResolution, *, use_json: bool) -> None:
    emit_error(
        f"Approval gate not found: {query}",
        code="not_found",
        hint=not_found_hint(
            query,
            search_command=f'builder backlog approval search "{query}" --json',
            suggestions=resolution.suggestions,
        ),
        detail={"query": query, "suggestions": resolution.suggestions},
        use_json=use_json,
    )
    sys.exit(1)


@app.command("list")
def list_approvals(
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List approval gates for a task or the whole project."""
    client = get_client(use_json=json)
    try:
        items = _approval_list(client, task=task)
        if status:
            items = [a for a in items if a.get("status") == status]
        compact = [_approval_compact(item) for item in items]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "GATE TYPE", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], format_status(row["status"]), row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload("list", compact, next_step="builder backlog approval summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Approval query."),
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search approval gates by ID, task, type, or status."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        items = _approval_list(client, task=task)
        if status:
            items = [a for a in items if a.get("status") == status]
        matches = []
        for item in items:
            resolution = resolve_collection_item(
                query,
                [item],
                id_keys=("id", "task_id"),
                text_keys=("gate_type", "status"),
                suggestion_id_key="id",
                suggestion_label_key="gate_type",
            )
            if resolution and resolution.item:
                matches.append(item)
        compact = [_approval_compact(item) for item in matches[:limit]]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "GATE TYPE", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], format_status(row["status"]), row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload(query, compact, next_step="builder backlog approval summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Approval gate ID or natural-language query."),
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded approval overview."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        resolution = _approval_resolution(query, client, task=task)
        if not resolution.item:
            _approval_lookup_error(query, resolution, use_json=json)
        item = resolution.item
        payload = {
            "id": item.get("gate_id", ""),
            "title": item.get("gate_type", ""),
            "doc_type": "approval",
            "matched_on": resolution.matched_on,
            "status": item.get("gate_status", ""),
            "summary": "\n".join(
                [
                    f"task: {item.get('task_title', '')}",
                    f"feature: {item.get('feature_title', '')}",
                    f"project: {item.get('project_name', '')}",
                    f"thread_entries: {len(item.get('thread', []))}",
                ]
            ),
            "next_step": f"builder backlog approval show {item.get('gate_id', '')} --json",
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
    gate_parts: list[str] = typer.Argument(help="Approval gate ID or natural-language query."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show approval gate details with thread."""
    query = join_query_parts(gate_parts)
    client = get_client(use_json=json)
    try:
        resolution = _approval_resolution(query, client)
        if not resolution.item:
            _approval_lookup_error(query, resolution, use_json=json)
        data = {**resolution.item, "matched_on": resolution.matched_on}
        data["next_step"] = f"builder backlog approval summary {data.get('gate_id', '')} --json"

        def fmt(d: dict) -> str:
            lines = [
                f"gate_id: {d.get('gate_id', '')}",
                f"gate_type: {d.get('gate_type', '')}",
                f"gate_status: {format_status(d.get('gate_status', ''))}",
                f"task: {d.get('task_title', '')} ({d.get('task_status', '')})",
                f"feature: {d.get('feature_title', '')}",
                f"project: {d.get('project_name', '')}",
                f"matched_on: {d.get('matched_on', '')}",
            ]
            thread = d.get("thread", [])
            if thread:
                lines.append(f"\n--- THREAD ({len(thread)}) ---")
                for entry in thread[:10]:
                    role = entry.get("role", "")
                    author = entry.get("author") or entry.get("agent_name", "")
                    content = truncate(entry.get("content", ""), 300)
                    lines.append(f"  [{role}] {author}: {content}")
            lines.append(f"\nNext: {d.get('next_step', '')}")
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def submit(
    gate_id: str = typer.Argument(help="Approval gate ID."),
    decision: str = typer.Option(
        ..., help="Decision: approve, reject, override, request_changes."
    ),
    email: str = typer.Option(..., help="Approver email."),
    comment: str = typer.Option("", help="Comment."),
    reason: str = typer.Option("", help="Reason for decision."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Submit an approval decision."""
    valid = {"approve", "reject", "override", "request_changes"}
    if decision not in valid:
        from autonomous_agent_builder.cli.output import error
        error(f"Error: decision must be one of {valid}")
        sys.exit(2)

    if not yes:
        render(
            {"gate_id": gate_id, "decision": decision, "confirmed": False},
            lambda _d: f"Would submit '{decision}' for gate {gate_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client(use_json=json)
    try:
        payload = {
            "approver_email": email,
            "decision": decision,
            "comment": comment,
            "reason": reason,
        }
        data = client.post(f"/approval-gates/{gate_id}/approve", payload)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        def fmt(d: dict) -> str:
            return (
                f"submitted {decision} for gate {gate_id}\n"
                f"status: {d.get('status', '')}\n"
                f"gate_status: {d.get('gate_status', '')}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
