"""Metrics command — cost, tokens, gate pass rate."""

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

app = typer.Typer(help="Project metrics and cost tracking.")


@app.command("show")
def show(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show project metrics — cost, tokens, runs, gate pass rate."""
    client = get_client()
    try:
        data = client.get("/dashboard/metrics")
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            lines = [
                "--- METRICS ---",
                f"total_cost:      ${d.get('total_cost', 0):.2f}",
                f"total_tokens:    {d.get('total_tokens', 0):,}",
                f"total_runs:      {d.get('total_runs', 0)}",
                f"gate_pass_rate:  {d.get('gate_pass_rate', 0):.1%}",
            ]
            runs = d.get("runs", [])
            if runs:
                lines.append(f"\n--- RECENT RUNS ({min(len(runs), 5)}) ---")
                headers = ["AGENT", "COST", "TOKENS", "DURATION", "STATUS"]
                rows = [
                    [
                        r.get("agent_name", "")[:15],
                        f"${r.get('cost_usd', 0):.2f}",
                        str(r.get("tokens_input", 0) + r.get("tokens_output", 0)),
                        f"{r.get('duration_ms', 0)}ms",
                        r.get("status", ""),
                    ]
                    for r in runs[:5]
                ]
                lines.append(table(headers, rows))
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
