"""Feature and Task CRUD routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot
from autonomous_agent_builder.api.schemas import (
    BacklogItemCreate,
    BacklogItemResponse,
    BacklogItemUpdate,
    FeatureCreate,
    FeatureResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from autonomous_agent_builder.backlog_items import (
    feature_to_item_payload,
    mirror_item_to_artifact,
    normalize_feature_status,
    normalize_item_type,
    normalize_severity,
    normalize_source,
    parse_tags,
    require_primary_tag,
)
from autonomous_agent_builder.db.models import (
    BacklogItemSeverity,
    BacklogItemSource,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.knowledge.system_docs import reconcile_task_system_docs
from autonomous_agent_builder.services.project_context import request_project_root

router = APIRouter(tags=["features"])


def _project_root(request: Request):
    return request_project_root(request)


def _feature_payload(feature: Feature) -> dict:
    return feature_to_item_payload(feature)


def _item_enums(
    data: BacklogItemCreate,
) -> tuple[BacklogItemType, list[str], BacklogItemSeverity | None, BacklogItemSource]:
    item_type = normalize_item_type(data.item_type)
    severity = normalize_severity(data.severity, item_type=item_type)
    if item_type == "incident" and not data.evidence.strip():
        raise ValueError("incident evidence is required")
    return (
        BacklogItemType(item_type),
        require_primary_tag(parse_tags(data.tags)),
        BacklogItemSeverity(severity) if severity else None,
        BacklogItemSource(normalize_source(data.source)),
    )


def _update_item_enums(
    item: Feature,
    data: BacklogItemUpdate,
) -> tuple[BacklogItemType, list[str], BacklogItemSeverity | None, BacklogItemSource]:
    item_type = normalize_item_type(data.item_type or item.item_type)
    tags = require_primary_tag(parse_tags(data.tags if data.tags is not None else item.tags))
    severity_input = (
        data.severity
        if data.severity is not None
        else (item.severity.value if hasattr(item.severity, "value") else item.severity)
    )
    severity = normalize_severity(severity_input, item_type=item_type)
    source = normalize_source(
        data.source
        if data.source is not None
        else (item.source.value if hasattr(item.source, "value") else item.source)
    )
    evidence = data.evidence if data.evidence is not None else item.evidence
    if item_type == "incident" and not str(evidence or "").strip():
        raise ValueError("incident evidence is required")
    return (
        BacklogItemType(item_type),
        tags,
        BacklogItemSeverity(severity) if severity else None,
        BacklogItemSource(source),
    )


async def _create_backlog_item(
    project_id: str,
    data: BacklogItemCreate,
    db: AsyncSession,
    project_root: Path,
) -> Feature:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        item_type, tags, severity, source = _item_enums(data)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_backlog_item", "message": str(exc)}
        ) from exc

    item = Feature(
        project_id=project_id,
        title=data.title,
        description=data.description,
        status=FeatureStatus.BACKLOG,
        priority=data.priority,
        item_type=item_type,
        tags=tags,
        severity=severity,
        source=source,
        evidence=data.evidence,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    mirror_item_to_artifact(project_root, feature_to_item_payload(item))
    return item


# ── Features ──


@router.post("/projects/{project_id}/features", response_model=FeatureResponse, status_code=201)
async def create_feature(
    project_id: str,
    data: FeatureCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    item = await _create_backlog_item(
        project_id,
        BacklogItemCreate(
            type="feature",
            title=data.title,
            description=data.description,
            priority=data.priority,
            tags=data.tags,
            severity=data.severity,
            source=data.source,
            evidence=data.evidence,
        ),
        db,
        _project_root(request),
    )
    return _feature_payload(item)


@router.get("/projects/{project_id}/features", response_model=list[FeatureResponse])
async def list_features(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .where(Feature.item_type == BacklogItemType.FEATURE)
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
    )
    return [_feature_payload(feature) for feature in result.scalars().all()]


@router.get("/features/{feature_id}", response_model=FeatureResponse)
async def get_feature(feature_id: str, db: AsyncSession = Depends(get_db)):
    feature = await db.get(Feature, feature_id)
    if not feature or feature.item_type != BacklogItemType.FEATURE:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _feature_payload(feature)


@router.post(
    "/projects/{project_id}/backlog/items", response_model=BacklogItemResponse, status_code=201
)
async def create_backlog_item(
    project_id: str,
    data: BacklogItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    item = await _create_backlog_item(project_id, data, db, _project_root(request))
    return _feature_payload(item)


@router.get("/projects/{project_id}/backlog/items", response_model=list[BacklogItemResponse])
async def list_backlog_items(
    project_id: str,
    item_type: str | None = Query(None, alias="type"),
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Feature).where(Feature.project_id == project_id)
    if item_type:
        try:
            query = query.where(
                Feature.item_type == BacklogItemType(normalize_item_type(item_type))
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "invalid_backlog_item", "message": str(exc)}
            ) from exc
    result = await db.execute(query.order_by(Feature.priority.desc(), Feature.created_at.desc()))
    items = [_feature_payload(feature) for feature in result.scalars().all()]
    if tag:
        tag_value = tag.strip().lower()
        items = [item for item in items if tag_value in item.get("tags", [])]
    return items


@router.get("/backlog/items/{item_id}", response_model=BacklogItemResponse)
async def get_backlog_item(item_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(Feature, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    return _feature_payload(item)


@router.put("/backlog/items/{item_id}", response_model=BacklogItemResponse)
async def update_backlog_item(
    item_id: str,
    data: BacklogItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(Feature, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    try:
        item_type, tags, severity, source = _update_item_enums(item, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_backlog_item", "message": str(exc)},
        ) from exc

    if data.title is not None:
        item.title = data.title
    if data.description is not None:
        item.description = data.description
    if data.status is not None:
        try:
            item.status = normalize_feature_status(data.status)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_backlog_item", "message": str(exc)},
            ) from exc
    if data.priority is not None:
        item.priority = data.priority
    if data.evidence is not None:
        item.evidence = data.evidence

    item.item_type = item_type
    item.tags = tags
    item.severity = severity
    item.source = source

    await db.flush()
    await db.refresh(item)
    mirror_item_to_artifact(_project_root(request), _feature_payload(item))
    await db.commit()
    return _feature_payload(item)


# ── Tasks ──


@router.post("/features/{feature_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(feature_id: str, data: TaskCreate, db: AsyncSession = Depends(get_db)):
    feature = await db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    depends_on = reconcile_task_system_docs(data.depends_on)
    task = Task(
        feature_id=feature_id,
        title=data.title,
        description=data.description,
        complexity=data.complexity,
        depends_on=depends_on,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await db.commit()
    await publish_board_snapshot(db)
    return task


@router.get("/features/{feature_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(feature_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.feature_id == feature_id).order_by(Task.created_at)
    )
    return result.scalars().all()


@router.get("/tasks", response_model=list[TaskResponse])
async def list_all_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, data: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if data.title is not None:
        task.title = data.title
    if data.description is not None:
        task.description = data.description
    if data.complexity is not None:
        task.complexity = data.complexity
    if data.depends_on is not None:
        task.depends_on = reconcile_task_system_docs(data.depends_on)

    await db.flush()
    await db.refresh(task)
    await db.commit()
    await publish_board_snapshot(db)
    return task
