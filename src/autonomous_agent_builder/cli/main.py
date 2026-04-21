"""Root CLI application — `builder` command entry point.

Command shape: builder <resource> <verb>
Help is grouped by job for structured discoverability.
"""

from __future__ import annotations

import sys

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
    script,
    server,
    task,
)
from autonomous_agent_builder.cli.commands.init import init_command
from autonomous_agent_builder.cli.commands.start import start_command

# ── Root app ──
app = typer.Typer(
    name="builder",
    help=(
        "Autonomous SDLC builder CLI — agent-first interface.\n\n"
        "Operates the full software development lifecycle: projects, features, "
        "tasks, quality gates, approvals, knowledge base, and agent memory.\n\n"
        "Start here:\n"
        "  builder init              Initialize agent builder in current repo\n"
        "  builder server health     Check server connectivity\n"
        "  builder board show        View the task pipeline\n"
        "  builder project list      List all projects\n"
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── Project Initialization ──
app.command(name="init", help="Initialize agent builder (start here).")(init_command)
app.command(name="start", help="Start embedded server and dashboard.")(start_command)

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

# ── Script Library ──
app.add_typer(script.app, name="script", help="Script library — pre-built agent scripts.")


def main() -> None:
    """CLI entry point."""
    # Force UTF-8 I/O on all platforms. On Windows the default codec (charmap/cp1252)
    # rejects the Unicode symbols used throughout the CLI (✓, ✅, ❌, ⚠). On macOS/Linux
    # this is a no-op since stdout is already UTF-8. errors="replace" prevents a hard
    # crash if a symbol is somehow unencodable rather than silently dropping output.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    app()


if __name__ == "__main__":
    main()
