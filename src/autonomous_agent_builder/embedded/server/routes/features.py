"""Feature API routes for the embedded server."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    TERMINAL_FEATURE_STATUSES,
    BacklogItemSeverity,
    BacklogItemSource,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Project,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.onboarding import sync_forward_engineering_feature_backlog
from autonomous_agent_builder.services.project_context import request_project_root

router = APIRouter()


class FeatureCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 0
    item_type: str = "feature"
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    source: str = "manual"
    evidence: str = ""


class BacklogItemCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 0
    item_type: str = "feature"
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    source: str = "manual"
    evidence: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_type_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "type" in data and "item_type" not in data:
            return {**data, "item_type": data["type"]}
        return data


class BacklogItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    item_type: str | None = None
    tags: list[str] | None = None
    severity: str | None = None
    source: str | None = None
    evidence: str | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_type_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "type" in data and "item_type" not in data:
            return {**data, "item_type": data["type"]}
        return data


def _project_root(request: Request):
    return request_project_root(request)


def _feature_payload(feature: Feature) -> dict[str, object]:
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


@router.get("/features")
async def list_features(request: Request, db: AsyncSession = Depends(get_db)):
    """List all features for the current project."""
    if await sync_forward_engineering_feature_backlog(db, _project_root(request)):
        await db.commit()
    result = await db.execute(select(Feature).where(Feature.item_type == BacklogItemType.FEATURE))
    features = result.scalars().all()

    return [_feature_payload(feature) for feature in features]


@router.get("/projects/{project_id}/features")
async def list_project_features(
    project_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """List features for one project using the canonical project-scoped route."""
    if await sync_forward_engineering_feature_backlog(db, _project_root(request)):
        await db.commit()
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .where(Feature.item_type == BacklogItemType.FEATURE)
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
    )
    return [_feature_payload(feature) for feature in result.scalars().all()]


@router.get("/features/{feature_id}")
async def get_feature(feature_id: str, db: AsyncSession = Depends(get_db)):
    """Return one feature by ID."""
    feature = await db.get(Feature, feature_id)
    if not feature or feature.item_type != BacklogItemType.FEATURE:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _feature_payload(feature)


@router.post("/features")
async def create_feature(
    title: str,
    description: str = "",
    priority: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Create a new feature."""
    feature = Feature(project_id="default", title=title, description=description, priority=priority)
    db.add(feature)
    await db.flush()
    return {
        "id": feature.id,
        "title": feature.title,
        "status": feature.status.value,
    }


@router.post("/projects/{project_id}/features", status_code=201)
async def create_project_feature(
    project_id: str,
    data: FeatureCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a feature for one project using the canonical project-scoped route."""
    item = await _create_backlog_item(
        project_id,
        BacklogItemCreate(
            title=data.title,
            description=data.description,
            priority=data.priority,
            item_type="feature",
            tags=data.tags,
            severity=data.severity,
            source=data.source,
            evidence=data.evidence,
        ),
        db,
        _project_root(request),
    )
    return _feature_payload(item)


@router.post("/projects/{project_id}/backlog/items", status_code=201)
async def create_backlog_item(
    project_id: str,
    data: BacklogItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    item = await _create_backlog_item(project_id, data, db, _project_root(request))
    return _feature_payload(item)


@router.get("/projects/{project_id}/backlog/items")
async def list_backlog_items(
    project_id: str,
    request: Request,
    item_type: str | None = Query(None, alias="type"),
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if await sync_forward_engineering_feature_backlog(db, _project_root(request)):
        await db.commit()
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


@router.get("/backlog/items/{item_id}")
async def get_backlog_item(item_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(Feature, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    return _feature_payload(item)


@router.put("/backlog/items/{item_id}")
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


@router.post("/backlog/items/{item_id}/cancel")
async def cancel_backlog_item(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Move a backlog item to the terminal cancelled state.

    Cancelling is the operator-facing way to retire a backlog item. It is only
    valid from a non-terminal state; an item that is already done or cancelled
    cannot be cancelled again.
    """
    item = await db.get(Feature, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Backlog item not found")
    if item.status in TERMINAL_FEATURE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "backlog_item_terminal",
                "message": (
                    f"cannot cancel backlog item in terminal state "
                    f"'{item.status.value if hasattr(item.status, 'value') else item.status}'"
                ),
            },
        )
    item.status = FeatureStatus.CANCELLED
    await db.flush()
    await db.refresh(item)
    mirror_item_to_artifact(_project_root(request), _feature_payload(item))
    await db.commit()
    return _feature_payload(item)


@router.get("/features/{feature_id}/tasks")
async def list_feature_tasks(feature_id: str, db: AsyncSession = Depends(get_db)):
    """List tasks belonging to one feature."""
    from sqlalchemy import select

    from autonomous_agent_builder.db.models import Task

    result = await db.execute(
        select(Task).where(Task.feature_id == feature_id).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "feature_id": t.feature_id,
            "title": t.title,
            "description": t.description,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "complexity": t.complexity,
            "retry_count": t.retry_count,
            "blocked_reason": t.blocked_reason,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]
