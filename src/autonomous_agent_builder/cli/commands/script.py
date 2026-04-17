"""Script commands — list and run pre-built scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.project_discovery import find_agent_builder_dir

app = typer.Typer(help="Script library — pre-built agent scripts.")

EXIT_SUCCESS = 0
EXIT_GENERAL_ERROR = 1
EXIT_INVALID_USAGE = 2


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
    
    # Import executor to discover scripts
    try:
        from autonomous_agent_builder.embedded.scripts import ScriptExecutor
        
        executor = ScriptExecutor(scripts_dir)
        script_names = executor.discover_scripts()
        
        # Load each script to get its description
        scripts_info = []
        for script_name in script_names:
            script = executor.load_script(script_name)
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
        
        executor = ScriptExecutor(scripts_dir)
        result = executor.execute_script(script_name, args)
        
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
