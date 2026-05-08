"""Filesystem-backed knowledge base API for local and global knowledge roots."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from autonomous_agent_builder.knowledge.document_spec import STANDARD_DOC_TYPES
from autonomous_agent_builder.knowledge.publisher import (
    global_kb_root,
    knowledge_root,
    local_kb_root,
    parse_markdown_document,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

def _global_routing_articles() -> list[dict[str, Any]]:
    routing_path = global_kb_root() / "routing.json"
    if not routing_path.exists():
        return []

    try:
        data = json.loads(routing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    articles = data.get("articles", [])
    return articles if isinstance(articles, list) else []


def _doc_type_for_path(path: Path, scope: str) -> str:
    if scope == "global":
        return "raw"

    root = local_kb_root()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "context"

    parts = relative.parts
    return parts[0] if len(parts) > 1 else "context"


def _clean_excerpt(body: str) -> str:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _tags_from_doc(path: Path, doc_type: str, body: str, metadata: dict[str, Any]) -> list[str]:
    if "tags" in metadata and isinstance(metadata["tags"], list):
        return metadata["tags"]

    tags = {doc_type}
    if doc_type == "raw":
        tags.add("global")
    else:
        tags.add("local")

    lower_body = body.lower()
    for keyword in ("agents", "architecture", "testing", "workflow", "api", "knowledge"):
        if keyword in lower_body:
            tags.add(keyword)

    if path.parent != knowledge_root("global") and len(path.parts) > 1:
        tags.update(
            part
            for part in path.parts[-3:-1]
            if part not in {".agent-builder", "knowledge", "raw"}
        )

    return sorted(tags)


def _serialize_doc(path: Path, scope: str) -> dict[str, Any]:
    parsed = parse_markdown_document(
        path.read_text(encoding="utf-8"),
        default_doc_type=_doc_type_for_path(path, scope),
    )
    metadata = parsed.extra_fields
    body = parsed.body
    doc_type = _doc_type_for_path(path, scope)
    title = parsed.title
    tags = parsed.tags or _tags_from_doc(path, doc_type, body, metadata)
    created_at = (
        metadata.get("date_published")
        or metadata.get("date_processed")
        or parsed.created
        or ""
    )
    source_url = metadata.get("source_url") or metadata.get("source")

    return {
        "id": path.relative_to(knowledge_root(scope)).as_posix(),
        "task_id": metadata.get("task_id", ""),
        "doc_type": parsed.doc_type or doc_type,
        "doc_family": metadata.get("doc_family", ""),
        "title": title,
        "content": body.strip(),
        "version": parsed.version,
        "created_at": created_at,
        "wikilinks": sorted(set(WIKILINK_PATTERN.findall(body))),
        "tags": tags,
        "date_published": created_at,
        "source_author": metadata.get("source_author"),
        "source_title": metadata.get("source_title"),
        "source_url": source_url,
        "card_summary": metadata.get("card_summary"),
        "detail_summary": metadata.get("detail_summary"),
        "scope": scope,
        "path": str(path),
        "excerpt": _clean_excerpt(body),
    }


def _global_doc_paths() -> list[Path]:
    root = global_kb_root()
    raw_root = root / "raw"

    routed = []
    for article in _global_routing_articles():
        file_name = article.get("file")
        if not file_name:
            continue
        candidate = raw_root / file_name
        if candidate.exists():
            routed.append(candidate)

    if routed:
        return routed

    return sorted(raw_root.rglob("*.md")) if raw_root.exists() else []


def _is_canonical_local_doc_path(path: Path) -> bool:
    try:
        relative = path.relative_to(local_kb_root())
    except ValueError:
        return False

    if len(relative.parts) < 2:
        return False
    return relative.parts[0] in STANDARD_DOC_TYPES


def _list_doc_paths(scope: str) -> list[Path]:
    root = knowledge_root(scope)
    if not root.exists():
        return []

    if scope == "global":
        return _global_doc_paths()

    return sorted(path for path in root.rglob("*.md") if _is_canonical_local_doc_path(path))


def _load_docs(scope: str) -> list[dict[str, Any]]:
    docs = [_serialize_doc(path, scope) for path in _list_doc_paths(scope)]
    docs.sort(key=lambda doc: (doc.get("created_at") or "", doc["title"].lower()), reverse=True)
    return docs


def _find_doc(doc_id: str, scope: str) -> dict[str, Any]:
    for doc in _load_docs(scope):
        if doc["id"] == doc_id:
            return doc
    raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")


def _similar_docs(selected: dict[str, Any], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_tags = set(selected.get("tags", []))
    results = []

    for doc in docs:
        if doc["id"] == selected["id"]:
            continue

        shared_tags = sorted(selected_tags.intersection(doc.get("tags", [])))
        if not shared_tags:
            continue

        score = len(shared_tags) / max(len(selected_tags.union(doc.get("tags", []))), 1)
        results.append({**doc, "shared_tags": shared_tags, "similarity_score": score})

    results.sort(key=lambda doc: doc["similarity_score"], reverse=True)
    return results[:8]


def _parse_selected_tags(tags: str | None) -> set[str]:
    return {tag.strip() for tag in (tags or "").split(",") if tag.strip()}


@router.get("/")
async def list_documents(
    scope: str = Query("local", pattern="^(local|global)$"),
    doc_type: str | None = Query(None),
    tags: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """List knowledge documents from the selected filesystem root."""
    docs = _load_docs(scope)

    if doc_type:
        docs = [doc for doc in docs if doc["doc_type"] == doc_type]

    required = _parse_selected_tags(tags)
    if required:
        docs = [doc for doc in docs if required.issubset(set(doc.get("tags", [])))]

    return docs[:limit]


@router.get("/search")
async def search_documents(
    q: str = Query(..., min_length=1),
    scope: str = Query("local", pattern="^(local|global)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Search knowledge documents by title, tags, and content."""
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    results = []

    for doc in _load_docs(scope):
        haystacks = [doc["title"], doc.get("content", ""), " ".join(doc.get("tags", []))]
        if any(pattern.search(text) for text in haystacks):
            results.append(doc)

    return results[:limit]


