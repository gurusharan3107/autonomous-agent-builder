"""SDK hooks — PreToolUse and PostToolUse for safety and audit.

Replaces the custom sandbox.py from v1. These hooks are registered
with the SDK via HookMatcher at query() time.

Signatures follow Claude Agent SDK v0.1.56:
- PreToolUse: (input: PreToolUseHookInput, tool_use_id, context: HookContext)
- PostToolUse: (input: PostToolUseHookInput, tool_use_id, context: HookContext)

Safety contract:
- PreToolUse: block writes outside workspace + validate bash argv
- PostToolUse: audit log all tool calls to agent_run_events
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.cli.doc_contracts import check_quality_gate_wording
from autonomous_agent_builder.cli.doc_ownership import (
    check_doc_ownership,
    looks_like_reserved_doc_path,
)

log = structlog.get_logger()

# Dangerous shell patterns that indicate shell=True-style commands
_SHELL_PATTERNS = re.compile(r"[|;&`$]|&&|\|\||>>|<<|2>&1|\beval\b|\bexec\b|\bsource\b")
_BLOCKED_KB_BASH = re.compile(r"^\s*builder\s+(?:kb|knowledge)\s+(add|update)\b")
_BLOCKED_MEMORY_BASH = re.compile(r"^\s*builder\s+memory\s+add\b")


async def keep_tool_stream_open(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Keep Python SDK permission callbacks alive during streaming tool interactions."""

    return {"continue_": True}


