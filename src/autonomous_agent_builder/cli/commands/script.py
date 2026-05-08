"""Script commands — list and run pre-built scripts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.project_discovery import find_agent_builder_dir

app = typer.Typer(help="Script library — pre-built agent scripts.")

EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_INVALID_USAGE = 2


def _package_scripts_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "embedded" / "scripts"


def _script_executor_candidates(project_scripts_dir: Path):
    from autonomous_agent_builder.embedded.scripts import ScriptExecutor

    dirs = [project_scripts_dir, _package_scripts_dir()]
    seen: set[Path] = set()
    for scripts_dir in dirs:
        resolved = scripts_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield ScriptExecutor(scripts_dir)


@app.command("list")
def list_scripts(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all available scripts in the script library."""
    # Find .agent-builder directory
    agent_builder_dir = find_agent_builder_dir()
    if agent_builder_dir is None:
        typer.echo(
            "Error: Not in an initialized agent builder project.\n"
            "Hint: Run 'builder init' to initialize the project.",
            err=True,
        )
        sys.exit(EXIT_GENERAL_ERROR)
    
    scripts_dir = agent_builder_dir / "scripts"
    
    # Check if scripts directory exists
    if not scripts_dir.exists():
        typer.echo(
            f"Error: Scripts directory not found at {scripts_dir}\n"
            "Hint: The project may not be properly initialized.",
            err=True,
        )
        sys.exit(EXIT_GENERAL_ERROR)
    
    try:
        script_names = sorted(
            {
                script_name
                for executor in _script_executor_candidates(scripts_dir)
                for script_name in executor.discover_scripts()
            }
        )
        scripts_info = []
        for script_name in script_names:
            script = None
            for executor in _script_executor_candidates(scripts_dir):
                script = executor.load_script(script_name)
                if script:
                    break
            if script:
                scripts_info.append({
                    "name": script.name,
                    "description": script.description.strip().split('\n')[0],  # First line only
                })
        
        def fmt(items: list) -> str:
            if not items:
                return "No scripts found."
            
            lines = ["Available scripts:"]
            for item in items:
                lines.append(f"  {item['name']:<20} {item['description']}")
            return "\n".join(lines)
        
        render(scripts_info, fmt, use_json=json_output)
        sys.exit(EXIT_SUCCESS)
        
    except Exception as e:
        typer.echo(f"Error: Failed to list scripts: {str(e)}", err=True)
        sys.exit(EXIT_GENERAL_ERROR)


@app.command("run")
def run_script(
    script_name: str = typer.Argument(help="Name of the script to run."),
    args_json: str = typer.Option(
        "{}",
        "--args",
        help="Script arguments as JSON string (e.g., '{\"key\": \"value\"}').",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Execute a script with the provided arguments.
    
    Examples:
        builder script run create_feature --args '{"project_id": "123", "title": "New Feature"}'
        builder script run update_dashboard --args '{"event_type": "board_update", "data": {}}' --json
    """
    # Find .agent-builder directory
    agent_builder_dir = find_agent_builder_dir()
    if agent_builder_dir is None:
        typer.echo(
            "Error: Not in an initialized agent builder project.\n"
            "Hint: Run 'builder init' to initialize the project.",
            err=True,
        )
        sys.exit(EXIT_GENERAL_ERROR)
    
    scripts_dir = agent_builder_dir / "scripts"
    db_name = str((agent_builder_dir / "agent_builder").resolve())
    
    # Parse arguments
    try:
        args = json.loads(args_json)
        if not isinstance(args, dict):
            typer.echo(
                "Error: Arguments must be a JSON object.\n"
                "Hint: Use --args '{\"key\": \"value\"}'",
                err=True,
            )
            sys.exit(EXIT_INVALID_USAGE)
    except json.JSONDecodeError as e:
        typer.echo(
            f"Error: Invalid JSON in arguments: {str(e)}\n"
            "Hint: Use --args '{\"key\": \"value\"}'",
            err=True,
        )
        sys.exit(EXIT_INVALID_USAGE)
    
    # Execute script
    try:
        from autonomous_agent_builder.embedded.scripts import ScriptExecutor
        from autonomous_agent_builder.db import session as db_session

        os.environ["DB_NAME"] = db_name
        db_session._engine = None
        db_session._session_factory = None

        result = {
            "success": False,
            "data": None,
            "error": f"Script '{script_name}' not found or invalid",
        }
        for executor in _script_executor_candidates(scripts_dir):
            result = executor.execute_script(script_name, args)
            if result["success"] or result["error"] != f"Script '{script_name}' not found or invalid":
                break
        
        def fmt(r: dict) -> str:
            if r["success"]:
                output = "Success"
                if r["data"] is not None:
                    output += f"\n{json.dumps(r['data'], indent=2)}"
                return output
            else:
                output = "Error"
                if r["error"]:
                    output += f": {r['error']}"
                return output
        
        render(result, fmt, use_json=json_output)
        
        # Exit with appropriate code
        if result["success"]:
            sys.exit(EXIT_SUCCESS)
        else:
            sys.exit(EXIT_GENERAL_ERROR)
        
    except Exception as e:
        typer.echo(f"Error: Script execution failed: {str(e)}", err=True)
        sys.exit(EXIT_GENERAL_ERROR)
