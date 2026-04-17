"""Architecture generator."""

from __future__ import annotations

from typing import Any

from .base import BaseGenerator


class ArchitectureGenerator(BaseGenerator):
    """Generate system architecture documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate architecture overview with component diagram."""
        
        # Analyze project structure
        components = self._identify_components()
        layers = self._identify_layers()
        
        if not components:
            return None
        
        content = """# System Architecture

## Architecture Overview

This document describes the high-level architecture of the system,
including its components, layers, and their relationships.

"""
        
        # Add architecture diagram (Mermaid)
        if components:
            content += self._generate_architecture_diagram(components)
        
        # Add layer description
        if layers:
            content += "\n## Architectural Layers\n\n"
            for layer in layers:
                content += f"### {layer['name']}\n\n"
                content += f"{layer['description']}\n\n"
                if layer.get('components'):
                    content += "**Components**: " + ", ".join(layer['components']) + "\n\n"
        
        # Add component descriptions
        if components:
            content += "## Components\n\n"
            for component in components:
                content += f"### {component['name']}\n\n"
                content += f"**Purpose**: {component['purpose']}\n\n"
                if component.get('path'):
                    content += f"**Location**: `{component['path']}`\n\n"
        
        content += """## Integration Points

The system integrates with:
- Database (for persistence)
- External APIs (if applicable)
- File system (for storage)

## Data Flow

Data flows through the system in the following pattern:
1. Request received at API layer
2. Validation and processing in service layer
3. Data persistence in database layer
4. Response returned to client
"""
        
        return {
            "title": "System Architecture",
            "content": content,
            "tags": ["architecture", "reverse-engineering", "design"],
            "doc_type": "reverse-engineering",
        }

    def _identify_components(self) -> list[dict[str, Any]]:
        """Identify major components from directory structure."""
        components = []
        
        # Look for common component directories
        component_indicators = {
            "api": "API layer - handles HTTP requests and responses",
            "routes": "API routes - defines endpoints and handlers",
            "agents": "Agent system - autonomous task execution",
            "orchestrator": "Orchestration layer - coordinates workflows",
            "quality_gates": "Quality gates - automated checks and validations",
            "security": "Security layer - authentication and authorization",
            "db": "Database layer - data models and persistence",
            "models": "Data models - domain entities",
            "services": "Service layer - business logic",
            "cli": "Command-line interface",
            "dashboard": "Web dashboard - user interface",
            "frontend": "Frontend application",
            "embedded": "Embedded components",
            "knowledge": "Knowledge management system",
        }
        
        # Check for src/ directory structure
        src_dir = self.workspace_path / "src"
        if src_dir.exists():
            for item in src_dir.rglob("*"):
                if item.is_dir():
                    dir_name = item.name.lower()
                    if dir_name in component_indicators:
                        relative_path = item.relative_to(self.workspace_path)
                        components.append({
                            "name": dir_name.title(),
                            "purpose": component_indicators[dir_name],
                            "path": str(relative_path),
                        })
        
        # Check root level directories
        for dir_name, purpose in component_indicators.items():
            dir_path = self.workspace_path / dir_name
            if dir_path.exists() and dir_path.is_dir():
                components.append({
                    "name": dir_name.title(),
                    "purpose": purpose,
                    "path": dir_name,
                })
        
        # Remove duplicates by name
        seen = set()
        unique_components = []
        for comp in components:
            if comp["name"] not in seen:
                seen.add(comp["name"])
                unique_components.append(comp)
        
        return unique_components

    def _identify_layers(self) -> list[dict[str, Any]]:
        """Identify architectural layers."""
        layers = []
        components = self._identify_components()
        component_names = [c["name"].lower() for c in components]
        
        # Presentation layer
        presentation_components = []
        for name in ["api", "routes", "cli", "dashboard", "frontend"]:
            if name in component_names:
                presentation_components.append(name.title())
        
        if presentation_components:
            layers.append({
                "name": "Presentation Layer",
                "description": "Handles user interaction and external communication",
                "components": presentation_components,
            })
        
        # Business logic layer
        business_components = []
        for name in ["agents", "orchestrator", "services"]:
            if name in component_names:
                business_components.append(name.title())
        
        if business_components:
            layers.append({
                "name": "Business Logic Layer",
                "description": "Implements core business rules and workflows",
                "components": business_components,
            })
        
        # Data layer
        data_components = []
        for name in ["db", "models"]:
            if name in component_names:
                data_components.append(name.title())
        
        if data_components:
            layers.append({
                "name": "Data Layer",
                "description": "Manages data persistence and retrieval",
                "components": data_components,
            })
        
        # Cross-cutting concerns
        crosscutting_components = []
        for name in ["security", "quality_gates", "knowledge"]:
            if name in component_names:
                crosscutting_components.append(name.title())
        
        if crosscutting_components:
            layers.append({
                "name": "Cross-Cutting Concerns",
                "description": "Provides system-wide capabilities",
                "components": crosscutting_components,
            })
        
        return layers

    def _generate_architecture_diagram(self, components: list[dict]) -> str:
        """Generate Mermaid architecture diagram."""
        diagram = """## Architecture Diagram

```mermaid
graph TB
    subgraph "Presentation Layer"
"""
        
        # Add presentation components
        presentation = [c for c in components if c["name"].lower() in ["api", "routes", "cli", "dashboard", "frontend"]]
        for comp in presentation:
            comp_id = comp["name"].replace(" ", "")
            diagram += f"        {comp_id}[{comp['name']}]\n"
        
        diagram += "    end\n\n    subgraph \"Business Logic Layer\"\n"
        
        # Add business logic components
        business = [c for c in components if c["name"].lower() in ["agents", "orchestrator", "services"]]
        for comp in business:
            comp_id = comp["name"].replace(" ", "")
            diagram += f"        {comp_id}[{comp['name']}]\n"
        
        diagram += "    end\n\n    subgraph \"Data Layer\"\n"
        
        # Add data components
        data = [c for c in components if c["name"].lower() in ["db", "models"]]
        for comp in data:
            comp_id = comp["name"].replace(" ", "")
            diagram += f"        {comp_id}[{comp['name']}]\n"
        
        diagram += "    end\n"
        
        # Add relationships (simplified)
        if presentation and business:
            pres_id = presentation[0]["name"].replace(" ", "")
            bus_id = business[0]["name"].replace(" ", "")
            diagram += f"\n    {pres_id} --> {bus_id}\n"
        
        if business and data:
            bus_id = business[0]["name"].replace(" ", "")
            data_id = data[0]["name"].replace(" ", "")
            diagram += f"    {bus_id} --> {data_id}\n"
        
        diagram += "```\n"
        
        return diagram
