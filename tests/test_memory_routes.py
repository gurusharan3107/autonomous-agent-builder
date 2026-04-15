"""Tests for Memory API routes."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    """Set up a temporary .memory/ directory with test data."""
    mem_dir = tmp_path / ".memory"
    mem_dir.mkdir()

    # Create routing.json
    routing = {
        "entries": [
            {
                "slug": "sdk-foundation",
                "file": "decision_sdk-foundation.md",
                "title": "Claude Agent SDK as foundation",
                "type": "decision",
                "phase": "design",
                "entity": "orchestrator",
                "tags": ["sdk", "architecture"],
                "status": "active",
                "date": "2026-04-13",
            },
            {
                "slug": "concurrent-gates",
                "file": "pattern_concurrent-gates.md",
                "title": "Concurrent quality gates with asyncio.gather",
                "type": "pattern",
                "phase": "testing",
                "entity": "quality-gates",
                "tags": ["asyncio", "concurrency"],
                "status": "active",
                "date": "2026-04-14",
            },
        ],
    }
    (mem_dir / "routing.json").write_text(json.dumps(routing))
    (mem_dir / "decision_sdk-foundation.md").write_text(
        "# SDK Foundation\nUsing Claude Agent SDK for agent execution."
    )
    (mem_dir / "pattern_concurrent-gates.md").write_text(
        "# Concurrent Gates\nasyncio.gather for parallel gate execution."
    )

    monkeypatch.setenv("AAB_MEMORY_ROOT", str(mem_dir))
    return mem_dir


@pytest.mark.asyncio
async def test_list_memories(client, test_db, memory_dir):
    resp = await client.get("/api/memory/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_memories_filter_type(client, test_db, memory_dir):
    resp = await client.get("/api/memory/", params={"type": "decision"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["type"] == "decision"


@pytest.mark.asyncio
async def test_get_memory(client, test_db, memory_dir):
    resp = await client.get("/api/memory/sdk-foundation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "sdk-foundation"
    assert "SDK Foundation" in data["content"]


@pytest.mark.asyncio
async def test_get_memory_not_found(client, test_db, memory_dir):
    resp = await client.get("/api/memory/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_memories(client, test_db, memory_dir):
    resp = await client.get("/api/memory/search", params={"q": "SDK"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any("sdk" in e.get("slug", "").lower() for e in data)
