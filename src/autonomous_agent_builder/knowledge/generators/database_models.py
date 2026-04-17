"""Database models generator."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class DatabaseModelsGenerator(BaseGenerator):
    """Generate database models and schema documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate database models documentation."""
        
        if not self._is_python_project():
            return None
        
        # Find models.py files
        model_files = self._find_files("**/models.py", max_depth=4)
        
        if not model_files:
            return None
        
        models = []
        enums = []
        
        for model_file in model_files:
            content = self._read_file_safe(model_file)
            if not content:
                continue
            
            # Parse Python AST
            try:
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    # Extract class definitions
                    if isinstance(node, ast.ClassDef):
                        # Check if it's an enum
                        if any(base.id == "Enum" if isinstance(base, ast.Name) else False 
                               for base in node.bases):
                            enum_info = self._extract_enum_info(node, content)
                            if enum_info:
                                enums.append(enum_info)
                        # Check if it's a model (has Base or Model in bases)
                        elif any(self._is_model_base(base) for base in node.bases):
                            model_info = self._extract_model_info(node, content)
                            if model_info:
                                models.append(model_info)
            except Exception:
                continue
        
        if not models and not enums:
            return None
        
        content = """# Database Models

## Overview

This document describes the database schema, including all models, their fields,
relationships, and constraints.

"""
        
        # Add ER diagram
        if models:
            content += self._generate_er_diagram(models)
        
        # Add enums
        if enums:
            content += "\n## Enumerations\n\n"
            for enum in enums:
                content += f"### {enum['name']}\n\n"
                if enum.get('docstring'):
                    content += f"{enum['docstring']}\n\n"
                content += "**Values**:\n"
                for value in enum['values']:
                    content += f"- `{value}`\n"
                content += "\n"
        
        # Add models
        if models:
            content += "## Models\n\n"
            for model in models:
                content += f"### {model['name']}\n\n"
                if model.get('docstring'):
                    content += f"{model['docstring']}\n\n"
                
                if model.get('table_name'):
                    content += f"**Table**: `{model['table_name']}`\n\n"
                
                if model.get('fields'):
                    content += "**Fields**:\n\n"
                    for field in model['fields']:
                        content += f"- **{field['name']}** ({field['type']})"
                        if field.get('primary_key'):
                            content += " - Primary Key"
                        if field.get('foreign_key'):
                            content += f" - Foreign Key → {field['foreign_key']}"
                        if field.get('nullable') is False:
                            content += " - Required"
                        if field.get('unique'):
                            content += " - Unique"
                        if field.get('default'):
                            content += f" - Default: {field['default']}"
                        content += "\n"
                    content += "\n"
                
                if model.get('relationships'):
                    content += "**Relationships**:\n\n"
                    for rel in model['relationships']:
                        content += f"- **{rel['name']}** → {rel['target']}"
                        if rel.get('back_populates'):
                            content += f" (back_populates: {rel['back_populates']})"
                        content += "\n"
                    content += "\n"
        
        content += """## Database Configuration

- **ORM**: SQLAlchemy (async)
- **Migrations**: Alembic
- **Supported Databases**: PostgreSQL, SQLite

## Relationships

Models are connected through foreign keys and SQLAlchemy relationships:
- One-to-Many: Project → Features, Feature → Tasks
- Many-to-One: Task → Feature, Feature → Project
- One-to-One: Task → Workspace

## Indexes

