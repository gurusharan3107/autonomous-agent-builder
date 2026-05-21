"""Shared builder services for SDK-facing MCP tools.

These functions preserve the builder JSON contract exposed to the agent runtime
without shelling out to `builder --json` internally.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

from autonomous_agent_builder.cli.client import resolve_base_url
from autonomous_agent_builder.cli.commands import kb as kb_cli
from autonomous_agent_builder.cli.commands import memory as memory_cli
from autonomous_agent_builder.cli.knowledge_validation_payloads import validate_output_payload
from autonomous_agent_builder.cli.output import truncate
from autonomous_agent_builder.cli.retrieval import compact_results_payload
from autonomous_agent_builder.knowledge.document_spec import DocumentLinter, contract_payload
from autonomous_agent_builder.knowledge.kb_paths import resolve_repo_local_kb_path
from autonomous_agent_builder.knowledge.publisher import (
    DEFAULT_LOCAL_KB_COLLECTION,
    PublishError,
    publish_document,
    update_document,
)
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate
from autonomous_agent_builder.knowledge.retrieval import find_doc, search_docs

_TASK_LIST_NEXT_STEP = "builder backlog task summary <query> --json"
_BACKLOG_ITEM_LIST_NEXT_STEP = "builder backlog item list --project <id> --json"
_BACKLOG_ITEM_SHOW_NEXT_STEP = "builder backlog item show <item_id> --json"
_KB_SHOW_NEXT_STEP = "builder knowledge summary <query> --json"
_MEMORY_SHOW_NEXT_STEP = "builder memory summary <query> --json"
_KB_CONTRACT_NEXT_STEP = "builder knowledge contract --type <doc_type> --json"
_KB_LINT_NEXT_STEP = "Fix the listed contract issues, then retry the KB mutation."
_TASK_SHOW_FULL_NEXT_STEP = "builder backlog task show <task-id> --full --json"
_KB_SHOW_FULL_NEXT_STEP = "builder knowledge show <doc-id> --json"


class BuilderToolServiceError(Exception):
    """Internal builder-tool service error with an agent-facing exit code."""

    def __init__(self, message: str, *, exit_code: int = 1, detail: Any = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.detail = detail


def _extract_lint_issues(report: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("ERRORS:") or stripped.startswith("WARNINGS:") or not stripped:
            continue
        if "❌" in stripped:
            errors.append(stripped.split("❌", 1)[1].strip())
        elif stripped.startswith("[FAIL]"):
            errors.append(stripped.split("[FAIL]", 1)[1].strip())
        elif "⚠️" in stripped:
            warnings.append(stripped.split("⚠️", 1)[1].strip())
        elif stripped.startswith("[WARN]"):
            warnings.append(stripped.split("[WARN]", 1)[1].strip())
    return errors, warnings


def validate_repo_local_kb_dir(
    kb_dir: str | None,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, Path, Path]:
    normalized_kb_dir, kb_root, kb_path = resolve_repo_local_kb_path(
        kb_dir,
        project_root=project_root,
    )
    requested_path = Path(normalized_kb_dir)
    if (
        requested_path.is_absolute()
        or ".." in requested_path.parts
        or (kb_path != kb_root and kb_root not in kb_path.parents)
    ):
        raise BuilderToolServiceError(
            "KB validation is limited to repo-local directories under .agent-builder/knowledge.",
            exit_code=1,
            detail={
                "kb_dir": normalized_kb_dir,
                "safe_lane": ".agent-builder/knowledge/<kb_dir>",
            },
        )
    return normalized_kb_dir, kb_root, kb_path


def _mcp_text_payload(payload: Any, *, exit_code: int = 0) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, default=str)}],
        "metadata": {"exit_code": exit_code},
    }


def _error_payload(
    message: str,
    *,
    exit_code: int = 1,
    code: str = "error",
    hint: str = "",
    detail: Any = None,
) -> dict[str, Any]:
    return _mcp_text_payload(
        {
            "status": "error",
            "error": {
                "code": code,
                "message": message,
                "hint": hint,
                "detail": detail,
            },
            "schema_version": "1",
        },
        exit_code=exit_code,
    )


@contextmanager
def _project_scope(project_root: str | None):
    if not project_root:
        yield
        return

    resolved_root = str(Path(project_root).resolve())
    scoped_env = {
        "AAB_PROJECT_ROOT": resolved_root,
        "AAB_LOCAL_KB_ROOT": str(Path(resolved_root) / ".agent-builder" / "knowledge"),
        "AAB_MEMORY_ROOT": str(Path(resolved_root) / ".memory"),
    }
    previous = {key: os.environ.get(key) for key in scoped_env}
    os.environ.update(scoped_env)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def _api_request(
    method: str,
    path: str,
    *,
    project_root: str | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    with _project_scope(project_root):
        base_url = resolve_base_url()

    api_path = path if path.startswith("/api") else f"/api{path}"
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.request(method, api_path, params=params, json=json_body)
    except httpx.HTTPError as exc:
        raise BuilderToolServiceError(
            f"cannot connect to server at {base_url}",
            exit_code=3,
            detail=str(exc),
        ) from exc

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if response.status_code >= 400:
        raise BuilderToolServiceError(
            f"server returned {response.status_code}",
            exit_code=1,
            detail=payload,
        )
    return payload


def _task_preview(item: dict[str, Any]) -> str:
    for key in ("description", "blocked_reason"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return " ".join(value.split())[:120]
    return ""


def _task_compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("title", "")),
        "doc_type": "task",
        "status": str(item.get("status", "")),
        "phase": str(item.get("phase", "")),
        "feature_id": str(item.get("feature_id", "")),
        "feature_title": str(item.get("feature_title", "")),
        "preview": _task_preview(item),
    }


def _compact_board_section(items: list[Any], *, limit: int = 10) -> dict[str, Any]:
    compact_items = [_task_compact(item) for item in items[:limit] if isinstance(item, dict)]
    omitted = max(len(items) - len(compact_items), 0)
    return {
        "count": len(items),
        "returned": len(compact_items),
        "items": compact_items,
        "omitted": omitted,
    }


def _short_text(value: Any, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _compact_sprint_execution(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    keys = (
        "sprint_id",
        "feature_id",
        "task_key",
        "batch_id",
        "batch_index",
        "mode",
        "execution_mode",
        "recommended_model",
        "recommended_effort",
        "parallel_group",
        "depends_on_batches",
    )
    return {key: value.get(key) for key in keys if value.get(key) not in (None, "", [])}


def _compact_task_depends_on(depends_on: Any) -> dict[str, Any]:
    if not isinstance(depends_on, dict):
        return {}
    compact: dict[str, Any] = {}
    sprint_execution = _compact_sprint_execution(depends_on.get("sprint_execution"))
    if sprint_execution:
        compact["sprint_execution"] = sprint_execution
    for key in (
        "summary",
        "sprint_merge_error",
        "integration_error",
        "recommended_next_step",
        "completed_at",
    ):
        if depends_on.get(key):
            compact[key] = _short_text(depends_on.get(key), limit=800)
    verification = depends_on.get("materialized_checkout_verification")
    if isinstance(verification, dict):
        compact["materialized_checkout_verification"] = {
            key: _short_text(value, limit=1200) if key == "output" else value
            for key, value in verification.items()
            if key in {"status", "command", "project_root", "output", "completed_at"}
            and value not in (None, "", [])
        }
    for key in ("generated_task_ids", "feature_acceptance_run_ids"):
        value = depends_on.get(key)
        if isinstance(value, list):
            compact[key] = {"count": len(value), "sample": value[:5]}
    return compact


def _compact_gate_result(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    compact = {
        key: item.get(key)
        for key in (
            "id",
            "gate",
            "gate_name",
            "name",
            "status",
            "passed",
            "created_at",
            "completed_at",
        )
        if item.get(key) not in (None, "", [])
    }
    for source_key, target_key in (
        ("summary", "summary"),
        ("message", "message"),
        ("error", "error"),
        ("error_message", "error"),
        ("output", "output_preview"),
    ):
        if item.get(source_key):
            compact[target_key] = _short_text(item.get(source_key), limit=500)
    return compact


def _compact_agent_run(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    tokens = int(item.get("tokens_input") or 0) + int(item.get("tokens_output") or 0)
    compact = {
        key: item.get(key)
        for key in (
            "id",
            "agent_name",
            "status",
            "runtime_sdk",
            "provider",
            "model",
            "effort",
            "cost_usd",
            "duration_ms",
            "stop_reason",
            "created_at",
            "completed_at",
        )
        if item.get(key) not in (None, "", [])
    }
    compact["tokens"] = tokens
    for source_key, target_key in (
        ("summary", "summary"),
        ("error", "error"),
        ("error_message", "error"),
        ("output_text", "output_preview"),
    ):
        if item.get(source_key):
            compact[target_key] = _short_text(item.get(source_key), limit=500)
    return compact


def _compact_voice_ledger(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict):
        return {}
    totals = ledger.get("totals") if isinstance(ledger.get("totals"), dict) else {}
    tool_outputs = (
        ledger.get("tool_outputs") if isinstance(ledger.get("tool_outputs"), list) else []
    )
    failed_outputs = [
        item for item in tool_outputs if isinstance(item, dict) and item.get("ok") is False
    ]
    return {
        "totals": {
            "responses": totals.get("responses", 0),
            "total_tokens": totals.get("total_tokens", 0),
            "input_text_tokens": totals.get("input_text_tokens", 0),
            "input_audio_tokens": totals.get("input_audio_tokens", 0),
            "output_text_tokens": totals.get("output_text_tokens", 0),
            "output_audio_tokens": totals.get("output_audio_tokens", 0),
            "cached_tokens": totals.get("cached_tokens", 0),
            "estimated_cost_usd": totals.get("estimated_cost_usd"),
            "cost_source": totals.get("cost_source", ""),
            "delegated_messages": totals.get("delegated_messages", 0),
            "voice_digests": totals.get("voice_digests", 0),
            "tool_calls": totals.get("tool_calls", 0),
            "tool_outputs": totals.get("tool_outputs", 0),
            "failed_tool_outputs": totals.get("failed_tool_outputs", len(failed_outputs)),
            "wait_events": totals.get("wait_events", 0),
            "prepared_actions": totals.get("prepared_actions", 0),
            "confirmed_actions": totals.get("confirmed_actions", 0),
            "delegation_ratio": totals.get("delegation_ratio", 0.0),
        },
        "recent_failures": [
            {
                "tool_name": item.get("tool_name", ""),
                "tool_call_id": item.get("tool_call_id", ""),
                "error": _short_text(item.get("error", ""), limit=300),
                "event_id": item.get("event_id", ""),
            }
            for item in failed_outputs[:5]
        ],
        "raw_evidence": {
            "command": "builder metrics show --json --full",
            "contains": ["voice_usage", "voice_tool_call", "voice_tool_output", "voice_digest"],
        },
    }


def _compact_runtime_decision_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    phase_decisions = (
        value.get("phase_decisions") if isinstance(value.get("phase_decisions"), list) else []
    )
    return {
        "runtime": value.get("runtime", ""),
        "native_capability_count": value.get("native_capability_count", 0),
        "fallback_capability_count": value.get("fallback_capability_count", 0),
        "capability_gaps": value.get("capability_gaps", [])[:5]
        if isinstance(value.get("capability_gaps"), list)
        else [],
        "next": value.get("next", ""),
        "phase_decisions": [
            {
                "phase": item.get("phase", ""),
                "reason_code": item.get("reason_code", ""),
                "tool_route": item.get("tool_route", ""),
                "model_effort": item.get("model_effort", ""),
                "permission_policy": item.get("permission_policy", ""),
                "selected_subagents": item.get("selected_subagents", []),
            }
            for item in phase_decisions[:8]
            if isinstance(item, dict)
        ],
        "omitted_phase_decisions": max(len(phase_decisions) - 8, 0),
    }


def _compact_backlog_item_detail(item: dict[str, Any]) -> dict[str, Any]:
    item_type = item.get("item_type") or item.get("type") or "feature"
    acceptance = item.get("acceptance_criteria")
    dependencies = item.get("dependencies")
    return {
        "schema_version": "1",
        "doc_type": "backlog_item_detail",
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "type": item_type,
        "title": item.get("title"),
        "description": _short_text(item.get("description"), limit=800),
        "status": item.get("status"),
        "priority": item.get("priority", 0),
        "severity": item.get("severity"),
        "source": item.get("source"),
        "tags": item.get("tags", []),
        "evidence": _short_text(item.get("evidence"), limit=800),
        "acceptance_criteria": {
            "count": len(acceptance) if isinstance(acceptance, list) else 0,
            "items": acceptance[:8] if isinstance(acceptance, list) else [],
            "omitted": max(len(acceptance) - 8, 0) if isinstance(acceptance, list) else 0,
        },
        "dependencies": {
            "count": len(dependencies) if isinstance(dependencies, list) else 0,
            "items": dependencies[:8] if isinstance(dependencies, list) else [],
            "omitted": max(len(dependencies) - 8, 0) if isinstance(dependencies, list) else 0,
        },
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _compact_kb_document(
    payload: dict[str, Any],
    *,
    include_content: bool,
    content_limit: int = 2000,
) -> dict[str, Any]:
    content = str(payload.get("content") or "")
    compact = {
        key: payload.get(key)
        for key in (
            "id",
            "task_id",
            "doc_type",
            "doc_family",
            "lifecycle_status",
            "superseded_by",
            "linked_feature",
            "feature_id",
            "refresh_required",
            "documented_against_commit",
            "documented_against_ref",
            "owned_paths",
            "last_verified_at",
            "verified_with",
            "title",
            "version",
            "created_at",
            "updated",
            "tags",
            "date_published",
            "source_author",
            "source_title",
            "source_url",
            "scope",
            "path",
            "excerpt",
            "matched_on",
        )
        if payload.get(key) not in (None, "", [])
    }
    compact["content_chars"] = len(content)
    compact["content_truncated"] = len(content) > content_limit
    if include_content:
        compact["content"] = truncate(content, content_limit)
    else:
        compact["content_preview"] = _short_text(content, limit=min(content_limit, 800))
    return compact


def _memory_query_resolution(
    query: str,
    entries: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, list[str]]:
    lowered = query.lower().strip()
    suggestions = [str(entry.get("slug", "")) for entry in entries[:3] if entry.get("slug")]
    if not lowered:
        return None, "", suggestions

    for entry in entries:
        slug = str(entry.get("slug", "")).lower()
        title = str(entry.get("title", "")).lower()
        if lowered == slug:
            return entry, "slug", suggestions
        if lowered == title:
            return entry, "title", suggestions

    for entry in entries:
        haystack = " ".join(
            [
                str(entry.get("slug", "")),
                str(entry.get("title", "")),
                str(entry.get("entity", "")),
                str(entry.get("phase", "")),
                " ".join(str(tag) for tag in entry.get("tags", [])),
            ]
        ).lower()
        if lowered in haystack:
            return entry, "search", suggestions

    return None, "", suggestions


async def builder_board(project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request("GET", "/dashboard/board", project_root=project_root)
        sections = {}
        for section in ("pending", "active", "review", "done", "blocked"):
            if section in data and isinstance(data[section], list):
                sections[section] = _compact_board_section(data[section])
        counts = data.get("counts")
        if not isinstance(counts, dict) or not counts:
            counts = {
                section: payload["count"]
                for section, payload in sections.items()
                if isinstance(payload, dict) and isinstance(payload.get("count"), int)
            }
        payload = {
            "schema_version": "1",
            "doc_type": "board_summary",
            "count_semantics": "counts and sections.*.count are total counts; omitted is already included in count and must not be added again.",
            "sections": sections,
            "counts": counts,
            "sprints_summary": data.get("sprints_summary", {}),
            "next_step": "Use builder task_list or task_show for focused task details.",
        }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_task_list(
    feature_id: str,
    status: str = "",
    limit: int = 50,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        items = await _api_request(
            "GET", f"/features/{feature_id}/tasks", project_root=project_root
        )
        if status:
            items = [item for item in items if item.get("status") == status]
        compact = [_task_compact(item) for item in items[:limit]]
        payload = compact_results_payload("list", compact, next_step=_TASK_LIST_NEXT_STEP)
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_task_show(task_id: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request("GET", f"/tasks/{task_id}", project_root=project_root)
        gate_results = await _api_request(
            "GET",
            f"/tasks/{task_id}/gates",
            project_root=project_root,
        )
        agent_runs = await _api_request(
            "GET",
            f"/tasks/{task_id}/runs",
            project_root=project_root,
        )
        gate_items = gate_results if isinstance(gate_results, list) else []
        run_items = agent_runs if isinstance(agent_runs, list) else []
        payload = {
            "schema_version": "1",
            "doc_type": "task_detail",
            "id": data.get("id"),
            "feature_id": data.get("feature_id"),
            "title": data.get("title"),
            "description": _short_text(data.get("description"), limit=500),
            "status": data.get("status"),
            "phase": data.get("phase"),
            "complexity": data.get("complexity"),
            "retry_count": data.get("retry_count", 0),
            "blocked_reason": data.get("blocked_reason"),
            "capability_limit_reason": data.get("capability_limit_reason"),
            "provider_limit": data.get("provider_limit"),
            "created_at": data.get("created_at"),
            "blocked_at": data.get("blocked_at"),
            "capability_limit_at": data.get("capability_limit_at"),
            "depends_on": _compact_task_depends_on(data.get("depends_on")),
            "gate_results": {
                "count": len(gate_items),
                "items": [
                    compact
                    for compact in (_compact_gate_result(item) for item in gate_items[:10])
                    if compact
                ],
                "omitted": max(len(gate_items) - 10, 0),
            },
            "agent_runs": {
                "count": len(run_items),
                "recent": [
                    compact
                    for compact in (_compact_agent_run(item) for item in run_items[:5])
                    if compact
                ],
                "omitted": max(len(run_items) - 5, 0),
            },
            "matched_on": "id",
            "next_step": f"builder backlog task status {task_id} --json",
            "raw_evidence": {
                "full_payload_command": _TASK_SHOW_FULL_NEXT_STEP.replace("<task-id>", task_id),
                "note": "SDK task_show is compact by default; load full task details only when the compact evidence is insufficient.",
            },
        }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_task_status(task_id: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request("GET", f"/tasks/{task_id}", project_root=project_root)
        payload = {
            "id": data.get("id"),
            "status": data.get("status"),
            "retry_count": data.get("retry_count", 0),
            "blocked_reason": data.get("blocked_reason"),
            "capability_limit_reason": data.get("capability_limit_reason"),
            "next_step": f"builder backlog task show {task_id} --json",
        }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_task_dispatch(task_id: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request(
            "POST",
            "/dispatch",
            project_root=project_root,
            json_body={"task_id": task_id},
        )
        return _mcp_text_payload(data)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_task_recover(task_id: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request(
            "POST",
            f"/tasks/{task_id}/recover",
            project_root=project_root,
        )
        return _mcp_text_payload(data)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_workspace_scaffold(
    task_id: str, *, project_root: str | None = None
) -> dict[str, Any]:
    """Trigger the workspace scaffold step for a task.

    Idempotent: the orchestrator-side helper deterministically skips when a
    language is already detectable. Exposed as `mcp__builder__workspace_scaffold`
    so the chat agent can route a setup intent through the lifecycle instead of
    attempting shell or filesystem workarounds.

    Uses a 300 s timeout because the scaffold agent runs a full agent loop
    that can exceed the default 30 s (IMP-009).
    """
    try:
        data = await _api_request(
            "POST",
            f"/tasks/{task_id}/scaffold",
            project_root=project_root,
            timeout=300.0,
        )
        return _mcp_text_payload(data)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_metrics(project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request("GET", "/dashboard/metrics", project_root=project_root)
        if not isinstance(data, dict):
            return _mcp_text_payload(data)
        runs = data.get("runs")
        optimization = (
            data.get("optimization_summary")
            if isinstance(data.get("optimization_summary"), dict)
            else {}
        )
        compact_payload = {
            key: value
            for key, value in data.items()
            if key not in {"runs", "raw", "voice_ledger", "runtime_decision_summary"}
        }
        if "voice_ledger" in data:
            compact_payload["voice_ledger"] = _compact_voice_ledger(data.get("voice_ledger"))
        if "runtime_decision_summary" in data:
            compact_payload["runtime_decision_summary"] = _compact_runtime_decision_summary(
                data.get("runtime_decision_summary")
            )
        compact_payload["run_count"] = len(runs) if isinstance(runs, list) else 0
        compact_payload["recent_runs"] = (
            [
                {
                    "id": run.get("id", ""),
                    "task_id": run.get("task_id", ""),
                    "agent_name": run.get("agent_name", ""),
                    "status": run.get("status", ""),
                    "runtime_sdk": run.get("runtime_sdk", ""),
                    "model": run.get("model", ""),
                    "effort": run.get("effort", ""),
                    "tokens": int(run.get("tokens_input") or 0)
                    + int(run.get("tokens_output") or 0),
                    "cached_tokens": int(run.get("tokens_cached") or 0),
                    "duration_ms": run.get("duration_ms", 0),
                    "stop_reason": run.get("stop_reason", ""),
                }
                for run in runs[:5]
                if isinstance(run, dict)
            ]
            if isinstance(runs, list)
            else []
        )
        compact_payload["raw_evidence"] = {
            "available": isinstance(runs, list) and len(runs) > 0,
            "command": "builder metrics show --json",
            "full_payload_command": "builder metrics show --json --full",
            "note": "MCP metrics is compact by default; request exact run summaries before loading full raw metrics.",
        }
        compact_payload["optimization_preflight"] = {
            "raw_token_total": optimization.get("raw_token_total", 0),
            "cache_ratio": optimization.get("cache_ratio", 0),
            "avoidable_token_estimate": optimization.get("avoidable_token_estimate", 0),
            "avoidable_cost_flags": optimization.get("avoidable_cost_flags", []),
            "top_cost_drivers": optimization.get("top_cost_drivers", [])[:5]
            if isinstance(optimization.get("top_cost_drivers"), list)
            else [],
            "recommended_next_change": optimization.get("recommended_next_change", ""),
        }
        return _mcp_text_payload(compact_payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


def _backlog_item_compact(item: dict[str, Any]) -> dict[str, Any]:
    item_type = str(item.get("type") or item.get("item_type") or "feature")
    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "type": item_type,
        "title": item.get("title"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "severity": item.get("severity"),
        "source": item.get("source"),
        "tags": item.get("tags") or [],
        "created_at": item.get("created_at"),
    }


async def _default_project_id(project_root: str | None) -> str:
    projects = await _api_request("GET", "/projects/", project_root=project_root)
    if not isinstance(projects, list) or not projects:
        raise BuilderToolServiceError(
            "No builder project found for this repo.",
            detail={"hint": "Initialize the repo project first, then retry the backlog query."},
        )
    return str(projects[0].get("id", "")).strip()


async def builder_backlog_item_list(
    project: str = "",
    item_type: str = "",
    tag: str = "",
    status: str = "",
    limit: int = 50,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        project_id = project.strip() or await _default_project_id(project_root)
        params: dict[str, Any] = {}
        if item_type:
            params["type"] = item_type
        if tag:
            params["tag"] = tag
        items = await _api_request(
            "GET",
            f"/projects/{project_id}/backlog/items",
            project_root=project_root,
            params=params,
        )
        if status:
            items = [item for item in items if item.get("status") == status]
        counts_by_type: dict[str, int] = {}
        for item in items:
            type_name = str(item.get("type") or item.get("item_type") or "feature")
            counts_by_type[type_name] = counts_by_type.get(type_name, 0) + 1
        compact = [_backlog_item_compact(item) for item in items[:limit]]
        payload = compact_results_payload("list", compact, next_step=_BACKLOG_ITEM_LIST_NEXT_STEP)
        payload["project_id"] = project_id
        payload["count"] = len(items)
        payload["counts_by_type"] = counts_by_type
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_backlog_item_show(
    item_id: str,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        data = await _api_request("GET", f"/backlog/items/{item_id}", project_root=project_root)
        payload = _compact_backlog_item_detail(data)
        payload["matched_on"] = "id"
        payload["next_step"] = _BACKLOG_ITEM_SHOW_NEXT_STEP.replace("<item_id>", item_id)
        payload["raw_evidence"] = {
            "full_payload_command": payload["next_step"],
            "note": "SDK backlog_item_show is compact by default; use the CLI command when raw backlog fields are needed.",
        }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_kb_search(
    query: str,
    doc_type: str = "",
    tags: list[str] | None = None,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            items = search_docs(
                query,
                scope="local",
                doc_type=doc_type or None,
                tags=tags,
                limit=10,
            )
            payload = kb_cli._kb_search_payload(query, items)
        return _mcp_text_payload(payload)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _error_payload("knowledge search failed", detail=str(exc))


async def builder_kb_show(doc_id: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            data = find_doc(doc_id, scope="local")
            if data is None:
                raise BuilderToolServiceError(
                    f"Document '{doc_id}' not found",
                    detail=kb_cli._kb_not_found_detail(doc_id),
                )
            payload = _compact_kb_document(dict(data), include_content=True)
            payload["matched_on"] = "id"
            payload["next_step"] = _KB_SHOW_NEXT_STEP
            payload["raw_evidence"] = {
                "full_payload_command": _KB_SHOW_FULL_NEXT_STEP.replace("<doc-id>", doc_id),
                "note": "SDK kb_show includes bounded content by default; use the CLI command for the raw document.",
            }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_kb_contract(
    doc_type: str = "system-docs",
    sample_title: str = "Document Title",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            payload = contract_payload(doc_type=doc_type, sample_title=sample_title)
            payload["next_step"] = _KB_CONTRACT_NEXT_STEP.replace("<doc_type>", payload["doc_type"])
        return _mcp_text_payload(payload)
    except ValueError as exc:
        return _error_payload(str(exc), exit_code=2, detail={"doc_type": doc_type})


async def builder_kb_lint(
    doc_type: str,
    content: str,
    doc_id: str = "",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            linter = DocumentLinter(strict=True)
            source = doc_id or f"<draft:{doc_type}>"
            passed = linter.lint_content(content, source)
            report = linter.get_report()
            errors, warnings = _extract_lint_issues(report)
            payload = {
                "status": "ok" if passed else "error",
                "passed": passed,
                "doc_type": doc_type,
                "doc_id": doc_id,
                "errors": errors,
                "warnings": warnings,
                "summary": "KB contract checks passed." if passed else "KB contract checks failed.",
                "next_step": "" if passed else _KB_LINT_NEXT_STEP,
                "report_preview": truncate(report, 1200),
                "raw_evidence": {
                    "report_chars": len(report),
                    "report_truncated": len(report) > 1200,
                    "note": "SDK kb_lint keeps the report bounded; fix listed errors first, then retry.",
                },
            }
        return _mcp_text_payload(payload, exit_code=0 if passed else 1)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _error_payload(
            "knowledge lint failed", detail={"doc_type": doc_type, "error": str(exc)}
        )


async def builder_kb_add(
    doc_type: str,
    title: str,
    content: str,
    task_id: str = "",
    tags: list[str] | None = None,
    family: str = "",
    linked_feature: str = "",
    feature_id: str = "",
    refresh_required: bool | None = None,
    documented_against_commit: str = "",
    documented_against_ref: str = "",
    owned_paths: list[str] | None = None,
    verified_with: str = "",
    last_verified_at: str = "",
    lifecycle_status: str = "",
    superseded_by: str = "",
    source_url: str = "",
    source_title: str = "",
    source_author: str = "",
    date_published: str = "",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            payload = publish_document(
                title=title,
                body=content,
                doc_type=doc_type,
                tags=kb_cli._normalize_tags(
                    None,
                    doc_type=doc_type,
                    family=family or None,
                    tag_values=tags,
                ),
                scope="local",
                task_id=task_id,
                source_url=source_url or None,
                source_title=source_title or None,
                source_author=source_author or None,
                date_published=date_published or None,
                extra_fields=kb_cli._system_doc_extra_fields(
                    family=family or None,
                    linked_feature=linked_feature or None,
                    feature_id=feature_id or None,
                    refresh_required=refresh_required,
                    documented_against_commit=documented_against_commit or None,
                    documented_against_ref=documented_against_ref or None,
                    owned_paths=owned_paths or None,
                    verified_with=verified_with or None,
                    last_verified_at=last_verified_at or None,
                    lifecycle_status=lifecycle_status or None,
                    superseded_by=superseded_by or None,
                ),
            )
            payload = _compact_kb_document(payload, include_content=False)
            payload["status"] = "ok"
            payload["mutation"] = "created"
            payload["next_step"] = _KB_SHOW_FULL_NEXT_STEP.replace("<doc-id>", str(payload["id"]))
            payload["raw_evidence"] = {
                "full_payload_command": payload["next_step"],
                "note": "SDK kb_add returns compact mutation evidence; read the document only if the write metadata is insufficient.",
            }
        return _mcp_text_payload(payload)
    except PublishError as exc:
        return _error_payload(str(exc), detail={"doc_type": doc_type, "title": title})


async def builder_kb_update(
    doc_id: str,
    title: str = "",
    content: str = "",
    tags: list[str] | None = None,
    family: str = "",
    linked_feature: str = "",
    feature_id: str = "",
    refresh_required: bool | None = None,
    documented_against_commit: str = "",
    documented_against_ref: str = "",
    owned_paths: list[str] | None = None,
    verified_with: str = "",
    last_verified_at: str = "",
    lifecycle_status: str = "",
    superseded_by: str = "",
    source_url: str = "",
    source_title: str = "",
    source_author: str = "",
    date_published: str = "",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            existing = find_doc(doc_id, scope="local")
            normalized_tags = None
            if tags is not None:
                if existing is None:
                    raise PublishError(f"Document '{doc_id}' not found")
                normalized_tags = kb_cli._normalize_tags(
                    None,
                    doc_type=str(existing.get("doc_type", "")),
                    family=family or str(existing.get("doc_family", "") or "") or None,
                    tag_values=tags,
                )
            payload = update_document(
                doc_id=doc_id,
                scope="local",
                title=title or None,
                body=content if content else None,
                source_url=source_url or None,
                source_title=source_title or None,
                source_author=source_author or None,
                date_published=date_published or None,
                extra_fields=kb_cli._system_doc_extra_fields(
                    family=family or None,
                    linked_feature=linked_feature or None,
                    feature_id=feature_id or None,
                    refresh_required=refresh_required,
                    documented_against_commit=documented_against_commit or None,
                    documented_against_ref=documented_against_ref or None,
                    owned_paths=owned_paths or None,
                    verified_with=verified_with or None,
                    last_verified_at=last_verified_at or None,
                    lifecycle_status=lifecycle_status or None,
                    superseded_by=superseded_by or None,
                )
                or None,
                tags=normalized_tags,
            )
            payload = _compact_kb_document(payload, include_content=False)
            payload["status"] = "ok"
            payload["mutation"] = "updated"
            payload["next_step"] = _KB_SHOW_FULL_NEXT_STEP.replace("<doc-id>", str(payload["id"]))
            payload["raw_evidence"] = {
                "full_payload_command": payload["next_step"],
                "note": "SDK kb_update returns compact mutation evidence; read the document only if the write metadata is insufficient.",
            }
        return _mcp_text_payload(payload)
    except PublishError as exc:
        return _error_payload(str(exc), detail={"doc_id": doc_id})


async def builder_kb_validate(
    kb_dir: str = "system-docs",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            normalized_kb_dir, _kb_root, kb_path = validate_repo_local_kb_dir(
                kb_dir,
                project_root=project_root,
            )
            if not kb_path.exists():
                raise BuilderToolServiceError(
                    f"Knowledge base not found at {kb_path}",
                    exit_code=1,
                    detail={"kb_dir": normalized_kb_dir},
                )
            payload = validate_output_payload(KnowledgeQualityGate(kb_path, Path.cwd()).validate())
        return _mcp_text_payload(payload, exit_code=0 if payload["passed"] else 1)
    except BuilderToolServiceError as exc:
        hint = ""
        if isinstance(exc.detail, dict) and exc.detail.get("safe_lane"):
            hint = (
                'Retry with `kb_dir: "system-docs"` or another relative directory under '
                "`.agent-builder/knowledge/`."
            )
        elif isinstance(exc.detail, dict) and exc.detail.get("kb_dir"):
            hint = "Run `builder knowledge list` to inspect available repo-local KB directories."
        return _error_payload(str(exc), exit_code=exc.exit_code, hint=hint, detail=exc.detail)


async def builder_kb_extract(
    kb_dir: str = DEFAULT_LOCAL_KB_COLLECTION,
    scope: str = "full",
    doc_slug: str = "",
    force: bool = False,
    run_validation: bool = True,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        workspace_path = Path(project_root).resolve() if project_root else Path.cwd()
        with _project_scope(project_root):
            if (kb_dir or DEFAULT_LOCAL_KB_COLLECTION) != DEFAULT_LOCAL_KB_COLLECTION:
                payload = kb_cli._build_extract_contract(
                    kb_path=workspace_path
                    / ".agent-builder"
                    / "knowledge"
                    / (kb_dir or DEFAULT_LOCAL_KB_COLLECTION),
                    documents=[],
                    errors=[{"stage": "preflight", "error": "noncanonical_output_dir"}],
                    graph=None,
                    lint=None,
                    deterministic_validation=None,
                    agent_advisory=None,
                    passed=False,
                    operator_message=(
                        "Only the canonical local KB collection is supported. "
                        f"Use {DEFAULT_LOCAL_KB_COLLECTION}."
                    ),
                    next_step=kb_cli._kb_extract_next_step(
                        action="stop",
                        reason="noncanonical_output_dir",
                        recommended_command=(
                            "builder knowledge extract "
                            f"--output-dir {DEFAULT_LOCAL_KB_COLLECTION} --json"
                        ),
                    ),
                )
                return _mcp_text_payload(payload, exit_code=1)

            agent_builder_dir = workspace_path / ".agent-builder"
            kb_path = agent_builder_dir / "knowledge" / DEFAULT_LOCAL_KB_COLLECTION
            if not agent_builder_dir.exists():
                payload = kb_cli._build_extract_contract(
                    kb_path=kb_path,
                    documents=[],
                    errors=[{"stage": "preflight", "error": ".agent-builder/ not found"}],
                    graph=None,
                    lint=None,
                    deterministic_validation=None,
                    agent_advisory=None,
                    passed=False,
                    operator_message=".agent-builder/ not found. Run 'builder init' first.",
                    next_step=kb_cli._kb_extract_next_step(
                        action="stop",
                        reason="builder_dir_missing",
                        recommended_command="builder init",
                    ),
                )
                return _mcp_text_payload(payload, exit_code=1)

            if kb_path.exists() and not force:
                target_file = kb_path / f"{doc_slug}.md" if doc_slug else None
                if doc_slug and (not target_file or not target_file.exists()):
                    target_file = None
                if not doc_slug or target_file is not None:
                    payload = kb_cli._build_extract_contract(
                        kb_path=kb_path,
                        documents=[],
                        errors=[{"stage": "preflight", "error": "knowledge_already_exists"}],
                        graph=None,
                        lint=None,
                        deterministic_validation=None,
                        agent_advisory=None,
                        passed=False,
                        operator_message=(
                            f"Knowledge already extracted at {kb_path}. "
                            "Use force=true to regenerate."
                        ),
                        next_step=kb_cli._kb_extract_next_step(
                            action="stop",
                            reason="knowledge_already_exists",
                            recommended_command=(
                                "builder knowledge extract --force "
                                f"--doc {doc_slug} --output-dir {DEFAULT_LOCAL_KB_COLLECTION} --json"
                                if doc_slug
                                else (
                                    "builder knowledge extract --force "
                                    f"--output-dir {DEFAULT_LOCAL_KB_COLLECTION} --json"
                                )
                            ),
                        ),
                    )
                    return _mcp_text_payload(payload, exit_code=1)

            payload = kb_cli._run_extract_pipeline(
                workspace_path=workspace_path,
                kb_path=kb_path,
                scope=scope,
                run_validation=run_validation,
                doc_slug=doc_slug or None,
            )
        return _mcp_text_payload(payload, exit_code=0 if payload.get("passed") else 1)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _error_payload("knowledge extract failed", detail=str(exc))


async def builder_memory_search(
    query: str,
    entity: str = "",
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            entries = memory_cli._load_routing()
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            matches: list[dict[str, Any]] = []
            for entry in entries:
                if entity and entry.get("entity") != entity:
                    continue
                body = memory_cli._body_for_entry(entry)
                haystacks = [entry.get("title", ""), " ".join(entry.get("tags", [])), body]
                if any(pattern.search(str(haystack)) for haystack in haystacks):
                    matches.append(
                        memory_cli._memory_compact(
                            entry,
                            preview=truncate(body.replace("\n", " "), 160),
                        )
                    )
            payload = compact_results_payload(
                query,
                matches[:10],
                next_step=_MEMORY_SHOW_NEXT_STEP,
            )
        return _mcp_text_payload(payload)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _error_payload("memory search failed", detail=str(exc))


async def builder_memory_show(slug: str, *, project_root: str | None = None) -> dict[str, Any]:
    try:
        with _project_scope(project_root):
            entries = memory_cli._load_routing()
            entry, matched_on, suggestions = _memory_query_resolution(slug, entries)
            if entry is None:
                raise BuilderToolServiceError(
                    f"Memory not found: {slug}",
                    detail={"query": slug, "suggestions": suggestions},
                )
            content = memory_cli._read_text(memory_cli._entry_path(entry))
            payload = {
                **entry,
                "content": truncate(content),
                "matched_on": matched_on,
                "next_step": _MEMORY_SHOW_NEXT_STEP,
            }
        return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)


async def builder_recommendation_create(
    target_path: str,
    title: str,
    rationale: str,
    *,
    suggested_value: str | None = None,
    current_value: str | None = None,
    severity: str = "medium",
    evidence: dict[str, Any] | None = None,
    source_session_id: str | None = None,
    source_run_id: str | None = None,
    source_task_id: str | None = None,
) -> dict[str, Any]:
    """File a builder-side improvement suggestion for human review.

    Optimization-agent's blast radius is the target app workspace. Anything
    that would change Autonomous Agent Builder internals (``_AGENT_POLICY``,
    agent definitions, dispatch routing, builder hooks/subagents, builder
    repo source) must NOT be edited directly — it lands here as a
    ``BuilderRecommendation`` for a human maintainer to review and apply.

    See plan: P9a; ownership memo:
    sprint-1-dispatch-exposed-critical-scope-handoff-and-gate-routing.
    """
    from autonomous_agent_builder.db.models import BuilderRecommendation
    from autonomous_agent_builder.db.session import get_session_factory

    severity_value = severity.strip().lower() or "medium"
    if severity_value not in {"low", "medium", "high", "critical"}:
        return _error_payload(
            "severity must be one of: low, medium, high, critical",
            exit_code=2,
        )
    target = (target_path or "").strip()
    if not target:
        return _error_payload("target_path is required", exit_code=2)
    if not (title or "").strip():
        return _error_payload("title is required", exit_code=2)
    if not (rationale or "").strip():
        return _error_payload("rationale is required", exit_code=2)

    factory = get_session_factory()
    try:
        async with factory() as db:
            record = BuilderRecommendation(
                source_session_id=source_session_id,
                source_run_id=source_run_id,
                source_task_id=source_task_id,
                target_path=target,
                title=title.strip(),
                rationale=rationale.strip(),
                current_value=current_value,
                suggested_value=suggested_value,
                evidence_json=evidence or {},
                severity=severity_value,
                status="pending_review",
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)
            payload = {
                "id": record.id,
                "target_path": record.target_path,
                "title": record.title,
                "severity": record.severity,
                "status": record.status,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "next_step": (
                    "A maintainer reviews this recommendation via the dashboard Inbox / "
                    "`builder backlog item list --type optimization` before any builder-repo "
                    "change is made."
                ),
            }
            return _mcp_text_payload(payload)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)
    except Exception as exc:  # pragma: no cover — defensive boundary
        return _error_payload(
            f"Failed to record builder recommendation: {exc}",
            exit_code=1,
        )


async def builder_memory_add(
    mem_type: str,
    phase: str,
    entity: str,
    tags: str,
    title: str,
    content: str,
    *,
    project_root: str | None = None,
) -> dict[str, Any]:
    try:
        if mem_type not in memory_cli.TYPE_DIRS:
            raise BuilderToolServiceError(
                "--type must be one of decision, pattern, correction",
                exit_code=2,
            )

        with _project_scope(project_root):
            slug = memory_cli._slugify(title)
            entry = {
                "slug": slug,
                "file": f"{memory_cli.TYPE_DIRS[mem_type]}/{slug}.md",
                "title": title,
                "type": mem_type,
                "phase": phase,
                "entity": entity,
                "tags": [tag.strip() for tag in tags.split(",") if tag.strip()],
                "status": "active",
                "related": [],
                "date": memory_cli.datetime.now(memory_cli.UTC).strftime("%Y-%m-%d"),
                "preserve_as_precedent": False,
                "flag_reason": "",
                "graduated_into": "",
            }
            memory_cli._write_entry_file(entry, content)
            post_mutation = memory_cli._post_mutation_check(slug)
            payload = {**entry, "post_mutation": post_mutation}
            exit_code = memory_cli._post_mutation_exit_code(post_mutation)
        return _mcp_text_payload(payload, exit_code=exit_code)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)
