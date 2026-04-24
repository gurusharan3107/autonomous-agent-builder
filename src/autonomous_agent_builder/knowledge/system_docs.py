"""Helpers for repo-local system-doc requirements and freshness checks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomous_agent_builder.knowledge.publisher import local_kb_root, parse_markdown_document

ACTIVE_DOC_LIFECYCLE = "active"
SUPERSEDED_DOC_LIFECYCLE = "superseded"
QUARANTINED_DOC_LIFECYCLE = "quarantined"
SYSTEM_DOC_LIFECYCLES = {
    ACTIVE_DOC_LIFECYCLE,
    SUPERSEDED_DOC_LIFECYCLE,
    QUARANTINED_DOC_LIFECYCLE,
}


@dataclass(frozen=True)
class SystemDocRequirementResult:
    passed: bool
    issues: list[str]
    required_docs: list[str]
    testing_doc_id: str | None = None
    missing_docs: list[str] | None = None
    stale_docs: list[str] | None = None
    mismatched_docs: list[str] | None = None
    superseded_docs: list[str] | None = None
    quarantined_docs: list[str] | None = None
    replacement_docs: dict[str, str] | None = None


def _required_doc_ids(depends_on: dict[str, Any] | None) -> list[str]:
    if not isinstance(depends_on, dict):
        return []
    payload = depends_on.get("system_docs")
    if not isinstance(payload, dict):
        return []
    required = payload.get("required_docs")
    if not isinstance(required, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in required:
        value = str(item).strip().replace("\\", "/")
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _doc_lifecycle_status(metadata: dict[str, Any]) -> str:
    value = str(metadata.get("lifecycle_status", "") or "").strip().lower()
    if value in SYSTEM_DOC_LIFECYCLES:
        return value
    return ACTIVE_DOC_LIFECYCLE


def _doc_replacement(metadata: dict[str, Any]) -> str:
    return str(metadata.get("superseded_by", "") or "").strip().replace("\\", "/")


def _load_doc_metadata(doc_id: str, root: Path) -> dict[str, Any] | None:
    path = root / doc_id
    if not path.exists():
        return None
    parsed = parse_markdown_document(path.read_text(encoding="utf-8"))
    return parsed.extra_fields


def _resolve_superseded_doc(doc_id: str, root: Path) -> str:
    current = doc_id
    visited = {doc_id}
    for _ in range(8):
        metadata = _load_doc_metadata(current, root)
        if metadata is None:
            return doc_id
        if _doc_lifecycle_status(metadata) != SUPERSEDED_DOC_LIFECYCLE:
            return current
        replacement = _doc_replacement(metadata)
        if not replacement or replacement in visited:
            return doc_id
        replacement_metadata = _load_doc_metadata(replacement, root)
        if replacement_metadata is None:
            return doc_id
        current = replacement
        visited.add(current)
    return doc_id


def reconcile_task_system_docs(
    depends_on: dict[str, Any] | None,
    *,
    kb_root: Path | None = None,
) -> dict[str, Any] | None:
    """Canonicalize required_docs and rewrite clean superseded chains to active docs."""
    if not isinstance(depends_on, dict):
        return depends_on

    payload = depends_on.get("system_docs")
    if not isinstance(payload, dict):
        return depends_on

    required_docs = _required_doc_ids(depends_on)
    if not required_docs:
        normalized = deepcopy(depends_on)
        normalized["system_docs"] = {**payload, "required_docs": []}
        return normalized

    root = (kb_root or local_kb_root()).resolve()
    reconciled: list[str] = []
    seen: set[str] = set()
    for doc_id in required_docs:
        resolved = _resolve_superseded_doc(doc_id, root)
        if resolved in seen:
            continue
        seen.add(resolved)
        reconciled.append(resolved)

    normalized = deepcopy(depends_on)
    normalized["system_docs"] = {**payload, "required_docs": reconciled}
    return normalized


def validate_task_system_docs(
    depends_on: dict[str, Any] | None,
    *,
    kb_root: Path | None = None,
    task_id: str | None = None,
    feature_id: str | None = None,
) -> SystemDocRequirementResult:
    required_docs = _required_doc_ids(depends_on)
    if not required_docs:
        return SystemDocRequirementResult(
            passed=True,
            issues=[],
            required_docs=[],
            missing_docs=[],
            stale_docs=[],
            mismatched_docs=[],
            superseded_docs=[],
            quarantined_docs=[],
            replacement_docs={},
        )

    root = (kb_root or local_kb_root()).resolve()
    issues: list[str] = []
    testing_doc_id: str | None = None
    missing_docs: list[str] = []
    stale_docs: list[str] = []
    mismatched_docs: list[str] = []
    superseded_docs: list[str] = []
    quarantined_docs: list[str] = []
    replacement_docs: dict[str, str] = {}

    for doc_id in required_docs:
        path = root / doc_id
        if not path.exists():
            issues.append(f"missing required system doc: {doc_id}")
            missing_docs.append(doc_id)
            continue

        parsed = parse_markdown_document(path.read_text(encoding="utf-8"))
        metadata = parsed.extra_fields
        doc_type = parsed.doc_type
        family = str(metadata.get("doc_family", "") or "")
        lifecycle_status = _doc_lifecycle_status(metadata)

        if lifecycle_status == QUARANTINED_DOC_LIFECYCLE:
            issues.append(f"required system doc is quarantined: {doc_id}")
            quarantined_docs.append(doc_id)
            continue
        if lifecycle_status == SUPERSEDED_DOC_LIFECYCLE:
            replacement = _doc_replacement(metadata)
            if replacement:
                replacement_docs[doc_id] = replacement
                issues.append(f"required system doc is superseded: {doc_id} -> {replacement}")
            else:
                issues.append(f"required system doc is superseded without replacement: {doc_id}")
            superseded_docs.append(doc_id)
            continue

        if doc_type == "testing" or family == "testing":
            testing_doc_id = doc_id
            if not metadata.get("last_verified_at"):
                issues.append(f"testing doc missing last_verified_at: {doc_id}")
                stale_docs.append(doc_id)

        if metadata.get("refresh_required") is True and not parsed.updated:
            issues.append(f"system doc marked refresh_required but missing updated timestamp: {doc_id}")
            stale_docs.append(doc_id)
        recorded_task_id = str(metadata.get("task_id", "") or "").strip()
        linked_feature = str(metadata.get("linked_feature", "") or "").strip()
        recorded_feature_id = str(metadata.get("feature_id", "") or "").strip()
        if task_id and recorded_task_id not in {"", task_id}:
            issues.append(f"system doc linked to a different task: {doc_id}")
            mismatched_docs.append(doc_id)
        if feature_id:
            if any(
                value not in {"", feature_id}
                for value in (linked_feature, recorded_feature_id)
            ):
                issues.append(f"system doc linked to a different feature: {doc_id}")
                mismatched_docs.append(doc_id)
            if not any(value == feature_id for value in (linked_feature, recorded_feature_id)) and recorded_task_id not in {
                "",
                task_id or "",
            }:
                issues.append(f"system doc is not linked to the active task or feature: {doc_id}")
                mismatched_docs.append(doc_id)

    return SystemDocRequirementResult(
        passed=not issues,
        issues=issues,
        required_docs=required_docs,
        testing_doc_id=testing_doc_id,
        missing_docs=sorted(set(missing_docs)),
        stale_docs=sorted(set(stale_docs)),
        mismatched_docs=sorted(set(mismatched_docs)),
        superseded_docs=sorted(set(superseded_docs)),
        quarantined_docs=sorted(set(quarantined_docs)),
        replacement_docs=replacement_docs,
    )


def format_task_system_doc_guidance(result: SystemDocRequirementResult) -> str:
    """Return prompt-friendly guidance for task-scoped KB obligations."""
    if not result.required_docs:
        return (
            "No task-scoped repo-local knowledge docs are currently required. "
            "If this task introduces durable feature behavior or verification flow, "
            "identify the required KB docs under depends_on.system_docs.required_docs "
            "and keep any maintained docs in .agent-builder/knowledge/ via builder_kb_add "
            "or builder_kb_update only."
        )

    lines = ["Task-scoped repo-local knowledge requirements:"]
    for doc_id in result.required_docs:
        if doc_id in (result.missing_docs or []):
            status = "missing"
        elif doc_id in (result.quarantined_docs or []):
            status = "quarantined"
        elif doc_id in (result.superseded_docs or []):
            replacement = (result.replacement_docs or {}).get(doc_id, "")
            status = f"superseded by {replacement}" if replacement else "superseded"
        elif doc_id in (result.stale_docs or []):
            status = "stale"
        elif doc_id in (result.mismatched_docs or []):
            status = "linked to the wrong task or feature"
        else:
            status = "present"
        lines.append(f"- {doc_id}: {status}")

    lines.extend(
        [
            "Use builder_kb_search and builder_kb_show for retrieval.",
            "Use builder_kb_add or builder_kb_update for any durable repo-local KB mutation.",
            "Do not edit .agent-builder/knowledge/ files directly.",
        ]
    )
    return "\n".join(lines)