@router.get("/tags")
async def list_tags(
    scope: str = Query("local", pattern="^(local|global)$"),
    tags: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Aggregate tags for the selected knowledge scope."""
    all_docs = _load_docs(scope)
    selected = _parse_selected_tags(tags)
    docs = all_docs
    if selected:
        docs = [doc for doc in all_docs if selected.issubset(set(doc.get("tags", [])))]

    counter = Counter(tag for doc in docs for tag in doc.get("tags", []))

    tag_docs = {
        tag: [doc for doc in docs if tag in doc.get("tags", [])]
        for tag in counter
    }

    if selected:
        available_tags = set(selected)
        for tag in counter:
            if tag in selected:
                continue

            candidate = selected | {tag}
            if any(candidate.issubset(set(doc.get("tags", []))) for doc in all_docs):
                available_tags.add(tag)
    else:
        available_tags = set(counter)

    payload = []
    for tag, count in counter.most_common():
        related_counts = Counter(
            other
            for doc in tag_docs[tag]
            for other in doc.get("tags", [])
            if other != tag
        )
        payload.append(
            {
                "name": tag,
                "count": count,
                "related": dict(related_counts.most_common(8)),
                "available": tag in available_tags,
            }
        )

    return payload


@router.get("/{doc_id:path}/related")
async def related_documents(
    doc_id: str,
    scope: str = Query("local", pattern="^(local|global)$"),
) -> dict[str, list[dict[str, Any]]]:
    """Return wikilinks, backlinks, and similar docs for a selected document."""
    docs = _load_docs(scope)
    selected = next((doc for doc in docs if doc["id"] == doc_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    target_titles = {selected["title"], Path(selected["id"]).stem.replace("-", " ")}
    wikilinks = [doc for doc in docs if doc["title"] in selected.get("wikilinks", [])]
    backlinks = [
        doc
        for doc in docs
        if doc["id"] != selected["id"]
        and (
            selected["title"] in doc.get("wikilinks", [])
            or any(target.lower() in doc.get("content", "").lower() for target in target_titles)
        )
    ]

    return {
        "wikilinks": wikilinks[:8],
        "backlinks": backlinks[:8],
        "similar": _similar_docs(selected, docs),
    }


@router.get("/{doc_id:path}")
async def get_document(
    doc_id: str,
    scope: str = Query("local", pattern="^(local|global)$"),
) -> dict[str, Any]:
    """Get a single document from the selected knowledge root."""
    return _find_doc(doc_id, scope)
