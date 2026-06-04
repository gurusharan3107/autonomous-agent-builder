"""Tests for Memory API routes."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


@pytest.fixture
def project_memory_dir(monkeypatch):
    """Set up project-scoped .memory/ without AAB_MEMORY_ROOT override."""
    monkeypatch.delenv("AAB_MEMORY_ROOT", raising=False)
    project_root = Path(os.environ["AAB_PROJECT_ROOT"])
    mem_dir = project_root / ".memory"
    mem_dir.mkdir(parents=True)
    routing = {
        "entries": [
            {
                "slug": "project-scoped",
                "file": "decision_project-scoped.md",
                "title": "Project scoped memory",
                "type": "decision",
                "phase": "design",
                "entity": "memory",
                "tags": ["project"],
                "status": "active",
                "date": "2026-05-18",
            }
        ]
    }
    (mem_dir / "routing.json").write_text(json.dumps(routing))
    (mem_dir / "decision_project-scoped.md").write_text(
        "# Project Scoped\nThis came from the app project root.",
        encoding="utf-8",
    )
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


@pytest.mark.asyncio
async def test_get_memory_rejects_absolute_routing_file_escape(client, test_db, tmp_path, monkeypatch):
    mem_dir = tmp_path / ".memory"
    mem_dir.mkdir()
    outside = tmp_path / "outside-secret.md"
    outside.write_text("# Outside\nabsolute route secret", encoding="utf-8")
    routing = {
        "entries": [
            {
                "slug": "absolute-escape",
                "file": str(outside),
                "title": "Escaping memory file",
                "type": "decision",
                "phase": "design",
                "entity": "memory",
                "tags": [],
                "status": "active",
                "date": "2026-05-18",
            }
        ]
    }
    (mem_dir / "routing.json").write_text(json.dumps(routing))
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(mem_dir))

    resp = await client.get("/api/memory/absolute-escape")
    assert resp.status_code == 200
    assert resp.json()["content"] == ""

    search = await client.get("/api/memory/search", params={"q": "absolute route secret"})
    assert search.status_code == 200
    assert search.json() == []


@pytest.mark.asyncio
async def test_get_memory_rejects_parent_traversal_routing_file(client, test_db, tmp_path, monkeypatch):
    mem_dir = tmp_path / ".memory"
    mem_dir.mkdir()
    outside = tmp_path / "outside-secret.md"
    outside.write_text("# Outside\nparent traversal secret", encoding="utf-8")
    routing = {
        "entries": [
            {
                "slug": "parent-escape",
                "file": "../outside-secret.md",
                "title": "Parent escape memory file",
                "type": "decision",
                "phase": "design",
                "entity": "memory",
                "tags": [],
                "status": "active",
                "date": "2026-05-18",
            }
        ]
    }
    (mem_dir / "routing.json").write_text(json.dumps(routing))
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(mem_dir))

    resp = await client.get("/api/memory/parent-escape")
    assert resp.status_code == 200
    assert resp.json()["content"] == ""

    search = await client.get("/api/memory/search", params={"q": "parent traversal secret"})
    assert search.status_code == 200
    assert search.json() == []


@pytest.mark.asyncio
async def test_memory_routes_use_app_project_root_not_process_cwd(
    client,
    test_db,
    project_memory_dir,
    tmp_path,
    monkeypatch,
):
    wrong_cwd = tmp_path / "wrong-cwd"
    wrong_cwd.mkdir()
    monkeypatch.chdir(wrong_cwd)
    (wrong_cwd / ".memory").mkdir()
    (wrong_cwd / ".memory" / "routing.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "slug": "wrong-cwd",
                        "file": "wrong.md",
                        "title": "Wrong cwd memory",
                    }
                ]
            }
        )
    )
    (wrong_cwd / ".memory" / "wrong.md").write_text("# Wrong CWD", encoding="utf-8")

    resp = await client.get("/api/memory/project-scoped")
    assert resp.status_code == 200
    assert "Project Scoped" in resp.json()["content"]

    wrong = await client.get("/api/memory/wrong-cwd")
    assert wrong.status_code == 404
