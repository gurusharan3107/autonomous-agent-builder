"""Run commands — compact discovery, summary, and exact reads."""

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
        "Agent run history.\n\n"
        "Start here:\n"
        "  builder backlog run list --json\n"
        "  builder backlog run search <query> --json\n"
        "  builder backlog run summary <query> --json\n"
    )
)


def _run_list(client, *, task: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    data = client.get(f"/tasks/{task}/runs") if task else client.get("/runs")
    items = data if isinstance(data, list) else []
    return items[:limit] if limit else items


def _run_compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("agent_name", "")),
        "doc_type": "run",
        "status": str(item.get("status", "")),
        "preview": make_preview(item, preview_keys=("error", "stop_reason"), max_chars=100),
    }


def _run_resolution(query: str, client, *, task: str | None = None) -> RetrievalResolution:
    items = _run_list(client, task=task)
    resolution = resolve_collection_item(
        query,
        items,
        id_keys=("id", "task_id", "session_id"),
        text_keys=("agent_name", "status", "stop_reason", "error"),
        suggestion_id_key="id",
        suggestion_label_key="agent_name",
    )
    if resolution is None:
        return RetrievalResolution(item={}, matched_on="", suggestions=[])
    if resolution.item:
        return RetrievalResolution(
            item=client.get(f"/runs/{resolution.item['id']}"),
            matched_on=resolution.matched_on,
            suggestions=resolution.suggestions,
        )
    return resolution


def _run_lookup_error(query: str, resolution: RetrievalResolution, *, use_json: bool) -> None:
    emit_error(
        f"Agent run not found: {query}",
        code="not_found",
        hint=not_found_hint(
            query,
            search_command=f'builder backlog run search "{query}" --json',
            suggestions=resolution.suggestions,
        ),
        detail={"query": query, "suggestions": resolution.suggestions},
        use_json=use_json,
    )
    sys.exit(1)


@app.command("list")
def list_runs(
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List agent runs for a task or the whole project."""
    client = get_client(use_json=json)
    try:
        compact = [_run_compact(item) for item in _run_list(client, task=task, limit=limit)]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "AGENT", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], row["status"], row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload("list", compact, next_step="builder backlog run summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Run query."),
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search runs by ID, task, session, agent, or status."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        items = _run_list(client, task=task)
        matches = []
        for item in items:
            resolution = resolve_collection_item(
                query,
                [item],
                id_keys=("id", "task_id", "session_id"),
                text_keys=("agent_name", "status", "stop_reason", "error"),
                suggestion_id_key="id",
                suggestion_label_key="agent_name",
            )
            if resolution and resolution.item:
                matches.append(item)
        compact = [_run_compact(item) for item in matches[:limit]]

        def fmt(rows: list[dict[str, Any]]) -> str:
            headers = ["ID", "AGENT", "STATUS", "PREVIEW"]
            table_rows = [[row["id"], row["title"], row["status"], row["preview"]] for row in rows]
            return table(headers, table_rows)

        render(
            compact_results_payload(query, compact, next_step="builder backlog run summary <query> --json")
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
    query_parts: list[str] = typer.Argument(help="Run ID or natural-language query."),
    task: str | None = typer.Option(None, "--task", help="Task ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded agent run overview."""
    query = join_query_parts(query_parts)
    client = get_client(use_json=json)
    try:
        resolution = _run_resolution(query, client, task=task)
        if not resolution.item:
            _run_lookup_error(query, resolution, use_json=json)
        item = resolution.item
        payload = {
            "id": item.get("id", ""),
            "title": item.get("agent_name", ""),
            "doc_type": "run",
            "matched_on": resolution.matched_on,
            "status": item.get("status", ""),
            "summary": "\n".join(
                [
                    f"task_id: {item.get('task_id', '')}",
                    f"cost_usd: {item.get('cost_usd', 0)}",
                    f"tokens_total: {item.get('tokens_input', 0) + item.get('tokens_output', 0)}",
                    f"duration_ms: {item.get('duration_ms', 0)}",
                    f"stop_reason: {item.get('stop_reason', '') or ''}",
                ]
            ),
            "next_step": f"builder backlog run show {item.get('id', '')} --json",
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
    run_parts: list[str] = typer.Argument(help="Agent run ID or natural-language query."),
    full: bool = typer.Option(False, "--full", help="Include events timeline."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show agent run details."""
    query = join_query_parts(run_parts)
    client = get_client(use_json=json)
    try:
        resolution = _run_resolution(query, client)
        if not resolution.item:
            _run_lookup_error(query, resolution, use_json=json)
        data = {**resolution.item, "matched_on": resolution.matched_on}
        data["next_step"] = f"builder backlog run summary {data.get('id', '')} --json"

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
                f"matched_on: {d.get('matched_on', '')}",
            ]
            if d.get("error"):
                lines.append(f"error: {truncate(d['error'], 500)}")
            lines.append(f"Next: {d.get('next_step', '')}")
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
