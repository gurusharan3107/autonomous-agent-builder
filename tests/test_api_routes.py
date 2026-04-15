"""Tests for API route contracts — request/response shapes, status codes, errors."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestProjectRoutes:
    """Test /api/projects/ endpoints."""

    async def test_create_project(self, client, test_db):
        resp = await client.post(
            "/api/projects/",
            json={"name": "test-proj", "language": "python"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-proj"
        assert data["language"] == "python"
        assert "id" in data
        assert "created_at" in data

    async def test_create_project_with_all_fields(self, client, test_db):
        resp = await client.post(
            "/api/projects/",
            json={
                "name": "full-proj",
                "description": "A test project",
                "repo_url": "https://github.com/test/repo",
                "language": "node",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "A test project"
        assert data["repo_url"] == "https://github.com/test/repo"

    async def test_list_projects_empty(self, client, test_db):
        resp = await client.get("/api/projects/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_projects_returns_created(self, client, test_db):
        await client.post(
            "/api/projects/", json={"name": "proj-a", "language": "python"}
        )
        await client.post(
            "/api/projects/", json={"name": "proj-b", "language": "node"}
        )
        resp = await client.get("/api/projects/")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "proj-a" in names
        assert "proj-b" in names

    async def test_get_project_by_id(self, client, test_db):
        create_resp = await client.post(
            "/api/projects/", json={"name": "get-me", "language": "python"}
        )
        project_id = create_resp.json()["id"]
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    async def test_get_project_not_found(self, client, test_db):
        resp = await client.get("/api/projects/nonexistent-id")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestFeatureRoutes:
    """Test /api/projects/{id}/features and /api/features/{id} endpoints."""

    async def _create_project(self, client):
        resp = await client.post(
            "/api/projects/", json={"name": "feat-proj", "language": "python"}
        )
        return resp.json()["id"]

    async def test_create_feature(self, client, test_db):
        pid = await self._create_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/features",
            json={"title": "Add login", "description": "OAuth flow"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Add login"
        assert data["project_id"] == pid

    async def test_create_feature_project_not_found(self, client, test_db):
        resp = await client.post(
            "/api/projects/bad-id/features",
            json={"title": "Orphan feature"},
        )
        assert resp.status_code == 404

    async def test_list_features(self, client, test_db):
        pid = await self._create_project(client)
        await client.post(
            f"/api/projects/{pid}/features",
            json={"title": "Feature A"},
        )
        await client.post(
            f"/api/projects/{pid}/features",
            json={"title": "Feature B"},
        )
        resp = await client.get(f"/api/projects/{pid}/features")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_feature_by_id(self, client, test_db):
        pid = await self._create_project(client)
        create_resp = await client.post(
            f"/api/projects/{pid}/features",
            json={"title": "Get me"},
        )
        fid = create_resp.json()["id"]
        resp = await client.get(f"/api/features/{fid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get me"

    async def test_get_feature_not_found(self, client, test_db):
        resp = await client.get("/api/features/nonexistent")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestTaskRoutes:
    """Test /api/features/{id}/tasks and /api/tasks/{id} endpoints."""

    async def _create_feature(self, client):
        proj = await client.post(
            "/api/projects/", json={"name": "task-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Task feature"},
        )
        return feat.json()["id"]

    async def test_create_task(self, client, test_db):
        fid = await self._create_feature(client)
        resp = await client.post(
            f"/api/features/{fid}/tasks",
            json={"title": "Implement login", "complexity": 3},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Implement login"
        assert data["complexity"] == 3
        assert data["status"] == "pending"

    async def test_create_task_feature_not_found(self, client, test_db):
        resp = await client.post(
            "/api/features/bad-id/tasks",
            json={"title": "Orphan task"},
        )
        assert resp.status_code == 404

    async def test_list_tasks(self, client, test_db):
        fid = await self._create_feature(client)
        await client.post(
            f"/api/features/{fid}/tasks", json={"title": "Task 1"}
        )
        await client.post(
            f"/api/features/{fid}/tasks", json={"title": "Task 2"}
        )
        resp = await client.get(f"/api/features/{fid}/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_get_task_by_id(self, client, test_db):
        fid = await self._create_feature(client)
        create_resp = await client.post(
            f"/api/features/{fid}/tasks", json={"title": "Get me"}
        )
        tid = create_resp.json()["id"]
        resp = await client.get(f"/api/tasks/{tid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get me"

    async def test_get_task_not_found(self, client, test_db):
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestGateRoutes:
    """Test gate results, agent runs, and approval endpoints."""

    async def test_list_gate_results_empty(self, client, test_db):
        resp = await client.get("/api/tasks/some-task-id/gates")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_agent_runs_empty(self, client, test_db):
        resp = await client.get("/api/tasks/some-task-id/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_approval_gates_empty(self, client, test_db):
        resp = await client.get("/api/tasks/some-task-id/approvals")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_submit_approval_gate_not_found(self, client, test_db):
        resp = await client.post(
            "/api/approval-gates/bad-id/approve",
            json={
                "approver_email": "test@test.com",
                "decision": "approve",
            },
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestDispatchRoute:
    """Test /api/dispatch endpoint."""

    async def test_dispatch_task_not_found(self, client, test_db):
        resp = await client.post(
            "/api/dispatch", json={"task_id": "nonexistent"}
        )
        assert resp.status_code == 404

    async def test_dispatch_valid_task(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "dispatch-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Dispatch feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch task"},
        )
        task_id = task.json()["id"]
        resp = await client.post(
            "/api/dispatch", json={"task_id": task_id}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert data["task_id"] == task_id


@pytest.mark.asyncio
class TestHealthCheck:
    """Test /health endpoint."""

    async def test_health(self, client, test_db):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
