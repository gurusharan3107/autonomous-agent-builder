"""Dependencies generator."""

from __future__ import annotations

import json
from typing import Any

try:
    import tomli
except ImportError:
    import tomllib as tomli  # Python 3.11+

from .base import BaseGenerator


class DependenciesGenerator(BaseGenerator):
    """Generate dependencies documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate dependencies overview."""
        
        # Collect dependencies
        python_deps = self._get_python_dependencies()
        node_deps = self._get_node_dependencies()
        
        if not python_deps and not node_deps:
            return None
        
        content = """# Dependencies

## Overview

This document lists all external dependencies used in the project.

"""
        
        # Python dependencies
        if python_deps:
            content += "## Python Dependencies\n\n"
            
            if python_deps.get("production"):
                content += "### Production Dependencies\n\n"
                for dep in sorted(python_deps["production"], key=lambda x: x["name"]):
                    content += f"- **{dep['name']}**"
                    if dep.get("version"):
                        content += f" (v{dep['version']})"
                    if dep.get("purpose"):
                        content += f" - {dep['purpose']}"
                    content += "\n"
                content += "\n"
            
            if python_deps.get("dev"):
                content += "### Development Dependencies\n\n"
                for dep in sorted(python_deps["dev"], key=lambda x: x["name"]):
                    content += f"- **{dep['name']}**"
                    if dep.get("version"):
                        content += f" (v{dep['version']})"
                    if dep.get("purpose"):
                        content += f" - {dep['purpose']}"
                    content += "\n"
                content += "\n"
        
        # Node.js dependencies
        if node_deps:
            content += "## Node.js Dependencies\n\n"
            
            if node_deps.get("production"):
                content += "### Production Dependencies\n\n"
                for dep in sorted(node_deps["production"], key=lambda x: x["name"]):
                    content += f"- **{dep['name']}** (v{dep['version']})\n"
                content += "\n"
            
            if node_deps.get("dev"):
                content += "### Development Dependencies\n\n"
                for dep in sorted(node_deps["dev"], key=lambda x: x["name"]):
                    content += f"- **{dep['name']}** (v{dep['version']})\n"
                content += "\n"
        
        content += """## Dependency Management

Dependencies are managed through:
- Python: `pyproject.toml` or `requirements.txt`
- Node.js: `package.json`

## Security

Regularly update dependencies to patch security vulnerabilities.
Use tools like `pip-audit` or `npm audit` to check for known issues.
"""
        
        return {
            "title": "Dependencies",
            "content": content,
            "tags": ["dependencies", "reverse-engineering", "packages"],
            "doc_type": "reverse-engineering",
        }

    def _get_python_dependencies(self) -> dict[str, list[dict]]:
        """Extract Python dependencies from pyproject.toml or requirements.txt."""
        deps = {"production": [], "dev": []}
        
        # Try pyproject.toml first
        pyproject = self.workspace_path / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomli.loads(pyproject.read_text(encoding="utf-8"))
                
                # Get production dependencies
                if "project" in data and "dependencies" in data["project"]:
                    for dep_str in data["project"]["dependencies"]:
                        dep_info = self._parse_python_dep(dep_str)
                        if dep_info:
                            deps["production"].append(dep_info)
                
                # Get dev dependencies (Poetry style)
                if "tool" in data and "poetry" in data["tool"]:
                    if "group" in data["tool"]["poetry"] and "dev" in data["tool"]["poetry"]["group"]:
                        dev_deps = data["tool"]["poetry"]["group"]["dev"].get("dependencies", {})
                        for name, version in dev_deps.items():
                            deps["dev"].append({
                                "name": name,
                                "version": str(version) if not isinstance(version, dict) else None,
                            })
                
                # Get optional dependencies
                if "project" in data and "optional-dependencies" in data["project"]:
                    for group_name, group_deps in data["project"]["optional-dependencies"].items():
                        if group_name in ["dev", "test", "docs"]:
                            for dep_str in group_deps:
                                dep_info = self._parse_python_dep(dep_str)
                                if dep_info:
                                    deps["dev"].append(dep_info)
                
            except Exception:
                pass
        
        # Try requirements.txt
        requirements = self.workspace_path / "requirements.txt"
        if requirements.exists() and not deps["production"]:
            content = self._read_file_safe(requirements)
            if content:
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep_info = self._parse_python_dep(line)
                        if dep_info:
                            deps["production"].append(dep_info)
        
        # Try requirements-dev.txt
        requirements_dev = self.workspace_path / "requirements-dev.txt"
        if requirements_dev.exists():
            content = self._read_file_safe(requirements_dev)
            if content:
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep_info = self._parse_python_dep(line)
                        if dep_info:
                            deps["dev"].append(dep_info)
        
        return deps if (deps["production"] or deps["dev"]) else {}

    def _parse_python_dep(self, dep_str: str) -> dict[str, str] | None:
        """Parse Python dependency string."""
        if not dep_str or dep_str.startswith("#"):
            return None
        
        # Remove extras [extra1,extra2]
        if "[" in dep_str:
            dep_str = dep_str.split("[")[0]
        
        # Parse name and version
        name = dep_str
        version = None
        
        for sep in ["==", ">=", "<=", "~=", ">", "<"]:
            if sep in dep_str:
                parts = dep_str.split(sep)
                name = parts[0].strip()
                version = parts[1].strip() if len(parts) > 1 else None
                break
        
        # Get purpose for common packages
        purpose = self._get_package_purpose(name.lower())
        
        return {
            "name": name.strip(),
            "version": version,
            "purpose": purpose,
        }

    def _get_node_dependencies(self) -> dict[str, list[dict]]:
        """Extract Node.js dependencies from package.json."""
        deps = {"production": [], "dev": []}
        
        package_json = self.workspace_path / "package.json"
        if not package_json.exists():
            return {}
        
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            
            # Production dependencies
            if "dependencies" in data:
                for name, version in data["dependencies"].items():
                    deps["production"].append({
                        "name": name,
                        "version": version.lstrip("^~"),
                    })
            
            # Dev dependencies
            if "devDependencies" in data:
                for name, version in data["devDependencies"].items():
                    deps["dev"].append({
                        "name": name,
                        "version": version.lstrip("^~"),
                    })
        
        except Exception:
            pass
        
        return deps if (deps["production"] or deps["dev"]) else {}

    def _get_package_purpose(self, package_name: str) -> str | None:
        """Get common purpose for well-known packages."""
        purposes = {
            "fastapi": "Web framework",
            "django": "Web framework",
            "flask": "Web framework",
            "sqlalchemy": "ORM",
            "pydantic": "Data validation",
            "typer": "CLI framework",
            "pytest": "Testing",
            "uvicorn": "ASGI server",
            "requests": "HTTP client",
            "httpx": "Async HTTP client",
            "redis": "Caching",
            "celery": "Task queue",
            "alembic": "Database migrations",
            "ruff": "Linter",
            "black": "Code formatter",
            "mypy": "Type checker",
        }
        
        return purposes.get(package_name)
