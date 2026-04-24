"""Builder context command — task bootstrap profiles."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.cli.client import EXIT_SUCCESS
from autonomous_agent_builder.cli.output import emit_error, render

CONTEXT_PROFILES: dict[str, dict[str, object]] = {
    "repo-init": {
        "title": "Repo initialization",
        "summary": "Prepare a repository so builder can manage tasks, approvals, and repo-local knowledge.",
        "commands": [
            "builder init",
            "builder --json doctor",
            "builder start --port 9876",
            "builder map",
        ],
        "success_criteria": [
            ".agent-builder/ exists",
            "local dashboard/API responds on the chosen port",
            "initial project and memory surfaces are discoverable",
        ],
    },
    "system-docs": {
        "title": "System docs",
        "summary": "Extract seed system docs into `.agent-builder/knowledge/system-docs` and validate the output.",
        "commands": [
            "builder knowledge contract --type system-docs",
            "builder knowledge extract",
            "builder knowledge summary <doc>",
            "builder knowledge validate",
        ],
        "success_criteria": [
            "expected seed system docs are present",
            "quality gate or lint passes",
            "agents can search and summarize the extracted docs",
        ],
    },
    "task-dispatch": {
        "title": "Task dispatch",
        "summary": "Inspect the active pipeline state, then dispatch a task through the SDLC stages.",
        "commands": [
            "builder map",
            "builder board show",
            "builder backlog task status <task-id>",
            "builder backlog task dispatch <task-id> --yes",
        ],
        "success_criteria": [
            "task moves into the expected phase",
            "gate results and approvals remain inspectable",
        ],
    },
    "verification": {
        "title": "Verification",
        "summary": "Use builder's gate and metrics surfaces to verify task health after execution.",
        "commands": [
            "builder quality-gate quality-gates",
            "builder backlog task status <task-id>",
            "builder backlog task show <task-id> --full",
            "builder metrics show",
        ],
        "success_criteria": [
            "gate pass/fail state is visible",
            "agent runs and cost metrics are inspectable",
            "follow-up action is clear when verification fails",
        ],
    },
}


def context_command(
    task: str = typer.Argument(..., help="Task profile: repo-init, system-docs, task-dispatch, verification."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Resolve the recommended builder commands for a known task profile."""
    profile = CONTEXT_PROFILES.get(task)
    if not profile:
        emit_error(
            "Unknown context profile",
            code="invalid_context_profile",
            hint="builder context --help",
            detail={
                "query": task,
                "valid_profiles": sorted(CONTEXT_PROFILES),
            },
            exit_code=2,
            use_json=json,
        )
        sys.exit(2)

    payload = {"task": task, **profile, "next_step": profile["commands"][0]}

    def fmt(data: dict[str, object]) -> str:
        lines = [
            str(data["title"]),
            "",
            str(data["summary"]),
            "",
            "Commands:",
        ]
        lines.extend(f"  - {command}" for command in data["commands"])
        lines.append("")
        lines.append("Success criteria:")
        lines.extend(f"  - {criterion}" for criterion in data["success_criteria"])
        lines.append("")
        lines.append(f"Next: {data['next_step']}")
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)
