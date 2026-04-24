"""Init command — initialize agent builder in current repository.

This command bootstraps a project-level agent builder instance by creating
the .agent-builder/ directory structure with local database, embedded server,
dashboard assets, and script library.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.output import render

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def init_command(
    project_name: str = typer.Option(None, "--project-name", help="Project name."),
    language: str | None = typer.Option(
        None,
        "--language",
        help="Primary language (python, node, java, go, rust). Auto-detected when omitted.",
    ),
    framework: str = typer.Option(None, "--framework", help="Framework (django, fastapi, express, spring)."),
    force: bool = typer.Option(False, "--force", help="Reinitialize existing installation."),
    no_input: bool = typer.Option(False, "--no-input", help="Skip interactive prompts."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Initialize agent builder in current repository.
    
    Creates .agent-builder/ directory with:
    - Local SQLite database
    - Embedded FastAPI server
    - React dashboard assets
    - Pre-built agent scripts
    - Configuration file
    - Knowledge base directory
    
    Examples:
        builder init
        builder init --project-name my-app --language python --framework fastapi
        builder init --no-input --force
    """
    from autonomous_agent_builder.cli.commands.init_impl import run_init
    
    try:
        result = run_init(
            project_name=project_name,
            language=language,
            framework=framework,
            force=force,
            no_input=no_input,
        )
        
        def fmt(d: dict) -> str:
            if d.get("error"):
                return f"Error: {d['error']}\n\nHint: {d.get('hint', '')}"
            
            lines = [
                f"[OK] Initialized agent builder in {d['directory']}",
                f"  Project: {d['project_name']}",
                f"  Language: {d['language']}",
                f"  Framework: {d.get('framework', 'none')}",
                "",
                "Next steps:",
                "  1. builder start          # Start the embedded server and dashboard",
                "  2. Open the dashboard URL # Begin first-run onboarding from the UI",
            ]
            return "\n".join(lines)
        
        render(result, fmt, use_json=json)
        
        if result.get("error"):
            sys.exit(EXIT_FAILURE)
        else:
            sys.exit(EXIT_SUCCESS)
            
    except Exception as e:
        error_result = {
            "error": str(e),
            "hint": "Check that you have write permissions in the current directory.",
        }
        
        def fmt(d: dict) -> str:
            return f"Error: {d['error']}\n\nHint: {d['hint']}"
        
        render(error_result, fmt, use_json=json)
        sys.exit(EXIT_FAILURE)
