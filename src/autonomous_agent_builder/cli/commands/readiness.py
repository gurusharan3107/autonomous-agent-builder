"""Readiness CLI for Day-0 autonomous builder preconditions."""

from __future__ import annotations

from pathlib import Path
import sys

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
            f"  - {item.get('code')}: {item.get('message')}"
            for item in status["blocking_reasons"]
        )
    if status["invalidated_by"]:
        lines.append(f"invalidated_by: {', '.join(status['invalidated_by'])}")
    if status["next"]:
        first = status["next"][0]
        lines.append(f"next: {first.get('command', '')}")
    return "\n".join(lines)


@app.command()
def assess(
    project_root: Path | None = typer.Option(
        None, "--project-root", help="Project root to assess."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Recompute readiness from local project state and persist readiness.json."""
    root = _resolve_project_root(project_root)
    payload = assess_readiness(root, write=True)
    exit_code = readiness_exit_code(payload)
    payload = {
        **payload,
        "ok": exit_code == 0,
        "status": "ok" if exit_code == 0 else payload["state"],
        "code": payload["state"],
        "exit_code": exit_code,
    }
    render(payload, _format, use_json=json)
    sys.exit(exit_code)


@app.command()
def status(
    project_root: Path | None = typer.Option(
        None, "--project-root", help="Project root to inspect."
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Read persisted readiness and report stale or missing assessments."""
    root = _resolve_project_root(project_root)
    payload = load_readiness_status(root)
    exit_code = readiness_exit_code(payload)
    payload = {
        **payload,
        "ok": exit_code == 0,
        "status": "ok" if exit_code == 0 else payload["state"],
        "code": payload["state"],
        "exit_code": exit_code,
    }
    render(payload, _format, use_json=json)
    sys.exit(exit_code)
