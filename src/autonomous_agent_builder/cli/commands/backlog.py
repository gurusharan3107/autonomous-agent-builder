"""Backlog command group — canonical work-planning surface."""

from __future__ import annotations

import typer

from autonomous_agent_builder.cli.commands import approval, feature, project, run, task

app = typer.Typer(
    help=(
        "Backlog planning and execution surfaces.\n"
        "Use this lane for repo-local project, feature, task, approval, and run state.\n\n"
        "Start here:\n"
        "  builder backlog project list --json\n"
        "  builder backlog feature list --project <id> --json\n"
        "  builder backlog task list --json\n"
    )
)

app.add_typer(project.app, name="project", help="Repo-local project scope.")
app.add_typer(feature.app, name="feature", help="Feature backlog and delivery slices.")
app.add_typer(task.app, name="task", help="Task lifecycle and dispatch.")
app.add_typer(approval.app, name="approval", help="Approval gates and decisions.")
app.add_typer(run.app, name="run", help="Agent run history.")
