"""SDK MCP server factories for builder and workspace tool bridges."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.tools import browser_tools, workspace_tools
from autonomous_agent_builder.services import builder_tool_service


def _to_mcp(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap a plain handler result in the MCP ``content`` envelope the SDK
    requires. Without ``content`` the SDK ``call_tool`` handler returns an empty
    ``CallToolResult`` and the model receives nothing. ``builder_tool_service``
    already returns this envelope; the browser tools return plain dicts, so wrap
    them here at the SDK boundary (keeps browser_tools.py cleanly testable)."""
    if "content" in result:
        return result
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


# ── Common param aliases that cause "not allowed" retry burn ──────────────────
# Map of tool_name -> {wrong_param: correct_param} for the most common
# model-side confusions seen in builder logs.  validate_mcp_args() uses this
# table to produce self-correcting error messages before the call reaches the
# handler, cutting retry cycles when the model uses a wrong param name.
_PARAM_ALIASES: dict[str, dict[str, str]] = {
    "run_tests": {"test_p": "test_pattern", "pattern": "test_pattern", "path": "test_pattern"},
    "read_file": {"path": "file_path", "file": "file_path", "filepath": "file_path"},
    "list_directory": {
        "path": "relative_path",
        "dir": "relative_path",
        "directory": "relative_path",
    },
    "task_list": {
        "item_id": "feature_id",
        "task_id": "feature_id",
        "project_id": "feature_id",
    },
    "task_show": {"id": "task_id", "task": "task_id"},
    "task_status": {"id": "task_id", "task": "task_id"},
    "task_dispatch": {"id": "task_id", "task": "task_id"},
    "task_recover": {"id": "task_id", "task": "task_id"},
    "backlog_item_show": {"id": "item_id", "item": "item_id", "backlog_id": "item_id"},
    "backlog_item_update": {"id": "item_id", "item": "item_id"},
    "kb_show": {"id": "doc_id", "kb_id": "doc_id", "document_id": "doc_id"},
    "kb_update": {"id": "doc_id", "kb_id": "doc_id", "document_id": "doc_id"},
    "memory_show": {"id": "slug", "mem_id": "slug", "key": "slug"},
}


