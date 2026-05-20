"""Tests for API route contracts — request/response shapes, status codes, errors."""

from __future__ import annotations

import json
import sqlite3

import pytest

from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Feature,
    FeatureStatus,
    GateResult,
    GateStatus,
    Task,
    TaskPhase,
    TaskStatus,
)


async def _queue_feature(test_db, feature_id: str) -> None:
    _, factory = test_db
    async with factory() as db:
        feature = await db.get(Feature, feature_id)
        feature.status = FeatureStatus.QUEUED
        await db.commit()


@pytest.mark.asyncio
async def test_init_db_soft_migrates_backlog_item_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "create table features ("
            "id varchar(36) primary key, "
            "project_id varchar(36) not null, "
            "title varchar(255) not null, "
            "description text, "
            "status varchar(32), "
            "priority integer, "
            "created_at datetime, "
            "updated_at datetime)"
        )
        conn.commit()

    import autonomous_agent_builder.db.session as session_mod

    old_engine = session_mod._engine
    old_factory = session_mod._session_factory
    session_mod._engine = None
    session_mod._session_factory = None
    monkeypatch.setenv("DB_URL_OVERRIDE", f"sqlite+aiosqlite:///{db_path}")
    try:
        await session_mod.init_db()
        with sqlite3.connect(db_path) as conn:
            columns = {row[1] for row in conn.execute("pragma table_info(features)").fetchall()}
    finally:
        await session_mod.close_db()
        session_mod._engine = old_engine
        session_mod._session_factory = old_factory

    assert {"item_type", "tags", "severity", "source", "evidence"}.issubset(columns)


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

    async def test_create_typed_backlog_incident_requires_evidence(self, client, test_db, tmp_path):
        client._transport.app.state.project_root = tmp_path
        pid = await self._create_project(client)
        resp = await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={"type": "incident", "title": "Backlog mismatch", "severity": "high"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_backlog_item"

    async def test_create_and_filter_typed_backlog_items(self, client, test_db, tmp_path):
        client._transport.app.state.project_root = tmp_path
        pid = await self._create_project(client)
        create_resp = await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={
                "type": "incident",
                "title": "Backlog count mismatch",
                "description": "Total and rendered rows disagree.",
                "tags": ["reverse-engineering"],
                "severity": "high",
                "source": "validation",
                "evidence": "Backlog showed total 5 but rendered 2 rows.",
            },
        )
        assert create_resp.status_code == 201
        item = create_resp.json()
        assert item["item_type"] == "incident"
        assert item["type"] == "incident"
        assert item["tags"] == ["reverse-engineering"]
        assert item["severity"] == "high"
        assert item["source"] == "validation"
        assert item["evidence"] == "Backlog showed total 5 but rendered 2 rows."

        list_resp = await client.get(
            f"/api/projects/{pid}/backlog/items",
            params={"type": "incident", "tag": "reverse-engineering"},
        )
        assert list_resp.status_code == 200
        assert [row["id"] for row in list_resp.json()] == [item["id"]]
        assert (tmp_path / ".claude" / "progress" / "incident-list.json").exists()

    async def test_create_typed_backlog_item_rejects_multiple_tags(
        self, client, test_db, tmp_path
    ):
        client._transport.app.state.project_root = tmp_path
        pid = await self._create_project(client)

        resp = await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={
                "type": "incident",
                "title": "Backlog count mismatch",
                "tags": ["reverse-engineering", "dashboard"],
                "severity": "high",
                "evidence": "Backlog showed total 5 but rendered 2 rows.",
            },
        )

        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "invalid_backlog_item"

    async def test_update_typed_backlog_item(
        self, client, test_db, tmp_path
    ):
        client._transport.app.state.project_root = tmp_path
        pid = await self._create_project(client)
        create_resp = await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={
                "type": "improvement",
                "title": "Tighten reverse workflow",
                "tags": ["testing-closeout"],
            },
        )
        item_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/api/backlog/items/{item_id}",
            json={
                "title": "Tighten workflow closeout",
                "status": "done",
                "tags": ["backlog"],
                "source": "validation",
                "evidence": "Closeout required manual tag normalization.",
            },
        )

        assert update_resp.status_code == 200
        item = update_resp.json()
        assert item["title"] == "Tighten workflow closeout"
        assert item["status"] == "done"
        assert item["tags"] == ["backlog"]
        assert item["source"] == "validation"
        assert item["evidence"] == "Closeout required manual tag normalization."

    async def test_update_typed_backlog_item_rejects_multiple_tags(
        self, client, test_db, tmp_path
    ):
        client._transport.app.state.project_root = tmp_path
        pid = await self._create_project(client)
        create_resp = await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={"type": "improvement", "title": "Tighten reverse workflow"},
        )
        item_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/api/backlog/items/{item_id}",
            json={"tags": ["backlog", "dashboard"]},
        )

        assert update_resp.status_code == 422
        assert update_resp.json()["detail"]["code"] == "invalid_backlog_item"

    async def test_dashboard_backlog_merges_typed_artifacts_and_db_items(
        self, client, test_db, tmp_path
    ):
        client._transport.app.state.project_root = tmp_path
        progress = tmp_path / ".claude" / "progress"
        progress.mkdir(parents=True)
        (progress / "improvement-list.json").write_text(
            json.dumps(
                {
                    "improvements": [
                        {
                            "id": "IMP-1",
                            "title": "Tighten reverse workflow",
                            "description": "Closeout learning loop.",
                            "status": "backlog",
                            "priority": "P1",
                            "tags": ["reverse-engineering"],
                        }
                    ]
                }
            )
        )
        pid = await self._create_project(client)
        await client.post(
            f"/api/projects/{pid}/backlog/items",
            json={
                "type": "incident",
                "title": "Inbox badge mismatch",
                "severity": "medium",
                "evidence": "Inbox badge did not identify approval type.",
                "tags": ["inbox"],
            },
        )

        resp = await client.get("/api/dashboard/features")

        assert resp.status_code == 200
        rows = resp.json()["features"]
        assert {row["item_type"] for row in rows} >= {"improvement", "incident"}
        assert any(row["tags"] == ["reverse-engineering"] for row in rows)


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

    async def test_list_gate_results_serializes_model_fields(self, client, test_db):
        _, factory = test_db
        proj = await client.post(
            "/api/projects/", json={"name": "gate-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Gate feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Gate task"},
        )
        task_id = task.json()["id"]
        async with factory() as db:
            db.add(
                GateResult(
                    task_id=task_id,
                    gate_name="testing",
                    status=GateStatus.WARN,
                    evidence={"summary": "No supported test runner found."},
                    findings_count=0,
                    elapsed_ms=12,
                    error_code="UNSUPPORTED_LANGUAGE",
                )
            )
            await db.commit()

        resp = await client.get(f"/api/tasks/{task_id}/gates")

        assert resp.status_code == 200
        assert resp.json() == [
            {
                "id": resp.json()[0]["id"],
                "task_id": task_id,
                "gate_name": "testing",
                "status": "warn",
                "findings_count": 0,
                "elapsed_ms": 12,
                "timeout": False,
                "error_code": "UNSUPPORTED_LANGUAGE",
                "remediation_attempted": False,
                "remediation_succeeded": False,
                "created_at": resp.json()[0]["created_at"],
            }
        ]

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
            task = await db.get(Task, task_id)
            task.blocked_reason = "stale gate failure"
            gate = ApprovalGate(task_id=task_id, gate_type="planning", status="pending")
            db.add(gate)
            await db.commit()
            gate_id = gate.id

        dispatched: list[tuple[object, tuple[object, ...]]] = []

        async def _fake_run_dispatch(dispatched_task_id: str) -> None:
            return None

        monkeypatch.setattr(
            "autonomous_agent_builder.api.routes.dispatch._run_dispatch",
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
            assert task.blocked_reason is None
            assert gate is not None
            assert gate.status == "approve"

    async def test_pr_request_changes_routes_back_to_implementation(
        self, client, test_db, monkeypatch
    ):
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
            task = await db.get(Task, task_id)
            task.status = TaskStatus.REVIEW_PENDING
            task.phase = TaskPhase.INTEGRATION
            gate = ApprovalGate(task_id=task_id, gate_type="pr", status="pending")
            db.add(gate)
            await db.commit()
            gate_id = gate.id

        dispatched: list[tuple[object, tuple[object, ...]]] = []

        async def _fake_run_dispatch(dispatched_task_id: str) -> None:
            return None

        monkeypatch.setattr(
            "autonomous_agent_builder.api.routes.dispatch._run_dispatch",
            _fake_run_dispatch,
        )

        def _fake_add_task(self, func, *args, **kwargs):
            dispatched.append((func, args))

        monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _fake_add_task)

        resp = await client.post(
            f"/api/approval-gates/{gate_id}/approve",
            json={
                "approver_email": "test@test.com",
                "decision": "request_changes",
                "reason": "Fix the missing lint dependency.",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["gate_status"] == "request_changes"
        assert dispatched == [(_fake_run_dispatch, (task_id,))]

        async with factory() as db:
            task = await db.get(Task, task_id)
            gate = await db.get(ApprovalGate, gate_id)
            assert task is not None
            assert task.status == TaskStatus.IMPLEMENTATION
            assert task.phase == TaskPhase.IMPLEMENTATION
            assert task.blocked_reason is None
            assert task.depends_on["phase_context"]["pr_change_request"] == (
                "Fix the missing lint dependency."
            )
            assert gate is not None
            assert gate.status == "request_changes"


@pytest.mark.asyncio
class TestDispatchRoute:
    """Test /api/dispatch endpoint."""

    async def test_dispatch_task_not_found(self, client, test_db):
        resp = await client.post(
            "/api/dispatch", json={"task_id": "nonexistent"}
        )
        assert resp.status_code == 404

    async def test_dispatch_valid_task(self, client, test_db, monkeypatch):
        from autonomous_agent_builder.services.dispatch_lock import release_dispatch

        def _capture_background_task(self, func, *args, **kwargs):
            return None

        monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _capture_background_task)
        proj = await client.post(
            "/api/projects/", json={"name": "dispatch-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Dispatch feature"},
        )
        await _queue_feature(test_db, feat.json()["id"])
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch task"},
        )
        task_id = task.json()["id"]
        try:
            resp = await client.post(
                "/api/dispatch", json={"task_id": task_id}
            )
        finally:
            release_dispatch(task_id)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert data["task_id"] == task_id

    async def test_dispatch_is_idempotent_for_duplicate_active_run(
        self, client, test_db, monkeypatch
    ):
        from autonomous_agent_builder.services.dispatch_lock import release_dispatch

        proj = await client.post(
            "/api/projects/", json={"name": "dispatch-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Dispatch feature"},
        )
        await _queue_feature(test_db, feat.json()["id"])
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch task"},
        )
        task_id = task.json()["id"]

        def _capture_background_task(self, func, *args, **kwargs):
            return None

        monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _capture_background_task)

        try:
            first = await client.post("/api/dispatch", json={"task_id": task_id})
            second = await client.post("/api/dispatch", json={"task_id": task_id})
        finally:
            release_dispatch(task_id)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "already_running"

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

    @pytest.mark.parametrize(
        ("task_status", "expected_status"),
        [
            (TaskStatus.PENDING, 200),
            (TaskStatus.QUEUED, 200),
            (TaskStatus.FAILED, 409),
            (TaskStatus.REVIEW_PENDING, 409),
            (TaskStatus.CAPABILITY_LIMIT, 409),
        ],
    )
    async def test_dispatch_policy_payloads_match_shared_contract(
        self, client, test_db, monkeypatch, task_status, expected_status
    ):
        from autonomous_agent_builder.services.dispatch_lock import release_dispatch

        def _capture_background_task(self, func, *args, **kwargs):
            return None

        monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _capture_background_task)
        proj = await client.post(
            "/api/projects/", json={"name": "dispatch-policy-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Dispatch policy feature"},
        )
        await _queue_feature(test_db, feat.json()["id"])
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch policy task"},
        )
        task_id = task.json()["id"]
        _, factory = test_db
        async with factory() as db:
            task_row = await db.get(Task, task_id)
            task_row.status = task_status
            task_row.blocked_reason = "provider limit blocked" if task_status == TaskStatus.CAPABILITY_LIMIT else "blocked"
            if task_status == TaskStatus.CAPABILITY_LIMIT:
                task_row.depends_on = {
                    "provider_limit": {
                        "code": "provider_limit",
                        "resume_status": "implementation",
                        "resume_task_id": task_id,
                    }
                }
            await db.commit()

        try:
            resp = await client.post("/api/dispatch", json={"task_id": task_id})
        finally:
            release_dispatch(task_id)

        assert resp.status_code == expected_status
        data = resp.json()
        if expected_status == 200:
            assert data["status"] == "dispatched"
            assert data["current_status"] == task_status.value
        else:
            detail = data["detail"]
            assert detail["code"] == "task_not_dispatchable"
            assert detail["status"] == task_status.value
            if task_status == TaskStatus.CAPABILITY_LIMIT:
                assert detail["provider_limit"]["code"] == "provider_limit"

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

    async def test_recover_allows_documentation_gate_blocked_task(self, client, test_db):
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
            task_row.status = TaskStatus.BLOCKED
            task_row.phase = TaskPhase.VERIFICATION
            task_row.blocked_reason = (
                "documentation refresh gate blocked: validation failed without actionable stale maintained docs"
            )
            await db.commit()

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "status": "ok",
            "task_id": task_id,
            "previous_status": "blocked",
            "current_status": "quality_gates",
            "next_step": f"builder backlog task dispatch {task_id} --yes --json",
        }

        verify = await client.get(f"/api/tasks/{task_id}")
        assert verify.status_code == 200
        assert verify.json()["status"] == "quality_gates"
        assert verify.json()["blocked_reason"] is None

    async def test_recover_allows_pr_change_request_blocked_task(self, client, test_db):
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
            task_row.status = TaskStatus.BLOCKED
            task_row.phase = TaskPhase.INTEGRATION
            task_row.blocked_reason = "Approval rejected"
            db.add(ApprovalGate(task_id=task_id, gate_type="pr", status="request_changes"))
            await db.commit()

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "status": "ok",
            "task_id": task_id,
            "previous_status": "blocked",
            "current_status": "implementation",
            "next_step": f"builder backlog task dispatch {task_id} --yes --json",
        }

        verify = await client.get(f"/api/tasks/{task_id}")
        assert verify.status_code == 200
        assert verify.json()["status"] == "implementation"
        assert verify.json()["blocked_reason"] is None

    async def test_recover_allows_capability_limit_task_from_preserved_phase(
        self, client, test_db
    ):
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
            task_row.status = TaskStatus.CAPABILITY_LIMIT
            task_row.phase = TaskPhase.IMPLEMENTATION
            task_row.blocked_reason = "Quality gate failures:\n\n- implementation_delta: fail"
            task_row.capability_limit_reason = "SDK limit: provider_limit"
            await db.commit()

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "status": "ok",
            "task_id": task_id,
            "previous_status": "capability_limit",
            "current_status": "implementation",
            "next_step": f"builder backlog task dispatch {task_id} --yes --json",
        }

        verify = await client.get(f"/api/tasks/{task_id}")
        assert verify.status_code == 200
        payload = verify.json()
        assert payload["status"] == "implementation"
        assert payload["blocked_reason"] is None

    async def test_recover_rejects_non_documentation_blocked_task(self, client, test_db):
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
            task_row.status = TaskStatus.BLOCKED
            task_row.phase = TaskPhase.VERIFICATION
            task_row.blocked_reason = "human review required"
            await db.commit()

        resp = await client.post(f"/api/tasks/{task_id}/recover")

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "task_not_recoverable"
        assert detail["status"] == "blocked"


@pytest.mark.asyncio
class TestHealthCheck:
    """Test /health endpoint."""

    async def test_health(self, client, test_db):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
