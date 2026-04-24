"""Tests for API route contracts — request/response shapes, status codes, errors."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.db.models import ApprovalGate, Task, TaskStatus


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

    async def test_create_task_reconciles_superseded_required_docs(self, client, monkeypatch, tmp_path):
        kb_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
        kb_root.mkdir(parents=True)
        (kb_root / "current-onboarding.md").write_text(
            "---\n"
            "title: Current Onboarding\n"
            "tags:\n"
            "- feature\n"
            "doc_type: feature\n"
            "doc_family: feature\n"
            "refresh_required: true\n"
            "lifecycle_status: active\n"
            "---\n\n"
            "# Current Onboarding\n\n"
            "## Overview\n\n"
            "Current onboarding behavior.\n\n"
            "## Current behavior\n\n"
            "Live feature path.\n\n"
            "## Boundaries\n\n"
            "Routes and handlers.\n\n"
            "## Verification\n\n"
            "Use testing coverage.\n\n"
            "## Change guidance\n\n"
            "Refresh after onboarding changes.\n",
            encoding="utf-8",
        )
        (kb_root / "legacy-onboarding.md").write_text(
            "---\n"
            "title: Legacy Onboarding\n"
            "tags:\n"
            "- feature\n"
            "doc_type: feature\n"
            "doc_family: feature\n"
            "refresh_required: true\n"
            "lifecycle_status: superseded\n"
            "superseded_by: feature/current-onboarding.md\n"
            "---\n\n"
            "# Legacy Onboarding\n\n"
            "## Overview\n\n"
            "Superseded onboarding behavior.\n\n"
            "## Current behavior\n\n"
            "Old path.\n\n"
            "## Boundaries\n\n"
            "Retired handlers.\n\n"
            "## Verification\n\n"
            "Legacy checks.\n\n"
            "## Change guidance\n\n"
            "Do not update this doc.\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge"))

        fid = await self._create_feature(client)
        resp = await client.post(
            f"/api/features/{fid}/tasks",
            json={
                "title": "Implement login",
                "depends_on": {
                    "system_docs": {
                        "required_docs": [
                            "feature/legacy-onboarding.md",
                            "feature/current-onboarding.md",
                        ]
                    }
                },
            },
        )
        assert resp.status_code == 201
        assert resp.json()["depends_on"]["system_docs"]["required_docs"] == [
            "feature/current-onboarding.md"
        ]

    async def test_update_task_reconciles_required_docs(self, client, monkeypatch, tmp_path):
        kb_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
        kb_root.mkdir(parents=True)
        (kb_root / "replacement.md").write_text(
            "---\n"
            "title: Replacement Feature Doc\n"
            "tags:\n"
            "- feature\n"
            "doc_type: feature\n"
            "doc_family: feature\n"
            "refresh_required: true\n"
            "lifecycle_status: active\n"
            "---\n\n"
            "# Replacement Feature Doc\n\n"
            "## Overview\n\n"
            "Replacement doc.\n\n"
            "## Current behavior\n\n"
            "Current behavior.\n\n"
            "## Boundaries\n\n"
            "Relevant boundaries.\n\n"
            "## Verification\n\n"
            "Relevant verification.\n\n"
            "## Change guidance\n\n"
            "Refresh when behavior changes.\n",
            encoding="utf-8",
        )
        (kb_root / "superseded.md").write_text(
            "---\n"
            "title: Superseded Feature Doc\n"
            "tags:\n"
            "- feature\n"
            "doc_type: feature\n"
            "doc_family: feature\n"
            "refresh_required: true\n"
            "lifecycle_status: superseded\n"
            "superseded_by: feature/replacement.md\n"
            "---\n\n"
            "# Superseded Feature Doc\n\n"
            "## Overview\n\n"
            "Old doc.\n\n"
            "## Current behavior\n\n"
            "Old behavior.\n\n"
            "## Boundaries\n\n"
            "Old boundaries.\n\n"
            "## Verification\n\n"
            "Old verification.\n\n"
            "## Change guidance\n\n"
            "Do not refresh.\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge"))

        fid = await self._create_feature(client)
        created = await client.post(f"/api/features/{fid}/tasks", json={"title": "Task"})
        task_id = created.json()["id"]

        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={
                "depends_on": {
                    "system_docs": {"required_docs": ["feature/superseded.md"]}
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["depends_on"]["system_docs"]["required_docs"] == ["feature/replacement.md"]

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

    async def test_submit_approval_dispatches_next_phase(self, client, test_db, monkeypatch):
        project_resp = await client.post(
            "/api/projects/",
            json={"name": "approval-proj", "language": "python"},
        )
        feature_resp = await client.post(
            f"/api/projects/{project_resp.json()['id']}/features",
            json={"title": "Approval feature"},
        )
        task_resp = await client.post(
            f"/api/features/{feature_resp.json()['id']}/tasks",
            json={"title": "Approval task"},
        )
        task_id = task_resp.json()["id"]

        _, factory = test_db
        async with factory() as db:
            gate = ApprovalGate(task_id=task_id, gate_type="planning", status="pending")
            db.add(gate)
            await db.commit()
            gate_id = gate.id

        dispatched: list[tuple[object, tuple[object, ...]]] = []

        async def _fake_run_dispatch(dispatched_task_id: str) -> None:
            return None

        monkeypatch.setattr(
            "autonomous_agent_builder.embedded.server.routes.tasks._run_dispatch",
            _fake_run_dispatch,
        )

        def _fake_add_task(self, func, *args, **kwargs):
            dispatched.append((func, args))

        monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _fake_add_task)

        resp = await client.post(
            f"/api/approval-gates/{gate_id}/approve",
            json={
                "approver_email": "test@test.com",
                "decision": "approve",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["gate_status"] == "approve"
        assert dispatched == [(_fake_run_dispatch, (task_id,))]

        async with factory() as db:
            task = await db.get(Task, task_id)
            gate = await db.get(ApprovalGate, gate_id)
            assert task is not None
            assert task.status == TaskStatus.DESIGN
            assert gate is not None
            assert gate.status == "approve"


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

    async def test_dispatch_rejects_failed_task(self, client, test_db):
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
        _, factory = test_db
        async with factory() as db:
            task_row = await db.get(Task, task_id)
            task_row.status = TaskStatus.FAILED
            task_row.blocked_reason = "planner failed"
            await db.commit()

        resp = await client.post("/api/dispatch", json={"task_id": task_id})

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "task_not_dispatchable"
        assert detail["status"] == "failed"
        assert detail["blocked_reason"] == "planner failed"

    async def test_recover_failed_task_resets_it_to_pending(self, client, test_db):
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
        _, factory = test_db
        async with factory() as db:
            task_row = await db.get(Task, task_id)
            task_row.status = TaskStatus.FAILED
            task_row.blocked_reason = "planner failed"
            await db.commit()

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "status": "ok",
            "task_id": task_id,
            "previous_status": "failed",
            "current_status": "pending",
            "next_step": f"builder backlog task dispatch {task_id} --yes --json",
        }

        verify = await client.get(f"/api/tasks/{task_id}")
        assert verify.status_code == 200
        assert verify.json()["status"] == "pending"
        assert verify.json()["blocked_reason"] is None

    async def test_recover_rejects_non_failed_task(self, client, test_db):
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

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "task_not_recoverable"
        assert detail["status"] == "pending"


@pytest.mark.asyncio
class TestHealthCheck:
    """Test /health endpoint."""

    async def test_health(self, client, test_db):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
