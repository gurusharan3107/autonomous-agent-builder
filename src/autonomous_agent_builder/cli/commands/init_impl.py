"""Implementation logic for builder init command.

Handles directory creation, resource copying, database initialization,
and configuration file generation.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from autonomous_agent_builder.cli.project_discovery import _is_builder_source_repo

_BUILDER_GITIGNORE_ENTRIES = (".agent-builder/",)


class InitError(Exception):
    """Initialization error with hint."""

    def __init__(self, message: str, hint: str):
        self.message = message
        self.hint = hint
        super().__init__(message)


def run_init(
    project_name: str | None,
    language: str | None,
    framework: str | None,
    force: bool,
    no_input: bool,
) -> dict[str, Any]:
    """Run the initialization process.

    Args:
        project_name: Project name (auto-detected if None)
        language: Primary language (auto-detected when omitted)
        framework: Framework (optional)
        force: Reinitialize if .agent-builder/ exists
        no_input: Skip interactive prompts

    Returns:
        Result dictionary with success/error information
    """
    cwd = Path.cwd()
    agent_builder_dir = cwd / ".agent-builder"

    if _is_builder_source_repo(cwd):
        return {
            "error": "Cannot initialize the autonomous builder source repository as a managed app",
            "hint": (
                "Run 'builder init' inside the generated app workspace instead. "
                "The builder repo/worktree must stay free of project-local .agent-builder state."
            ),
        }

    resolved_project_name = project_name or cwd.name
    resolved_language = _resolve_language(cwd, language)
    initial_mode = _classify_init_mode(cwd)

    # Validate language. ``unknown`` is intentional for empty / clean-slate
    # workspaces (P1) — the orchestrator fills it in deterministically after
    # the init-project-chat interview.
    valid_languages = ["python", "node", "java", "go", "rust", "unknown"]
    if resolved_language not in valid_languages:
        return {
            "error": f"Invalid language: {resolved_language}",
            "hint": f"Valid languages: {', '.join(valid_languages)}",
        }

    # Check if already initialized
    if agent_builder_dir.exists() and not force:
        from autonomous_agent_builder.services.runtime_guidance import (
            ensure_project_runtime_guidance,
            ensure_project_telemetry_env,
            infer_runtime_guidance_context,
        )

        mode = _classify_init_mode(cwd)
        guidance_context = infer_runtime_guidance_context(
            cwd,
            mode=mode,
            language=resolved_language,
            framework=framework,
        )
        runtime_guidance = ensure_project_runtime_guidance(
            cwd,
            project_name=resolved_project_name,
            **guidance_context,
        )
        telemetry_env = ensure_project_telemetry_env(
            cwd,
            project_name=resolved_project_name,
        )
        _ensure_builder_gitignore(cwd)
        onboarding_state = _ensure_onboarding_state(cwd)
        guidance_changed = runtime_guidance["created"] or runtime_guidance["status"] == "migrated"
        telemetry_changed = telemetry_env["created"] or bool(telemetry_env.get("changed_keys"))
        if guidance_changed or telemetry_changed:
            from autonomous_agent_builder.services.readiness import (
                assess_readiness,
                compact_status,
            )

            return {
                "success": True,
                "already_initialized": True,
                "directory": str(agent_builder_dir),
                "project_name": resolved_project_name,
                "language": resolved_language,
                "framework": framework,
                "runtime_guidance": runtime_guidance,
                "telemetry_env": telemetry_env,
                "onboarding_state": onboarding_state,
                "readiness": compact_status(assess_readiness(cwd, write=True)),
            }
        return {
            "error": "Agent builder already initialized in this directory",
            "hint": "Use --force to reinitialize, or cd to a different directory",
            "directory": str(agent_builder_dir),
        }

    # Auto-detect project name if not provided
    project_name = resolved_project_name

    try:
        # Create directory structure
        _create_directory_structure(agent_builder_dir, force)

        # Copy embedded resources
        _copy_embedded_resources(agent_builder_dir)

        # Keep builder-owned runtime assets out of target app lint/git scope.
        _ensure_builder_gitignore(cwd)

        # Initialize database
        _initialize_database(agent_builder_dir)

        # Generate configuration
        _generate_config(agent_builder_dir, project_name, resolved_language, framework)

        from autonomous_agent_builder.services.runtime_guidance import (
            ensure_project_runtime_guidance,
            ensure_project_telemetry_env,
            infer_runtime_guidance_context,
        )

        guidance_context = infer_runtime_guidance_context(
            cwd,
            mode=initial_mode,
            language=resolved_language,
            framework=framework,
        )
        runtime_guidance = ensure_project_runtime_guidance(
            cwd,
            project_name=project_name,
            **guidance_context,
        )
        telemetry_env = ensure_project_telemetry_env(
            cwd,
            project_name=project_name,
        )
        onboarding_state = _ensure_onboarding_state(cwd)

        from autonomous_agent_builder.services.readiness import assess_readiness, compact_status

        readiness = compact_status(assess_readiness(cwd, write=True))

        return {
            "success": True,
            "directory": str(agent_builder_dir),
            "project_name": project_name,
            "language": resolved_language,
            "framework": framework,
            "runtime_guidance": runtime_guidance,
            "telemetry_env": telemetry_env,
            "onboarding_state": onboarding_state,
            "readiness": readiness,
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


def _resolve_language(project_root: Path, requested_language: str | None) -> str:
    """Resolve init language from explicit flag or repository markers."""
    if requested_language:
        return requested_language
    detected = _detect_language(project_root)
    if detected == "unknown":
        # Honest fallback: empty / clean-slate workspaces should not pretend to
        # have a language. The orchestrator fills this in deterministically
        # after the init-project-chat interview produces an answer (P5 in
        # docs/plans/can-you-create-plan-cozy-toast.md). Lying with "python"
        # here led code-gen to build a Flask app for a vanilla-JS scope.
        return "unknown"
    return detected


def _detect_language(project_root: Path) -> str:
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "python"
    if (project_root / "package.json").exists():
        return "node"
    if (project_root / "pom.xml").exists() or (project_root / "build.gradle").exists():
        return "java"
    if (project_root / "go.mod").exists():
        return "go"
    if (project_root / "Cargo.toml").exists():
        return "rust"
    return "unknown"


def _classify_init_mode(project_root: Path) -> str:
    try:
        from autonomous_agent_builder.onboarding import _classify_onboarding_mode

        return _classify_onboarding_mode(project_root)
    except Exception:
        return "forward_engineering"


def _ensure_onboarding_state(project_root: Path) -> dict[str, Any]:
    from autonomous_agent_builder.onboarding import (
        default_onboarding_state,
        save_onboarding_state,
    )

    state_path = project_root / ".agent-builder" / "onboarding-state.json"
    if state_path.exists():
        return {
            "created": False,
            "status": "existing",
            "path": str(state_path),
            "relative_path": ".agent-builder/onboarding-state.json",
        }
    state = default_onboarding_state(project_root)
    save_onboarding_state(project_root, state)
    return {
        "created": True,
        "status": "created",
        "path": str(state_path),
        "relative_path": ".agent-builder/onboarding-state.json",
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

    # Prefer the live built frontend bundle when it exists so fresh repos
    # inherit the current dashboard, not a stale copied snapshot.
    package_root = embedded_dir.parent
    live_dashboard_src = package_root.parent.parent / "frontend" / "dist"
    dashboard_src = (
        live_dashboard_src
        if live_dashboard_src.exists() and any(live_dashboard_src.iterdir())
        else embedded_dir / "dashboard"
    )
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


def _ensure_builder_gitignore(project_root: Path) -> None:
    gitignore_path = project_root / ".gitignore"
    text = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    existing = {line.strip() for line in text.splitlines()}
    missing = [entry for entry in _BUILDER_GITIGNORE_ENTRIES if entry not in existing]
    if not missing:
        return
    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    gitignore_path.write_text(prefix + "\n".join(missing) + "\n", encoding="utf-8")


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
                "Database file was not created", "Check file permissions and disk space"
            )

    except Exception as e:
        # If database initialization fails, create an empty file
        # so the user can at least start the server
        if not db_path.exists():
            db_path.touch()
        raise InitError(
            f"Database initialization failed: {str(e)}",
            "The database file was created but schema initialization failed. "
            "You may need to run migrations manually.",
        ) from e
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
  framework: "{framework or ""}"

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
