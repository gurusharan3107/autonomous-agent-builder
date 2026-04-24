"""Chat and tool log inspection for the repo-local builder runtime."""

from __future__ import annotations

import json
import sqlite3
import time
import sys
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_INVALID_USAGE, EXIT_SUCCESS
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate
from autonomous_agent_builder.cli.retrieval import compact_results_payload
from autonomous_agent_builder.cli.project_discovery import ProjectNotFoundError, find_agent_builder_dir
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event

app = typer.Typer(
    help=(
        "Inspect repo-local embedded chat logs and tool outcomes.\n\n"
        "Start here:\n"
        "  builder logs --error\n"
        "  builder logs --info --compact\n"
        "  builder logs --session <id>\n"
        "  builder logs --error --follow --ndjson\n"
        "  builder logs --tool mcp__builder__kb_add --json\n"
    )
)

_DEFAULT_TYPES = ("tool_result", "tool_error", "run_error")


def _db_path() -> Path:
    try:
        return find_agent_builder_dir(Path.cwd()).resolve() / "agent_builder.db"
    except ProjectNotFoundError as exc:
        raise RuntimeError(exc.hint or "Initialize this repo with 'builder init' first.") from exc


def _load_rows(
    *,
    session_id: str | None,
    tool_name: str | None,
    event_type: str | None,
    errors_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    db_path = _db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Log database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if session_id:
            resolved_session = session_id
        else:
            row = conn.execute(
                "select id from chat_sessions order by updated_at desc, created_at desc limit 1"
            ).fetchone()
            resolved_session = str(row["id"]) if row else ""

        if not resolved_session:
            return []

        clauses = ["session_id = ?"]
        params: list[Any] = [resolved_session]

        if errors_only:
            clauses.append("event_type in ('tool_error', 'run_error')")
        elif event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        else:
            placeholders = ", ".join("?" for _ in _DEFAULT_TYPES)
            clauses.append(f"event_type in ({placeholders})")
            params.extend(_DEFAULT_TYPES)

        if tool_name:
            clauses.append("json_extract(payload_json, '$.tool_name') = ?")
            params.append(tool_name)

        params.append(max(limit, 1))
        query = (
            "select id, session_id, event_type, status, payload_json, tool_use_id, created_at "
            "from chat_events "
            f"where {' and '.join(clauses)} "
            "order by created_at desc "
            "limit ?"
        )
        rows = conn.execute(query, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"content": payload}
            items.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "tool_use_id": row["tool_use_id"],
                    "created_at": row["created_at"],
                    "payload": payload or {},
                }
            )
        return items
    finally:
        conn.close()


def _render_line(item: dict[str, Any]) -> str:
    payload = item.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"content": str(payload)}
    diagnostic = payload.get("diagnostic")
    if not isinstance(diagnostic, dict):
        diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
    tool_name = str(diagnostic.get("tool_name", "") or payload.get("tool_name", "") or "-")
    summary = truncate(str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 160).replace("\n", " ")
    return f"{str(item.get('created_at', ''))[:19]}  {item.get('event_type', ''):<16}  {tool_name:<28}  {summary}"


def _compact_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"content": str(payload)}
        diagnostic = payload.get("diagnostic")
        if not isinstance(diagnostic, dict):
            diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
        event_type = str(item.get("event_type", ""))
        is_error = event_type in {"tool_error", "run_error"}
        row = {
            "id": item.get("id"),
            "event_type": event_type,
            "created_at": item.get("created_at"),
            "tool_name": diagnostic.get("tool_name", "") or payload.get("tool_name", ""),
            "outcome": diagnostic.get("outcome", ""),
            "summary": diagnostic.get("summary", ""),
        }
        input_focus = diagnostic.get("input_focus", "")
        if input_focus:
            row["input_focus"] = input_focus
        if is_error:
            error_message = diagnostic.get("error_message", "") or diagnostic.get("detail", "")
            if error_message:
                row["error_message"] = error_message
        next_action = diagnostic.get("next_action", "")
        if next_action:
            row["next_action"] = next_action
        compacted.append(row)
    return compacted