def validate_mcp_args(
    tool_name: str,
    schema: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate MCP tool args against the schema and return a self-correcting
    error envelope when mismatches are found, or ``None`` when args are valid.

    Returns an MCP content envelope (``{"content": [...], "is_error": True}``)
    when:
    - A required param is missing.
    - An unrecognised param is present (``additionalProperties: false``).

    The error message names the correct param so the model can self-correct on
    the next turn without an operator retry.  Schema validation errors that
    reach this function are also surfaced in ``builder logs --error`` output
    because the returned envelope sets ``is_error: True``, which
    ``normalize_tool_response`` classifies as ``tool_error``.
    """
    allowed_props: set[str] = set(schema.get("properties", {}).keys())
    required_props: set[str] = set(schema.get("required", []))
    rejects_extra: bool = schema.get("additionalProperties") is False
    aliases: dict[str, str] = _PARAM_ALIASES.get(tool_name, {})

    errors: list[str] = []

    # Check for disallowed (unknown) params and try to suggest the right one.
    if rejects_extra:
        for key in args:
            if key not in allowed_props:
                if key in aliases:
                    errors.append(f"Unknown param '{key}' — use '{aliases[key]}' instead.")
                else:
                    # Try to find a close match from allowed props.
                    suggestion = _closest_param(key, allowed_props)
                    if suggestion:
                        errors.append(
                            f"Unknown param '{key}' is not allowed — did you mean '{suggestion}'?"
                        )
                    else:
                        allowed_list = ", ".join(f"'{p}'" for p in sorted(allowed_props))
                        errors.append(
                            f"Unknown param '{key}' is not allowed. "
                            f"Allowed params: {allowed_list or 'none'}."
                        )

    # Check for missing required params.
    for req in required_props:
        if req not in args:
            errors.append(f"Required param '{req}' is missing.")

    if not errors:
        return None

    message = f"Schema error for tool '{tool_name}': " + " ".join(errors)
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": True,
    }


def _closest_param(key: str, candidates: set[str]) -> str | None:
    """Return the closest candidate by simple character-overlap heuristic."""
    if not candidates:
        return None
    key_lower = key.lower().replace("_", "")
    best_score = 0
    best = None
    for c in candidates:
        c_lower = c.lower().replace("_", "")
        # Count shared leading characters and common substrings (cheap heuristic).
        overlap = sum(1 for a, b in zip(key_lower, c_lower) if a == b)
        if overlap > best_score:
            best_score = overlap
            best = c
    # Only suggest if there's meaningful overlap (≥2 chars).
    return best if best_score >= 2 else None


_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
_BROWSER_NAVIGATE_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
    "additionalProperties": False,
}
_BROWSER_CLICK_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
_BROWSER_FILL_SCHEMA = {
    "type": "object",
    "properties": {"selector": {"type": "string"}, "value": {"type": "string"}},
    "required": ["selector", "value"],
    "additionalProperties": False,
}
_BACKLOG_ITEM_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "project": {"type": "string"},
        "item_type": {"type": "string"},
        "tag": {"type": "string"},
        "status": {"type": "string"},
        "limit": {"type": "integer"},
    },
    "additionalProperties": False,
}
_BACKLOG_ITEM_ID_SCHEMA = {
    "type": "object",
    "properties": {"item_id": {"type": "string"}},
    "required": ["item_id"],
    "additionalProperties": False,
}
_TASK_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "feature_id": {
            "type": "string",
            "description": (
                "Required. The backlog item (feature) ID whose tasks to list. "
                "Use 'feature_id', not 'item_id', 'task_id', or 'project_id'."
            ),
        },
        "status": {"type": "string", "description": "Optional status filter."},
        "limit": {"type": "integer", "description": "Maximum number of tasks to return."},
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
_RECOMMENDATION_CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "target_path": {
            "type": "string",
            "description": (
                "Builder-repo file or logical target — e.g. "
                "'src/autonomous_agent_builder/agents/execution_policy.py' or "
                "'_AGENT_POLICY[code-gen].context_strategy'."
            ),
        },
        "title": {"type": "string", "description": "Short imperative title."},
        "rationale": {
            "type": "string",
            "description": "Why this change should be made — evidence-grounded summary.",
        },
        "current_value": {"type": "string"},
        "suggested_value": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "description": "Impact severity of leaving this unaddressed.",
        },
        "evidence": {
            "type": "object",
            "description": (
                "Structured evidence — span IDs, metric snapshots, log refs, "
                "session/run IDs that justify the suggestion."
            ),
        },
        "source_session_id": {"type": "string"},
        "source_run_id": {"type": "string"},
        "source_task_id": {"type": "string"},
    },
    "required": ["target_path", "title", "rationale"],
    "additionalProperties": False,
}
_RUN_TESTS_SCHEMA = {
    "type": "object",
    "properties": {
        "test_pattern": {
            "type": "string",
            "description": (
                "Optional pytest selector (e.g. 'tests/test_foo.py::test_bar'). "
                "Use 'test_pattern', not 'path', 'pattern', or 'test_p'."
            ),
        },
        "timeout_sec": {"type": "integer", "description": "Timeout in seconds."},
    },
    "additionalProperties": False,
}
_RUN_LINTER_SCHEMA = {
    "type": "object",
    "properties": {"fix": {"type": "boolean"}, "timeout_sec": {"type": "integer"}},
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
    "properties": {
        "file_path": {
            "type": "string",
            "description": (
                "Required. File path relative to the workspace root. "
                "Use 'file_path', not 'path', 'file', or 'filepath'."
            ),
        },
        "start_line": {
            "type": "integer",
            "description": "1-based starting line (default: 1).",
        },
        "max_lines": {
            "type": "integer",
            "description": "Maximum lines to return (default: 200).",
        },
    },
    "required": ["file_path"],
    "additionalProperties": False,
}
_LIST_DIRECTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "relative_path": {
            "type": "string",
            "description": (
                "Directory path relative to the workspace root (default: '.'). "
                "Use 'relative_path', not 'path' or 'directory'."
            ),
        },
    },
    "additionalProperties": False,
}


def _project_root(project_root: str | None = None) -> str:
    if project_root:
        return project_root
    env_root = os.environ.get("AAB_PROJECT_ROOT", "").strip()
    if env_root:
        return env_root
    return str(Path.cwd())


def _filter_mcp_tools(
    server_name: str,
    tools: list[tuple[str, Any]],
    allowed_tool_names: set[str] | None,
) -> list[Any]:
    if allowed_tool_names is None:
        return [tool for _, tool in tools]
    return [
        tool
        for tool_name, tool in tools
        if tool_name in allowed_tool_names
        or f"mcp__{server_name}__{tool_name}" in allowed_tool_names
    ]


def build_default_mcp_servers(
    *,
    workspace_path: str,
    project_root: str | None = None,
    allowed_tool_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Create in-process SDK MCP servers for repo-local builder and workspace tools."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    resolved_project_root = _project_root(project_root)
    allowed_tool_set = set(allowed_tool_names) if allowed_tool_names is not None else None

    @tool("board", "Get the current task pipeline board status.", _EMPTY_SCHEMA)
    async def board(_args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_board(project_root=resolved_project_root)

    @tool("task_list", "List tasks for a feature.", _TASK_LIST_SCHEMA)
    async def task_list(args: dict[str, Any]) -> dict:
        err = validate_mcp_args("task_list", _TASK_LIST_SCHEMA, args)
        if err is not None:
            return err
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

    @tool(
        "task_recover",
        "Recover a blocked, failed, or capability-limited task so it can continue.",
        _TASK_ID_SCHEMA,
    )
    async def task_recover(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_task_recover(
            args["task_id"], project_root=resolved_project_root
        )

    @tool(
        "workspace_scaffold",
        (
            "Scaffold the workspace for the task's project: decide the stack at "
            "runtime, write minimum lint/test config, and persist the chosen "
            "language so quality gates resolve their binaries. Idempotent — "
            "calling on an already-scaffolded workspace is a no-op."
        ),
        _TASK_ID_SCHEMA,
    )
    async def workspace_scaffold(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_workspace_scaffold(
            args["task_id"], project_root=resolved_project_root
        )

    @tool("metrics", "Get project metrics such as cost, runs, and gate pass rate.", _EMPTY_SCHEMA)
    async def metrics(_args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_metrics(project_root=resolved_project_root)

    @tool(
        "backlog_item_list",
        "List typed backlog items such as feature, improvement, optimization, and incident entries.",
        _BACKLOG_ITEM_LIST_SCHEMA,
    )
    async def backlog_item_list(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_backlog_item_list(
            args.get("project", ""),
            args.get("item_type", ""),
            args.get("tag", ""),
            args.get("status", ""),
            int(args.get("limit", 50)),
            project_root=resolved_project_root,
        )

    @tool("backlog_item_show", "Show one typed backlog item by ID.", _BACKLOG_ITEM_ID_SCHEMA)
    async def backlog_item_show(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_backlog_item_show(
            args["item_id"],
            project_root=resolved_project_root,
        )

    @tool(
        "backlog_item_update",
        "Update a typed backlog item's status, title, or description. Use to sync stale status (e.g. mark a feature 'done' when all its tasks have shipped).",
        {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "status": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["item_id"],
            "additionalProperties": False,
        },
    )
    async def backlog_item_update(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_backlog_item_update(
            args["item_id"],
            status=args.get("status"),
            title=args.get("title"),
            description=args.get("description"),
            project_root=resolved_project_root,
        )

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

    @tool(
        "recommendation_create",
        (
            "File a builder-side improvement suggestion (BuilderRecommendation) "
            "for human review. Use this for anything that would change "
            "Autonomous Builder internals — _AGENT_POLICY, agent definitions, "
            "dispatch routing, builder hooks/subagents — instead of editing "
            "the builder repo directly. Direct edits to target-app surfaces "
            "do NOT need this tool."
        ),
        _RECOMMENDATION_CREATE_SCHEMA,
    )
    async def recommendation_create(args: dict[str, Any]) -> dict:
        return await builder_tool_service.builder_recommendation_create(
            args["target_path"],
            args["title"],
            args["rationale"],
            suggested_value=args.get("suggested_value"),
            current_value=args.get("current_value"),
            severity=str(args.get("severity") or "medium"),
            evidence=args.get("evidence") or {},
            source_session_id=args.get("source_session_id"),
            source_run_id=args.get("source_run_id"),
            source_task_id=args.get("source_task_id"),
        )

    @tool("run_tests", "Run tests inside the isolated workspace.", _RUN_TESTS_SCHEMA)
    async def run_tests(args: dict[str, Any]) -> dict:
        err = validate_mcp_args("run_tests", _RUN_TESTS_SCHEMA, args)
        if err is not None:
            return err
        return await workspace_tools.run_tests(
            workspace_path,
            args.get("test_pattern", ""),
            int(args.get("timeout_sec", workspace_tools.DEFAULT_TEST_TIMEOUT_SEC)),
        )

    @tool("run_linter", "Run the linter inside the isolated workspace.", _RUN_LINTER_SCHEMA)
    async def run_linter(args: dict[str, Any]) -> dict:
        return await workspace_tools.run_linter(
            workspace_path,
            bool(args.get("fix", False)),
            int(args.get("timeout_sec", workspace_tools.DEFAULT_LINTER_TIMEOUT_SEC)),
        )

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
        err = validate_mcp_args("read_file", _READ_FILE_SCHEMA, args)
        if err is not None:
            return err
        return await workspace_tools.read_file(
            workspace_path,
            args["file_path"],
            int(args.get("start_line", 1)),
            int(args.get("max_lines", 200)),
        )

    @tool(
        "list_directory", "List a directory within the isolated workspace.", _LIST_DIRECTORY_SCHEMA
    )
    async def list_directory(args: dict[str, Any]) -> dict:
        err = validate_mcp_args("list_directory", _LIST_DIRECTORY_SCHEMA, args)
        if err is not None:
            return err
        return await workspace_tools.list_directory(workspace_path, args.get("relative_path", "."))

    @tool(
        "get_project_info",
        "Detect language and build files for the isolated workspace.",
        _EMPTY_SCHEMA,
    )
    async def get_project_info(_args: dict[str, Any]) -> dict:
        return await workspace_tools.get_project_info(workspace_path)

    builder_tools = _filter_mcp_tools(
        "builder",
        [
            ("board", board),
            ("task_list", task_list),
            ("task_show", task_show),
            ("task_status", task_status),
            ("task_dispatch", task_dispatch),
            ("task_recover", task_recover),
            ("workspace_scaffold", workspace_scaffold),
            ("metrics", metrics),
            ("backlog_item_list", backlog_item_list),
            ("backlog_item_show", backlog_item_show),
            ("kb_search", kb_search),
            ("kb_show", kb_show),
            ("kb_contract", kb_contract),
            ("kb_lint", kb_lint),
            ("kb_validate", kb_validate),
            ("kb_extract", kb_extract),
            ("kb_add", kb_add),
            ("kb_update", kb_update),
            ("memory_search", memory_search),
            ("memory_show", memory_show),
            ("memory_add", memory_add),
            ("recommendation_create", recommendation_create),
        ],
        allowed_tool_set,
    )
    workspace_tools_list = _filter_mcp_tools(
        "workspace",
        [
            ("run_tests", run_tests),
            ("run_linter", run_linter),
            ("run_command", run_command),
            ("read_file", read_file),
            ("list_directory", list_directory),
            ("get_project_info", get_project_info),
        ],
        allowed_tool_set,
    )

    # ── Browser verification tools (IMP-019) — Hermes Chrome bridge ──
    @tool(
        "navigate",
        "Open the running app in a real browser and return rendered page context "
        "(url, title, headings, nav, buttons, inputs).",
        _BROWSER_NAVIGATE_SCHEMA,
    )
    async def browser_navigate(args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_navigate(args["url"]))

    @tool(
        "page_context",
        "Compact context for the current browser tab (url, title, headings, nav, "
        "buttons, inputs) — the cheapest way to verify rendered state.",
        _EMPTY_SCHEMA,
    )
    async def browser_page_context(_args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_page_context())

    @tool(
        "read_text",
        "Visible rendered text of the current page, to assert real content/values.",
        _EMPTY_SCHEMA,
    )
    async def browser_read_text(_args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_read_text())

    @tool(
        "click_text",
        "Click the first element whose visible text matches, then return page context.",
        _BROWSER_CLICK_SCHEMA,
    )
    async def browser_click_text(args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_click_text(args["text"]))

    @tool(
        "fill",
        "Fill the form field matched by CSS selector with a value; return page context.",
        _BROWSER_FILL_SCHEMA,
    )
    async def browser_fill(args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_fill(args["selector"], args["value"]))

    @tool(
        "screenshot",
        "Capture a viewport screenshot as visual proof; returns the on-disk path.",
        _EMPTY_SCHEMA,
    )
    async def browser_screenshot(_args: dict[str, Any]) -> dict:
        return _to_mcp(await browser_tools.browser_screenshot())

    @tool(
        "resolve_app_url",
        "Resolve how to serve this generated web app and the URL to open "
        "(reads the workspace package.json serve script / index.html). Call this "
        "first to learn the start command + URL before navigating.",
        _EMPTY_SCHEMA,
    )
    async def browser_resolve_app_url(_args: dict[str, Any]) -> dict:
        return _to_mcp(browser_tools.resolve_dev_server(workspace_path))

    browser_tools_list = _filter_mcp_tools(
        "browser",
        [
            ("resolve_app_url", browser_resolve_app_url),
            ("navigate", browser_navigate),
            ("page_context", browser_page_context),
            ("read_text", browser_read_text),
            ("click_text", browser_click_text),
            ("fill", browser_fill),
            ("screenshot", browser_screenshot),
        ],
        allowed_tool_set,
    )

    builder_server = create_sdk_mcp_server(name="builder", tools=builder_tools)
    workspace_server = create_sdk_mcp_server(name="workspace", tools=workspace_tools_list)

    servers: dict[str, Any] = {
        "builder": builder_server,
        "workspace": workspace_server,
    }
    if browser_tools_list:
        servers["browser"] = create_sdk_mcp_server(name="browser", tools=browser_tools_list)
    return servers
