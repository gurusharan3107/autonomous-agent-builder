"""Project overview generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import tomli
except ImportError:
    import tomllib as tomli  # Python 3.11+

from .base import BaseGenerator


class ProjectOverviewGenerator(BaseGenerator):
    """Generate high-level project overview document."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate project overview from README, config files, etc."""
        
        # Collect project metadata
        project_name = self._get_project_name()
        description = self._get_description()
        languages = self._detect_languages()
        frameworks = self._detect_frameworks()
        
        # Build content
        content = f"""# {project_name}

## Overview

{description}

## Project Type

"""
        
        if languages:
            content += "**Primary Languages**: " + ", ".join(languages) + "\n\n"
        
        if frameworks:
            content += "**Frameworks**: " + ", ".join(frameworks) + "\n\n"
        
        # Add directory structure
        content += self._generate_directory_structure()
        
        # Add quick start if available
        quick_start = self._extract_quick_start()
        if quick_start:
            content += f"\n## Quick Start\n\n{quick_start}\n"
        
        return {
            "title": "Project Overview",
            "content": content,
            "tags": ["overview", "reverse-engineering", "project"],
            "doc_type": "reverse-engineering",
        }

    def _get_project_name(self) -> str:
        """Extract project name from various sources."""
        # Try pyproject.toml
        pyproject = self.workspace_path / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomli.loads(pyproject.read_text(encoding="utf-8"))
                if "project" in data and "name" in data["project"]:
                    return data["project"]["name"]
                if "tool" in data and "poetry" in data["tool"] and "name" in data["tool"]["poetry"]:
                    return data["tool"]["poetry"]["name"]
            except Exception:
                pass
        
        # Try package.json
        package_json = self.workspace_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                if "name" in data:
                    return data["name"]
            except Exception:
                pass
        
        # Fallback to directory name
        return self.workspace_path.name

    def _get_description(self) -> str:
        """Extract project description from README or config files."""
        # Try README
        readme_files = ["README.md", "README.rst", "README.txt", "README"]
        for readme_name in readme_files:
            readme = self.workspace_path / readme_name
            if readme.exists():
                content = self._read_file_safe(readme)
                if content:
                    # Extract first paragraph after title
                    lines = content.split("\n")
                    description_lines = []
                    skip_title = False
                    
                    for line in lines:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        if stripped.startswith("#"):
                            skip_title = True
                            continue
                        if skip_title:
                            description_lines.append(stripped)
                            if len(description_lines) >= 3:  # Get first few lines
                                break
                    
                    if description_lines:
                        return " ".join(description_lines)
        
        # Try pyproject.toml
        pyproject = self.workspace_path / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomli.loads(pyproject.read_text(encoding="utf-8"))
                if "project" in data and "description" in data["project"]:
                    return data["project"]["description"]
                if "tool" in data and "poetry" in data["tool"] and "description" in data["tool"]["poetry"]:
                    return data["tool"]["poetry"]["description"]
            except Exception:
                pass
        
        # Try package.json
        package_json = self.workspace_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                if "description" in data:
                    return data["description"]
            except Exception:
                pass
        
        return "No description available."

    def _detect_languages(self) -> list[str]:
        """Detect programming languages used in the project."""
        languages = []
        
        if self._is_python_project():
            languages.append("Python")
        if self._is_node_project():
            languages.append("JavaScript/TypeScript")
        if self._is_java_project():
            languages.append("Java")
        
        # Check for other languages by file extensions
        if self._find_files("*.go"):
            languages.append("Go")
        if self._find_files("*.rs"):
            languages.append("Rust")
        if self._find_files("*.rb"):
            languages.append("Ruby")
        
        return languages

    def _detect_frameworks(self) -> list[str]:
        """Detect frameworks used in the project."""
        frameworks = []
        
        # Python frameworks
        if self._is_python_project():
            pyproject = self.workspace_path / "pyproject.toml"
            requirements = self.workspace_path / "requirements.txt"
            
            framework_indicators = {
                "fastapi": "FastAPI",
                "django": "Django",
                "flask": "Flask",
                "starlette": "Starlette",
            }
            
            # Check pyproject.toml
            if pyproject.exists():
                content = self._read_file_safe(pyproject)
                if content:
                    for indicator, framework in framework_indicators.items():
                        if indicator in content.lower():
                            frameworks.append(framework)
            
            # Check requirements.txt
            if requirements.exists():
                content = self._read_file_safe(requirements)
                if content:
                    for indicator, framework in framework_indicators.items():
                        if indicator in content.lower():
                            frameworks.append(framework)
        
        # Node.js frameworks
        if self._is_node_project():
            package_json = self.workspace_path / "package.json"
            if package_json.exists():
                try:
                    data = json.loads(package_json.read_text(encoding="utf-8"))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    
                    if "react" in deps:
                        frameworks.append("React")
                    if "vue" in deps:
                        frameworks.append("Vue")
                    if "express" in deps:
                        frameworks.append("Express")
                    if "next" in deps:
                        frameworks.append("Next.js")
                except Exception:
                    pass
        
        return list(set(frameworks))  # Remove duplicates

    def _generate_directory_structure(self) -> str:
        """Generate a high-level directory structure overview."""
        content = "## Directory Structure\n\n```\n"
        
        # Get top-level directories and key files
        items = []
        try:
            for item in sorted(self.workspace_path.iterdir()):
                if item.name.startswith(".") and item.name not in [".github", ".agent-builder"]:
                    continue
                if item.is_dir():
                    items.append(f"{item.name}/")
                elif item.name in ["README.md", "pyproject.toml", "package.json", "Dockerfile"]:
                    items.append(item.name)
        except Exception:
            pass
        
        for item in items[:20]:  # Limit to first 20 items
            content += f"{item}\n"
        
        content += "```\n"
        return content

    def _extract_quick_start(self) -> str | None:
        """Extract quick start instructions from README."""
        readme_files = ["README.md", "README.rst", "README.txt"]
        for readme_name in readme_files:
            readme = self.workspace_path / readme_name
            if readme.exists():
                content = self._read_file_safe(readme)
                if content:
                    # Look for quick start, getting started, installation sections
                    lines = content.split("\n")
                    in_section = False
                    section_lines = []
                    
                    for line in lines:
                        if any(keyword in line.lower() for keyword in ["quick start", "getting started", "installation"]):
                            if line.strip().startswith("#"):
                                in_section = True
                                continue
                        elif in_section:
                            if line.strip().startswith("#"):
                                break
                            section_lines.append(line)
                    
                    if section_lines:
                        return "\n".join(section_lines[:15])  # First 15 lines
        
        return None
