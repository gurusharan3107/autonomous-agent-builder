"""Board command — bounded pipeline state for active work."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    BuilderConnectivityError,
    get_client,
    handle_api_error,
    request_json,
)
from autonomous_agent_builder.cli.local_fallback import load_local_board
from autonomous_agent_builder.cli.output import format_status, render

app = typer.Typer(
    help=(
        "Task pipeline board.\n\n"
        "Start here:\n"
        "  builder board show --json\n"
        "  builder backlog task status <task-id> --json\n"
        "  builder backlog approval list --task <task-id> --json\n"
    )
)


@app.command("show")
def show(
    limit: int = typer.Option(50, help="Max tasks per section."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show the task pipeline board — Pending | Active | Review | Done | Blocked."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/dashboard/board")
        except BuilderConnectivityError:
            data = load_local_board(limit)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        if "counts" not in data:
            for section in ("pending", "active", "review", "done", "blocked"):
                if section in data and isinstance(data[section], list):
                    data[section] = data[section][:limit]
            data["counts"] = {
                section: len(data.get(section, []))
                for section in ("pending", "active", "review", "done", "blocked")
            }
        data.setdefault("next_step", "builder backlog task status <task-id> --json")

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
            if sections:
                sections.append("\nNext: " + str(d.get("next_step", "")))
                return "\n\n".join(sections)
            return "(board is empty)\n\nNext: builder backlog task list --json"

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
