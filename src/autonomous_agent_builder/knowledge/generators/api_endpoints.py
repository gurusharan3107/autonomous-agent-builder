"""API endpoints generator."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class APIEndpointsGenerator(BaseGenerator):
    """Generate API endpoints documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate API endpoints documentation."""
        if not self._is_python_project():
            return None
        route_files = (
            self._find_files("**/routes.py", max_depth=4) +
            self._find_files("**/routes/*.py", max_depth=5) +
            self._find_files("**/api/*.py", max_depth=4)
        )
        
        if not route_files:
            return None
        
        endpoints = []
        
        for route_file in route_files:
            content = self._read_file_safe(route_file)
            if not content:
                continue
            
            # Extract endpoints from decorators
            file_endpoints = self._extract_endpoints_from_content(content, route_file.name)
            endpoints.extend(file_endpoints)
        if not endpoints:
            return None
        grouped = self._group_endpoints(endpoints)
        overview = (
            "This document inventories the HTTP endpoints discovered from Python route modules and decorator-based handlers in the repository. "
            "It is the quickest way to see which resources exist, how they are grouped, and where API behavior is most likely to change."
        )
        boundaries = (
            "Endpoint ownership is defined by the route files scanned from `routes.py`, nested `routes/*.py`, and `api/*.py` modules. "
            "Changes to those handlers, their prefixes, or parameter signatures will change the API contract captured here."
        )
        invariants = [
            "- Keep HTTP methods, route paths, and handler signatures aligned with the actual decorated functions in the route modules.",
            "- Treat route-module prefixes and endpoint groupings as the main ownership boundary when changing API behavior.",
            "- Refresh this inventory whenever route decorators, auth requirements, or response models change.",
        ]

        evidence_lines = ["### Route inventory"]
        for group_name, group_endpoints in grouped.items():
            evidence_lines.append(f"\n#### {group_name}")
            for endpoint in group_endpoints:
                evidence_lines.append(f"- `{endpoint['method']} {endpoint['path']}`")
                if endpoint.get("docstring"):
                    evidence_lines.append(f"  - Purpose: {endpoint['docstring']}")
                if endpoint.get("parameters"):
                    evidence_lines.append("  - Parameters:")
                    for param in endpoint["parameters"]:
                        evidence_lines.append(
                            f"    - `{param['name']}` ({param['type']})"
                        )
                if endpoint.get("response"):
                    evidence_lines.append(f"  - Response: `{endpoint['response']}`")

        evidence_lines.extend(
            [
                "",
                "### Runtime notes",
                "- Development base URL is typically `http://localhost:8000` unless local config overrides it.",
                "- Authentication and error handling remain route-specific and should be verified against the owning handler before changing public behavior.",
            ]
        )

        content = "\n\n".join(
            [
                "# API Endpoints",
                "## Overview",
                overview,
                "## Boundaries",
                boundaries,
                "## Invariants",
                "\n".join(invariants),
                "## Evidence",
                "\n".join(evidence_lines),
                "## Change guidance",
                "Edit the owning route module, verify method and path changes against callers, and rerun `builder knowledge extract --force` after changing endpoint decorators or response contracts.",
            ]
        )
        
        return {
            "title": "API Endpoints",
            "content": content,
            "tags": ["api", "endpoints", "rest", "system-docs", "seed"],
            "doc_type": "system-docs",
        }

    def _extract_endpoints_from_content(self, content: str, filename: str) -> list[dict]:
        """Extract endpoints from file content."""
        endpoints = []
        
        try:
            tree = ast.parse(content)
            
            # Check all nodes in the module body (not ast.walk which misses some)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Look for route decorators
                    for decorator in node.decorator_list:
                        endpoint_info = self._extract_endpoint_from_decorator(decorator, node)
                        if endpoint_info:
                            endpoint_info['file'] = filename
                            endpoints.append(endpoint_info)
        except Exception:
            pass
        
        return endpoints

    def _extract_endpoint_from_decorator(self, decorator, func_node: ast.FunctionDef) -> dict | None:
        """Extract endpoint info from decorator."""
        method = None
        path = None
        
        # Check for @router.get(...), @app.post(...), etc.
        if isinstance(decorator, ast.Call):
            # The decorator is a function call like @router.get("/path")
            if isinstance(decorator.func, ast.Attribute):
                # Get the method name (get, post, put, delete, patch)
                method = decorator.func.attr.upper()
                
                # Get path from first argument
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    path = decorator.args[0].value
            elif isinstance(decorator.func, ast.Name):
                # Handle @get("/path") style (less common)
                method = decorator.func.id.upper()
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    path = decorator.args[0].value
        
        # Validate we found both method and path
        if not method or not path:
            return None
        
        # Only accept valid HTTP methods
        if method not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
            return None
        
        # Extract function docstring
        docstring = ast.get_docstring(func_node)
        
        # Extract parameters from function signature
        parameters = []
        for arg in func_node.args.args:
            if arg.arg not in ['self', 'cls', 'request', 'db', 'req']:
                param_info = {
                    "name": arg.arg,
                    "type": self._get_annotation_string(arg.annotation) if arg.annotation else "Any",
                }
                parameters.append(param_info)
        
        # Extract return type
        response = "JSON"
        if func_node.returns:
            response = self._get_annotation_string(func_node.returns)
        
        return {
            "method": method,
            "path": path,
            "function": func_node.name,
            "docstring": docstring,
            "parameters": parameters,
            "response": response,
        }

    def _get_annotation_string(self, annotation) -> str:
        """Convert AST annotation to string."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                return annotation.value.id
        return "Any"

    def _group_endpoints(self, endpoints: list[dict]) -> dict[str, list]:
        """Group endpoints by path prefix."""
        groups = {}
        
        for endpoint in endpoints:
            # Extract first path segment as group
            path_parts = endpoint['path'].strip('/').split('/')
            group_name = path_parts[0].title() if path_parts and path_parts[0] else "Root"
            
            if group_name not in groups:
                groups[group_name] = []
            
            groups[group_name].append(endpoint)
        
        # Sort groups
        return dict(sorted(groups.items()))
