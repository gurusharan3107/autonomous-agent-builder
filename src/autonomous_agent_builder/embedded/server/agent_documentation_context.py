"""Documentation-specialist context assembly for Agent chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import Feature, Task
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_delivery_lifecycle,
    message_requests_feature_spec,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_has_documentation_intent,
    message_suggests_recent_change,
    resolve_documentation_action,
    task_has_doc_expectations,
    task_required_docs,
)
from autonomous_agent_builder.knowledge.maintained_freshness import (
    git_current_branch,
    git_head_for_ref,
    maintained_doc_report,
    resolve_canonical_doc_ref,
)
from autonomous_agent_builder.knowledge.publisher import parse_markdown_document
from autonomous_agent_builder.knowledge.retrieval import load_docs, search_docs


async def latest_task_context(db: AsyncSession) -> Task | None:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def knowledge_doc_path(project_root: Path, doc_id: str) -> Path:
    return project_root / ".agent-builder" / "knowledge" / doc_id


def doc_context_view(project_root: Path, doc: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "id": str(doc.get("id", "")),
        "title": str(doc.get("title", "")),
        "doc_type": str(doc.get("doc_type", "")),
        "task_id": str(doc.get("task_id", "")),
        "doc_family": str(doc.get("doc_family", "")),
        "tags": list(doc.get("tags", [])),
        "card_summary": str(doc.get("card_summary", "")),
        "detail_summary": str(doc.get("detail_summary", "")),
    }
    doc_path = knowledge_doc_path(project_root, payload["id"])
    if not doc_path.exists():
        return payload
    parsed = parse_markdown_document(
        doc_path.read_text(encoding="utf-8"),
        default_doc_type=payload["doc_type"] or "context",
    )
    metadata = parsed.extra_fields
    payload.update(
        {
            "refresh_required": bool(metadata.get("refresh_required", False)),
            "updated": parsed.updated or "",
            "last_verified_at": str(metadata.get("last_verified_at", "") or ""),
            "lifecycle_status": str(metadata.get("lifecycle_status", "") or ""),
            "superseded_by": str(metadata.get("superseded_by", "") or ""),
            "linked_feature": str(metadata.get("linked_feature", "") or ""),
            "feature_id": str(metadata.get("feature_id", "") or ""),
            "documented_against_commit": str(metadata.get("documented_against_commit", "") or ""),
            "documented_against_ref": str(metadata.get("documented_against_ref", "") or ""),
            "owned_paths": metadata.get("owned_paths")
            if isinstance(metadata.get("owned_paths"), list)
            else [],
        }
    )
    return payload


def search_targeted_docs(
    project_root: Path,
    *,
    query: str,
    task: Task | None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_doc(doc: dict[str, Any]) -> None:
        doc_id = str(doc.get("id", ""))
        if not doc_id or doc_id in seen or doc.get("doc_type") not in {"feature", "testing"}:
            return
        seen.add(doc_id)
        docs.append(doc_context_view(project_root, doc))

    required_docs = task_required_docs(task.depends_on) if task is not None else []
    for doc_id in required_docs:
        for doc in load_docs(scope="local"):
            if str(doc.get("id", "")) == doc_id:
                add_doc(doc)
                break
    if task is not None:
        query_parts = [
            str(task.title or ""),
            str(getattr(task.feature, "title", "") or ""),
            str(task.feature_id or ""),
        ]
        for query_part in query_parts:
            for doc in search_docs(query_part, scope="local", limit=limit):
                add_doc(doc)
                if len(docs) >= limit:
                    return docs[:limit]
    for doc in search_docs(query, scope="local", limit=limit):
        add_doc(doc)
        if len(docs) >= limit:
            break
    return docs[:limit]


def freshness_candidates(project_root: Path, *, limit: int = 6) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for doc in load_docs(scope="local"):
        if doc.get("doc_type") not in {"feature", "testing"}:
            continue
        lifecycle_status = str(doc.get("lifecycle_status", "") or "").strip().lower()
        if lifecycle_status in {"superseded", "quarantined"}:
            continue
        metadata = {
            "created": doc.get("created_at", ""),
            "updated": doc.get("updated", ""),
            "linked_feature": doc.get("linked_feature", ""),
            "feature_id": doc.get("feature_id", ""),
            "task_id": doc.get("task_id", ""),
            "documented_against_commit": doc.get("documented_against_commit", ""),
            "documented_against_ref": doc.get("documented_against_ref", ""),
            "owned_paths": doc.get("owned_paths", []),
        }
        report = maintained_doc_report(
            workspace_path=project_root,
            doc_id=str(doc.get("id", "")),
            doc_type=str(doc.get("doc_type", "")),
            lifecycle_status=lifecycle_status or "active",
            metadata=metadata,
            created=str(doc.get("created_at", "") or ""),
            updated=str(doc.get("updated", "") or ""),
        ).to_dict()
        if report["status"] == "current":
            continue
        reports.append(report)
    reports.sort(key=lambda item: (item["blocking"], item["status"], item["doc_id"]), reverse=True)
    return reports[:limit]


async def documentation_context_pack(
    db: AsyncSession,
    project_root: Path,
    user_message: str,
    *,
    route_reason_override: str | None = None,
    force_route: bool = False,
) -> dict[str, Any] | None:
    explicit_intent = message_has_documentation_intent(user_message)
    feature_spec_request = message_requests_feature_spec(user_message)
    delivery_lifecycle_request = message_requests_delivery_lifecycle(user_message)
    recent_change_signal = message_suggests_recent_change(user_message)
    latest_task = await latest_task_context(db)
    has_doc_expectations = task_has_doc_expectations(latest_task)
    if not force_route and (
        feature_spec_request
        or delivery_lifecycle_request
        or not explicit_intent
        and not (has_doc_expectations and recent_change_signal)
    ):
        return None

    task_payload: dict[str, Any] | None = None
    if latest_task is not None:
        task_payload = {
            "task_id": latest_task.id,
            "task_title": latest_task.title,
            "task_description": latest_task.description,
            "feature_id": latest_task.feature_id,
            "feature_title": getattr(latest_task.feature, "title", ""),
            "required_docs": task_required_docs(latest_task.depends_on),
        }

    route_reason = route_reason_override or (
        "explicit_intent" if explicit_intent else "active_task_doc_expectation"
    )
    targeted_docs = search_targeted_docs(
        project_root,
        query=user_message,
        task=latest_task,
        limit=4,
    )
    current_branch = git_current_branch(project_root) or ""
    canonical_ref = resolve_canonical_doc_ref(project_root)
    canonical_head = git_head_for_ref(project_root, canonical_ref) or ""
    resolution = resolve_documentation_action(
        user_message=user_message,
        targeted_docs=targeted_docs,
        current_branch=current_branch,
        canonical_ref=canonical_ref,
    )
    return {
        "route_reason": route_reason,
        "project_root": str(project_root),
        "current_branch": current_branch,
        "canonical_ref": canonical_ref,
        "canonical_head": canonical_head,
        "canonical_refresh_mode": "canonical"
        if current_branch == canonical_ref
        else "advisory_only",
        "user_brief": " ".join(user_message.split())[:240],
        "task": task_payload,
        "recent_change_signal": recent_change_signal,
        "targeted_docs": targeted_docs,
        "resolved_action": resolution["action"],
        "target_doc_type": resolution["target_doc_type"],
        "mode": resolution["mode"],
        "testing_scope": resolution["testing_scope"],
        "freshness_mode": resolution["freshness_mode"],
        "doc_id": resolution["doc_id"],
        "requires_validate": resolution["requires_validate"],
        "doc_exists": resolution["doc_exists"],
        "targeted_doc_count": resolution["targeted_doc_count"],
        "retry_budget": resolution["retry_budget"],
        "freshness_candidates": freshness_candidates(project_root),
    }
