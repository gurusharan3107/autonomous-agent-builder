"""Project directory discovery utilities.

Searches for .agent-builder/ directory in current and parent directories
to support running CLI commands from any subdirectory within a project.
"""

from __future__ import annotations

import sys
from pathlib import Path


class ProjectNotFoundError(Exception):
    """Raised when .agent-builder/ directory cannot be found."""
    
    def __init__(self, message: str, hint: str):
        self.message = message
        self.hint = hint
        super().__init__(message)


def _is_repo_boundary(path: Path) -> bool:
    """Return True when path is a repository boundary for upward discovery.

    Today we stop at VCS roots so a fresh cloned repo does not inherit a
    `.agent-builder/` directory from a parent temp directory.
    """
    return any((path / marker).exists() for marker in (".git", ".hg"))


def find_agent_builder_dir(start_path: Path | None = None) -> Path:
    """Search for .agent-builder/ directory in current and parent directories.
    
    Searches from the starting path up to the filesystem root, looking for
    a .agent-builder/ directory. This allows CLI commands to be run from
    any subdirectory within a project.
    
    Args:
        start_path: Starting directory (defaults to current working directory)
        
    Returns:
        Path to .agent-builder/ directory
        
    Raises:
        ProjectNotFoundError: If .agent-builder/ directory not found
        
    Examples:
        >>> agent_builder_dir = find_agent_builder_dir()
        >>> db_path = agent_builder_dir / "agent_builder.db"
    """
    if start_path is None:
        start_path = Path.cwd()
    
    current = start_path.resolve()
    
    # Search up to filesystem root
    while True:
        agent_builder_dir = current / ".agent-builder"
        
        if agent_builder_dir.exists() and agent_builder_dir.is_dir():
            return agent_builder_dir

        if _is_repo_boundary(current):
            raise ProjectNotFoundError(
                message="No .agent-builder/ directory found in this repository",
                hint="Run 'builder init' to initialize agent builder in this repository",
            )
        
        # Check if we've reached the filesystem root
        parent = current.parent
        if parent == current:
            # Reached root without finding .agent-builder/
            raise ProjectNotFoundError(
                message="No .agent-builder/ directory found",
                hint="Run 'builder init' to initialize agent builder in this repository",
            )
        
        current = parent


def get_project_root(start_path: Path | None = None) -> Path:
    """Get the project root directory (parent of .agent-builder/).
    
    Args:
        start_path: Starting directory (defaults to current working directory)
        
    Returns:
        Path to project root directory
        
    Raises:
        ProjectNotFoundError: If .agent-builder/ directory not found
    """
    agent_builder_dir = find_agent_builder_dir(start_path)
    return agent_builder_dir.parent


def get_database_path(start_path: Path | None = None) -> Path:
    """Get the path to the local SQLite database.
    
    Args:
        start_path: Starting directory (defaults to current working directory)
        
    Returns:
        Path to agent_builder.db
        
    Raises:
        ProjectNotFoundError: If .agent-builder/ directory not found
    """
    agent_builder_dir = find_agent_builder_dir(start_path)
    return agent_builder_dir / "agent_builder.db"


def get_config_path(start_path: Path | None = None) -> Path:
    """Get the path to the project configuration file.
    
    Args:
        start_path: Starting directory (defaults to current working directory)
        
    Returns:
        Path to config.yaml
        
    Raises:
        ProjectNotFoundError: If .agent-builder/ directory not found
    """
    agent_builder_dir = find_agent_builder_dir(start_path)
    return agent_builder_dir / "config.yaml"


def is_project_initialized(start_path: Path | None = None) -> bool:
    """Check if agent builder is initialized in current or parent directories.
    
    Args:
        start_path: Starting directory (defaults to current working directory)
        
    Returns:
        True if .agent-builder/ directory exists, False otherwise
    """
    try:
        find_agent_builder_dir(start_path)
        return True
    except ProjectNotFoundError:
        return False


def handle_project_not_found(error: ProjectNotFoundError, use_json: bool = False) -> None:
    """Handle ProjectNotFoundError with formatted output and exit.
    
    Args:
        error: The ProjectNotFoundError exception
        use_json: Whether to output as JSON
    """
    from autonomous_agent_builder.cli.output import render
    
    error_data = {
        "error": error.message,
        "hint": error.hint,
    }
    
    def fmt(d: dict) -> str:
        return f"Error: {d['error']}\n\nHint: {d['hint']}"
    
    render(error_data, fmt, use_json=use_json)
    sys.exit(4)  # Exit code 4 for "not initialized"


def require_project() -> Path:
    """Require that agent builder is initialized, exit with error if not.
    
    This is a convenience function for CLI commands that require an
    initialized project. It will find the .agent-builder/ directory
    or exit with an error message.
    
    Returns:
        Path to .agent-builder/ directory
        
    Examples:
        >>> agent_builder_dir = require_project()
        >>> # Command logic here...
    """
    try:
        return find_agent_builder_dir()
    except ProjectNotFoundError as e:
        handle_project_not_found(e)
        # This line is never reached, but satisfies type checker
        raise
