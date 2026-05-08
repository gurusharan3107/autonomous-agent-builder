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
        
        domain_concepts = self._extract_domain_concepts()
        business_entities = self._extract_business_entities()
        services = self._extract_services()
        business_rules = self._extract_business_rules()
        
        if not domain_concepts and not business_entities and not services:
            return None  # Skip if no business context found
        
        overview_parts = [
            "This document summarizes the domain concepts that show up in entities, service names, and business-oriented rules across the repository.",
            "Use it to orient around what the system appears to be doing before changing workflows that cut across multiple modules.",
        ]
        if business_entities:
            overview_parts.append(
                f"The current scan found {len(business_entities)} candidate entities that represent the main business nouns in the codebase."
            )
        overview = " ".join(overview_parts)
        boundaries = (
            "Business context is inferred from entities, service modules, validators, and route-adjacent terminology rather than from one explicit product brief. "
            "Treat those model and service files as the owning surfaces when confirming or changing domain behavior."
        )
        invariants = [
            "- Preserve the relationship between domain entities, service-layer operations, and validation rules when changing business behavior.",
            "- Re-check inferred business terms against actual code owners before treating them as product truth in user-facing docs.",
        ]
        if business_rules:
            invariants.append("- Refresh rule descriptions when validators, constraints, or policy checks change so the inferred domain guidance stays current.")

        evidence_lines: list[str] = []
        if business_entities:
            evidence_lines.append("### Business entities")
            evidence_lines.append(
                "These classes and models are the clearest code-level nouns for the business domain inferred from the repository."
            )
            for entity in business_entities[:15]:
                line = f"- **{entity['name']}**"
                if entity.get('description'):
                    line += f": {entity['description']}"
                evidence_lines.append(line)
            evidence_lines.append("")
        if services:
            evidence_lines.append("### Business services")
            evidence_lines.append(
                "Service-layer names reveal where the codebase centralizes business decisions instead of leaving them scattered across handlers."
            )
            for service in services[:10]:
                line = f"- **{service['name']}**"
                if service.get('description'):
                    line += f": {service['description']}"
                evidence_lines.append(line)
            evidence_lines.append("")
        if domain_concepts:
            evidence_lines.append("### Domain concepts")
            for concept in domain_concepts[:20]:
                evidence_lines.append(f"- **{concept}**")
            evidence_lines.append("")
        if business_rules:
            evidence_lines.append("### Business rules")
            for rule in business_rules[:10]:
                evidence_lines.append(f"- **{rule['name']}**: {rule.get('description', '')}".rstrip())
        evidence_lines.extend(
            [
                "",
                "This evidence is intentionally inferential rather than declarative, so operators should confirm domain wording against the owning services and models before treating it as externally published product language.",
            ]
        )

        content = "\n\n".join(
            [
                "# Business Overview",
                "## Overview",
                overview,
                "## Boundaries",
                boundaries,
                "## Invariants",
                "\n".join(invariants),
                "## Evidence",
                "\n".join(evidence_lines).strip(),
                "## Change guidance",
                "Confirm inferred domain terms against the owning models, services, and validators before editing workflows, then rerun `builder knowledge extract --force` after business logic changes.",
            ]
        )
        
        return {
            "title": "Business Overview",
            "content": content,
            "tags": ["business", "domain", "system-docs", "seed"],
            "doc_type": "system-docs",
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
