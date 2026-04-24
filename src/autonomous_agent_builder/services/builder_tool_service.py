"""Shared builder services for SDK-facing MCP tools.

These functions preserve the builder JSON contract exposed to the agent runtime
without shelling out to `builder --json` internally.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
from typing import Any

import httpx

from autonomous_agent_builder.cli.client import resolve_base_url
from autonomous_agent_builder.cli.commands import kb as kb_cli
from autonomous_agent_builder.cli.commands import memory as memory_cli
from autonomous_agent_builder.cli.output import truncate
from autonomous_agent_builder.cli.retrieval import compact_results_payload
from autonomous_agent_builder.knowledge.document_spec import DocumentLinter, contract_payload
from autonomous_agent_builder.knowledge.kb_paths import resolve_repo_local_kb_path
from autonomous_agent_builder.knowledge.publisher import DEFAULT_LOCAL_KB_COLLECTION
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate
from autonomous_agent_builder.knowledge.publisher import PublishError, publish_document, update_document
from autonomous_agent_builder.knowledge.retrieval import find_doc, search_docs

_TASK_LIST_NEXT_STEP = "builder backlog task summary <query> --json"
_KB_SHOW_NEXT_STEP = "builder knowledge summary <query> --json"
_MEMORY_SHOW_NEXT_STEP = "builder memory summary <query> --json"
_KB_CONTRACT_NEXT_STEP = "builder knowledge contract --type <doc_type> --json"
_KB_LINT_NEXT_STEP = "Fix the listed contract issues, then retry the KB mutation."


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
        elif "⚠️" in stripped:
            warnings.append(stripped.split("⚠️", 1)[1].strip())
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
) -> Any:
    with _project_scope(project_root):
        base_url = resolve_base_url()

    api_path = path if path.startswith("/api") else f"/api{path}"
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
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
        "preview": _task_preview(item),
    }


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
        for section in ("pending", "active", "review", "done", "blocked"):
            if section in data and isinstance(data[section], list):
                data[section] = data[section][:50]
        return _mcp_text_payload(data)
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
        items = await _api_request("GET", f"/features/{feature_id}/tasks", project_root=project_root)
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
        data["gate_results"] = await _api_request(
            "GET",
            f"/tasks/{task_id}/gates",
            project_root=project_root,
        )
        data["agent_runs"] = await _api_request(
            "GET",
            f"/tasks/{task_id}/runs",
            project_root=project_root,
        )
        data["matched_on"] = "id"
        data["next_step"] = f"builder backlog task status {task_id} --json"
        return _mcp_text_payload(data)
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


async def builder_metrics(project_root: str | None = None) -> dict[str, Any]:
    try:
        data = await _api_request("GET", "/dashboard/metrics", project_root=project_root)
        return _mcp_text_payload(data)
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
            payload = dict(data)
            payload["matched_on"] = "id"
            if isinstance(payload.get("content"), str):
                payload["content"] = truncate(payload["content"])
            payload["next_step"] = _KB_SHOW_NEXT_STEP
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
                "report": report,
            }
        return _mcp_text_payload(payload, exit_code=0 if passed else 1)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _error_payload("knowledge lint failed", detail={"doc_type": doc_type, "error": str(exc)})


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
            payload = kb_cli._validate_output_payload(
                KnowledgeQualityGate(kb_path, Path.cwd()).validate()
            )
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
            entries = [item for item in memory_cli._load_routing() if item.get("slug") != slug]
            entries.append(entry)
            memory_cli._write_entry_file(entry, content)
            memory_cli._save_routing(entries)
        return _mcp_text_payload(entry)
    except BuilderToolServiceError as exc:
        return _error_payload(str(exc), exit_code=exc.exit_code, detail=exc.detail)
