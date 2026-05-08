"""Helpers for canonical-branch freshness checks on maintained KB documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

CANONICAL_DOC_REF = "main"
_BASELINE_ENFORCEMENT_CUTOFF = datetime(2026, 4, 23, 0, 0, 0)


@dataclass(frozen=True)
class MaintainedDocFreshnessReport:
    doc_id: str
    doc_type: str
    lifecycle_status: str
    canonical_ref: str
    documented_against_commit: str
    documented_against_ref: str
    current_main_commit: str
    owned_paths: list[str]
    matched_changed_paths: list[str]
    status: str
    stale_reason: str
    blocking: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "lifecycle_status": self.lifecycle_status,
            "canonical_ref": self.canonical_ref,
            "documented_against_commit": self.documented_against_commit,
            "documented_against_ref": self.documented_against_ref,
            "current_main_commit": self.current_main_commit,
            "owned_paths": self.owned_paths,
            "matched_changed_paths": self.matched_changed_paths,
            "status": self.status,
            "stale_reason": self.stale_reason,
            "blocking": self.blocking,
        }


def git_head_for_ref(workspace_path: Path, ref: str = CANONICAL_DOC_REF) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "rev-parse", ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def resolve_canonical_doc_ref(workspace_path: Path) -> str:
    """Resolve the canonical freshness branch for a repo.

    Prefer `main` for repos that have it. Otherwise fall back to the remote
    default branch, then the current local branch, and finally `main` as a
    deterministic last resort.
    """
    if git_head_for_ref(workspace_path, CANONICAL_DOC_REF):
        return CANONICAL_DOC_REF

    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        remote_head = result.stdout.strip()
    except Exception:
        remote_head = ""
    if remote_head.startswith("origin/") and len(remote_head) > len("origin/"):
        return remote_head.split("/", 1)[1]

    current_branch = git_current_branch(workspace_path) or ""
    if current_branch and current_branch != "HEAD":
        return current_branch

    if git_head_for_ref(workspace_path, "master"):
        return "master"

    return CANONICAL_DOC_REF


def git_current_branch(workspace_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def commit_is_reachable_from_ref(workspace_path: Path, commit: str, ref: str = CANONICAL_DOC_REF) -> bool:
    if not commit.strip():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "merge-base", "--is-ancestor", commit, ref],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    return result.returncode == 0


def changed_paths_since(workspace_path: Path, commit: str, ref: str = CANONICAL_DOC_REF) -> list[str]:
    if not commit.strip():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "diff", "--name-only", f"{commit}..{ref}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def normalize_owned_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip().replace("\\", "/").strip("/")
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def matched_changed_paths(owned_paths: list[str], changed_paths: list[str]) -> list[str]:
    matches: list[str] = []
    for changed_path in changed_paths:
        for owned_path in owned_paths:
            if changed_path == owned_path or changed_path.startswith(f"{owned_path}/"):
                matches.append(changed_path)
                break
    return sorted(set(matches))


def baseline_required_for_doc(metadata: dict[str, Any], *, created: str | None = None, updated: str | None = None) -> bool:
    latest = updated or created or str(metadata.get("updated", "") or "") or str(metadata.get("created", "") or "")
    parsed = _parse_iso_timestamp(latest)
    if parsed is None:
        return False
    return parsed >= _BASELINE_ENFORCEMENT_CUTOFF


def maintained_doc_report(
    *,
    workspace_path: Path,
    doc_id: str,
    doc_type: str,
    lifecycle_status: str,
    metadata: dict[str, Any],
    created: str | None = None,
    updated: str | None = None,
    canonical_ref: str | None = None,
) -> MaintainedDocFreshnessReport:
    resolved_ref = canonical_ref or resolve_canonical_doc_ref(workspace_path)
    documented_against_commit = str(metadata.get("documented_against_commit", "") or "").strip()
    documented_against_ref = str(metadata.get("documented_against_ref", "") or "").strip()
    owned_paths = normalize_owned_paths(metadata.get("owned_paths"))
    current_main_commit = git_head_for_ref(workspace_path, resolved_ref) or ""
    required = baseline_required_for_doc(metadata, created=created, updated=updated)

    if not documented_against_commit:
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit="",
            documented_against_ref=documented_against_ref,
            current_main_commit=current_main_commit,
            owned_paths=owned_paths,
            matched_changed_paths=[],
            status="migration_needed",
            stale_reason="missing documented_against_commit",
            blocking=required,
        )

    if documented_against_ref != resolved_ref:
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            current_main_commit=current_main_commit,
            owned_paths=owned_paths,
            matched_changed_paths=[],
            status="stale",
            stale_reason=f"documented_against_ref must be {resolved_ref}",
            blocking=True,
        )

    if not owned_paths:
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            current_main_commit=current_main_commit,
            owned_paths=[],
            matched_changed_paths=[],
            status="migration_needed",
            stale_reason="missing owned_paths",
            blocking=required,
        )

    if not current_main_commit:
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            current_main_commit="",
            owned_paths=owned_paths,
            matched_changed_paths=[],
            status="blocked",
            stale_reason=f"unable to resolve {resolved_ref} head",
            blocking=True,
        )

    if not commit_is_reachable_from_ref(workspace_path, documented_against_commit, resolved_ref):
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            current_main_commit=current_main_commit,
            owned_paths=owned_paths,
            matched_changed_paths=[],
            status="stale",
            stale_reason=f"documented_against_commit is not reachable from {resolved_ref}",
            blocking=True,
        )

    changed_paths = changed_paths_since(workspace_path, documented_against_commit, resolved_ref)
    matched_paths = matched_changed_paths(owned_paths, changed_paths)
    if matched_paths:
        return MaintainedDocFreshnessReport(
            doc_id=doc_id,
            doc_type=doc_type,
            lifecycle_status=lifecycle_status,
            canonical_ref=resolved_ref,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            current_main_commit=current_main_commit,
            owned_paths=owned_paths,
            matched_changed_paths=matched_paths,
            status="stale",
            stale_reason=f"owned_paths changed on {resolved_ref} since documented baseline",
            blocking=True,
        )

    return MaintainedDocFreshnessReport(
        doc_id=doc_id,
        doc_type=doc_type,
        lifecycle_status=lifecycle_status,
        canonical_ref=resolved_ref,
        documented_against_commit=documented_against_commit,
        documented_against_ref=documented_against_ref,
        current_main_commit=current_main_commit,
        owned_paths=owned_paths,
        matched_changed_paths=[],
        status="current",
        stale_reason="",
        blocking=False,
    )


def _parse_iso_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
