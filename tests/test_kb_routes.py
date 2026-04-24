"""Tests for filesystem-backed Knowledge Base API routes."""

from __future__ import annotations

import json

import pytest

from autonomous_agent_builder.api.routes import knowledge


@pytest.fixture
def kb_roots(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    global_root = tmp_path / ".codex" / "knowledge"
    (local_root / "adr").mkdir(parents=True)
    (local_root / "context").mkdir(parents=True)
    (local_root / "knowledge").mkdir(parents=True)
    (global_root / "raw").mkdir(parents=True)

    (local_root / "adr" / "001-use-fastapi.md").write_text(
        "# ADR 001: Use FastAPI\n\nWe use FastAPI for the API layer.\n\n[[Project Overview]]\n"
    )
    (local_root / "context" / "project-overview.md").write_text(
        "# Project Overview\n\nFastAPI project context and orchestration notes.\n"
    )
    (local_root / "knowledge" / "stale-shadow-copy.md").write_text(
        "---\n"
        "title: Stale Shadow Copy\n"
        "doc_type: system-docs\n"
        "created: 2026-04-19T12:00:00\n"
        "auto_generated: true\n"
        "version: 1\n"
        "---\n\n"
        "# Stale Shadow Copy\n\nThis file lives in a noncanonical collection and must be ignored.\n"
    )
    (global_root / "raw" / "2026-04-14-verify-cli.md").write_text(
        "---\n"
        "title: Verify CLI works outside source directory\n"
        "date_processed: 2026-04-14\n"
        "tags: [tools, coding-agents]\n"
        "---\n\n"
        "CLI verification guidance.\n"
    )
    (global_root / "routing.json").write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "file": "2026-04-14-verify-cli.md",
                        "title": "Verify CLI works outside source directory",
                        "tags": ["tools", "coding-agents"],
                        "date_processed": "2026-04-14",
                    }
                ]
            }
        )
    )

    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))
    monkeypatch.setenv("AAB_GLOBAL_KB_ROOT", str(global_root))
    return local_root, global_root


@pytest.mark.asyncio
async def test_list_local_kb_documents(client, test_db, kb_roots):
    resp = await client.get("/api/kb/", params={"scope": "local"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {doc["doc_type"] for doc in data} == {"adr", "context"}
    assert all(doc["title"] != "Stale Shadow Copy" for doc in data)


@pytest.mark.asyncio
async def test_list_global_kb_documents(client, test_db, kb_roots):
    resp = await client.get("/api/kb/", params={"scope": "global"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["doc_type"] == "raw"
    assert data[0]["title"] == "Verify CLI works outside source directory"


@pytest.mark.asyncio
async def test_search_kb_documents(client, test_db, kb_roots):
    resp = await client.get("/api/kb/search", params={"q": "FastAPI", "scope": "local"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any("FastAPI" in doc["title"] or "FastAPI" in doc["content"] for doc in data)


@pytest.mark.asyncio
async def test_get_kb_document_not_found(client, test_db, kb_roots):
    resp = await client.get("/api/kb/nonexistent-id", params={"scope": "local"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_kb_tags(client, test_db, kb_roots):
    resp = await client.get("/api/kb/tags", params={"scope": "global"})
    assert resp.status_code == 200
    data = resp.json()
    assert any(tag["name"] == "tools" for tag in data)


@pytest.mark.asyncio
async def test_get_related_kb_documents(client, test_db, kb_roots):
    resp = await client.get("/api/kb/adr/001-use-fastapi.md/related", params={"scope": "local"})
    assert resp.status_code == 200
    data = resp.json()
    assert "wikilinks" in data
    assert "backlinks" in data
    assert "similar" in data


def test_knowledge_api_routes_are_read_only():
    mutating = {"POST", "PUT", "PATCH", "DELETE"}
    for route in knowledge.router.routes:
        methods = set(getattr(route, "methods", []) or [])
        assert not (methods & mutating)
