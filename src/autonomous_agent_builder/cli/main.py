"""Root CLI application — `builder` command entry point.

Command shape: builder <resource> <verb>
Help is grouped by job for structured discoverability.
"""

from __future__ import annotations

import typer

from autonomous_agent_builder.cli.commands import (
    approval,
    board,
    feature,
    gate,
    kb,
    memory,
    metrics,
    project,
    run,
    server,
    task,
)

# ── Root app ──
app = typer.Typer(
    name="builder",
    help=(
        "Autonomous SDLC builder CLI — agent-first interface.\n\n"
        "Operates the full software development lifecycle: projects, features, "
        "tasks, quality gates, approvals, knowledge base, and agent memory.\n\n"
        "Start here:\n"
        "  builder server health     Check server connectivity\n"
        "  builder board show        View the task pipeline\n"
        "  builder project list      List all projects\n"
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── SDLC Operations ──
app.add_typer(project.app, name="project", help="Project CRUD.")
app.add_typer(feature.app, name="feature", help="Feature CRUD.")
app.add_typer(task.app, name="task", help="Task lifecycle and dispatch.")
app.add_typer(gate.app, name="gate", help="Quality gate results.")
app.add_typer(run.app, name="run", help="Agent run history.")
app.add_typer(approval.app, name="approval", help="Approval gates and decisions.")

# ── Dashboard Views ──
app.add_typer(board.app, name="board", help="Task pipeline board.")
app.add_typer(metrics.app, name="metrics", help="Cost and performance metrics.")

# ── Server Management ──
app.add_typer(server.app, name="server", help="Server management (start here).")

# ── Knowledge Base ──
app.add_typer(kb.app, name="kb", help="Knowledge base — agent-written docs.")

# ── Memory ──
app.add_typer(memory.app, name="memory", help="Project memory — decisions and patterns.")


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