def _emit_ndjson(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sys.stdout.write(json.dumps(row, ensure_ascii=True) + "\n")
    sys.stdout.flush()


@app.callback(invoke_without_command=True)
def logs(
    ctx: typer.Context,
    session_id: str | None = typer.Option(None, "--session", help="Chat session ID."),
    tool: str | None = typer.Option(None, "--tool", help="Only show one tool name."),
    event_type: str | None = typer.Option(
        None,
        "--type",
        help="One event type such as tool_result, tool_error, or run_error.",
    ),
    error: bool = typer.Option(False, "--error", help="Only show error events."),
    info: bool = typer.Option(False, "--info", help="Only show non-error tool result events."),
    follow: bool | None = typer.Option(
        None,
        "--follow/--no-follow",
        help="Stream new matching log events. Defaults to on for '--error' in TTY mode.",
    ),
    compact: bool = typer.Option(False, "--compact", help="Trim payloads to the minimum useful fields."),
    ndjson: bool = typer.Option(
        False,
        "--ndjson",
        help="Emit one JSON object per line. Use this for follow/watch style machine streams.",
    ),
    limit: int = typer.Option(5, min=1, max=200, help="Max log entries."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Inspect embedded chat logs for the latest or selected session."""
    if ctx.invoked_subcommand is not None:
        return
    if ndjson and json:
        emit_error(
            "Choose either --json or --ndjson, not both.",
            code="invalid_usage",
            hint="Use --ndjson for line-delimited streams, or --json for one bounded envelope.",
            use_json=True,
        )
        raise typer.Exit(EXIT_INVALID_USAGE)
    if sum(1 for flag in (error, info, bool(event_type)) if flag) > 1:
        emit_error(
            "choose only one log selector",
            code="invalid_input",
            hint="Use one of '--error', '--info', or '--type <event_type>' to narrow the log stream.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_INVALID_USAGE)
    selected_type = "tool_result" if info else event_type
    should_follow = bool(follow) if follow is not None else bool(error and not (json or ndjson) and sys.stdout.isatty())

    try:
        items = _load_rows(
            session_id=session_id,
            tool_name=tool,
            event_type=selected_type,
            errors_only=error,
            limit=limit,
        )
    except FileNotFoundError as exc:
        emit_error(
            str(exc),
            code="not_found",
            hint="Run 'builder start' or initialize the repo so .agent-builder/agent_builder.db exists.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_FAILURE) from exc
    except RuntimeError as exc:
        emit_error(
            str(exc),
            code="project_not_initialized",
            hint="Run 'builder init' in the repo root first.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_FAILURE) from exc

    compact_mode = compact or (json and (error or info))
    rendered_items = _compact_items(items) if compact_mode else items

    def fmt(rows: list[dict[str, Any]]) -> str:
        headers = ["TIME", "TYPE", "TOOL", "SUMMARY", "FOCUS"]
        body: list[list[str]] = []
        for item in rows:
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                payload = {"content": str(payload)}
            diagnostic = payload.get("diagnostic")
            if not isinstance(diagnostic, dict):
                diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
            body.append(
                [
                    str(item.get("created_at", ""))[:19],
                    str(item.get("event_type", "")),
                    str(diagnostic.get("tool_name", "") or payload.get("tool_name", "") or "-"),
                    truncate(str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 120).replace("\n", " "),
                    truncate(str(diagnostic.get("input_focus", "") or "-"), 80).replace("\n", " "),
                ]
            )
        return table(headers, body, max_col_width=60)

    payload = (
        compact_results_payload(
            "logs",
            rendered_items,
            next_step="builder logs --session <id> --compact --json",
        )
        if json and compact_mode
        else rendered_items
    )
    if ndjson:
        _emit_ndjson(rendered_items)
    else:
        render(payload, fmt, use_json=json)
    if should_follow:
        seen_ids = {str(item.get("id", "")) for item in items}
        try:
            while True:
                time.sleep(1.0)
                fresh = _load_rows(
                    session_id=session_id,
                    tool_name=tool,
                    event_type=selected_type,
                    errors_only=error,
                    limit=limit,
                )
                new_items = [item for item in reversed(fresh) if str(item.get("id", "")) not in seen_ids]
                for item in new_items:
                    display_item = _compact_items([item])[0] if compact_mode else item
                    if ndjson:
                        _emit_ndjson([display_item])
                    else:
                        print(_render_line(display_item))
                    seen_ids.add(str(item.get("id", "")))
        except KeyboardInterrupt:
            pass
    raise typer.Exit(EXIT_SUCCESS)
