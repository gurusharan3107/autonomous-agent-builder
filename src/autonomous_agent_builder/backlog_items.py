"""Shared typed backlog item helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import (
    BacklogItemSeverity,
    BacklogItemSource,
    BacklogItemType,
    Feature,
    FeatureStatus,
)

ITEM_TYPES = {item.value for item in BacklogItemType}
SEVERITIES = {item.value for item in BacklogItemSeverity}
SOURCES = {item.value for item in BacklogItemSource}
FEATURE_STATUSES = {item.value for item in FeatureStatus}

ARTIFACTS: dict[str, tuple[str, str]] = {
    "feature": ("feature-list.json", "features"),
    "improvement": ("improvement-list.json", "improvements"),
    "optimization": ("optimization-list.json", "optimizations"),
    "incident": ("incident-list.json", "incidents"),
}


def normalize_item_type(value: str | None) -> str:
    item_type = (value or "feature").strip().lower().replace("_", "-")
    if item_type not in ITEM_TYPES:
        raise ValueError(f"unsupported backlog item type: {value}")
    return item_type


def normalize_source(value: str | None) -> str:
    source = (value or "manual").strip().lower()
    if source not in SOURCES:
        raise ValueError(f"unsupported backlog item source: {value}")
    return source


def normalize_severity(value: str | None, *, item_type: str) -> str | None:
    severity = (value or "").strip().lower()
    if item_type == "incident" and not severity:
        raise ValueError("incident severity is required")
    if not severity:
        return None
    if severity not in SEVERITIES:
        raise ValueError(f"unsupported incident severity: {value}")
    return severity


def parse_tags(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    raw_tags = value.split(",") if isinstance(value, str) else value
    seen: set[str] = set()
    tags: list[str] = []
    for raw in raw_tags:
        tag = str(raw).strip().lower()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def require_primary_tag(tags: list[str]) -> list[str]:
    if len(tags) > 1:
        raise ValueError("backlog items accept at most one primary tag")
    return tags


def normalize_feature_status(value: str | None) -> FeatureStatus:
    status = (value or FeatureStatus.BACKLOG.value).strip().lower()
    if status == "pending":
        status = FeatureStatus.BACKLOG.value
    if status not in FEATURE_STATUSES:
        raise ValueError(f"unsupported feature status: {value}")
    return FeatureStatus(status)


def backlog_item_reaches_board(value: str | None) -> bool:
    try:
        status = normalize_feature_status(value)
    except ValueError:
        return False
    return status not in {FeatureStatus.BACKLOG, FeatureStatus.SPRINT_BACKLOG}


def feature_to_item_payload(feature: Feature) -> dict[str, Any]:
    item_type = (
        feature.item_type.value
        if hasattr(feature.item_type, "value")
        else str(feature.item_type or "feature")
    )
    severity = feature.severity.value if hasattr(feature.severity, "value") else feature.severity
    source = (
        feature.source.value
        if hasattr(feature.source, "value")
        else str(feature.source or "manual")
    )
    status = feature.status.value if hasattr(feature.status, "value") else str(feature.status)
    return {
        "id": feature.id,
        "project_id": feature.project_id,
        "title": feature.title,
        "description": feature.description or "",
        "status": status,
        "priority": feature.priority,
        "item_type": item_type or "feature",
        "type": item_type or "feature",
        "tags": list(feature.tags or []),
        "severity": severity or "",
        "source": source or "manual",
        "evidence": feature.evidence or "",
        "acceptance_criteria": list(feature.acceptance_criteria or []),
        "dependencies": list(feature.dependencies or []),
        "created_at": feature.created_at.isoformat() if feature.created_at else None,
    }


def artifact_path(project_root: Path, item_type: str) -> tuple[Path, str]:
    filename, key = ARTIFACTS[normalize_item_type(item_type)]
    return project_root / ".claude" / "progress" / filename, key


def read_item_artifact(project_root: Path, item_type: str) -> dict[str, Any]:
    path, key = artifact_path(project_root, item_type)
    if not path.exists():
        return {key: [], "metadata": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {key: [], "metadata": {}}
    if key not in payload or not isinstance(payload.get(key), list):
        payload[key] = []
    payload.setdefault("metadata", {})
    return payload


def read_all_item_artifacts(project_root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item_type, (_filename, key) in ARTIFACTS.items():
        payload = read_item_artifact(project_root, item_type)
        for raw in payload.get(key, []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item.setdefault("item_type", item_type)
            item.setdefault("type", item_type)
            item.setdefault("tags", [])
            item.setdefault("source", "manual")
            item.setdefault("severity", "")
            item.setdefault("evidence", "")
            items.append(item)
    return items


def mirror_item_to_artifact(project_root: Path, item: dict[str, Any]) -> None:
    item_type = normalize_item_type(str(item.get("item_type") or item.get("type") or "feature"))
    path, key = artifact_path(project_root, item_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = read_item_artifact(project_root, item_type)
    items = [
        entry
        for entry in payload.get(key, [])
        if isinstance(entry, dict) and entry.get("id") != item.get("id")
    ]
    artifact_item = {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "priority": item.get("priority", 0),
        "status": item.get("status", "backlog"),
        "item_type": item_type,
        "type": item_type,
        "tags": item.get("tags", []),
        "severity": item.get("severity", ""),
        "source": item.get("source", "manual"),
        "evidence": item.get("evidence", ""),
        "acceptance_criteria": item.get("acceptance_criteria", []),
        "dependencies": item.get("dependencies", []),
    }
    items.append(artifact_item)
    payload[key] = items
    payload["metadata"] = {
        **dict(payload.get("metadata", {})),
        "total": len(items),
        "pending": sum(1 for entry in items if entry.get("status") != "done"),
        "done": sum(1 for entry in items if entry.get("status") == "done"),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
