"""Project overview generator."""

from __future__ import annotations

import json
import re
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
        project_name = self._get_project_name()
        description = self._get_description()
        languages = self._detect_languages()
        frameworks = self._detect_frameworks()
        quick_start = self._extract_quick_start()
        structure_items = self._top_level_items()

        overview_parts = [
            f"{project_name} is the repository surface this onboarding run is documenting as seed system docs.",
            description,
        ]
        if languages:
            overview_parts.append(
                "The current implementation is primarily written in "
                + ", ".join(languages)
                + "."
            )
        if frameworks:
            overview_parts.append(
                "Detected frameworks and delivery layers include "
                + ", ".join(frameworks)
                + "."
            )
        overview = " ".join(
            part.strip().rstrip(".") + "."
            for part in overview_parts
            if part and part.strip()
        )
        overview = self._trim_words(overview, 75)

        boundary_parts: list[str] = []
        if structure_items:
            boundary_parts.append(
                "Top-level ownership is concentrated in "
                + ", ".join(f"`{item}`" for item in structure_items[:6])
                + ", which define where runtime code, package metadata, and supporting documentation currently live."
            )
        if quick_start:
            boundary_parts.append(
                "README-level bootstrap guidance is present and should stay aligned with runtime setup and package-manager choices."
            )
        boundaries = " ".join(boundary_parts) or (
            "Ownership currently falls back to the repository root and the primary manifests discovered during extraction."
        )

        invariants = [
            "- Keep the project name, language signals, and framework signals consistent with the checked-in manifests and README.",
            "- Treat the top-level directory layout as the first ownership map for runtime, dashboard, and support surfaces.",
        ]
        if quick_start:
            invariants.append(
                "- Refresh quick-start guidance when setup commands, runtime entrypoints, or package managers change."
            )

        evidence_parts = [
            "### Repository identity",
            "This run uses checked-in manifests, README signals, and the top-level tree to describe the repo without assuming hidden deployment context or untracked local setup.",
            f"- **Project name**: `{project_name}`",
            f"- **Workspace root**: `{self.workspace_path}`",
        ]
        if languages:
            evidence_parts.append("- **Primary languages**: " + ", ".join(languages))
        if frameworks:
            evidence_parts.append("- **Frameworks**: " + ", ".join(frameworks))
        if structure_items:
            evidence_parts.extend(
                [
                    "",
                    "### Top-level layout",
                    "```text",
                    *structure_items[:20],
                    "```",
                ]
            )
        if quick_start:
            evidence_parts.extend(
                [
                    "",
                    "### Quick start signals",
                    self._trim_words(quick_start, 140),
                ]
            )
        evidence_parts.extend(
            [
                "",
                "The evidence above is intentionally lightweight: it preserves the root manifests, main directories, and setup guidance that future extraction runs should continue to agree with.",
            ]
        )

        content = "\n\n".join(
            [
                "# Project Overview",
                "## Overview",
                overview,
                "## Boundaries",
                boundaries,
                "## Invariants",
                "\n".join(invariants),
                "## Evidence",
                "\n".join(evidence_parts),
                "## Change guidance",
                "Update the README, top-level manifests, and any renamed root directories together, then rerun `builder knowledge extract --force` to refresh this repository overview.",
            ]
        )

        return {
            "title": "Project Overview",
            "content": content,
            "tags": ["overview", "system-docs", "seed", "project"],
            "doc_type": "system-docs",
            "verified": False,
            "authoritative": False,
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
                            cleaned = self._clean_readme_summary_line(stripped)
                            if not cleaned:
                                continue
                            description_lines.append(cleaned)
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

    def _clean_readme_summary_line(self, line: str) -> str:
        """Strip badge and media markup before using README lines as prose."""
        cleaned = re.sub(r"<img\b[^>]*>", " ", line, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?a\b[^>]*>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""
        if cleaned.lower() in {"api docs"}:
            return ""
        if not re.search(r"[A-Za-z]{3,}", cleaned):
            return ""
        return cleaned

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

    def _top_level_items(self) -> list[str]:
        items: list[str] = []
        try:
            for item in sorted(self.workspace_path.iterdir()):
                if item.name.startswith(".") and item.name not in [".github", ".agent-builder"]:
                    continue
                if item.is_dir():
                    items.append(f"{item.name}/")
                elif item.name in ["README.md", "pyproject.toml", "package.json", "Dockerfile"]:
                    items.append(item.name)
        except Exception:
            return []
        return items

    def _trim_words(self, text: str, limit: int) -> str:
        words = text.split()
        if len(words) <= limit:
            return text.strip()
        return " ".join(words[:limit]).strip() + "..."

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
