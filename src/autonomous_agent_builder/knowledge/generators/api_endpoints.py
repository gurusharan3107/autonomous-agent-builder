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
        
        # Find route files
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
        
        # Group by prefix/module
        grouped = self._group_endpoints(endpoints)
        
        content = """# API Endpoints

## Overview

This document describes all REST API endpoints, their methods, parameters,
and expected responses.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: Configured via environment

"""
        
        # Add endpoints by group
        for group_name, group_endpoints in grouped.items():
            content += f"## {group_name}\n\n"
            
            for endpoint in group_endpoints:
                content += f"### {endpoint['method']} {endpoint['path']}\n\n"
                
                if endpoint.get('docstring'):
                    content += f"{endpoint['docstring']}\n\n"
                
                if endpoint.get('parameters'):
                    content += "**Parameters**:\n\n"
                    for param in endpoint['parameters']:
                        content += f"- `{param['name']}` ({param['type']})"
                        if param.get('required'):
                            content += " - Required"
                        if param.get('description'):
                            content += f" - {param['description']}"
                        content += "\n"
                    content += "\n"
                
                if endpoint.get('response'):
                    content += f"**Response**: {endpoint['response']}\n\n"
        
        content += """## Authentication

Authentication details (if applicable):
- API keys
- JWT tokens
- OAuth

## Error Responses

Standard error response format:
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

Common status codes:
- 200: Success
- 201: Created
- 400: Bad Request
- 401: Unauthorized
- 404: Not Found
- 500: Internal Server Error
"""
        
        return {
            "title": "API Endpoints",
            "content": content,
            "tags": ["api", "endpoints", "rest", "reverse-engineering"],
            "doc_type": "reverse-engineering",
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
            group_name = path_parts[0].title() if path_parts else "Root"
            
            if group_name not in groups:
                groups[group_name] = []
            
            groups[group_name].append(endpoint)
        
        # Sort groups
        return dict(sorted(groups.items()))
