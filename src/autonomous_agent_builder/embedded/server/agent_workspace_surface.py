"""Generated-app surface detection for Agent chat routing."""

from __future__ import annotations

from pathlib import Path

IGNORED_WORKSPACE_SURFACE_NAMES = {
    ".agent-builder",
    ".claude",
    ".git",
    ".memory",
    "AGENTS.md",
    "CLAUDE.md",
    "README",
    "README.md",
    "LICENSE",
    "LICENSE.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    ".env",
    ".gitignore",
}
GENERATED_APP_DIRECTORIES = {
    "src",
    "app",
    "api",
    "server",
    "frontend",
    "backend",
    "lib",
    "dist",
    "public",
    "scripts",
    "test",
    "tests",
}
GENERATED_APP_FILE_SUFFIXES = {
    ".html",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".py",
    ".go",
    ".rs",
}


def has_generated_app_surface(project_root: Path) -> bool:
    for child in project_root.iterdir():
        name = child.name
        if name in IGNORED_WORKSPACE_SURFACE_NAMES:
            continue
        if child.is_dir() and name in GENERATED_APP_DIRECTORIES:
            return True
        if child.is_file() and child.suffix.lower() in GENERATED_APP_FILE_SUFFIXES:
            return True
    return False
