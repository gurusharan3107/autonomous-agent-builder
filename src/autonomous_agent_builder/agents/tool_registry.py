"""ToolRegistry — the keystone contract.

Agents query this at phase start for schema discovery: available tools,
signatures, return types, constraints. Pre-computed from @tool definitions
and SDK built-in schemas.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

# SDK built-in tool schemas — agents can reference these by name.
# The SDK handles execution; we just need schema for validation + prompt injection.
SDK_BUILTIN_SCHEMAS: dict[str, ToolSchema] = {}  # populated after ToolSchema defined


@dataclass(frozen=True)
class ToolParam:
    """Single parameter in a tool's input schema."""

    name: str
    type: str  # "string", "integer", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Any = None


@dataclass(frozen=True)
class ToolSchema:
    """Complete schema for a single tool."""

    name: str
    description: str
    params: tuple[ToolParam, ...] = ()
    return_type: str = "text"  # "text", "json", "image"
    read_only: bool = False
    constraints: tuple[str, ...] = ()  # e.g., ("workspace_boundary", "argv_only")


@dataclass
class ToolRegistry:
    """Pre-computed registry of available tools per agent type.

    Built once at phase start. Agents receive this as context so they know
    exactly what tools exist, what the signatures are, and what constraints apply.
    """

    tools: dict[str, ToolSchema] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        allowed_tool_names: list[str],
        custom_tools: dict[str, Any] | None = None,
    ) -> ToolRegistry:
        """Build registry from allowed tool names + custom tool definitions.

        Args:
            allowed_tool_names: List of tool names this agent can use.
                SDK built-ins: "Read", "Edit", "Write", "Bash", "Glob", "Grep", "Agent"
                Custom: "mcp__workspace__run_tests", etc.
            custom_tools: Dict of custom tool name -> callable decorated with @tool.
        """
        registry = cls()

        for name in allowed_tool_names:
            if name.startswith("mcp__") and custom_tools and name in custom_tools:
                schema = cls._extract_custom_schema(name, custom_tools[name])
                registry.tools[name] = schema
            elif name in _SDK_BUILTINS:
                registry.tools[name] = _SDK_BUILTINS[name]
            else:
                log.warning("tool_not_found_in_registry", tool=name)

        log.info(
            "tool_registry_built",
            tool_count=len(registry.tools),
            tools=list(registry.tools.keys()),
        )
        return registry

    @staticmethod
    def _extract_custom_schema(name: str, tool_func: Any) -> ToolSchema:
        """Extract schema from a @tool decorated function."""
        doc = inspect.getdoc(tool_func) or ""
        sig = inspect.signature(tool_func)

        params = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue
            param_type = "string"
            annotation = param.annotation
            if annotation is not inspect.Parameter.empty:
                type_map = {str: "string", int: "integer", bool: "boolean", dict: "object"}
                param_type = type_map.get(annotation, "string")

            params.append(
                ToolParam(
                    name=param_name,
                    type=param_type,
                    description="",
                    required=param.default is inspect.Parameter.empty,
                    default=None if param.default is inspect.Parameter.empty else param.default,
                )
            )

        return ToolSchema(name=name, description=doc, params=tuple(params))

    def validate_tool_call(self, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """Validate a tool call shape before execution. Fail fast."""
        if tool_name not in self.tools:
            raise ToolNotAvailableError(
                f"Tool '{tool_name}' not in registry. Available: {list(self.tools.keys())}"
            )
        if args is None:
            return True

        schema = self.tools[tool_name]
        for param in schema.params:
            if param.required and param.name not in args:
                raise ToolValidationError(
                    f"Required param '{param.name}' missing for tool '{tool_name}'"
                )
        return True

    def get_tool_prompt_context(self) -> str:
        """Generate tool descriptions for injection into agent prompts.

        This gives agents awareness of their available tools at phase start.
        """
        lines = ["## Available Tools\n"]
        for schema in self.tools.values():
            constraint_str = ""
            if schema.constraints:
                constraint_str = f" [constraints: {', '.join(schema.constraints)}]"
            params_str = ""
            if schema.params:
                param_parts = []
                for p in schema.params:
                    req = "" if p.required else "?"
                    param_parts.append(f"{p.name}{req}: {p.type}")
                params_str = f"({', '.join(param_parts)})"

            lines.append(f"- **{schema.name}**{params_str}: {schema.description}{constraint_str}")

        return "\n".join(lines)

    def list_tools(self) -> list[str]:
        """Return list of available tool names."""
        return list(self.tools.keys())


class ToolNotAvailableError(Exception):
    """Raised when an agent tries to use a tool not in its registry."""


class ToolValidationError(Exception):
    """Raised when tool call arguments don't match schema."""


# ── SDK Built-in Tool Schemas ──
# These are the tools the Claude Agent SDK provides natively.

_SDK_BUILTINS: dict[str, ToolSchema] = {
    "Read": ToolSchema(
        name="Read",
        description="Read a file from the filesystem",
        params=(
            ToolParam("file_path", "string", "Absolute path to file", required=True),
            ToolParam("offset", "integer", "Line number to start from", required=False),
            ToolParam("limit", "integer", "Number of lines to read", required=False),
        ),
        read_only=True,
    ),
    "Edit": ToolSchema(
        name="Edit",
        description="Replace exact string in a file",
        params=(
            ToolParam("file_path", "string", "Absolute path to file", required=True),
            ToolParam("old_string", "string", "Text to replace", required=True),
            ToolParam("new_string", "string", "Replacement text", required=True),
        ),
        constraints=("workspace_boundary",),
    ),
    "Write": ToolSchema(
        name="Write",
        description="Write content to a file (creates or overwrites)",
        params=(
            ToolParam("file_path", "string", "Absolute path to file", required=True),
            ToolParam("content", "string", "Content to write", required=True),
        ),
        constraints=("workspace_boundary",),
    ),
    "Bash": ToolSchema(
        name="Bash",
        description="Execute a shell command",
        params=(
            ToolParam("command", "string", "The command to execute", required=True),
            ToolParam("timeout", "integer", "Timeout in ms", required=False),
        ),
        constraints=("workspace_boundary", "argv_only"),
    ),
    "Glob": ToolSchema(
        name="Glob",
        description="Find files matching a glob pattern",
        params=(
            ToolParam("pattern", "string", "Glob pattern", required=True),
            ToolParam("path", "string", "Directory to search in", required=False),
        ),
        read_only=True,
    ),
    "Grep": ToolSchema(
        name="Grep",
        description="Search file contents with regex",
        params=(
            ToolParam("pattern", "string", "Regex pattern", required=True),
            ToolParam("path", "string", "File or directory to search", required=False),
        ),
        read_only=True,
    ),
    "Agent": ToolSchema(
        name="Agent",
        description="Spawn a sub-agent for complex tasks",
        params=(
            ToolParam("prompt", "string", "Task description", required=True),
            ToolParam("description", "string", "Short description", required=True),
        ),
    ),
    # ── CLI Tools (builder CLI bridge) ──
    "mcp__builder__board": ToolSchema(
        name="mcp__builder__board",
        description="Get the current task pipeline board status",
        read_only=True,
    ),
    "mcp__builder__task_show": ToolSchema(
        name="mcp__builder__task_show",
        description="Show task details (status, retries, gates, runs)",
        params=(ToolParam("task_id", "string", "Task ID", required=True),),
        read_only=True,
    ),
    "mcp__builder__task_status": ToolSchema(
        name="mcp__builder__task_status",
        description="Quick status check for a task",
        params=(ToolParam("task_id", "string", "Task ID", required=True),),
        read_only=True,
    ),
    "mcp__builder__task_dispatch": ToolSchema(
        name="mcp__builder__task_dispatch",
        description="Dispatch a task through the SDLC pipeline",
        params=(ToolParam("task_id", "string", "Task ID", required=True),),
    ),
    "mcp__builder__metrics": ToolSchema(
        name="mcp__builder__metrics",
        description="Get project metrics (cost, tokens, runs, gate pass rate)",
        read_only=True,
    ),
    "mcp__builder__kb_add": ToolSchema(
        name="mcp__builder__kb_add",
        description="Add a document to the knowledge base",
        params=(
            ToolParam("task_id", "string", "Task ID", required=True),
            ToolParam(
                "doc_type", "string",
                "Type: adr, api_contract, schema, runbook, context",
                required=True,
            ),
            ToolParam("title", "string", "Document title", required=True),
            ToolParam("content", "string", "Document content", required=True),
        ),
    ),
    "mcp__builder__kb_search": ToolSchema(
        name="mcp__builder__kb_search",
        description="Search knowledge base documents",
        params=(
            ToolParam("query", "string", "Search query", required=True),
            ToolParam("doc_type", "string", "Filter by type", required=False),
        ),
        read_only=True,
    ),
    "mcp__builder__kb_show": ToolSchema(
        name="mcp__builder__kb_show",
        description="Get a knowledge base document by ID",
        params=(ToolParam("doc_id", "string", "Document ID", required=True),),
        read_only=True,
    ),
    "mcp__builder__memory_search": ToolSchema(
        name="mcp__builder__memory_search",
        description="Search project memory for decisions, patterns, corrections",
        params=(
            ToolParam("query", "string", "Search query", required=True),
            ToolParam("entity", "string", "Filter by entity", required=False),
        ),
        read_only=True,
    ),
    "mcp__builder__memory_show": ToolSchema(
        name="mcp__builder__memory_show",
        description="Get a memory entry by slug",
        params=(ToolParam("slug", "string", "Memory slug", required=True),),
        read_only=True,
    ),
}
