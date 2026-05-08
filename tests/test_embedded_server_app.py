from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Feature,
    FeatureStatus,
    GateResult,
    GateStatus,
    Project,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server.app import create_app


def test_embedded_server_exposes_health(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_embedded_server_serves_dashboard_shell_without_cache(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html>builder</html>", encoding="utf-8")
    assets_dir = dashboard_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('builder');", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    client = TestClient(app)

    shell_response = client.get("/observability")
    asset_response = client.get("/assets/app.js")

    assert shell_response.status_code == 200
    assert shell_response.headers["cache-control"] == "no-store, max-age=0"
    assert shell_response.headers["pragma"] == "no-cache"
    assert asset_response.status_code == 200
    assert asset_response.headers["cache-control"] == "no-store, max-age=0"
    assert asset_response.headers["pragma"] == "no-cache"


def test_embedded_server_exposes_project_scoped_feature_routes(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path.parent / f"{tmp_path.name}-dashboard"
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


def test_embedded_server_exposes_typed_backlog_item_routes(tmp_path: Path) -> None:
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
            json={"name": "Builder", "description": "Repo-local builder project"},
        )
        project_id = project_response.json()["id"]

        response = client.post(
            f"/api/projects/{project_id}/backlog/items",
            json={
                "type": "incident",
                "title": "Quality gate environment mismatch",
                "severity": "high",
                "source": "validation",
                "tags": ["quality-gates"],
                "evidence": "Product pytest path imported installed package.",
            },
        )

        assert response.status_code == 201
        item = response.json()
        assert item["item_type"] == "incident"
        assert item["tags"] == ["quality-gates"]
        assert (tmp_path / ".claude" / "progress" / "incident-list.json").exists()

        list_response = client.get(
            f"/api/projects/{project_id}/backlog/items",
            params={"type": "incident", "tag": "quality-gates"},
        )
        assert list_response.status_code == 200
        assert [row["id"] for row in list_response.json()] == [item["id"]]

        update_response = client.put(
            f"/api/backlog/items/{item['id']}",
            json={"tags": ["verification"], "evidence": "Updated evidence."},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["tags"] == ["verification"]
        assert updated["evidence"] == "Updated evidence."

        invalid_response = client.put(
            f"/api/backlog/items/{item['id']}",
            json={"tags": ["verification", "dashboard"]},
        )
        assert invalid_response.status_code == 422


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
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
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


def test_embedded_server_serializes_gate_results(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def seed_gate_result() -> str:
        factory = get_session_factory()
        async with factory() as db:
            project = Project(name="Gate project", description="Gate route", language="python")
            db.add(project)
            await db.flush()
            feature = Feature(project_id=project.id, title="Gate feature", status=FeatureStatus.QUEUED)
            db.add(feature)
            await db.flush()
            task = Task(feature_id=feature.id, title="Gate task")
            db.add(task)
            await db.flush()
            db.add(
                GateResult(
                    task_id=task.id,
                    gate_name="testing",
                    status=GateStatus.WARN,
                    evidence={"summary": "No supported test runner found."},
                    findings_count=0,
                    elapsed_ms=12,
                    error_code="UNSUPPORTED_LANGUAGE",
                )
            )
            await db.commit()
            return task.id

    with TestClient(app) as client:
        task_id = asyncio.run(seed_gate_result())
        response = client.get(f"/api/tasks/{task_id}/gates")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["task_id"] == task_id
    assert payload[0]["gate_name"] == "testing"
    assert payload[0]["status"] == "warn"
    assert payload[0]["evidence"] == {"summary": "No supported test runner found."}
    assert payload[0]["summary"] == "No supported test runner found."


def test_embedded_server_hydrates_forward_engineering_feature_list_into_db(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True, exist_ok=True)
    (agent_builder_dir / "onboarding-state.json").write_text(
        json.dumps(
            {
                "repo": {"root": str(tmp_path), "name": tmp_path.name},
                "onboarding_mode": "forward_engineering",
                "current_phase": "ready",
                "ready": True,
                "updated_at": "2026-04-28T00:00:00+00:00",
                "phases": [],
                "entity_counts": {"projects": 1, "features": 3, "tasks": 6},
                "kb_status": {},
                "scan_summary": {},
                "archives": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    progress_dir = tmp_path / ".claude" / "progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    (progress_dir / "feature-list.json").write_text(
        json.dumps(
            {
                "metadata": {"project": tmp_path.name, "done": 0, "pending": 2},
                "features": [
                    {
                        "id": "feature-01",
                        "title": "Interview-backed feature one",
                        "description": "First generated backlog item.",
                        "status": "pending",
                        "priority": "100",
                        "acceptance_criteria": ["One"],
                        "dependencies": [],
                    },
                    {
                        "id": "feature-02",
                        "title": "Interview-backed feature two",
                        "description": "Second generated backlog item.",
                        "status": "pending",
                        "priority": "90",
                        "acceptance_criteria": ["Two"],
                        "dependencies": ["feature-01"],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def seed_forward_engineering_rows() -> str:
        factory = get_session_factory()
        async with factory() as db:
            project = Project(
                name=tmp_path.name,
                description="forward engineering demo",
                repo_url=str(tmp_path),
                language="python",
            )
            db.add(project)
            await db.flush()
            seed_feature = Feature(
                project_id=project.id,
                title="Define product intent and first user journey",
                description="seed",
                priority=100,
            )
            db.add(seed_feature)
            await db.flush()
            db.add(
                Task(
                    feature_id=seed_feature.id,
                    title="Capture product goal and success criteria",
                    description="seed task",
                )
            )
            await db.commit()
            return project.id

    with TestClient(app) as client:
        project_id = asyncio.run(seed_forward_engineering_rows())
        features_response = client.get("/api/dashboard/features")
        assert features_response.status_code == 200
        features_payload = features_response.json()

        backlog_response = client.get(f"/api/projects/{project_id}/backlog/items")
        assert backlog_response.status_code == 200
        backlog_payload = backlog_response.json()

        board_response = client.get("/api/dashboard/board")
        assert board_response.status_code == 200

    titles = [item["title"] for item in features_payload["features"]]
    assert titles == ["Interview-backed feature one", "Interview-backed feature two"]
    assert features_payload["total"] == 2
    assert [item["id"] for item in backlog_payload] == ["feature-01", "feature-02"]
    assert all(item["status"] == "backlog" for item in backlog_payload)
    assert board_response.json() == {
        "pending": [],
        "active": [],
        "review": [],
        "done": [],
        "blocked": [],
        "sprints": [],
        "current_sprint": None,
        "sprint_plan": None,
    }

    async def read_db_state() -> tuple[list[str], int]:
        factory = get_session_factory()
        async with factory() as db:
            feature_titles = [
                feature.title
                for feature in (await db.execute(select(Feature).order_by(Feature.priority.desc()))).scalars().all()
            ]
            task_count = len((await db.execute(select(Task))).scalars().all())
            return feature_titles, task_count

    feature_titles, task_count = asyncio.run(read_db_state())
    assert feature_titles == ["Interview-backed feature one", "Interview-backed feature two"]
    assert task_count == 0


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
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
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


def test_embedded_server_approval_auto_dispatches_next_phase(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    def fake_add_task(self, func, *args, **kwargs):
        dispatched.append(args[0])

    monkeypatch.setattr("fastapi.BackgroundTasks.add_task", fake_add_task)
    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.tasks._reserve_dispatch",
        lambda task_id: True,
    )

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def seed_approval_gate(feature_id: str) -> tuple[str, str]:
        factory = get_session_factory()
        async with factory() as db:
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
            task = Task(
                feature_id=feature_id,
                title="Reviewable task",
                description="Exercise approval dispatch",
                status=TaskStatus.REVIEW_PENDING,
                phase=TaskPhase.INTEGRATION,
            )
            db.add(task)
            await db.flush()
            gate = ApprovalGate(task_id=task.id, gate_type="pr", status="pending")
            db.add(gate)
            await db.commit()
            return task.id, gate.id

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects/",
            json={
                "name": "Builder",
                "description": "Repo-local builder project",
                "language": "python",
            },
        )
        project_id = project_response.json()["id"]
        feature_response = client.post(
            f"/api/projects/{project_id}/features",
            json={"title": "Reviewable feature", "description": "Ready for approval"},
        )
        task_id, gate_id = asyncio.run(seed_approval_gate(feature_response.json()["id"]))

        response = client.post(
            f"/api/approval-gates/{gate_id}/approve",
            json={"approver_email": "operator@example.com", "decision": "approve"},
        )

    assert response.status_code == 200
    assert response.json()["gate_status"] == "approve"
    assert dispatched == [task_id]

    async def read_task_status() -> TaskStatus:
        factory = get_session_factory()
        async with factory() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            return task.status

    assert asyncio.run(read_task_status()) == TaskStatus.BUILD_VERIFY


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
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
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
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
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


def test_embedded_server_recovers_capability_limit_task(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_capability_limit_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
            task = Task(
                feature_id=feature_id,
                title="Recoverable capability task",
                description="Exercise embedded recover from provider quota",
                status=TaskStatus.CAPABILITY_LIMIT,
                phase=TaskPhase.IMPLEMENTATION,
                blocked_reason="Quality gate failures:\n\n- implementation_delta: fail",
                capability_limit_reason="SDK limit: provider_limit",
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
        task_id = asyncio.run(create_capability_limit_task(feature_id))

        response = client.post(f"/api/tasks/{task_id}/recover")
        task_response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_id": task_id,
        "previous_status": "capability_limit",
        "current_status": "implementation",
        "next_step": f"builder backlog task dispatch {task_id} --yes --json",
    }
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "implementation"
    assert task_response.json()["blocked_reason"] is None
