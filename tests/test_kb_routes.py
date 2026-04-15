"""Tests for Knowledge Base API routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_kb_document(client, test_db):
    """Create a project and task first, then create a KB doc."""
    # Create project
    proj = await client.post(
        "/api/projects/",
        json={"name": "test-proj", "language": "python"},
    )
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    # Create feature
    feat = await client.post(
        f"/api/projects/{project_id}/features",
        json={"title": "Test feature"},
    )
    assert feat.status_code == 201
    feature_id = feat.json()["id"]

    # Create task
    task = await client.post(
        f"/api/features/{feature_id}/tasks",
        json={"title": "Test task"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    # Create KB document
    resp = await client.post(
        "/api/kb/",
        json={
            "task_id": task_id,
            "doc_type": "adr",
            "title": "ADR-001: Use PostgreSQL",
            "content": "We decided to use PostgreSQL for reliability.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["doc_type"] == "adr"
    assert data["title"] == "ADR-001: Use PostgreSQL"
    assert data["version"] == 1
    return data["id"]


@pytest.mark.asyncio
async def test_list_kb_documents(client, test_db):
    """List returns empty initially."""
    resp = await client.get("/api/kb/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_search_kb_documents(client, test_db):
    """Search with query param."""
    resp = await client.get("/api/kb/search", params={"q": "postgres"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_kb_document_not_found(client, test_db):
    """404 for missing doc."""
    resp = await client.get("/api/kb/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_kb_document(client, test_db):
    """Create then update a KB doc — version should bump."""
    # Create project → feature → task → doc
    proj = await client.post(
        "/api/projects/",
        json={"name": "update-test", "language": "python"},
    )
    project_id = proj.json()["id"]
    feat = await client.post(
        f"/api/projects/{project_id}/features",
        json={"title": "feat"},
    )
    feature_id = feat.json()["id"]
    task = await client.post(
        f"/api/features/{feature_id}/tasks",
        json={"title": "task"},
    )
    task_id = task.json()["id"]

    create_resp = await client.post(
        "/api/kb/",
        json={
            "task_id": task_id,
            "doc_type": "runbook",
            "title": "Runbook v1",
            "content": "Initial content",
        },
    )
    doc_id = create_resp.json()["id"]

    # Update content
    update_resp = await client.put(
        f"/api/kb/{doc_id}",
        json={"content": "Updated content"},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["version"] == 2
    assert data["content"] == "Updated content"
