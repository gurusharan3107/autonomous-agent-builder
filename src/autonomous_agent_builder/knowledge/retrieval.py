"""Filesystem-backed KB retrieval helpers shared by local CLI-style reads."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from autonomous_agent_builder.knowledge.publisher import (
    global_kb_root,
    knowledge_root,
    local_kb_root,
    parse_markdown_document,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


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
        return [str(tag) for tag in metadata["tags"]]

    tags = {doc_type}
    tags.add("global" if doc_type == "raw" else "local")

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
    doc_type = parsed.doc_type or _doc_type_for_path(path, scope)
    title = parsed.title
    tags = parsed.tags or _tags_from_doc(path, doc_type, body, metadata)
    created_at = (
        parsed.created
        or metadata.get("date_processed")
        or metadata.get("date_published")
        or metadata.get("updated")
        or ""
    )
    preview = _clean_excerpt(body)
    relative = path.relative_to(knowledge_root(scope)).as_posix()
    return {
        "id": relative,
        "task_id": str(metadata.get("task_id", "")),
        "doc_type": doc_type,
        "doc_family": str(metadata.get("doc_family", "") or ""),
        "lifecycle_status": str(metadata.get("lifecycle_status", "") or ""),
        "superseded_by": str(metadata.get("superseded_by", "") or ""),
        "linked_feature": str(metadata.get("linked_feature", "") or ""),
        "feature_id": str(metadata.get("feature_id", "") or ""),
        "refresh_required": bool(metadata.get("refresh_required", False)),
        "documented_against_commit": str(metadata.get("documented_against_commit", "") or ""),
        "documented_against_ref": str(metadata.get("documented_against_ref", "") or ""),
        "owned_paths": metadata.get("owned_paths") if isinstance(metadata.get("owned_paths"), list) else [],
        "last_verified_at": str(metadata.get("last_verified_at", "") or ""),
        "verified_with": str(metadata.get("verified_with", "") or ""),
        "title": title,
        "content": body,
        "version": parsed.version,
        "created_at": created_at,
        "updated": parsed.updated or "",
        "wikilinks": list(parsed.wikilinks or []),
        "tags": tags,
        "date_published": metadata.get("date_published"),
        "source_author": metadata.get("source_author"),
        "source_title": metadata.get("source_title"),
        "source_url": metadata.get("source_url"),
        "card_summary": metadata.get("card_summary") or preview,
        "detail_summary": metadata.get("detail_summary") or preview,
        "preview": preview,
    }


def load_docs(scope: str = "local") -> list[dict[str, Any]]:
    root = knowledge_root(scope)
    if not root.exists():
        return []

    docs: list[dict[str, Any]] = []

    if scope == "global":
        articles = {
            str(item.get("file", "")): item
            for item in _global_routing_articles()
            if str(item.get("file", "")).strip()
        }
        for path in root.rglob("*.md"):
            if path.name == "routing.json":
                continue
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            doc = _serialize_doc(path, scope)
            article = articles.get(path.name)
            if article:
                doc["title"] = str(article.get("title") or doc["title"])
                doc["tags"] = [str(tag) for tag in article.get("tags", [])] or doc["tags"]
                doc["date_published"] = article.get("date_processed") or doc["date_published"]
            docs.append(doc)
        docs.sort(key=lambda doc: (str(doc.get("date_published") or ""), doc["title"].lower()), reverse=True)
        return docs

    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if len(relative.parts) > 1 and relative.parts[0] not in {
            "context",
            "adr",
            "api_contract",
            "schema",
            "runbook",
            "system-docs",
            "feature",
            "testing",
            "metadata",
            "raw",
        }:
            continue
        docs.append(_serialize_doc(path, scope))

    docs.sort(key=lambda doc: (str(doc.get("created_at") or ""), doc["title"].lower()), reverse=True)
    return docs


def find_doc(doc_id: str, *, scope: str = "local") -> dict[str, Any] | None:
    for doc in load_docs(scope):
        if doc["id"] == doc_id:
            return doc
    return None


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _score_doc(doc: dict[str, Any], query: str) -> int:
    normalized_query = _normalize_text(query)
    query_tokens = list(dict.fromkeys(_tokenize(query)))
    if not normalized_query and not query_tokens:
        return 0

    title = _normalize_text(str(doc.get("title", "")))
    tags = _normalize_text(" ".join(str(tag) for tag in doc.get("tags", [])))
    content = _normalize_text(
        " ".join(
            part
            for part in (
                str(doc.get("card_summary", "")),
                str(doc.get("detail_summary", "")),
                str(doc.get("preview", "")),
                str(doc.get("content", "")),
            )
            if part
        )
    )

    score = 0
    if normalized_query:
        if normalized_query in title:
            score += 120
        if normalized_query in tags:
            score += 80
        if normalized_query in content:
            score += 50

    coverage = 0
    for token in query_tokens:
        matched = False
        if token in title:
            score += 24
            matched = True
        if token in tags:
            score += 14
            matched = True
        if token in content:
            score += 8
            matched = True
        coverage += int(matched)

    if query_tokens and coverage == len(query_tokens):
        score += 40
    elif coverage == 0:
        return 0

    return score


def search_docs(
    query: str,
    *,
    scope: str = "local",
    doc_type: str | None = None,
    task_id: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    results: list[tuple[int, dict[str, Any]]] = []
    selected_tags = {str(tag).strip() for tag in (tags or []) if str(tag).strip()}
    for doc in load_docs(scope):
        if doc_type and doc.get("doc_type") != doc_type:
            continue
        if task_id and doc.get("task_id") != task_id:
            continue
        if selected_tags and not selected_tags.issubset(set(doc.get("tags", []))):
            continue
        score = _score_doc(doc, query)
        if score > 0:
            results.append((score, doc))

    results.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("created_at") or item[1].get("date_published") or ""),
            item[1]["title"].lower(),
        ),
        reverse=True,
    )
    return [doc for _, doc in results[:limit]]
