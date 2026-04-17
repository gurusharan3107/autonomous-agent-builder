"""Business overview generator."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class BusinessOverviewGenerator(BaseGenerator):
    """Generate business context and domain overview.
    
    Project-agnostic: Works for any codebase by analyzing:
    - Domain models and entities
    - Business logic patterns
    - Service layer organization
    - Domain-specific terminology
    """

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate business overview from code analysis."""
        
        # Analyze domain concepts from code
        domain_concepts = self._extract_domain_concepts()
        business_entities = self._extract_business_entities()
        services = self._extract_services()
        business_rules = self._extract_business_rules()
        
        if not domain_concepts and not business_entities and not services:
            return None  # Skip if no business context found
        
        content = """# Business Overview

## Business Context

This document provides an overview of the business domain and key concepts
implemented in this system.

"""
        
        if business_entities:
            content += "## Business Entities\n\n"
            content += "Core domain entities that represent business concepts:\n\n"
            for entity in business_entities[:15]:  # Top 15
                content += f"- **{entity['name']}**"
                if entity.get('description'):
                    content += f": {entity['description']}"
                content += "\n"
            content += "\n"
        
        if services:
            content += "## Business Services\n\n"
            content += "Services that implement business logic:\n\n"
            for service in services[:10]:  # Top 10
                content += f"- **{service['name']}**"
                if service.get('description'):
                    content += f": {service['description']}"
                content += "\n"
            content += "\n"
        
        if domain_concepts:
            content += "## Domain Concepts\n\n"
            content += "Key concepts and terminology used in the domain:\n\n"
            for concept in domain_concepts[:20]:  # Top 20
                content += f"- **{concept}**\n"
            content += "\n"
        
        if business_rules:
            content += "## Business Rules\n\n"
            for rule in business_rules[:10]:  # Top 10
                content += f"### {rule['name']}\n\n"
                if rule.get('description'):
                    content += f"{rule['description']}\n\n"
        
        content += """## Business Transactions

Business transactions are implemented through:
- API endpoints (see API Documentation)
- Service layer methods
- Database transactions
- Event handlers (if applicable)

## Domain-Driven Design

The codebase follows domain-driven design principles:
- **Entities**: Core business objects with identity
- **Value Objects**: Immutable domain concepts
- **Aggregates**: Clusters of related entities
- **Services**: Business logic that doesn't belong to entities
- **Repositories**: Data access abstraction

## Business Logic Location

Business logic is typically found in:
- Service layer (`services/`, `*_service.py`)
- Domain models (`models/`, `entities/`)
- Use cases (`use_cases/`, `handlers/`)
- Controllers/Views (presentation logic)
"""
        
        return {
            "title": "Business Overview",
            "content": content,
            "tags": ["business", "domain", "reverse-engineering"],
            "doc_type": "reverse-engineering",
        }

    def _extract_business_entities(self) -> list[dict[str, str]]:
        """Extract business entities from models, entities, or domain classes."""
        entities = []
        
        # Look for model/entity files in any language
        if self._is_python_project():
            model_files = (
                self._find_files("**/models.py") +
                self._find_files("**/models/*.py") +
                self._find_files("**/entities.py") +
                self._find_files("**/entities/*.py") +
                self._find_files("**/domain/*.py")
            )
            
            for model_file in model_files[:15]:  # Limit to first 15 files
                content = self._read_file_safe(model_file)
                if not content:
                    continue
                
                # Look for class definitions
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            class_name = node.name
                            
                            # Skip base classes, internal classes, and test classes
                            if (class_name.startswith("_") or 
                                class_name in ["Base", "Model", "Entity", "BaseModel"] or
                                "Test" in class_name or "Mock" in class_name):
                                continue
                            
                            # Extract docstring
                            description = ast.get_docstring(node) or "Business entity"
                            # Get first line of docstring
                            if description:
                                description = description.split("\n")[0].strip()
                            
                            entities.append({
                                "name": class_name,
                                "description": description,
                            })
                except Exception:
                    continue
        
        # For Node.js projects, look for TypeScript interfaces/classes
        if self._is_node_project():
            ts_files = self._find_files("**/models/*.ts") + self._find_files("**/entities/*.ts")
            for ts_file in ts_files[:10]:
                content = self._read_file_safe(ts_file)
                if content:
                    # Simple regex-based extraction for TypeScript
                    import re
                    matches = re.findall(r'(?:interface|class)\s+(\w+)', content)
                    for match in matches:
                        if not match.startswith("_"):
                            entities.append({"name": match, "description": "Business entity"})
        
        return entities

    def _extract_services(self) -> list[dict[str, str]]:
        """Extract business services."""
        services = []
        
        if self._is_python_project():
            service_files = (
                self._find_files("**/services.py") +
                self._find_files("**/services/*.py") +
                self._find_files("**/*_service.py")
            )
            
            for service_file in service_files[:10]:
                content = self._read_file_safe(service_file)
                if not content:
                    continue
                
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            if "service" in node.name.lower():
                                description = ast.get_docstring(node) or "Business service"
                                if description:
                                    description = description.split("\n")[0].strip()
                                
                                services.append({
                                    "name": node.name,
                                    "description": description,
                                })
                except Exception:
                    continue
        
        return services

    def _extract_business_rules(self) -> list[dict[str, str]]:
        """Extract business rules from validators, constraints, etc."""
        rules = []
        
        if self._is_python_project():
            rule_files = (
                self._find_files("**/validators.py") +
                self._find_files("**/validators/*.py") +
                self._find_files("**/rules.py") +
                self._find_files("**/constraints.py")
            )
            
            for rule_file in rule_files[:5]:
                content = self._read_file_safe(rule_file)
                if not content:
                    continue
                
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                            if "validate" in node.name.lower() or "check" in node.name.lower():
                                description = ast.get_docstring(node)
                                if description:
                                    rules.append({
                                        "name": node.name.replace("_", " ").title(),
                                        "description": description.split("\n")[0].strip(),
                                    })
                except Exception:
                    continue
        
        return rules

    def _extract_domain_concepts(self) -> list[str]:
        """Extract domain concepts from code (class names, function names, etc.)."""
        concepts = set()
        
        # Python: Extract from class and function names
        if self._is_python_project():
            py_files = self._find_files("**/*.py", max_depth=4)
            
            for py_file in py_files[:30]:  # Limit to first 30 files
                # Skip test files, migrations, and generated files
                if any(skip in py_file.name.lower() for skip in ["test", "migration", "__pycache__", "alembic"]):
                    continue
                
                content = self._read_file_safe(py_file)
                if not content:
                    continue
                
                try:
                    tree = ast.parse(content)
                    
                    # Extract class names
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            class_name = node.name
                            if not class_name.startswith("_") and len(class_name) > 3:
                                # Skip common base classes
                                if class_name not in ["Base", "Model", "Config", "Settings", "Test"]:
                                    concepts.add(class_name)
                        
                        # Extract function names that look like domain operations
                        elif isinstance(node, ast.FunctionDef):
                            func_name = node.name
                            # Look for domain verbs
                            if any(verb in func_name.lower() for verb in 
                                   ["create", "update", "delete", "process", "calculate", 
                                    "validate", "approve", "reject", "submit", "execute"]):
                                # Extract the noun part
                                for verb in ["create_", "update_", "delete_", "process_", 
                                           "calculate_", "validate_", "approve_", "reject_"]:
                                    if func_name.startswith(verb):
                                        concept = func_name[len(verb):].replace("_", " ").title()
                                        if len(concept) > 3:
                                            concepts.add(concept)
                except Exception:
                    continue
        
        return sorted(list(concepts))[:25]  # Return top 25
