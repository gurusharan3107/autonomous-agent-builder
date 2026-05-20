"""Agent chat tool response and permission policy helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autonomous_agent_builder.knowledge.kb_paths import resolve_repo_local_kb_path

FEATURE_SPEC_BLOCKED_TOOLS = frozenset(
    {
        "Bash",
        "mcp__builder__kb_add",
        "mcp__builder__kb_update",
        "mcp__builder__memory_add",
        "mcp__workspace__run_command",
        "mcp__workspace__run_tests",
        "mcp__workspace__run_linter",
    }
)


def extract_tool_text_payload(tool_response: Any) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        return {}
    content = tool_response.get("content")
    if not isinstance(content, list) or not content:
        return {}
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        return {}
    text = first.get("text")
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def permission_allow(updated_input: dict[str, Any]) -> Any:
    from claude_agent_sdk.types import PermissionResultAllow

    return PermissionResultAllow(updated_input=updated_input)


def permission_deny(message: str) -> Any:
    from claude_agent_sdk.types import PermissionResultDeny

    return PermissionResultDeny(message=message)


def tool_summary(tool_name: str, input_data: dict[str, Any]) -> tuple[str, str]:
    if tool_name == "mcp__builder__kb_validate":
        kb_dir = str(input_data.get("kb_dir") or "system-docs").strip() or "system-docs"
        return (
            f"Validate repo-local KB `{kb_dir}`",
            "Claude needs approval to validate a repo-local knowledge directory.",
        )
    if tool_name == "Bash":
        command = str(input_data.get("command", "")).strip()
        description = str(input_data.get("description", "")).strip()
        return (
            command or "Run shell command",
            description or "Claude needs approval to execute this command.",
        )
    if tool_name == "mcp__builder__task_recover":
        task_id = str(input_data.get("task_id") or "").strip()
        return (
            f"Recover Board task `{task_id}`" if task_id else "Recover Board task",
            "Claude needs approval to recover this Board task for redispatch.",
        )
    if tool_name == "mcp__builder__task_dispatch":
        task_id = str(input_data.get("task_id") or "").strip()
        return (
            f"Dispatch Board task `{task_id}`" if task_id else "Dispatch Board task",
            "Claude needs approval to dispatch this Board task.",
        )
    if tool_name in {"Write", "Edit", "Read", "Glob", "Grep"}:
        path = str(
            input_data.get("file_path") or input_data.get("path") or input_data.get("pattern") or ""
        ).strip()
        summary = f"{tool_name} {path}".strip()
        return summary or tool_name, f"Claude needs approval to use `{tool_name}`."
    return tool_name, f"Claude needs approval to use `{tool_name}`."


def truncate_preview(value: str, *, limit: int = 800) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def normalize_tool_response(tool_response: Any) -> tuple[str, str]:
    if isinstance(tool_response, dict):
        try:
            rendered = json.dumps(tool_response, ensure_ascii=True, sort_keys=True)
        except TypeError:
            rendered = str(tool_response)
    else:
        rendered = str(tool_response or "")

    lowered = rendered.lower()
    if '"status": "error"' in lowered or '"status":"error"' in lowered:
        return "tool_error", truncate_preview(rendered)
    if lowered.startswith("error:") or "\nerror:" in lowered:
        return "tool_error", truncate_preview(rendered)
    return "tool_result", truncate_preview(rendered)


def kb_validate_policy(
    project_root: Path, input_data: dict[str, Any]
) -> tuple[bool, dict[str, Any], str, str]:
    normalized_kb_dir, kb_root, kb_path = resolve_repo_local_kb_path(
        input_data.get("kb_dir"),
        project_root=project_root,
    )
    updated_input = dict(input_data)
    updated_input["kb_dir"] = normalized_kb_dir
    requested_path = Path(normalized_kb_dir)
    if (
        requested_path.is_absolute()
        or ".." in requested_path.parts
        or (kb_path != kb_root and kb_root not in kb_path.parents)
    ):
        return (
            False,
            updated_input,
            "Denied `mcp__builder__kb_validate`: `kb_dir` must stay under `.agent-builder/knowledge/` in this repo.",
            'Retry with `{"kb_dir":"system-docs"}` or another relative directory under `.agent-builder/knowledge/`.',
        )
    return True, updated_input, "", ""


def feature_spec_tool_denial(tool_name: str) -> tuple[bool, str]:
    if tool_name in FEATURE_SPEC_BLOCKED_TOOLS:
        return (
            True,
            "Stay in the improvement-scoping interview lane. Do not use shell or mutating tools "
            "before the feature is captured. Ask the next bounded user question with "
            "AskUserQuestion or emit FEATURE_SPEC_JSON once the scope is ready.",
        )
    if tool_name in {"Edit", "Write"}:
        return (
            True,
            "Stay in the improvement-scoping interview lane. Ask the next bounded user question "
            "with AskUserQuestion or emit FEATURE_SPEC_JSON before making implementation changes.",
        )
    return False, ""
