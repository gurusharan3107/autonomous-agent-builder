"""Metrics command — bounded verification and cost state."""

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
from autonomous_agent_builder.cli.local_fallback import load_local_metrics
from autonomous_agent_builder.cli.output import render, table

app = typer.Typer(
    help=(
        "Cost and performance metrics.\n\n"
        "Start here:\n"
        "  builder metrics show --json\n"
        "  builder backlog run summary <query> --json\n"
        "  builder backlog task status <task-id> --json\n"
    )
)


def _compact_run(run: dict) -> dict:
    return {
        "agent_name": run.get("agent_name", ""),
        "status": run.get("status", ""),
        "cost_usd": run.get("cost_usd", 0),
        "tokens": run.get("tokens_input", 0) + run.get("tokens_output", 0),
        "duration_ms": run.get("duration_ms", 0),
    }


@app.command("show")
def show(
    full: bool = typer.Option(False, "--full", help="Include complete run payloads in JSON output."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show project metrics — cost, tokens, runs, gate pass rate."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/dashboard/metrics")
        except BuilderConnectivityError:
            data = load_local_metrics()
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        payload = dict(data) if isinstance(data, dict) else {"raw": data}
        payload.setdefault(
            "summary",
            {
                "total_cost": payload.get("total_cost", 0),
                "total_tokens": payload.get("total_tokens", 0),
                "total_runs": payload.get("total_runs", 0),
                "gate_pass_rate": payload.get("gate_pass_rate", 0),
            },
        )
        payload.setdefault("next_step", "builder backlog run summary <query> --json")
        if json and not full:
            runs = payload.get("runs", [])
            compact_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"runs", "raw"}
            }
            compact_payload["run_count"] = len(runs) if isinstance(runs, list) else 0
            compact_payload["recent_runs"] = (
                [_compact_run(run) for run in runs[:5]] if isinstance(runs, list) else []
            )
            payload = compact_payload

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
            lines.append(f"\nNext: {d.get('next_step', '')}")
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
