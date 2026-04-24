"""SDK MCP server factories for builder and workspace tool bridges."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.tools import workspace_tools
from autonomous_agent_builder.services import builder_tool_service

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
_TASK_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "feature_id": {"type": "string"},
        "status": {"type": "string"},
        "limit": {"type": "integer"},
    },
    "required": ["feature_id"],
    "additionalProperties": False,
}
_TASK_ID_SCHEMA = {
    "type": "object",
    "properties": {"task_id": {"type": "string"}},
    "required": ["task_id"],
    "additionalProperties": False,
}
_KB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "doc_type": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["query"],
    "additionalProperties": False,
}
_KB_SHOW_SCHEMA = {
    "type": "object",
    "properties": {"doc_id": {"type": "string"}},
    "required": ["doc_id"],
    "additionalProperties": False,
}
_KB_CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string"},
        "sample_title": {"type": "string"},
    },
    "additionalProperties": False,
}
_KB_LINT_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string"},
        "content": {"type": "string"},
        "doc_id": {"type": "string"},
    },
    "required": ["doc_type", "content"],
    "additionalProperties": False,
}
_KB_VALIDATE_SCHEMA = {
    "type": "object",
    "properties": {"kb_dir": {"type": "string"}},
    "additionalProperties": False,
}
_KB_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "kb_dir": {"type": "string"},
        "scope": {"type": "string"},
        "doc_slug": {"type": "string"},
        "force": {"type": "boolean"},
        "run_validation": {"type": "boolean"},
    },
    "additionalProperties": False,
}
_KB_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
        "task_id": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "family": {"type": "string"},
        "linked_feature": {"type": "string"},
        "feature_id": {"type": "string"},
        "refresh_required": {"type": "boolean"},
        "documented_against_commit": {"type": "string"},
        "documented_against_ref": {"type": "string"},
        "owned_paths": {"type": "array", "items": {"type": "string"}},
        "verified_with": {"type": "string"},
        "last_verified_at": {"type": "string"},
        "lifecycle_status": {"type": "string"},
        "superseded_by": {"type": "string"},
        "source_url": {"type": "string"},
        "source_title": {"type": "string"},
        "source_author": {"type": "string"},
        "date_published": {"type": "string"},
    },
    "required": ["doc_type", "title", "content"],
    "additionalProperties": False,
}
_KB_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_id": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "family": {"type": "string"},
        "linked_feature": {"type": "string"},
        "feature_id": {"type": "string"},
        "refresh_required": {"type": "boolean"},
        "documented_against_commit": {"type": "string"},
        "documented_against_ref": {"type": "string"},
        "owned_paths": {"type": "array", "items": {"type": "string"}},
        "verified_with": {"type": "string"},
        "last_verified_at": {"type": "string"},
        "lifecycle_status": {"type": "string"},
        "superseded_by": {"type": "string"},
        "source_url": {"type": "string"},
        "source_title": {"type": "string"},
        "source_author": {"type": "string"},
        "date_published": {"type": "string"},
    },
    "required": ["doc_id"],
    "additionalProperties": False,
}
_MEMORY_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "entity": {"type": "string"},
    },
    "required": ["query"],
    "additionalProperties": False,
}
_MEMORY_SHOW_SCHEMA = {
    "type": "object",
    "properties": {"slug": {"type": "string"}},
    "required": ["slug"],
    "additionalProperties": False,
}
_MEMORY_ADD_SCHEMA = {
    "type": "object",
    "properties": {
        "mem_type": {"type": "string"},
        "phase": {"type": "string"},
        "entity": {"type": "string"},
        "tags": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["mem_type", "phase", "entity", "tags", "title", "content"],
    "additionalProperties": False,
}
_RUN_TESTS_SCHEMA = {
    "type": "object",
    "properties": {"test_pattern": {"type": "string"}},
    "additionalProperties": False,
}
_RUN_LINTER_SCHEMA = {
    "type": "object",
    "properties": {"fix": {"type": "boolean"}},
    "additionalProperties": False,
}
_RUN_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "argv": {"type": "array", "items": {"type": "string"}},
        "timeout_sec": {"type": "integer"},
    },
    "required": ["argv"],
    "additionalProperties": False,
}
_READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {"file_path": {"type": "string"}},
    "required": ["file_path"],
    "additionalProperties": False,
}
_LIST_DIRECTORY_SCHEMA = {
    "type": "object",
    "properties": {"relative_path": {"type": "string"}},
    "additionalProperties": False,
}


def _project_root(project_root: str | None = None) -> str:
    if project_root:
        return project_root
    env_root = os.environ.get("AAB_PROJECT_ROOT", "").strip()
    if env_root:
        return env_root
    return str(Path.cwd())


def build_default_mcp_servers(
    *, workspace_path: str, project_root: str | None = None
) -> dict[str, Any]:
    """Create in-process SDK MCP servers for repo-local builder and workspace tools."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    resolved_project_root = _project_root(project_root)

    @tool("board", "Get the current task pipeline board status.", _EMPTY_SCHEMA)
    async def board(_args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_board(project_root=resolved_project_root)

    @tool("task_list", "List tasks for a feature.", _TASK_LIST_SCHEMA)
    async def task_list(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_task_list(
            args["feature_id"],
            args.get("status", ""),
            int(args.get("limit", 50)),
            project_root=resolved_project_root,
        )

    @tool("task_show", "Show task details, including retries and gate status.", _TASK_ID_SCHEMA)
    async def task_show(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_task_show(
            args["task_id"], project_root=resolved_project_root
        )

    @tool("task_status", "Quick status check for a task.", _TASK_ID_SCHEMA)
    async def task_status(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_task_status(
            args["task_id"], project_root=resolved_project_root
        )

    @tool("task_dispatch", "Dispatch a task through the SDLC pipeline.", _TASK_ID_SCHEMA)
    async def task_dispatch(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_task_dispatch(
            args["task_id"], project_root=resolved_project_root
        )

    @tool("metrics", "Get project metrics such as cost, runs, and gate pass rate.", _EMPTY_SCHEMA)
    async def metrics(_args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_metrics(project_root=resolved_project_root)

    @tool("kb_search", "Search project knowledge base documents.", _KB_SEARCH_SCHEMA)
    async def kb_search(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_search(
            args["query"],
            args.get("doc_type", ""),
            args.get("tags"),
            project_root=resolved_project_root,
        )

    @tool("kb_show", "Show a project knowledge base document by ID.", _KB_SHOW_SCHEMA)
    async def kb_show(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_show(
            args["doc_id"],
            project_root=resolved_project_root,
        )

    @tool(
        "kb_contract",
        "Show the canonical KB markdown contract and sample template for a doc type.",
        _KB_CONTRACT_SCHEMA,
    )
    async def kb_contract(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_contract(
            args.get("doc_type", "system-docs"),
            args.get("sample_title", "Document Title"),
            project_root=resolved_project_root,
        )

    @tool(
        "kb_lint",
        "Lint candidate KB markdown against the canonical contract before publish.",
        _KB_LINT_SCHEMA,
    )
    async def kb_lint(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_lint(
            args["doc_type"],
            args["content"],
            args.get("doc_id", ""),
            project_root=resolved_project_root,
        )

    @tool(
        "kb_validate",
        "Run deterministic validation on the repo-local knowledge base.",
        _KB_VALIDATE_SCHEMA,
    )
    async def kb_validate(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_validate(
            args.get("kb_dir", "system-docs"),
            project_root=resolved_project_root,
        )

    @tool(
        "kb_extract",
        "Run the canonical builder knowledge extraction flow for repo-local system docs.",
        _KB_EXTRACT_SCHEMA,
    )
    async def kb_extract(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_extract(
            args.get("kb_dir", "system-docs"),
            args.get("scope", "full"),
            args.get("doc_slug", ""),
            bool(args.get("force", False)),
            bool(args.get("run_validation", True)),
            project_root=resolved_project_root,
        )

    @tool(
        "kb_add",
        "Publish a repo-local knowledge base document through shared builder services.",
        _KB_ADD_SCHEMA,
    )
    async def kb_add(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_add(
            args["doc_type"],
            args["title"],
            args["content"],
            args.get("task_id", ""),
            args.get("tags"),
            args.get("family", ""),
            args.get("linked_feature", ""),
            args.get("feature_id", ""),
            args.get("refresh_required"),
            args.get("documented_against_commit", ""),
            args.get("documented_against_ref", ""),
            args.get("owned_paths"),
            args.get("verified_with", ""),
            args.get("last_verified_at", ""),
            args.get("lifecycle_status", ""),
            args.get("superseded_by", ""),
            args.get("source_url", ""),
            args.get("source_title", ""),
            args.get("source_author", ""),
            args.get("date_published", ""),
            project_root=resolved_project_root,
        )

    @tool(
        "kb_update",
        "Update a repo-local knowledge base document through shared builder services.",
        _KB_UPDATE_SCHEMA,
    )
    async def kb_update(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_kb_update(
            args["doc_id"],
            args.get("title", ""),
            args.get("content", ""),
            args.get("tags"),
            args.get("family", ""),
            args.get("linked_feature", ""),
            args.get("feature_id", ""),
            args.get("refresh_required"),
            args.get("documented_against_commit", ""),
            args.get("documented_against_ref", ""),
            args.get("owned_paths"),
            args.get("verified_with", ""),
            args.get("last_verified_at", ""),
            args.get("lifecycle_status", ""),
            args.get("superseded_by", ""),
            args.get("source_url", ""),
            args.get("source_title", ""),
            args.get("source_author", ""),
            args.get("date_published", ""),
            project_root=resolved_project_root,
        )

    @tool(
        "memory_search",
        "Search project memory for decisions, patterns, and corrections.",
        _MEMORY_SEARCH_SCHEMA,
    )
    async def memory_search(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_memory_search(
            args["query"],
            args.get("entity", ""),
            project_root=resolved_project_root,
        )

    @tool("memory_show", "Show a project memory entry by slug.", _MEMORY_SHOW_SCHEMA)
    async def memory_show(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_memory_show(
            args["slug"],
            project_root=resolved_project_root,
        )

    @tool(
        "memory_add",
        "Record a project memory entry through shared builder services.",
        _MEMORY_ADD_SCHEMA,
    )
    async def memory_add(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_memory_add(
            args["mem_type"],
            args["phase"],
            args["entity"],
            args["tags"],
            args["title"],
            args["content"],
            project_root=resolved_project_root,
        )

    @tool("run_tests", "Run tests inside the isolated workspace.", _RUN_TESTS_SCHEMA)
    async def run_tests(args: dict[str, Any]) -> dict:
        return await workspace_tools.run_tests(workspace_path, args.get("test_pattern", ""))

    @tool("run_linter", "Run the linter inside the isolated workspace.", _RUN_LINTER_SCHEMA)
    async def run_linter(args: dict[str, Any]) -> dict:
        return await workspace_tools.run_linter(workspace_path, bool(args.get("fix", False)))

    @tool(
        "run_command",
        "Run an argv-safe command inside the isolated workspace.",
        _RUN_COMMAND_SCHEMA,
    )
    async def run_command(args: dict[str, Any]) -> dict:
        return await workspace_tools.run_command(
            workspace_path,
            list(args["argv"]),
            int(args.get("timeout_sec", 60)),
        )

    @tool("read_file", "Read a file from the isolated workspace.", _READ_FILE_SCHEMA)
    async def read_file(args: dict[str, Any]) -> dict:
        return await workspace_tools.read_file(workspace_path, args["file_path"])

    @tool(
        "list_directory", "List a directory within the isolated workspace.", _LIST_DIRECTORY_SCHEMA
    )
    async def list_directory(args: dict[str, Any]) -> dict:
        return await workspace_tools.list_directory(workspace_path, args.get("relative_path", "."))

    @tool(
        "get_project_info",
        "Detect language and build files for the isolated workspace.",
        _EMPTY_SCHEMA,
    )
    async def get_project_info(_args: dict[str, Any]) -> dict:
        return await workspace_tools.get_project_info(workspace_path)

    builder_server = create_sdk_mcp_server(
        name="builder",
        tools=[
            board,
            task_list,
            task_show,
            task_status,
            task_dispatch,
            metrics,
            kb_search,
            kb_show,
            kb_validate,
            kb_extract,
            kb_add,
            kb_update,
            memory_search,
            memory_show,
            memory_add,
        ],
    )
    workspace_server = create_sdk_mcp_server(
        name="workspace",
        tools=[
            run_tests,
            run_linter,
            run_command,
            read_file,
            list_directory,
            get_project_info,
        ],
    )

    return {
        "builder": builder_server,
        "workspace": workspace_server,
    }
