"""Feature delivery persistence helpers for the embedded Agent route."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import ChatEvent, Feature, FeatureStatus, Project, Task
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    captured_feature_title_from_text,
)


async def latest_project_id(db: AsyncSession) -> str | None:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(1))
    project = result.scalar_one_or_none()
    return project.id if project is not None else None


async def persist_feature_spec(db: AsyncSession, payload: dict[str, Any]) -> Feature | None:
    project_id = await latest_project_id(db)
    if not project_id:
        return None
    feature = Feature(
        project_id=project_id,
        title=payload["title"],
        description=payload["description"],
        priority=payload["priority"],
        acceptance_criteria=[
            str(item).strip()
            for item in payload.get("acceptance_criteria", [])
            if str(item).strip()
        ],
        dependencies=[
            str(item).strip() for item in payload.get("dependencies", []) if str(item).strip()
        ],
        proposed_tasks=[
            {
                "title": str(task.get("title", "")).strip(),
                "purpose": str(task.get("purpose", "")).strip(),
            }
            for task in payload.get("proposed_tasks", [])
            if isinstance(task, dict) and str(task.get("title", "")).strip()
        ],
    )
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    return feature


async def create_feature_delivery_task(
    db: AsyncSession,
    feature: Feature,
    payload: dict[str, Any],
) -> Task:
    acceptance_criteria = [
        f"- {item}" for item in payload.get("acceptance_criteria", []) if str(item).strip()
    ]
    dependencies = [f"- {item}" for item in payload.get("dependencies", []) if str(item).strip()]
    description_sections = [str(payload.get("description", "")).strip()]
    if acceptance_criteria:
        description_sections.append("Acceptance criteria:\n" + "\n".join(acceptance_criteria))
    if dependencies:
        description_sections.append("Dependencies:\n" + "\n".join(dependencies))
    task = Task(
        feature_id=feature.id,
        title=f"Deliver {feature.title}",
        description="\n\n".join(section for section in description_sections if section).strip(),
        complexity=min(max(len(acceptance_criteria), 1), 3),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def latest_saved_feature_for_delivery(
    db: AsyncSession,
    user_message: str,
) -> Feature | None:
    result = await db.execute(
        select(Feature)
        .options(selectinload(Feature.tasks))
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
        .limit(25)
    )
    features = list(result.scalars().all())
    if not features:
        return None

    lower_message = user_message.lower()
    for feature in features:
        if feature.title.lower() in lower_message:
            return feature
    deliverable = [
        feature
        for feature in features
        if feature.status
        in {
            FeatureStatus.BACKLOG,
            FeatureStatus.PLANNING,
        }
    ]
    if "todo" in lower_message or "backlog" in lower_message:
        product_backlog = [
            feature
            for feature in deliverable
            if "todo" in f"{feature.title} {feature.description}".lower()
            or feature.status == FeatureStatus.BACKLOG
        ]
        if product_backlog:
            return product_backlog[0]
    if deliverable:
        return deliverable[0]
    return features[0]


async def feature_for_delivery_permission_question(
    db: AsyncSession,
    event: ChatEvent,
) -> Feature | None:
    payload = event.payload_json if isinstance(event.payload_json, dict) else {}
    assistant_event_id = str(payload.get("assistant_event_id") or "").strip()
    assistant_content = ""
    if assistant_event_id:
        assistant_event = await db.get(ChatEvent, assistant_event_id)
        if assistant_event is not None and isinstance(assistant_event.payload_json, dict):
            assistant_content = str(assistant_event.payload_json.get("content") or "")

    captured_title = captured_feature_title_from_text(assistant_content)
    if captured_title:
        result = await db.execute(
            select(Feature)
            .where(Feature.title == captured_title)
            .order_by(Feature.created_at.desc())
            .limit(1)
        )
        feature = result.scalar_one_or_none()
        if feature is not None:
            return feature

    return await latest_saved_feature_for_delivery(
        db,
        " ".join(
            part
            for part in (
                assistant_content,
                str(payload.get("question") or ""),
            )
            if part
        ),
    )


async def ensure_feature_delivery_task(db: AsyncSession, feature: Feature) -> tuple[Task, bool]:
    title = f"Deliver {feature.title}"
    for task in feature.tasks:
        if task.title == title:
            return task, False

    task = await create_feature_delivery_task(
        db,
        feature,
        {
            "description": feature.description,
            "acceptance_criteria": list(feature.acceptance_criteria or []),
            "dependencies": list(feature.dependencies or []),
        },
    )
    return task, True


async def schedule_task_dispatch(task_id: str) -> None:
    from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

    asyncio.create_task(_run_dispatch(task_id))
