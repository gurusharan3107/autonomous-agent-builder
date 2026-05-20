"""Readiness CLI for Day-0 autonomous builder preconditions."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
)
from autonomous_agent_builder.services.readiness import (
    assess_readiness,
    compact_status,
    load_readiness_status,
    readiness_exit_code,
)

app = typer.Typer(no_args_is_help=True)


def _resolve_project_root(project_root: Path | None) -> Path:
    if project_root is not None:
        return project_root.resolve()
    try:
        return find_agent_builder_dir(Path.cwd()).parent
    except ProjectNotFoundError:
        return Path.cwd().resolve()


def _format(payload: dict) -> str:
    status = compact_status(payload)
    lines = [
        f"mode: {status['mode']}",
        f"state: {status['state']}",
        f"can_continue: {str(status['can_continue']).lower()}",
    ]
    if status["blocking_reasons"]:
        lines.append("blocking_reasons:")
        lines.extend(
            f"  - {item.get('code')}: {item.get('message')}" for item in status["blocking_reasons"]
        )
    if status["invalidated_by"]:
        lines.append(f"invalidated_by: {', '.join(status['invalidated_by'])}")
    if status["next"]:
        first = status["next"][0]
        lines.append(f"next: {first.get('command', '')}")
    return "\n".join(lines)


def _compact_readiness_payload(payload: dict, *, exit_code: int) -> dict:
    status = compact_status(payload)
    next_items = status.get("next") or []
    next_step = (
        str(next_items[0].get("command", ""))
        if next_items and isinstance(next_items[0], dict)
        else "builder readiness assess --json"
    )
    state = str(status.get("state", payload.get("state", "unknown")))
    return {
        "mode": status.get("mode", "unknown"),
        "state": state,
        "can_continue": bool(status.get("can_continue")),
        "blocking_reasons": status.get("blocking_reasons", []),
        "invalidated_by": status.get("invalidated_by", []),
        "next": next_items,
        "next_step": next_step,
        "actionable_next": next_step,
        "progressive_disclosure": [
            {
                "when": "recompute readiness from the current workspace",
                "command": "builder readiness assess --json",
            },
            {
                "when": "inspect persisted readiness diagnostics and phase details",
                "command": "builder readiness status --json --full",
            },
            {
                "when": "inspect the canonical Day-0 readiness workflow",
                "command": "workflow --docs-dir docs summary day-0-readiness",
            },
        ],
        "diagnostics": {
            "full_payload_command": "builder readiness status --json --full",
            "contains": ["phase status", "compatibility state", "raw readiness file"],
        },
        "ok": exit_code == 0,
        "status": "ok" if exit_code == 0 else state,
        "code": state,
        "exit_code": exit_code,
    }


@app.command()
def assess(
    project_root: Path | None = typer.Option(
        None, "--project-root", help="Project root to assess."
    ),
    full: bool = typer.Option(False, "--full", help="Include full readiness diagnostics."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Recompute readiness from local project state and persist readiness.json."""
    root = _resolve_project_root(project_root)
    payload = assess_readiness(root, write=True)
    exit_code = readiness_exit_code(payload)
    full_payload = {
        **payload,
        "ok": exit_code == 0,
        "status": "ok" if exit_code == 0 else payload["state"],
        "code": payload["state"],
        "exit_code": exit_code,
    }
    payload = (
        full_payload if full else _compact_readiness_payload(full_payload, exit_code=exit_code)
    )
    render(payload, _format, use_json=json)
    sys.exit(exit_code)


@app.command()
def status(
    project_root: Path | None = typer.Option(
        None, "--project-root", help="Project root to inspect."
    ),
    full: bool = typer.Option(False, "--full", help="Include full readiness diagnostics."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Read persisted readiness and report stale or missing assessments."""
    root = _resolve_project_root(project_root)
    payload = load_readiness_status(root)
    exit_code = readiness_exit_code(payload)
    full_payload = {
        **payload,
        "ok": exit_code == 0,
        "status": "ok" if exit_code == 0 else payload["state"],
        "code": payload["state"],
        "exit_code": exit_code,
    }
    payload = (
        full_payload if full else _compact_readiness_payload(full_payload, exit_code=exit_code)
    )
    render(payload, _format, use_json=json)
    sys.exit(exit_code)
