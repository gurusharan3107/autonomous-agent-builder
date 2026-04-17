"""Base generator class for knowledge extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseGenerator(ABC):
    """Base class for knowledge document generators."""

    def __init__(self, workspace_path: Path):
        """Initialize generator.
        
        Args:
            workspace_path: Root directory of the project to analyze
        """
        self.workspace_path = workspace_path

    @abstractmethod
    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate knowledge document.
        
        Args:
            scope: Extraction scope - "full" | "package:<name>" | "feature:<id>"
        
        Returns:
            dict with 'title', 'content', 'tags', 'doc_type' or None if not applicable
        """
        pass

    def _is_python_project(self) -> bool:
        """Check if workspace contains a Python project."""
        indicators = [
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
        ]
        return any((self.workspace_path / indicator).exists() for indicator in indicators)

    def _is_node_project(self) -> bool:
        """Check if workspace contains a Node.js project."""
        return (self.workspace_path / "package.json").exists()

    def _is_java_project(self) -> bool:
        """Check if workspace contains a Java project."""
        indicators = ["pom.xml", "build.gradle", "build.gradle.kts"]
        return any((self.workspace_path / indicator).exists() for indicator in indicators)

    def _find_files(self, pattern: str, max_depth: int = 5) -> list[Path]:
        """Find files matching pattern up to max_depth.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.java")
            max_depth: Maximum directory depth to search
        
        Returns:
            List of matching file paths
        """
        files = []
        try:
            for path in self.workspace_path.rglob(pattern):
                # Calculate depth
                try:
                    relative = path.relative_to(self.workspace_path)
                    depth = len(relative.parts)
                    if depth <= max_depth and path.is_file():
                        files.append(path)
                except ValueError:
                    continue
        except Exception:
            pass
        return files

    def _read_file_safe(self, path: Path, max_size: int = 1024 * 1024) -> str | None:
        """Safely read file content with size limit.
        
        Args:
            path: File path to read
            max_size: Maximum file size in bytes (default 1MB)
        
        Returns:
            File content or None if error/too large
        """
        try:
            if path.stat().st_size > max_size:
                return None
            return path.read_text(encoding="utf-8")
        except Exception:
            return None
