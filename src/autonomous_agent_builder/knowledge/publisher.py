"""Single-writer publisher for the project-local builder knowledge base."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from autonomous_agent_builder.knowledge.document_spec import (
    DocumentLinter,
    build_document_markdown,
)
from autonomous_agent_builder.knowledge.maintained_freshness import resolve_canonical_doc_ref

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#+)\s+(.+)$", re.MULTILINE)
_WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
_LEGACY_RAW_HEADING = "## Application to Control Plane"
_CANONICAL_RAW_HEADING = "## Applicability"
_WORKFLOW_GLOBAL_HINT = (
    "Global KB publication is owned by workflow CLI. "
    "Use `workflow knowledge ingest <file>` for ~/.codex/knowledge updates."
)
DEFAULT_LOCAL_KB_COLLECTION = "system-docs"
DEFAULT_DOC_LIFECYCLE = "active"
DOC_LIFECYCLE_VALUES = {"active", "superseded", "quarantined"}


class PublishError(Exception):
    """Raised when a KB publish/update request is invalid."""


@dataclass
class ParsedDocument:
    title: str
    tags: list[str]
    doc_type: str
    body: str
    created: str | None = None
    auto_generated: bool = True
    version: int = 1
    updated: str | None = None
    wikilinks: list[str] | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)


def _default_collection_for_doc_type(doc_type: str) -> str:
    if doc_type in {"system-docs", "feature", "testing", "metadata"}:
        return DEFAULT_LOCAL_KB_COLLECTION
    return doc_type


def _normalize_system_doc_metadata(
    doc_type: str,
    extra_fields: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if doc_type == "reverse-engineering":
        doc_type = "system-docs"
    normalized = dict(extra_fields)
    lifecycle_status = str(normalized.get("lifecycle_status", "") or "").strip().lower()
    if lifecycle_status not in DOC_LIFECYCLE_VALUES:
        lifecycle_status = DEFAULT_DOC_LIFECYCLE
    if doc_type == "system-docs":
        normalized.setdefault("doc_family", "seed")
        normalized.setdefault("refresh_required", False)
        normalized.setdefault("lifecycle_status", lifecycle_status)
    elif doc_type == "feature":
        normalized.setdefault("doc_family", "feature")
        normalized.setdefault("refresh_required", True)
        normalized.setdefault("lifecycle_status", lifecycle_status)
        normalized.setdefault("documented_against_ref", resolve_canonical_doc_ref(project_root()))
    elif doc_type == "testing":
        normalized.setdefault("doc_family", "testing")
        normalized.setdefault("refresh_required", True)
        normalized.setdefault("lifecycle_status", lifecycle_status)
        normalized.setdefault("documented_against_ref", resolve_canonical_doc_ref(project_root()))
    elif doc_type == "metadata":
        normalized.setdefault("doc_family", "metadata")
    if lifecycle_status == "superseded":
        replacement = str(normalized.get("superseded_by", "") or "").strip().replace("\\", "/")
        if replacement:
            normalized["superseded_by"] = replacement
    else:
        normalized.pop("superseded_by", None)
    return doc_type, normalized


def project_root() -> Path:
    return Path(os.environ.get("AAB_PROJECT_ROOT", Path.cwd())).resolve()


def local_kb_root() -> Path:
    return Path(
        os.environ.get("AAB_LOCAL_KB_ROOT", project_root() / ".agent-builder" / "knowledge")
    ).resolve()


def global_kb_root() -> Path:
    return Path(
        os.environ.get(
            "AAB_GLOBAL_KB_ROOT",
            Path.home() / ".codex" / "knowledge",
        )
    ).resolve()


def knowledge_root(scope: str) -> Path:
    normalized = scope.strip().lower()
    if normalized not in {"local", "global"}:
        raise PublishError(f"Unsupported scope '{scope}'. Expected 'local' or 'global'.")
    return global_kb_root() if normalized == "global" else local_kb_root()


def parse_markdown_document(markdown: str, *, default_doc_type: str = "context") -> ParsedDocument:
    """Parse markdown with optional frontmatter into a structured document."""
    content = markdown.strip()
    frontmatter: dict[str, Any] = {}
    body = content

    match = _FRONTMATTER_RE.match(content)
    if match:
        try:
            parsed = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise PublishError(f"Invalid YAML frontmatter: {exc}") from exc
        if not isinstance(parsed, dict):
            raise PublishError("Frontmatter must be a YAML object.")
        frontmatter = parsed
        body = content[match.end() :].strip()

    title = str(frontmatter.get("title") or _title_from_body(body) or "Untitled").strip()
    tags = frontmatter.get("tags")
    if not isinstance(tags, list):
        tags = []

    doc_type = str(frontmatter.get("doc_type") or default_doc_type).strip()
    created = _string_or_none(frontmatter.pop("created", None))
    auto_generated = bool(frontmatter.pop("auto_generated", True))
    version = int(frontmatter.pop("version", 1) or 1)
    updated = _string_or_none(frontmatter.pop("updated", None))
    wikilinks = frontmatter.pop("wikilinks", None)
    if wikilinks is not None and not isinstance(wikilinks, list):
        wikilinks = None

    frontmatter.pop("title", None)
    frontmatter.pop("tags", None)
    frontmatter.pop("doc_type", None)

    return ParsedDocument(
        title=title,
        tags=[str(tag) for tag in tags],
        doc_type=doc_type,
        body=body,
        created=created,
        auto_generated=auto_generated,
        version=version,
        updated=updated,
        wikilinks=wikilinks,
        extra_fields=frontmatter,
    )


def publish_document(
    *,
    title: str,
    body: str,
    doc_type: str,
    tags: list[str],
    wikilinks: list[str] | None = None,
    scope: str = "local",
    task_id: str = "",
    collection: str | None = None,
    file_name: str | None = None,
    source_url: str | None = None,
    source_title: str | None = None,
    source_author: str | None = None,
    date_published: str | None = None,
    auto_generated: bool = True,
    existing_doc_id: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish a KB document via the single canonical write path."""
    _ensure_local_publish_scope(scope)
    normalized_doc_type, normalized_extra_fields = _normalize_system_doc_metadata(
        doc_type.strip(),
        dict(extra_fields or {}),
    )
    document = ParsedDocument(
        title=title.strip(),
        tags=_normalized_document_tags(
            [str(tag) for tag in tags if str(tag).strip()],
            doc_type=normalized_doc_type,
            extra_fields=normalized_extra_fields,
        ),
        doc_type=normalized_doc_type,
        body=body,
        auto_generated=auto_generated,
        wikilinks=[str(link) for link in (wikilinks or []) if str(link).strip()] or None,
        extra_fields=normalized_extra_fields,
    )
    if task_id:
        document.extra_fields["task_id"] = task_id

    overrides = {
        "source_url": source_url,
        "source_title": source_title,
        "source_author": source_author,
        "date_published": date_published,
    }
    return _persist_document(
        document=document,
        scope=scope,
        collection=collection,
        file_name=file_name,
        existing_doc_id=existing_doc_id,
        overrides=overrides,
    )