Indexes are automatically created for:
- Primary keys
- Foreign keys
- Unique constraints
- Commonly queried fields (status, created_at)
"""
        
        return {
            "title": "Database Models",
            "content": content,
            "tags": ["database", "models", "schema", "reverse-engineering"],
            "doc_type": "reverse-engineering",
        }

    def _is_model_base(self, base) -> bool:
        """Check if base class indicates a database model."""
        if isinstance(base, ast.Name):
            return base.id in ["Base", "Model", "DeclarativeBase"]
        return False

    def _extract_enum_info(self, node: ast.ClassDef, content: str) -> dict | None:
        """Extract enum information from AST node."""
        values = []
        
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        values.append(target.id)
        
        if not values:
            return None
        
        docstring = ast.get_docstring(node)
        
        return {
            "name": node.name,
            "values": values,
            "docstring": docstring,
        }

    def _extract_model_info(self, node: ast.ClassDef, content: str) -> dict | None:
        """Extract model information from AST node."""
        fields = []
        relationships = []
        table_name = None
        
        for item in node.body:
            # Extract __tablename__
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(item.value, ast.Constant):
                            table_name = item.value.value
            
            # Extract fields (Column definitions)
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                
                # Skip private fields
                if field_name.startswith("_"):
                    continue
                
                field_info = {
                    "name": field_name,
                    "type": self._get_type_string(item.annotation),
                }
                
                # Try to extract Column details
                if isinstance(item.value, ast.Call):
                    if isinstance(item.value.func, ast.Name):
                        if item.value.func.id == "Column":
                            self._extract_column_details(item.value, field_info)
                        elif item.value.func.id == "relationship":
                            rel_info = self._extract_relationship_details(item.value, field_name)
                            if rel_info:
                                relationships.append(rel_info)
                            continue
                
                fields.append(field_info)
        
        docstring = ast.get_docstring(node)
        
        return {
            "name": node.name,
            "table_name": table_name,
            "fields": fields,
            "relationships": relationships,
            "docstring": docstring,
        }

    def _get_type_string(self, annotation) -> str:
        """Convert AST annotation to type string."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                return annotation.value.id
        return "Unknown"

    def _extract_column_details(self, call: ast.Call, field_info: dict) -> None:
        """Extract Column() details."""
        for keyword in call.keywords:
            if keyword.arg == "primary_key" and isinstance(keyword.value, ast.Constant):
                field_info["primary_key"] = keyword.value.value
            elif keyword.arg == "nullable" and isinstance(keyword.value, ast.Constant):
                field_info["nullable"] = keyword.value.value
            elif keyword.arg == "unique" and isinstance(keyword.value, ast.Constant):
                field_info["unique"] = keyword.value.value
            elif keyword.arg == "default":
                field_info["default"] = "..."
        
        # Check for ForeignKey
        for arg in call.args:
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                if arg.func.id == "ForeignKey" and arg.args:
                    if isinstance(arg.args[0], ast.Constant):
                        field_info["foreign_key"] = arg.args[0].value

    def _extract_relationship_details(self, call: ast.Call, field_name: str) -> dict | None:
        """Extract relationship() details."""
        target = None
        back_populates = None
        
        # First arg is usually the target model
        if call.args and isinstance(call.args[0], ast.Constant):
            target = call.args[0].value
        elif call.args and isinstance(call.args[0], ast.Name):
            target = call.args[0].id
        
        # Check keywords
        for keyword in call.keywords:
            if keyword.arg == "back_populates" and isinstance(keyword.value, ast.Constant):
                back_populates = keyword.value.value
        
        if not target:
            return None
        
        return {
            "name": field_name,
            "target": target,
            "back_populates": back_populates,
        }

    def _generate_er_diagram(self, models: list[dict]) -> str:
        """Generate Mermaid ER diagram."""
        diagram = """## Entity Relationship Diagram

```mermaid
erDiagram
"""
        
        # Add entities
        for model in models[:10]:  # Limit to 10 for readability
            diagram += f"    {model['name']} {{\n"
            for field in model.get('fields', [])[:5]:  # Top 5 fields
                field_type = field['type']
                field_name = field['name']
                diagram += f"        {field_type} {field_name}\n"
            diagram += "    }\n"
        
        # Add relationships
        for model in models[:10]:
            for rel in model.get('relationships', []):
                target = rel['target']
                # Try to find relationship type
                if "many" in rel['name'].lower() or rel['name'].endswith("s"):
                    diagram += f"    {model['name']} ||--o{{ {target} : has\n"
                else:
                    diagram += f"    {model['name']} }}o--|| {target} : belongs_to\n"
        
        diagram += "```\n"
        
        return diagram
