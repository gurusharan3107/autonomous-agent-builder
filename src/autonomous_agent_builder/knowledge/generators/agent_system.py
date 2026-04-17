"""Agent system generator - captures agent definitions, tools, and hooks."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class AgentSystemGenerator(BaseGenerator):
    """Generate agent system documentation.
    
    Captures:
    - Agent definitions (if using agent-as-artifact pattern)
    - Tool registry and available tools
    - Hook system (PreToolUse/PostToolUse)
    - Agent SDK integration
    """

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate agent system documentation."""
        
        if not self._is_python_project():
            return None
        
        # Find agent-related files
        agent_defs = self._extract_agent_definitions()
        tools = self._extract_tools()
        hooks = self._extract_hooks()
        
        if not agent_defs and not tools and not hooks:
            return None
        
        content = """# Agent System

## Overview

This document describes the agent system, including agent definitions,
available tools, and security hooks.

"""
        
        # Add agent definitions
        if agent_defs:
            content += "## Agent Definitions\n\n"
            content += "The system uses an agent-as-artifact pattern where agents are versioned and immutable at execution.\n\n"
            
            for agent in agent_defs:
                content += f"### {agent['name']}\n\n"
                if agent.get('description'):
                    content += f"{agent['description']}\n\n"
                
                if agent.get('model'):
                    content += f"**Model**: {agent['model']}\n\n"
                
                if agent.get('max_turns'):
                    content += f"**Max Turns**: {agent['max_turns']}\n\n"
                
                if agent.get('max_budget'):
                    content += f"**Max Budget**: ${agent['max_budget']}\n\n"
                
                if agent.get('tools'):
                    content += f"**Tools**: {', '.join(agent['tools'][:10])}"
                    if len(agent['tools']) > 10:
                        content += f" (and {len(agent['tools']) - 10} more)"
                    content += "\n\n"
        
        # Add tools
        if tools:
            content += "## Available Tools\n\n"
            content += "Tools are organized into categories:\n\n"
            
            # Group tools by category
            tool_categories = {}
            for tool in tools:
                category = tool.get('category', 'Other')
                if category not in tool_categories:
                    tool_categories[category] = []
                tool_categories[category].append(tool)
            
            for category, category_tools in sorted(tool_categories.items()):
                content += f"### {category}\n\n"
                for tool in category_tools[:15]:  # Top 15 per category
                    content += f"- **{tool['name']}**"
                    if tool.get('description'):
                        content += f": {tool['description']}"
                    content += "\n"
                content += "\n"
        
        # Add hooks
        if hooks:
            content += "## Security Hooks\n\n"
            content += "The system uses SDK hooks for security and audit:\n\n"
            
            for hook in hooks:
                content += f"### {hook['name']}\n\n"
                if hook.get('type'):
                    content += f"**Type**: {hook['type']}\n\n"
                if hook.get('description'):
                    content += f"{hook['description']}\n\n"
                if hook.get('purpose'):
                    content += f"**Purpose**: {hook['purpose']}\n\n"
        
        content += """## Agent Execution Flow

1. **Agent Selection**: Orchestrator selects agent based on task phase
2. **Tool Registry**: Tools are registered and validated
3. **Hook Registration**: Security hooks are attached
4. **Execution**: Agent runs with SDK query() method
5. **Audit**: All tool calls are logged via PostToolUse hook

## Tool Access Control

- **Read-only tools**: Glob, Grep, Read
- **Write tools**: Write, Edit (workspace-restricted)
- **Execution tools**: Bash (argv-validated)
- **MCP tools**: Custom tools via Model Context Protocol

## Security Constraints

- Workspace boundary enforcement (PreToolUse)
- Bash command validation (no shell metacharacters)
- Tool call audit logging (PostToolUse)
- Permission caching with TTL
"""
        
        return {
            "title": "Agent System",
            "content": content,
            "tags": ["agents", "tools", "hooks", "security", "reverse-engineering"],
            "doc_type": "reverse-engineering",
        }

    def _extract_agent_definitions(self) -> list[dict]:
        """Extract agent definitions from definitions.py."""
        agents = []
        
        # Look for definitions.py
        def_files = self._find_files("**/definitions.py", max_depth=4)
        
        for def_file in def_files:
            content = self._read_file_safe(def_file)
            if not content or "AgentDefinition" not in content:
                continue
            
            try:
                tree = ast.parse(content)
                
                # Look for AGENT_DEFINITIONS dict in module body
                for node in tree.body:
                    # Handle both regular assignment and annotated assignment
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        # Get target name
                        target_name = None
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    target_name = target.id
                        elif isinstance(node, ast.AnnAssign):
                            if isinstance(node.target, ast.Name):
                                target_name = node.target.id
                        
                        if target_name == "AGENT_DEFINITIONS":
                            # Found the dict, extract agents
                            if isinstance(node.value, ast.Dict):
                                for key, value in zip(node.value.keys, node.value.values):
                                    if isinstance(key, ast.Constant) and isinstance(value, ast.Call):
                                        agent_info = self._extract_agent_from_call(key.value, value)
                                        if agent_info:
                                            agents.append(agent_info)
            except Exception:
                continue
        
        return agents

    def _extract_agent_from_call(self, name: str, call: ast.Call) -> dict | None:
        """Extract agent info from AgentDefinition() call."""
        agent = {"name": name}
        
        # Extract keyword arguments
        for keyword in call.keywords:
            if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                agent["description"] = keyword.value.value
            elif keyword.arg == "model" and isinstance(keyword.value, ast.Constant):
                agent["model"] = keyword.value.value
            elif keyword.arg == "max_turns" and isinstance(keyword.value, ast.Constant):
                agent["max_turns"] = keyword.value.value
            elif keyword.arg == "max_budget_usd" and isinstance(keyword.value, ast.Constant):
                agent["max_budget"] = keyword.value.value
            elif keyword.arg == "tools" and isinstance(keyword.value, ast.Tuple):
                tools = []
                for elt in keyword.value.elts:
                    if isinstance(elt, ast.Constant):
                        tools.append(elt.value)
                agent["tools"] = tools
        
        return agent if len(agent) > 1 else None

    def _extract_tools(self) -> list[dict]:
        """Extract tool definitions."""
        tools = []
        
        # Look for tool files
        tool_files = (
            self._find_files("**/tools.py", max_depth=4) +
            self._find_files("**/tools/*.py", max_depth=5) +
            self._find_files("**/tool_registry.py", max_depth=4)
        )
        
        for tool_file in tool_files:
            content = self._read_file_safe(tool_file)
            if not content:
                continue
            
            # Look for @tool decorator or tool definitions
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Check for @tool decorator
                        has_tool_decorator = any(
                            isinstance(d, ast.Name) and d.id == "tool"
                            for d in node.decorator_list
                        )
                        
                        if has_tool_decorator or "tool" in node.name.lower():
                            docstring = ast.get_docstring(node)
                            tools.append({
                                "name": node.name,
                                "description": docstring.split("\n")[0] if docstring else "",
                                "category": self._categorize_tool(node.name),
                            })
            except Exception:
                continue
        
        return tools[:30]  # Limit to 30 tools

    def _categorize_tool(self, tool_name: str) -> str:
        """Categorize tool by name."""
        name_lower = tool_name.lower()
        
        if any(word in name_lower for word in ["read", "get", "list", "show", "search"]):
            return "Read-Only"
        elif any(word in name_lower for word in ["write", "create", "update", "delete", "edit"]):
            return "Write"
        elif any(word in name_lower for word in ["bash", "run", "execute", "command"]):
            return "Execution"
        elif "workspace" in name_lower:
            return "Workspace"
        elif "git" in name_lower:
            return "Git"
        elif any(word in name_lower for word in ["kb", "knowledge", "memory"]):
            return "Knowledge"
        else:
            return "Other"

    def _extract_hooks(self) -> list[dict]:
        """Extract hook definitions."""
        hooks = []
        
        # Look for hooks.py
        hook_files = self._find_files("**/hooks.py", max_depth=4)
        
        for hook_file in hook_files:
            content = self._read_file_safe(hook_file)
            if not content:
                continue
            
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.AsyncFunctionDef):
                        # Check if it's a hook function
                        if "hook" in node.name.lower() or any(
                            param.arg == "context" for param in node.args.args
                        ):
                            docstring = ast.get_docstring(node)
                            
                            # Determine hook type
                            hook_type = "Unknown"
                            if "pretooluse" in node.name.lower() or "pre_tool" in node.name.lower():
                                hook_type = "PreToolUse"
                            elif "posttooluse" in node.name.lower() or "post_tool" in node.name.lower():
                                hook_type = "PostToolUse"
                            
                            hooks.append({
                                "name": node.name.replace("_", " ").title(),
                                "type": hook_type,
                                "description": docstring,
                                "purpose": docstring.split("\n")[0] if docstring else "",
                            })
            except Exception:
                continue
        
        return hooks
