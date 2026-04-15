"""Board command — pipeline status view."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import format_status, render

app = typer.Typer(help="Task pipeline board.")


@app.command("show")
def show(
    limit: int = typer.Option(50, help="Max tasks per section."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show the task pipeline board — Pending | Active | Review | Done | Blocked."""
    client = get_client()
    try:
        data = client.get("/dashboard/board")
    except AabApiError as e:
        handle_api_error(e)
    else:
        # Apply limit per section
        for section in ("pending", "active", "review", "done", "blocked"):
            if section in data and isinstance(data[section], list):
                data[section] = data[section][:limit]

        def fmt(d: dict) -> str:
            sections = []
            for section in ("pending", "active", "review", "done", "blocked"):
                items = d.get(section, [])
                if not items:
                    continue
                header = f"--- {section.upper()} ({len(items)}) ---"
                lines = [header]
                for task in items:
                    cost = task.get("cost_usd") or task.get("total_cost") or 0
                    line = (
                        f"  {str(task.get('id', ''))[:12]}  "
                        f"{task.get('title', '')[:35]}  "
                        f"{format_status(task.get('status', ''))}  "
                        f"${cost:.2f}"
                    )
                    if task.get("blocked_reason"):
                        line += f"  [{task['blocked_reason'][:30]}]"
                    lines.append(line)
                sections.append("\n".join(lines))
            return "\n\n".join(sections) if sections else "(board is empty)"

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
