"""Configuration generator."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class ConfigurationGenerator(BaseGenerator):
    """Generate configuration documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate configuration documentation."""
        
        if not self._is_python_project():
            return None
        
        # Find config files
        config_files = (
            self._find_files("**/config.py", max_depth=3) +
            self._find_files("**/settings.py", max_depth=3) +
            self._find_files("**/.env.example", max_depth=2)
        )
        
        if not config_files:
            return None
        
        config_classes = []
        env_vars = []
        
        for config_file in config_files:
            content = self._read_file_safe(config_file)
            if not content:
                continue
            
            if config_file.name.endswith(".py"):
                # Extract config classes
                classes = self._extract_config_classes(content)
                config_classes.extend(classes)
            elif config_file.name == ".env.example":
                # Extract environment variables
                vars = self._extract_env_vars(content)
                env_vars.extend(vars)
        
        if not config_classes and not env_vars:
            return None
        
        content = """# Configuration

## Overview

This document describes all configuration options, environment variables,
and settings for the system.

"""
        
        # Add config classes
        if config_classes:
            content += "## Configuration Classes\n\n"
            for config_class in config_classes:
                content += f"### {config_class['name']}\n\n"
                if config_class.get('docstring'):
                    content += f"{config_class['docstring']}\n\n"
                
                if config_class.get('fields'):
                    content += "**Settings**:\n\n"
                    for field in config_class['fields']:
                        content += f"- **{field['name']}** ({field['type']})"
                        if field.get('default'):
                            content += f" - Default: `{field['default']}`"
                        if field.get('description'):
                            content += f" - {field['description']}"
                        content += "\n"
                    content += "\n"
        
        # Add environment variables
        if env_vars:
            content += "## Environment Variables\n\n"
            for var in env_vars:
                content += f"### `{var['name']}`\n\n"
                if var.get('description'):
                    content += f"{var['description']}\n\n"
                if var.get('default'):
                    content += f"**Default**: `{var['default']}`\n\n"
                if var.get('example'):
                    content += f"**Example**: `{var['example']}`\n\n"
        
        content += """## Configuration Files

### pyproject.toml

Project metadata and dependencies.

### .env

Environment-specific configuration (not committed to git).

### config.yaml

Application configuration (if applicable).

## Configuration Precedence

Configuration is loaded in this order (later overrides earlier):

1. Default values in code
2. Configuration files
3. Environment variables
4. Command-line arguments

## Security

- Never commit `.env` files to version control
- Use environment variables for secrets
- Rotate credentials regularly
- Use different configs for dev/staging/prod
"""
        
        return {
            "title": "Configuration",
            "content": content,
            "tags": ["configuration", "settings", "environment", "system-docs", "seed"],
            "doc_type": "system-docs",
        }

    def _extract_config_classes(self, content: str) -> list[dict]:
        """Extract configuration classes from Python code."""
        classes = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if it's a config class (BaseSettings, Config, etc.)
                    if any(self._is_config_base(base) for base in node.bases):
                        class_info = self._extract_class_fields(node)
                        if class_info:
                            classes.append(class_info)
        except Exception:
            pass
        
        return classes

    def _is_config_base(self, base) -> bool:
        """Check if base class indicates a config class."""
        if isinstance(base, ast.Name):
            return base.id in ["BaseSettings", "Config", "Settings"]
        return False

    def _extract_class_fields(self, node: ast.ClassDef) -> dict | None:
        """Extract fields from config class."""
        fields = []
        
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                
                if field_name.startswith("_"):
                    continue
                
                field_info = {
                    "name": field_name,
                    "type": self._get_type_string(item.annotation),
                }
                
                # Extract default value
                if item.value:
                    field_info["default"] = self._get_value_string(item.value)
                
                fields.append(field_info)
        
        docstring = ast.get_docstring(node)
        
        return {
            "name": node.name,
            "fields": fields,
            "docstring": docstring,
        }

    def _get_type_string(self, annotation) -> str:
        """Convert AST annotation to type string."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                return annotation.value.id
        return "Any"

    def _get_value_string(self, value) -> str:
        """Convert AST value to string."""
        if isinstance(value, ast.Constant):
            return str(value.value)
        elif isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                return f"{value.func.id}(...)"
        return "..."

    def _extract_env_vars(self, content: str) -> list[dict]:
        """Extract environment variables from .env.example."""
        vars = []
        
        for line in content.split("\n"):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            
            # Parse KEY=value
            if "=" in line:
                key, value = line.split("=", 1)
                vars.append({
                    "name": key.strip(),
                    "example": value.strip(),
                })
        
        return vars