def publish_markdown(
    markdown: str,
    *,
    scope: str = "local",
    collection: str | None = None,
    file_name: str | None = None,
    default_doc_type: str = "context",
    existing_doc_id: str | None = None,
    source_url: str | None = None,
    source_title: str | None = None,
    source_author: str | None = None,
    date_published: str | None = None,
) -> dict[str, Any]:
    """Publish a markdown document that may already include frontmatter."""
    _ensure_local_publish_scope(scope)
    document = parse_markdown_document(markdown, default_doc_type=default_doc_type)
    overrides = {
        "source_url": source_url,
        "source_title": source_title,
        "source_author": source_author,
        "date_published": date_published,
    }
    return _persist_document(
        document=document,
        scope=scope,
        collection=collection,
        file_name=file_name,
        existing_doc_id=existing_doc_id,
        overrides=overrides,
    )


def update_document(
    *,
    doc_id: str,
    scope: str = "local",
    title: str | None = None,
    body: str | None = None,
    source_url: str | None = None,
    source_title: str | None = None,
    source_author: str | None = None,
    date_published: str | None = None,
    extra_fields: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Update an existing KB document through the publisher."""
    _ensure_local_publish_scope(scope)
    path = _resolve_doc_path(doc_id, scope)
    existing = parse_markdown_document(
        path.read_text(encoding="utf-8"),
        default_doc_type=_doc_type_for_existing_path(path, scope),
    )
    if title:
        existing.title = title.strip()
    if body is not None:
        existing.body = body
    if extra_fields:
        existing.extra_fields.update(extra_fields)
    existing.doc_type, existing.extra_fields = _normalize_system_doc_metadata(
        existing.doc_type,
        existing.extra_fields,
    )
    if tags is not None:
        existing.tags = _normalized_document_tags(
            tags,
            doc_type=existing.doc_type,
            extra_fields=existing.extra_fields,
        )

    overrides = {
        "source_url": source_url,
        "source_title": source_title,
        "source_author": source_author,
        "date_published": date_published,
    }
    return _persist_document(
        document=existing,
        scope=scope,
        existing_doc_id=doc_id,
        overrides=overrides,
    )


def _persist_document(
    *,
    document: ParsedDocument,
    scope: str,
    collection: str | None = None,
    file_name: str | None = None,
    existing_doc_id: str | None = None,
    overrides: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    _ensure_local_publish_scope(scope)
    normalized_scope = scope.strip().lower()
    root = knowledge_root(normalized_scope)

    doc_type = document.doc_type.strip().lower()
    if not document.title:
        raise PublishError("Document title cannot be empty.")

    body = _normalize_body(document.title, document.body, doc_type)
    extra_fields = dict(document.extra_fields)
    doc_type, extra_fields = _normalize_system_doc_metadata(doc_type, extra_fields)
    provenance = _resolved_provenance(
        title=document.title,
        created=document.created,
        existing_fields=extra_fields,
        overrides=overrides or {},
        scope=normalized_scope,
        doc_type=doc_type,
    )
    extra_fields.update(provenance)

    if doc_type == "raw":
        _validate_global_body(body)

    relative_path = (
        Path(existing_doc_id)
        if existing_doc_id
        else _target_relative_path(
            title=document.title,
            doc_type=doc_type,
            scope=normalized_scope,
            collection=collection,
            file_name=file_name,
            created=document.created,
            date_published=extra_fields.get("date_published"),
        )
    )
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)

    previous_markdown = path.read_text(encoding="utf-8") if path.exists() else None
    previous = parse_markdown_document(previous_markdown) if previous_markdown else None

    version = document.version if previous is None else previous.version
    updated = document.updated if previous is None else previous.updated
    canonical_preview = build_document_markdown(
        title=document.title,
        tags=_effective_tags(document.tags, doc_type, normalized_scope),
        doc_type=doc_type,
        body=body,
        created=previous.created if previous and previous.created else document.created,
        auto_generated=document.auto_generated if previous is None else previous.auto_generated,
        version=version,
        updated=updated,
        wikilinks=document.wikilinks,
        extra_fields=extra_fields,
    )

    if previous_markdown is not None:
        if previous_markdown == canonical_preview:
            raise PublishError(f"Document '{relative_path}' is unchanged.")
        version = previous.version + 1
        updated = datetime.now().isoformat()

    created = previous.created if previous and previous.created else document.created
    canonical_markdown = build_document_markdown(
        title=document.title,
        tags=_effective_tags(document.tags, doc_type, normalized_scope),
        doc_type=doc_type,
        body=body,
        created=created,
        auto_generated=document.auto_generated if previous is None else previous.auto_generated,
        version=version,
        updated=updated,
        wikilinks=document.wikilinks,
        extra_fields=extra_fields,
    )

    _lint_document(canonical_markdown, str(relative_path))
    _check_duplicates(
        root=root,
        path=path,
        title=document.title,
        content=canonical_markdown,
        allow_existing=previous_markdown is not None,
    )
    path.write_text(canonical_markdown, encoding="utf-8")

    return _serialize_document(path, normalized_scope)


def _ensure_local_publish_scope(scope: str) -> None:
    normalized_scope = scope.strip().lower()
    if normalized_scope == "global":
        raise PublishError(_WORKFLOW_GLOBAL_HINT)


def _resolve_doc_path(doc_id: str, scope: str) -> Path:
    path = knowledge_root(scope) / doc_id
    if not path.exists():
        raise PublishError(f"Document '{doc_id}' not found in {scope} KB.")
    return path


def _doc_type_for_existing_path(path: Path, scope: str) -> str:
    if scope == "global":
        return "raw"

    try:
        relative = path.relative_to(knowledge_root(scope))
    except ValueError:
        return "context"

    if len(relative.parts) > 1:
        return relative.parts[0]
    return "context"


def _target_relative_path(
    *,
    title: str,
    doc_type: str,
    scope: str,
    collection: str | None,
    file_name: str | None,
    created: str | None,
    date_published: str | None,
) -> Path:
    directory = Path("raw") if scope == "global" else Path(collection or _default_collection_for_doc_type(doc_type))
    if file_name:
        return directory / file_name

    slug = _slugify(title)
    if scope == "global":
        prefix = (date_published or created or datetime.now().isoformat())[:10]
        filename = f"{prefix}-{slug}.md"
    else:
        filename = f"{slug}.md"
    return directory / filename


def _resolved_provenance(
    *,
    title: str,
    created: str | None,
    existing_fields: dict[str, Any],
    overrides: dict[str, str | None],
    scope: str,
    doc_type: str,
) -> dict[str, Any]:
    resolved = dict(existing_fields)
    for key, value in overrides.items():
        if value:
            resolved[key] = value

    if scope == "global" or doc_type == "raw":
        source_url = resolved.get("source_url") or resolved.get("source")
        source_title = resolved.get("source_title") or title
        source_author = resolved.get("source_author")
        date_published = resolved.get("date_published") or resolved.get("date") or created

        missing = [
            field
            for field, value in (
                ("source_url", source_url),
                ("source_title", source_title),
                ("source_author", source_author),
                ("date_published", date_published),
            )
            if not value
        ]
        if missing:
            needed = ", ".join(missing)
            raise PublishError(f"Missing required provenance for global/raw publication: {needed}")

        resolved["source_url"] = str(source_url)
        resolved["source_title"] = str(source_title)
        resolved["source_author"] = str(source_author)
        resolved["date_published"] = str(date_published)
        resolved.pop("source", None)
        resolved.pop("date", None)

    return resolved


def _normalize_body(title: str, body: str, doc_type: str) -> str:
    normalized = body.strip()
    if doc_type == "raw":
        normalized = normalized.replace(_LEGACY_RAW_HEADING, _CANONICAL_RAW_HEADING)

    heading_matches = list(_HEADING_RE.finditer(normalized))
    if heading_matches and heading_matches[0].group(1) == "#":
        first_heading = heading_matches[0]
        replacement = f"# {title}"
        normalized = replacement + normalized[first_heading.end() :]
    else:
        normalized = f"# {title}\n\n{normalized}" if normalized else f"# {title}"

    return normalized.strip() + "\n"


def _validate_global_body(body: str) -> None:
    required = {"insight", "evidence", "applicability"}
    headings = {
        match.group(2).strip().lower()
        for match in _HEADING_RE.finditer(body)
        if len(match.group(1)) == 2
    }
    missing = sorted(required - headings)
    if missing:
        raise PublishError(
            "Global raw articles must include sections: Insight, Evidence, Applicability."
        )


def _effective_tags(tags: list[str], doc_type: str, scope: str) -> list[str]:
    if tags:
        return [str(tag) for tag in tags]
    defaults = [doc_type]
    defaults.append("global" if scope == "global" else "local")
    return defaults


def _normalized_document_tags(
    tags: list[str] | None,
    *,
    doc_type: str,
    extra_fields: dict[str, Any] | None = None,
) -> list[str]:
    items: list[str] = [doc_type]
    family = str((extra_fields or {}).get("doc_family", "") or "").strip()
    if family:
        items.append(family)
    items.extend(str(tag).strip() for tag in (tags or []))

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _lint_document(content: str, source: str) -> None:
    linter = DocumentLinter(strict=True)
    if not linter.lint_content(content, source):
        raise PublishError(linter.get_report())


def _check_duplicates(
    *,
    root: Path,
    path: Path,
    title: str,
    content: str,
    allow_existing: bool,
) -> None:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    for existing in sorted(root.rglob("*.md")):
        if existing == path:
            continue
        existing_content = existing.read_text(encoding="utf-8")
        existing_doc = parse_markdown_document(existing_content)
        existing_hash = hashlib.sha256(existing_content.encode("utf-8")).hexdigest()
        if existing_doc.title == title and existing_hash == content_hash:
            raise PublishError(f"Duplicate KB document detected at '{existing.relative_to(root)}'.")
    if path.exists() and not allow_existing:
        raise PublishError(
            f"Document '{path.relative_to(root)}' already exists. Use 'builder knowledge update' instead."
        )


def _serialize_document(path: Path, scope: str) -> dict[str, Any]:
    markdown = path.read_text(encoding="utf-8")
    document = parse_markdown_document(markdown)
    root = knowledge_root(scope)
    tags = _effective_tags(document.tags, document.doc_type, scope)
    body = document.body.strip()
    created_value = document.extra_fields.get("date_published") or document.created or ""
    return {
        "id": path.relative_to(root).as_posix(),
        "task_id": document.extra_fields.get("task_id", ""),
        "doc_type": document.doc_type,
        "doc_family": document.extra_fields.get("doc_family", ""),
        "lifecycle_status": document.extra_fields.get("lifecycle_status", ""),
        "superseded_by": document.extra_fields.get("superseded_by", ""),
        "linked_feature": document.extra_fields.get("linked_feature", ""),
        "feature_id": document.extra_fields.get("feature_id", ""),
        "refresh_required": bool(document.extra_fields.get("refresh_required", False)),
        "documented_against_commit": document.extra_fields.get("documented_against_commit", ""),
        "documented_against_ref": document.extra_fields.get("documented_against_ref", ""),
        "owned_paths": document.extra_fields.get("owned_paths", []),
        "last_verified_at": document.extra_fields.get("last_verified_at", ""),
        "verified_with": document.extra_fields.get("verified_with", ""),
        "title": document.title,
        "content": body,
        "version": document.version,
        "created_at": created_value,
        "updated": document.updated or "",
        "wikilinks": sorted(set(_WIKILINK_PATTERN.findall(body))),
        "tags": tags,
        "date_published": document.extra_fields.get("date_published"),
        "source_author": document.extra_fields.get("source_author"),
        "source_title": document.extra_fields.get("source_title"),
        "source_url": document.extra_fields.get("source_url"),
        "scope": scope,
        "path": str(path),
        "excerpt": _excerpt(body),
    }


def _title_from_body(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _excerpt(body: str) -> str:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _slugify(text: str) -> str:
    slug = text.lower().replace(" ", "-").replace("/", "-")
    slug = "".join(char for char in slug if char.isalnum() or char in "-_")
    slug = re.sub(r"-{2,}", "-", slug).strip("-_")
    return slug or "document"
