"""Memory API — read-only access to .memory/ for the dashboard.

Memory mutations go through the CLI (direct filesystem).
The API only exposes read access for the React dashboard.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_root() -> Path:
    """Resolve memory directory path."""
    return Path(os.environ.get("AAB_MEMORY_ROOT", ".memory"))


def _load_routing() -> list[dict]:
    """Load routing.json index."""
    routing_path = _memory_root() / "routing.json"
    if not routing_path.exists():
        return []
    try:
        data = json.loads(routing_path.read_text(encoding="utf-8"))
        return data.get("entries", []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, OSError):
        return []


def _read_file(entry: dict) -> str:
    """Read content from a memory file."""
    file_path = _memory_root() / entry.get("file", "")
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


@router.get("/")
async def list_memories(
    mem_type: str | None = Query(None, alias="type"),
    phase: str | None = Query(None),
    entity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """List memory entries from .memory/routing.json."""
    entries = _load_routing()
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
    q: str = Query(..., min_length=1),
    entity: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """Search memories by title, tags, and content."""
    entries = _load_routing()
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

        content = _read_file(entry)
        if pattern.search(content):
            results.append(entry)

    return results[:limit]


@router.get("/{slug}")
async def get_memory(slug: str) -> dict:
    """Get a single memory entry with content."""
    entries = _load_routing()
    entry = next((e for e in entries if e.get("slug") == slug), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Memory '{slug}' not found")
    content = _read_file(entry)
    return {**entry, "content": content}
