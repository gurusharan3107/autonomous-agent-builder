"""Implementation logic for builder init command.

Handles directory creation, resource copying, database initialization,
and configuration file generation.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


class InitError(Exception):
    """Initialization error with hint."""
    
    def __init__(self, message: str, hint: str):
        self.message = message
        self.hint = hint
        super().__init__(message)


def run_init(
    project_name: str | None,
    language: str,
    framework: str | None,
    force: bool,
    no_input: bool,
) -> dict[str, Any]:
    """Run the initialization process.
    
    Args:
        project_name: Project name (auto-detected if None)
        language: Primary language
        framework: Framework (optional)
        force: Reinitialize if .agent-builder/ exists
        no_input: Skip interactive prompts
        
    Returns:
        Result dictionary with success/error information
    """
    cwd = Path.cwd()
    agent_builder_dir = cwd / ".agent-builder"
    
    # Check if already initialized
    if agent_builder_dir.exists() and not force:
        return {
            "error": "Agent builder already initialized in this directory",
            "hint": "Use --force to reinitialize, or cd to a different directory",
            "directory": str(agent_builder_dir),
        }
    
    # Auto-detect project name if not provided
    if not project_name:
        project_name = cwd.name
    
    # Validate language
    valid_languages = ["python", "node", "java", "go", "rust"]
    if language not in valid_languages:
        return {
            "error": f"Invalid language: {language}",
            "hint": f"Valid languages: {', '.join(valid_languages)}",
        }
    
    try:
        # Create directory structure
        _create_directory_structure(agent_builder_dir, force)
        
        # Copy embedded resources
        _copy_embedded_resources(agent_builder_dir)
        
        # Initialize database
        _initialize_database(agent_builder_dir)
        
        # Generate configuration
        _generate_config(agent_builder_dir, project_name, language, framework)
        
        return {
            "success": True,
            "directory": str(agent_builder_dir),
            "project_name": project_name,
            "language": language,
            "framework": framework,
        }
        
    except InitError as e:
        return {
            "error": e.message,
            "hint": e.hint,
        }
    except Exception as e:
        return {
            "error": str(e),
            "hint": "Check file permissions and disk space",
        }


def _create_directory_structure(agent_builder_dir: Path, force: bool) -> None:
    """Create .agent-builder/ directory structure.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
        force: Remove existing directory if True
    """
    if agent_builder_dir.exists() and force:
        shutil.rmtree(agent_builder_dir)
    
    # Create main directory
    agent_builder_dir.mkdir(exist_ok=True)
    
    # Create subdirectories
    subdirs = [
        "server",
        "server/routes",
        "server/sse",
        "dashboard",
        "scripts",
        "knowledge",
        "migrations",
    ]
    
    for subdir in subdirs:
        (agent_builder_dir / subdir).mkdir(parents=True, exist_ok=True)


def _copy_embedded_resources(agent_builder_dir: Path) -> None:
    """Copy embedded server, dashboard, and scripts from package resources.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
    """
    # Import here to avoid circular dependencies
    import autonomous_agent_builder.embedded
    
    embedded_dir = Path(autonomous_agent_builder.embedded.__file__).parent
    
    # Copy server code
    server_src = embedded_dir / "server"
    server_dst = agent_builder_dir / "server"
    if server_src.exists():
        _copy_python_files(server_src, server_dst)
    
    # Copy dashboard assets
    dashboard_src = embedded_dir / "dashboard"
    dashboard_dst = agent_builder_dir / "dashboard"
    if dashboard_src.exists() and any(dashboard_src.iterdir()):
        shutil.copytree(dashboard_src, dashboard_dst, dirs_exist_ok=True)
    
    # Copy scripts
    scripts_src = embedded_dir / "scripts"
    scripts_dst = agent_builder_dir / "scripts"
    if scripts_src.exists():
        _copy_python_files(scripts_src, scripts_dst)


def _copy_python_files(src: Path, dst: Path) -> None:
    """Copy Python files from src to dst, preserving directory structure.
    
    Args:
        src: Source directory
        dst: Destination directory
    """
    for item in src.rglob("*.py"):
        if "__pycache__" in item.parts:
            continue
        
        rel_path = item.relative_to(src)
        dst_path = dst / rel_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dst_path)


def _initialize_database(agent_builder_dir: Path) -> None:
    """Initialize SQLite database with schema.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
    """
    import asyncio
    import os
    
    # Create database path
    db_path = agent_builder_dir / "agent_builder.db"
    
    # Set environment variables for database configuration
    # Use DB_ prefix as expected by DatabaseSettings
    # Note: DB_NAME should NOT include .db extension as it's added by the config
    original_driver = os.environ.get("DB_DRIVER")
    original_name = os.environ.get("DB_NAME")
    
    os.environ["DB_DRIVER"] = "sqlite"
    # Remove .db extension from the path since config adds it
    db_name_without_ext = str(db_path.absolute()).replace(".db", "")
    os.environ["DB_NAME"] = db_name_without_ext
    
    try:
        # Clear any cached engine/session factory
        from autonomous_agent_builder.db import session
        session._engine = None
        session._session_factory = None
        
        # Initialize database schema
        from autonomous_agent_builder.db.session import init_db
        asyncio.run(init_db())
        
        # Verify database was created
        if not db_path.exists():
            raise InitError(
                "Database file was not created",
                "Check file permissions and disk space"
            )
            
    except Exception as e:
        # If database initialization fails, create an empty file
        # so the user can at least start the server
        if not db_path.exists():
            db_path.touch()
        raise InitError(
            f"Database initialization failed: {str(e)}",
            "The database file was created but schema initialization failed. You may need to run migrations manually."
        )
    finally:
        # Restore original environment variables
        if original_driver:
            os.environ["DB_DRIVER"] = original_driver
        else:
            os.environ.pop("DB_DRIVER", None)
            
        if original_name:
            os.environ["DB_NAME"] = original_name
        else:
            os.environ.pop("DB_NAME", None)
        
        # Clear cached engine/session factory again
        from autonomous_agent_builder.db import session
        session._engine = None
        session._session_factory = None


def _generate_config(
    agent_builder_dir: Path,
    project_name: str,
    language: str,
    framework: str | None,
) -> None:
    """Generate default config.yaml file.
    
    Args:
        agent_builder_dir: Path to .agent-builder/ directory
        project_name: Project name
        language: Primary language
        framework: Framework (optional)
    """
    config_content = f"""# Agent Builder Configuration

# Project metadata
project:
  name: "{project_name}"
  language: "{language}"
  framework: "{framework or ''}"

# Agent budgets
agent:
  max_cost_per_task: 5.0  # USD
  max_turns_per_run: 50
  timeout_seconds: 300

# Quality gates
gates:
  timeout_seconds: 60
  max_retries: 2
  concurrent_execution: true
  
  # Gate-specific config
  ruff:
    enabled: true
    fix: true
  
  pytest:
    enabled: true
    coverage_threshold: 80
  
  semgrep:
    enabled: true
    rules: ["python.lang.security"]
  
  trivy:
    enabled: false  # Disabled by default (slow)

# Server
server:
  host: "127.0.0.1"
  port_range: [8000, 8010]
  debug: false

# Knowledge base
knowledge:
  auto_index: true
  search_tool: "grep"  # or "ripgrep" if available
"""
    
    config_path = agent_builder_dir / "config.yaml"
    config_path.write_text(config_content)
