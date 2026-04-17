"""Technology stack generator."""

from __future__ import annotations

import json
from typing import Any

try:
    import tomli
except ImportError:
    import tomllib as tomli  # Python 3.11+

from .base import BaseGenerator


class TechnologyStackGenerator(BaseGenerator):
    """Generate technology stack documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate technology stack overview."""
        
        # Collect technology information
        languages = self._detect_languages()
        frameworks = self._detect_frameworks()
        databases = self._detect_databases()
        tools = self._detect_tools()
        
        content = """# Technology Stack

## Overview

This document describes the technologies, frameworks, and tools used in this project.

"""
        
        # Programming languages
        if languages:
            content += "## Programming Languages\n\n"
            for lang in languages:
                content += f"- **{lang['name']}** - {lang['usage']}\n"
            content += "\n"
        
        # Frameworks
        if frameworks:
            content += "## Frameworks & Libraries\n\n"
            for framework in frameworks:
                content += f"- **{framework['name']}**"
                if framework.get('version'):
                    content += f" (v{framework['version']})"
                content += f" - {framework['purpose']}\n"
            content += "\n"
        
        # Databases
        if databases:
            content += "## Databases & Storage\n\n"
            for db in databases:
                content += f"- **{db['name']}** - {db['purpose']}\n"
            content += "\n"
        
        # Development tools
        if tools:
            content += "## Development Tools\n\n"
            for tool in tools:
                content += f"- **{tool['name']}** - {tool['purpose']}\n"
            content += "\n"
        
        return {
            "title": "Technology Stack",
            "content": content,
            "tags": ["technology", "stack", "reverse-engineering"],
            "doc_type": "reverse-engineering",
        }

    def _detect_languages(self) -> list[dict[str, str]]:
        """Detect programming languages and their usage."""
        languages = []
        
        if self._is_python_project():
            # Try to get Python version
            version = "3.x"
            pyproject = self.workspace_path / "pyproject.toml"
            if pyproject.exists():
                try:
                    data = tomli.loads(pyproject.read_text(encoding="utf-8"))
                    if "project" in data and "requires-python" in data["project"]:
                        version = data["project"]["requires-python"]
                except Exception:
                    pass
            
            languages.append({
                "name": f"Python {version}",
                "usage": "Primary backend language",
            })
        
        if self._is_node_project():
            languages.append({
                "name": "JavaScript/TypeScript",
                "usage": "Frontend and/or backend",
            })
        
        if self._is_java_project():
            languages.append({
                "name": "Java",
                "usage": "Backend application",
            })
        
        return languages

    def _detect_frameworks(self) -> list[dict[str, str]]:
        """Detect frameworks and major libraries."""
        frameworks = []
        
        # Python frameworks
        if self._is_python_project():
            pyproject = self.workspace_path / "pyproject.toml"
            if pyproject.exists():
                try:
                    data = tomli.loads(pyproject.read_text(encoding="utf-8"))
                    deps = {}
                    
                    # Get dependencies
                    if "project" in data and "dependencies" in data["project"]:
                        for dep in data["project"]["dependencies"]:
                            if isinstance(dep, str):
                                name = dep.split("[")[0].split(">=")[0].split("==")[0].strip()
                                version = None
                                if "==" in dep:
                                    version = dep.split("==")[1].split("[")[0].strip()
                                deps[name.lower()] = version
                    
                    # Check for common frameworks
                    framework_map = {
                        "fastapi": ("FastAPI", "Modern async web framework"),
                        "django": ("Django", "Full-featured web framework"),
                        "flask": ("Flask", "Lightweight web framework"),
                        "sqlalchemy": ("SQLAlchemy", "SQL toolkit and ORM"),
                        "pydantic": ("Pydantic", "Data validation"),
                        "typer": ("Typer", "CLI framework"),
                        "pytest": ("pytest", "Testing framework"),
                        "uvicorn": ("Uvicorn", "ASGI server"),
                    }
                    
                    for dep_name, (display_name, purpose) in framework_map.items():
                        if dep_name in deps:
                            frameworks.append({
                                "name": display_name,
                                "version": deps[dep_name],
                                "purpose": purpose,
                            })
                
                except Exception:
                    pass
        
        # Node.js frameworks
        if self._is_node_project():
            package_json = self.workspace_path / "package.json"
            if package_json.exists():
                try:
                    data = json.loads(package_json.read_text(encoding="utf-8"))
                    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    
                    framework_map = {
                        "react": ("React", "UI library"),
                        "vue": ("Vue.js", "Progressive framework"),
                        "express": ("Express", "Web framework"),
                        "next": ("Next.js", "React framework"),
                        "vite": ("Vite", "Build tool"),
                        "typescript": ("TypeScript", "Type-safe JavaScript"),
                    }
                    
                    for dep_name, (display_name, purpose) in framework_map.items():
                        if dep_name in all_deps:
                            frameworks.append({
                                "name": display_name,
                                "version": all_deps[dep_name].lstrip("^~"),
                                "purpose": purpose,
                            })
                
                except Exception:
                    pass
        
        return frameworks

    def _detect_databases(self) -> list[dict[str, str]]:
        """Detect databases and storage systems."""
        databases = []
        
        # Check for database indicators in Python dependencies
        if self._is_python_project():
            pyproject = self.workspace_path / "pyproject.toml"
            if pyproject.exists():
                content = self._read_file_safe(pyproject)
                if content:
                    db_indicators = {
                        "psycopg": ("PostgreSQL", "Relational database"),
                        "asyncpg": ("PostgreSQL", "Async relational database"),
                        "pymongo": ("MongoDB", "Document database"),
                        "redis": ("Redis", "In-memory data store"),
                        "sqlite": ("SQLite", "Embedded database"),
                    }
                    
                    for indicator, (name, purpose) in db_indicators.items():
                        if indicator in content.lower():
                            databases.append({"name": name, "purpose": purpose})
        
        # Check for database files
        if (self.workspace_path / "db.sqlite3").exists() or (self.workspace_path / "*.db").exists():
            databases.append({"name": "SQLite", "purpose": "Local database"})
        
        return databases

    def _detect_tools(self) -> list[dict[str, str]]:
        """Detect development tools."""
        tools = []
        
        # Check for common tool config files
        tool_indicators = {
            ".github/workflows": ("GitHub Actions", "CI/CD automation"),
            "Dockerfile": ("Docker", "Containerization"),
            "docker-compose.yml": ("Docker Compose", "Multi-container orchestration"),
            ".pre-commit-config.yaml": ("pre-commit", "Git hooks"),
            "pytest.ini": ("pytest", "Testing framework"),
            "ruff.toml": ("Ruff", "Python linter"),
            ".eslintrc": ("ESLint", "JavaScript linter"),
            "tsconfig.json": ("TypeScript", "Type checking"),
        }
        
        for indicator, (name, purpose) in tool_indicators.items():
            if (self.workspace_path / indicator).exists():
                tools.append({"name": name, "purpose": purpose})
        
        return tools
