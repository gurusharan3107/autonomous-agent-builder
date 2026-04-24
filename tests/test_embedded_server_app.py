from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from autonomous_agent_builder.db.models import Task, TaskStatus
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server.app import create_app


def test_embedded_server_exposes_health(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_embedded_server_exposes_project_scoped_feature_routes(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        create_feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Canonical backlog lane", "description": "Use backlog as the public lane"},
        )
        assert create_feature_response.status_code == 201
        assert create_feature_response.json()["project_id"] == project_id

        list_feature_response = client.get(f"/api/projects/{project_id}/features")
        assert list_feature_response.status_code == 200
        payload = list_feature_response.json()
        assert len(payload) == 1
        assert payload[0]["title"] == "Canonical backlog lane"


def test_embedded_server_dispatches_task_route(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    dispatched: list[str] = []

    async def fake_run_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.tasks._run_dispatch",
        fake_run_dispatch,
    )

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            task = Task(feature_id=feature_id, title="Dispatchable task", description="Exercise embedded dispatch")
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return task.id

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
            },
        )
        project_id = project_response.json()["id"]
        feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Dispatchable feature", "description": "Ready for task dispatch"},
        )
        feature_id = feature_response.json()["id"]
        task_id = asyncio.run(create_task(feature_id))

        response = client.post(f"/api/tasks/{task_id}/dispatch")

    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    assert response.json()["task_id"] == task_id
    assert dispatched == [task_id]


def test_embedded_server_exposes_dispatch_compat_route(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    dispatched: list[str] = []

    async def fake_run_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(
        "autonomous_agent_builder.api.routes.dispatch._run_dispatch",
        fake_run_dispatch,
    )

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            task = Task(feature_id=feature_id, title="Dispatchable task", description="Exercise embedded dispatch")
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return task.id

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
            },
        )
        project_id = project_response.json()["id"]
        feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Dispatchable feature", "description": "Ready for task dispatch"},
        )
        feature_id = feature_response.json()["id"]
        task_id = asyncio.run(create_task(feature_id))

        response = client.post("/api/dispatch", json={"task_id": task_id})

    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    assert response.json()["task_id"] == task_id
    assert dispatched == [task_id]


def test_embedded_server_rejects_dispatch_for_failed_task(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_failed_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            task = Task(
                feature_id=feature_id,
                title="Dispatchable task",
                description="Exercise embedded dispatch",
                status=TaskStatus.FAILED,
                blocked_reason="planner failed",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return task.id

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
            },
        )
        project_id = project_response.json()["id"]
        feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Dispatchable feature", "description": "Ready for task dispatch"},
        )
        feature_id = feature_response.json()["id"]
        task_id = asyncio.run(create_failed_task(feature_id))

        response = client.post(f"/api/tasks/{task_id}/dispatch")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "task_not_dispatchable"
    assert detail["status"] == "failed"
    assert detail["blocked_reason"] == "planner failed"


def test_embedded_server_recovers_failed_task(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_failed_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            task = Task(
                feature_id=feature_id,
                title="Recoverable task",
                description="Exercise embedded recover",
                status=TaskStatus.FAILED,
                blocked_reason="planner failed",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return task.id

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
            },
        )
        project_id = project_response.json()["id"]
        feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Recoverable feature", "description": "Ready for task recovery"},
        )
        feature_id = feature_response.json()["id"]
        task_id = asyncio.run(create_failed_task(feature_id))

        response = client.post(f"/api/tasks/{task_id}/recover")
        task_response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_id": task_id,
        "previous_status": "failed",
        "current_status": "pending",
        "next_step": f"builder backlog task dispatch {task_id} --yes --json",
    }
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "pending"
    assert task_response.json()["blocked_reason"] is None
