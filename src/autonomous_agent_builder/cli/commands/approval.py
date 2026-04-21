"""Approval commands — list, show, submit."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_INVALID_USAGE,
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import format_status, render, table, truncate

app = typer.Typer(help="Approval gates and decisions.")


@app.command("list")
def list_approvals(
    task: str = typer.Option(..., "--task", help="Task ID."),
    status: str | None = typer.Option(None, help="Filter by status."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List approval gates for a task."""
    client = get_client()
    try:
        data = client.get(f"/tasks/{task}/approvals")
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []
        if status:
            items = [a for a in items if a.get("status") == status]

        def fmt(items: list) -> str:
            headers = ["ID", "GATE TYPE", "STATUS", "CREATED"]
            rows = [
                [
                    str(a.get("id", ""))[:12],
                    a.get("gate_type", ""),
                    format_status(a.get("status", "")),
                    str(a.get("created_at", ""))[:10],
                ]
                for a in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    gate_id: str = typer.Argument(help="Approval gate ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show approval gate details with thread."""
    client = get_client()
    try:
        data = client.get(f"/dashboard/approvals/{gate_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                f"gate_id: {d.get('gate_id', '')}",
                f"gate_type: {d.get('gate_type', '')}",
                f"gate_status: {format_status(d.get('gate_status', ''))}",
                f"task: {d.get('task_title', '')} ({d.get('task_status', '')})",
                f"feature: {d.get('feature_title', '')}",
                f"project: {d.get('project_name', '')}",
            ]
            thread = d.get("thread", [])
            if thread:
                lines.append(f"\n--- THREAD ({len(thread)}) ---")
                for entry in thread[:10]:
                    role = entry.get("role", "")
                    author = entry.get("author") or entry.get("agent_name", "")
                    content = truncate(entry.get("content", ""), 300)
                    lines.append(f"  [{role}] {author}: {content}")
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
        sys.exit(EXIT_INVALID_USAGE)

    if not yes:
        render(
            {"gate_id": gate_id, "decision": decision, "confirmed": False},
            lambda _d: f"Would submit '{decision}' for gate {gate_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        payload = {
            "approver_email": email,
            "decision": decision,
            "comment": comment,
            "reason": reason,
        }
        data = client.post(f"/approval-gates/{gate_id}/approve", payload)
    except AabApiError as e:
        handle_api_error(e)
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
