"""Code structure generator."""

from __future__ import annotations

from typing import Any

from .base import BaseGenerator


class CodeStructureGenerator(BaseGenerator):
    """Generate code structure and organization documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate code structure overview."""
        
        # Analyze code organization
        modules = self._identify_modules()
        key_files = self._identify_key_files()
        
        if not modules and not key_files:
            return None
        
        content = """# Code Structure

## Code Organization

This document describes how the code is organized, including module structure,
key files, and coding patterns.

"""
        
        # Add module structure
        if modules:
            content += "## Module Structure\n\n"
            for module in modules:
                content += f"### `{module['path']}`\n\n"
                content += f"{module['description']}\n\n"
                if module.get('files'):
                    content += "**Key Files**:\n"
                    for file_info in module['files'][:5]:  # Top 5 files
                        content += f"- `{file_info['name']}` - {file_info['purpose']}\n"
                    content += "\n"
        
        # Add key files inventory
        if key_files:
            content += "## Key Files\n\n"
            for file_info in key_files[:20]:  # Top 20 files
                content += f"- `{file_info['path']}` - {file_info['purpose']}\n"
            content += "\n"
        
        content += """## Design Patterns

Common design patterns used in this codebase:
- **Dependency Injection**: Used for loose coupling
- **Factory Pattern**: For object creation
- **Repository Pattern**: For data access abstraction
- **Strategy Pattern**: For algorithm selection

## Code Conventions

- Follow PEP 8 style guide (Python)
- Use type hints for better code clarity
- Write docstrings for public APIs
- Keep functions focused and small
"""
        
        return {
            "title": "Code Structure",
            "content": content,
            "tags": ["code-structure", "reverse-engineering", "organization"],
            "doc_type": "reverse-engineering",
        }

    def _identify_modules(self) -> list[dict[str, Any]]:
        """Identify major modules/packages."""
        modules = []
        
        # Python: Look for packages (directories with __init__.py)
        if self._is_python_project():
            src_dir = self.workspace_path / "src"
            search_dirs = [src_dir] if src_dir.exists() else [self.workspace_path]
            
            for search_dir in search_dirs:
                for init_file in search_dir.rglob("__init__.py"):
                    module_dir = init_file.parent
                    
                    # Skip if too deep or in common ignore patterns
                    try:
                        relative = module_dir.relative_to(self.workspace_path)
                        if len(relative.parts) > 4:
                            continue
                        if any(part.startswith(".") or part in ["__pycache__", "tests"] for part in relative.parts):
                            continue
                    except ValueError:
                        continue
                    
                    # Get module description from __init__.py docstring
                    description = "Python module"
                    content = self._read_file_safe(init_file, max_size=10240)
                    if content:
                        lines = content.strip().split("\n")
                        if lines and (lines[0].startswith('"""') or lines[0].startswith("'''")):
                            # Extract docstring
                            docstring_lines = []
                            for line in lines:
                                if line.strip().endswith('"""') or line.strip().endswith("'''"):
                                    docstring_lines.append(line.strip('"\' '))
                                    break
                                docstring_lines.append(line.strip('"\' '))
                            description = " ".join(docstring_lines[:2])  # First 2 lines
                    
                    # List Python files in this module
                    files = []
                    for py_file in module_dir.glob("*.py"):
                        if py_file.name != "__init__.py":
                            files.append({
                                "name": py_file.name,
                                "purpose": self._infer_file_purpose(py_file.name),
                            })
                    
                    modules.append({
                        "path": str(relative),
                        "description": description,
                        "files": files,
                    })
        
        return modules[:15]  # Top 15 modules

    def _identify_key_files(self) -> list[dict[str, Any]]:
        """Identify key source files."""
        key_files = []
        
        # Python files
        if self._is_python_project():
            important_patterns = [
                ("main.py", "Application entry point"),
                ("app.py", "Application factory"),
                ("config.py", "Configuration management"),
                ("settings.py", "Settings and configuration"),
                ("models.py", "Data models"),
                ("schemas.py", "API schemas"),
                ("routes.py", "API routes"),
                ("cli.py", "Command-line interface"),
            ]
            
            for pattern, purpose in important_patterns:
                files = self._find_files(f"**/{pattern}", max_depth=4)
                for file_path in files:
                    try:
                        relative = file_path.relative_to(self.workspace_path)
                        key_files.append({
                            "path": str(relative),
                            "purpose": purpose,
                        })
                    except ValueError:
                        continue
        
        # Configuration files
        config_files = [
            ("pyproject.toml", "Python project configuration"),
            ("setup.py", "Python package setup"),
            ("package.json", "Node.js package configuration"),
            ("Dockerfile", "Docker container definition"),
            ("docker-compose.yml", "Docker Compose configuration"),
        ]
        
        for filename, purpose in config_files:
            file_path = self.workspace_path / filename
            if file_path.exists():
                key_files.append({
                    "path": filename,
                    "purpose": purpose,
                })
        
        return key_files

    def _infer_file_purpose(self, filename: str) -> str:
        """Infer file purpose from filename."""
        purpose_map = {
            "models": "Data models and database schema",
            "schemas": "API request/response schemas",
            "routes": "API route handlers",
            "views": "View functions",
            "controllers": "Controller logic",
            "services": "Business logic services",
            "utils": "Utility functions",
            "helpers": "Helper functions",
            "config": "Configuration",
            "settings": "Settings",
            "constants": "Constants and enums",
            "exceptions": "Custom exceptions",
            "middleware": "Middleware components",
            "decorators": "Decorator functions",
            "validators": "Validation logic",
            "serializers": "Data serialization",
        }
        
        name_lower = filename.lower().replace(".py", "")
        for key, purpose in purpose_map.items():
            if key in name_lower:
                return purpose
        
        return "Source file"
