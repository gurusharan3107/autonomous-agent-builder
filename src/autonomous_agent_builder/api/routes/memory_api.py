"""Memory API — read-only access to .memory/ for the dashboard.

Memory mutations go through the CLI (direct filesystem).
The API only exposes read access for the React dashboard.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from autonomous_agent_builder.services.path_containment import resolve_contained_path
from autonomous_agent_builder.services.project_context import request_project_root

router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_root(request: Request) -> Path:
    """Resolve memory directory path."""
    configured = os.environ.get("AAB_MEMORY_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (request_project_root(request) / ".memory").resolve()


def _load_routing(memory_root: Path) -> list[dict]:
    """Load routing.json index."""
    routing_path = memory_root / "routing.json"
    if not routing_path.exists():
        return []
    try:
        data = json.loads(routing_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []
        entries = data.get("entries")
        if isinstance(entries, list):
            return entries
        memories = data.get("memories")
        if isinstance(memories, list):
            return memories
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _read_file(entry: dict, memory_root: Path) -> str:
    """Read content from a memory file."""
    file_path = resolve_contained_path(memory_root, entry.get("file", ""))
    if file_path is None:
        return ""
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


@router.get("/")
async def list_memories(
    request: Request,
    mem_type: str | None = Query(None, alias="type"),
    phase: str | None = Query(None),
    entity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """List memory entries from .memory/routing.json."""
    entries = _load_routing(_memory_root(request))
    if mem_type:
        entries = [e for e in entries if e.get("type") == mem_type]
    if phase:
        entries = [e for e in entries if e.get("phase") == phase]
    if entity:
        entries = [e for e in entries if e.get("entity") == entity]
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:limit]


@router.get("/search")
async def search_memories(
    request: Request,
    q: str = Query(..., min_length=1),
    entity: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """Search memories by title, tags, and content."""
    memory_root = _memory_root(request)
    entries = _load_routing(memory_root)
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    results = []

    for entry in entries:
        if entity and entry.get("entity") != entity:
            continue
        if tag and tag not in entry.get("tags", []):
            continue

        if pattern.search(entry.get("title", "")):
            results.append(entry)
            continue

        if any(pattern.search(t) for t in entry.get("tags", [])):
            results.append(entry)
            continue

        content = _read_file(entry, memory_root)
        if pattern.search(content):
            results.append(entry)

    return results[:limit]


@router.get("/{slug}")
async def get_memory(slug: str, request: Request) -> dict:
    """Get a single memory entry with content."""
    memory_root = _memory_root(request)
    entries = _load_routing(memory_root)
    entry = next((e for e in entries if e.get("slug") == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Memory '{slug}' not found")
    content = _read_file(entry, memory_root)
    return {**entry, "content": content}