async def enforce_workspace_boundary(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PreToolUse hook: block file operations outside workspace.

    SDK signature: (input: PreToolUseHookInput, tool_use_id, context: HookContext)
    Returns empty dict to allow, or {"decision": "block", "reason": ...} to deny.
    """
    try:
        tool_name = input.get("tool_name", "")
        tool_input = input.get("tool_input", {})
        workspace_path = context.get("workspace_path", "")

        local_kb_root = Path(
            os.environ.get(
                "AAB_LOCAL_KB_ROOT",
                Path(workspace_path) / ".agent-builder" / "knowledge",
            )
        ).resolve()
        local_memory_root = Path(
            os.environ.get("AAB_MEMORY_ROOT", Path(workspace_path) / ".memory")
        ).resolve()
        global_kb_root = Path(
            os.environ.get("AAB_GLOBAL_KB_ROOT", Path.home() / ".codex" / "knowledge")
        ).resolve()

        # Check file_path for Read, Edit, Write
        file_path = tool_input.get("file_path", "")
        if file_path and _is_within_path(file_path, global_kb_root.parent):
            reason = (
                "Blocked: direct access to ~/.codex is not allowed from the builder agent. "
                "Use the workflow CLI to read or update owner docs instead."
            )
            log.warning("hook_blocked_codex_path", tool=tool_name, path=file_path)
            return {"decision": "block", "reason": reason}
        if file_path and not _is_within_workspace(file_path, workspace_path):
            reason = f"Blocked: file path '{file_path}' is outside workspace '{workspace_path}'"
            log.warning(
                "hook_blocked_write",
                tool=tool_name,
                path=file_path,
                workspace=workspace_path,
            )
            return {"decision": "block", "reason": reason}
        if (
            tool_name in {"Edit", "Write"}
            and file_path
            and (
                _is_within_path(file_path, local_kb_root)
                or _is_within_path(file_path, global_kb_root)
            )
        ):
            reason = (
                "Blocked: KB writes must go through the builder CLI publish path, "
                f"not direct {tool_name}. Use builder_kb_add or builder_kb_update."
            )
            log.warning("hook_blocked_kb_write", tool=tool_name, path=file_path)
            return {"decision": "block", "reason": reason}
        if (
            tool_name in {"Edit", "Write"}
            and file_path
            and _is_within_path(file_path, local_memory_root)
        ):
            reason = (
                "Blocked: memory writes must go through the official builder memory surface, "
                f"not direct {tool_name}. Use builder_memory_add."
            )
            log.warning("hook_blocked_memory_write", tool=tool_name, path=file_path)
            return {"decision": "block", "reason": reason}
        if tool_name in {"Edit", "Write"} and file_path and looks_like_reserved_doc_path(
            Path(file_path), repo_root=Path(workspace_path)
        ):
            ownership = check_doc_ownership(Path(file_path), repo_root=Path(workspace_path))
            if ownership.decision == "WRONG_SURFACE":
                log.warning(
                    "hook_blocked_reserved_doc_surface",
                    tool=tool_name,
                    path=file_path,
                    doc_class=ownership.doc_class,
                )
                return {"decision": "block", "reason": ownership.reason}
            resolved_file_path = str(Path(file_path).resolve())
            if (
                ownership.decision == "UPDATE_EXISTING"
                and ownership.owner_path != resolved_file_path
            ):
                log.warning(
                    "hook_blocked_duplicate_reserved_doc",
                    tool=tool_name,
                    path=file_path,
                    doc_class=ownership.doc_class,
                    owner_path=ownership.owner_path,
                )
                return {"decision": "block", "reason": ownership.reason}
            if ownership.doc_class == "quality-gate":
                content = tool_input.get("content")
                if content is None and tool_name == "Edit":
                    old_string = str(tool_input.get("old_string", "") or "")
                    new_string = str(tool_input.get("new_string", "") or "")
                    content = f"{old_string}\n{new_string}"
                contract = check_quality_gate_wording(
                    Path(file_path),
                    repo_root=Path(workspace_path),
                    content_override=content if isinstance(content, str) else None,
                )
                if contract.decision == "CONTENT_DRIFT":
                    log.warning(
                        "hook_blocked_quality_gate_content_drift",
                        tool=tool_name,
                        path=file_path,
                        reasons=list(contract.reasons),
                    )
                    return {
                        "decision": "block",
                        "reason": (
                            "Blocked: quality-gate docs must stay review-contract surfaces. "
                            + " ".join(contract.reasons)
                        ),
                    }

        # Check path for Glob, Grep
        search_path = tool_input.get("path", "")
        if search_path and _is_within_path(search_path, global_kb_root.parent):
            reason = (
                "Blocked: direct access to ~/.codex is not allowed from the builder agent. "
                "Use the workflow CLI to read or update owner docs instead."
            )
            log.warning("hook_blocked_codex_search", tool=tool_name, path=search_path)
            return {"decision": "block", "reason": reason}
        if search_path and not _is_within_workspace(search_path, workspace_path):
            reason = f"Blocked: search path '{search_path}' is outside workspace"
            log.warning("hook_blocked_search", tool=tool_name, path=search_path)
            return {"decision": "block", "reason": reason}

        return {}
    except Exception as e:
        log.error("hook_error", hook="enforce_workspace_boundary", error=str(e))
        return {"decision": "block", "reason": "Hook error (blocking for safety)"}


async def validate_bash_argv(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PreToolUse hook: validate Bash tool uses argv-safe commands.

    SDK signature: (input: PreToolUseHookInput, tool_use_id, context: HookContext)

    Non-negotiable security constraint from architecture council:
    - No shell metacharacters (|, ;, &, `, $)
    - No command chaining (&&, ||)
    - No redirection (>>, <<)
    - No eval/exec/source
    """
    try:
        tool_name = input.get("tool_name", "")
        if tool_name != "Bash":
            return {}

        tool_input = input.get("tool_input", {})
        command = tool_input.get("command", "")
        if not command:
            return {}

        if _SHELL_PATTERNS.search(command):
            reason = (
                f"Blocked: Bash command contains shell metacharacters. "
                f"Use argv-style commands without pipes, redirects, or chaining. "
                f"Command: {command[:100]}"
            )
            log.warning("hook_blocked_bash", command=command[:200])
            return {"decision": "block", "reason": reason}
        if _BLOCKED_KB_BASH.search(command):
            reason = (
                "Blocked: KB mutation commands must not be invoked from agent Bash. "
                "Use the builder_kb_add or builder_kb_update tool instead."
            )
            log.warning("hook_blocked_kb_bash", command=command[:200])
            return {"decision": "block", "reason": reason}
        if _BLOCKED_MEMORY_BASH.search(command):
            reason = (
                "Blocked: memory mutation commands must not be invoked from agent Bash. "
                "Use the builder_memory_add tool instead."
            )
            log.warning("hook_blocked_memory_bash", command=command[:200])
            return {"decision": "block", "reason": reason}

        return {}
    except Exception as e:
        log.error("hook_error", hook="validate_bash_argv", error=str(e))
        return {"decision": "block", "reason": "Hook error (blocking for safety)"}


async def audit_log_tool_use(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PostToolUse hook: log all tool calls for audit trail.

    SDK signature: (input: PostToolUseHookInput, tool_use_id, context: HookContext)

    Every tool invocation is recorded with input/output for replay capability.
    This replaces the need for a SessionRegistry — structured logs provide
    full audit trail.
    """
    try:
        tool_name = input.get("tool_name", "")
        tool_input = input.get("tool_input", {})
        tool_response = input.get("tool_response", "")
        run_id = context.get("run_id", "")
        db_session = context.get("db_session")

        event = {
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_input": _sanitize_for_log(tool_input),
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_use_id": tool_use_id,
        }

        # Log output summary (not full content — could be huge)
        if tool_response and isinstance(tool_response, (str, dict)):
            text = str(tool_response)
            event["output_preview"] = text[:500]
            event["output_length"] = len(text)

        log.info("tool_use", **event)

        # Persist to DB if session available
        if db_session is not None:
            from autonomous_agent_builder.db.models import AgentRunEvent

            db_event = AgentRunEvent(
                run_id=run_id,
                event_type="tool_use",
                tool_name=tool_name,
                tool_input=_sanitize_for_log(tool_input),
                output_preview=event.get("output_preview", ""),
                timestamp=datetime.now(UTC),
            )
            db_session.add(db_event)
            await db_session.flush()

        return {}
    except Exception as e:
        log.error("hook_error", hook="audit_log_tool_use", error=str(e))
        return {}  # audit errors should never block execution


def _is_within_workspace(path: str, workspace_path: str) -> bool:
    """Check if a path is within the workspace or approved scratch space."""
    try:
        resolved = Path(path).resolve()
        allowed_roots = [
            Path(workspace_path).resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]

        extra_scratch_root = os.environ.get("AAB_SCRATCH_ROOT")
        if extra_scratch_root:
            allowed_roots.append(Path(extra_scratch_root).resolve())

        return any(str(resolved).startswith(str(root)) for root in allowed_roots)
    except (OSError, ValueError):
        return False


def _is_within_path(path: str, root: Path) -> bool:
    try:
        return str(Path(path).resolve()).startswith(str(root.resolve()))
    except (OSError, ValueError):
        return False


def _sanitize_for_log(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize tool input for logging — truncate large values."""
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 1000:
            sanitized[key] = value[:1000] + f"... ({len(value)} chars)"
        else:
            sanitized[key] = value
    return sanitized
