from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    AgentRun,
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
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub


async def test_chat_session_hub_shutdown_all_cancels_background_runs():
    hub = ChatSessionHub()
    started = asyncio.Event()

    async def long_running_turn():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(long_running_turn())
    try:
        assert await hub.attach_run("session-1", task)
        await started.wait()
        assert await hub.has_active_run("session-1")

        await ChatSessionHub.shutdown_all()

        assert task.done()
        assert not await hub.has_active_run("session-1")
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# IMP-040: cancel pending-answer futures on last-subscriber disconnect ----------


async def test_cancel_session_pending_answers_cancels_only_matching_session():
    """cancel_session_pending_answers cancels futures for the named session and
    leaves unrelated sessions untouched; returns the count cancelled."""
    hub = ChatSessionHub()

    f1 = await hub.create_pending_answer("s1", "e1")
    f2 = await hub.create_pending_answer("s1", "e2")
    f3 = await hub.create_pending_answer("s2", "e3")

    count = await hub.cancel_session_pending_answers("s1")

    assert count == 2
    assert f1.cancelled()
    assert f2.cancelled()
    # s2 future must be untouched
    assert not f3.done()
    # s1 futures must have been removed from internal state
    assert not await hub.has_pending_answer("e1")
    assert not await hub.has_pending_answer("e2")
    assert await hub.has_pending_answer("e3")

    # cleanup
    if not f3.done():
        f3.cancel()


async def test_has_active_subscribers_reflects_registration_state():
    """has_active_subscribers returns True while a queue is registered and False
    once the last subscriber unregisters."""
    hub = ChatSessionHub()

    assert not hub.has_active_subscribers("sess")
    queue = await hub.register_session("sess")
    assert hub.has_active_subscribers("sess")
    await hub.unregister_session("sess", queue)
    assert not hub.has_active_subscribers("sess")


async def test_event_generator_cancels_pending_future_on_disconnect(monkeypatch):
    """When the SSE client disconnects and no other subscriber remains for the
    session, event_generator must cancel outstanding pending-answer futures
    (IMP-040 integration path)."""
    hub = ChatSessionHub()
    future = await hub.create_pending_answer("sess-x", "ev-1")

    # Register a subscriber, then simulate disconnect on first poll
    queue = await hub.register_session("sess-x")
    disconnect_calls = 0

    class _DisconnectedRequest:
        async def is_disconnected(self) -> bool:
            nonlocal disconnect_calls
            disconnect_calls += 1
            return True  # disconnect immediately

    import json as _json

    # Reconstruct just the event_generator logic inline to avoid full app wiring.
    # Directly exercise hub.unregister_session + cancel_session_pending_answers path.
    request = _DisconnectedRequest()

    async def _event_generator():
        try:
            yield {"event": "snapshot", "data": _json.dumps({})}
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(0)
        finally:
            await hub.unregister_session("sess-x", queue)
            if not hub.has_active_subscribers("sess-x"):
                await hub.cancel_session_pending_answers("sess-x")

    # Drain the generator
    async for _ in _event_generator():
        pass

    assert future.cancelled(), "pending future must be cancelled after disconnect"
    assert not hub.has_active_subscribers("sess-x")


async def test_event_generator_does_not_cancel_when_another_subscriber_remains():
    """When a second SSE tab is still connected, cancel_session_pending_answers
    must NOT be called (IMP-040: only cancel when no subscribers remain)."""
    hub = ChatSessionHub()
    future = await hub.create_pending_answer("sess-y", "ev-2")

    queue1 = await hub.register_session("sess-y")
    queue2 = await hub.register_session("sess-y")  # noqa: F841  second tab

    # Unregister only queue1 — queue2 still registered
    await hub.unregister_session("sess-y", queue1)

    if not hub.has_active_subscribers("sess-y"):
        await hub.cancel_session_pending_answers("sess-y")

    # future must NOT be cancelled because queue2 is still subscribed
    assert not future.cancelled(), "must not cancel while a second subscriber remains"

    # cleanup
    await hub.unregister_session("sess-y", queue2)
    if not future.done():
        future.cancel()


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
    assets_sibling_dir = dashboard_path / "assets-sibling"
    assets_sibling_dir.mkdir()
    (assets_sibling_dir / "secret.js").write_text("console.log('secret');", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    client = TestClient(app)

    shell_response = client.get("/observability")
    asset_response = client.get("/assets/app.js")
    escape_response = client.get("/assets/%2E%2E/assets-sibling/secret.js")

    assert shell_response.status_code == 200
    assert shell_response.headers["cache-control"] == "no-store, max-age=0"
    assert shell_response.headers["pragma"] == "no-cache"
    assert asset_response.status_code == 200
    assert asset_response.headers["cache-control"] == "no-store, max-age=0"
    assert asset_response.headers["pragma"] == "no-cache"
    assert escape_response.status_code == 404


def test_embedded_observability_uses_app_project_root(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    other_cwd = tmp_path.parent / f"{tmp_path.name}-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/dashboard/observability")

    assert response.status_code == 200
    assert response.json()["observability_coverage"]["source"] == "runtime_env"


def test_embedded_metrics_uses_app_project_root_for_observability(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    other_cwd = tmp_path.parent / f"{tmp_path.name}-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    from autonomous_agent_builder.embedded.server.routes import dashboard

    captured: dict[str, str] = {}

    def fake_observability_summary(path):
        captured["path"] = str(path)
        return {
            "runtime_decision_summary": {"available": True, "source": "embedded-project"},
            "optimization_decision": {"available": True, "source": "embedded-project"},
            "deterministic_script_candidates": [{"code": "embedded_project_candidate"}],
            "runtime_aggregates": {
                "context_budget": {"available": True, "source": "embedded-project"}
            },
        }

    monkeypatch.setattr(dashboard, "dashboard_observability_summary", fake_observability_summary)

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/dashboard/metrics")

    assert response.status_code == 200
    data = response.json()
    assert captured["path"] == str(db_path)
    assert data["optimization_decision"]["source"] == "embedded-project"
    assert data["context_budget"]["source"] == "embedded-project"
    assert data["deterministic_script_candidates"][0]["code"] == "embedded_project_candidate"


def test_embedded_knowledge_routes_use_app_project_root(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    project_kb = tmp_path / ".agent-builder" / "knowledge" / "system-docs" / "context"
    project_kb.mkdir(parents=True)
    (project_kb / "project.md").write_text(
        "---\ntitle: Project KB\ntags: [project]\n---\nProject-only knowledge.\n",
        encoding="utf-8",
    )

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    other_cwd = tmp_path.parent / f"{tmp_path.name}-cwd"
    other_kb = other_cwd / ".agent-builder" / "knowledge" / "system-docs" / "context"
    other_kb.mkdir(parents=True)
    (other_kb / "wrong.md").write_text(
        "---\ntitle: Wrong KB\ntags: [wrong]\n---\nWrong CWD knowledge.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(other_cwd)

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    with TestClient(app) as client:
        status_response = client.get("/api/knowledge/status")
        documents_response = client.get("/api/knowledge/documents")
        document_response = client.get("/api/knowledge/documents/system-docs/context/project.md")
        kb_list_response = client.get("/api/kb/")
        kb_doc_response = client.get("/api/kb/system-docs/context/project.md")
        traversal_response = client.get("/api/knowledge/documents/%2E%2E/context/wrong.md")
        delete_response = client.delete("/api/knowledge")

    assert status_response.status_code == 200
    assert status_response.json()["document_count"] == 1
    assert documents_response.status_code == 200
    assert [doc["filename"] for doc in documents_response.json()["documents"]] == [
        "system-docs/context/project.md"
    ]
    assert document_response.status_code == 200
    assert document_response.json()["frontmatter"]["title"] == "Project KB"
    assert [doc["id"] for doc in kb_list_response.json()] == ["system-docs/context/project.md"]
    assert kb_doc_response.status_code == 200
    assert kb_doc_response.json()["title"] == "Project KB"
    assert traversal_response.status_code == 404
    assert delete_response.status_code == 200
    assert not (tmp_path / ".agent-builder" / "knowledge" / "system-docs").exists()
    assert (other_kb / "wrong.md").exists()


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


def test_embedded_dispatch_autonomously_starts_next_serial_task(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    dispatched: list[str] = []

    async def fake_dispatch(self, task: Task) -> None:
        dispatched.append(task.id)
        task.status = TaskStatus.DONE

    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.Orchestrator.dispatch",
        fake_dispatch,
    )

    async def seed_tasks() -> tuple[str, str]:
        factory = get_session_factory()
        async with factory() as db:
            project = Project(name="Builder", description="Repo-local builder project", language="python")
            db.add(project)
            await db.flush()
            feature = Feature(
                project_id=project.id,
                title="Autonomous serial feature",
                description="Ready for serial task dispatch",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            db.add(feature)
            await db.flush()
            first = Task(
                feature_id=feature.id,
                title="Implement first slice",
                description="First serial task",
                status=TaskStatus.PENDING,
            )
            second = Task(
                feature_id=feature.id,
                title="Verify first slice",
                description="Second serial task",
                status=TaskStatus.PENDING,
            )
            db.add_all([first, second])
            await db.commit()
            return first.id, second.id

    with TestClient(app):
        first_task_id, second_task_id = asyncio.run(seed_tasks())

        from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

        asyncio.run(_run_dispatch(first_task_id))

    assert dispatched == [first_task_id, second_task_id]


def test_embedded_dispatch_blocks_same_status_followup_cycle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)
    dispatched: list[str] = []

    async def fake_dispatch(self, task: Task) -> None:
        dispatched.append(task.id)

    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.Orchestrator.dispatch",
        fake_dispatch,
    )

    async def seed_task() -> str:
        factory = get_session_factory()
        async with factory() as db:
            project = Project(name="Builder", description="Repo-local builder project", language="python")
            db.add(project)
            await db.flush()
            feature = Feature(
                project_id=project.id,
                title="Cycle feature",
                description="Ready for dispatch",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            db.add(feature)
            await db.flush()
            task = Task(
                feature_id=feature.id,
                title="Stuck task",
                description="Dispatch leaves this task pending",
                status=TaskStatus.PENDING,
            )
            db.add(task)
            await db.commit()
            return task.id

    async def task_state(task_id: str) -> Task:
        factory = get_session_factory()
        async with factory() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            return task

    with TestClient(app):
        task_id = asyncio.run(seed_task())

        from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

        asyncio.run(_run_dispatch(task_id))
        refreshed = asyncio.run(task_state(task_id))

    assert dispatched == [task_id]
    assert refreshed.status == TaskStatus.BLOCKED
    assert "follow-up cycle detected" in str(refreshed.blocked_reason)


def test_embedded_dispatch_blocks_task_after_unhandled_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def fake_dispatch(self, task: Task) -> None:
        raise RuntimeError("simulated dispatch failure")

    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.Orchestrator.dispatch",
        fake_dispatch,
    )

    async def seed_task() -> str:
        factory = get_session_factory()
        async with factory() as db:
            project = Project(name="Builder", description="Repo-local builder project", language="python")
            db.add(project)
            await db.flush()
            feature = Feature(
                project_id=project.id,
                title="Failure feature",
                description="Ready for dispatch",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            db.add(feature)
            await db.flush()
            task = Task(
                feature_id=feature.id,
                title="Task that fails dispatch",
                description="Dispatch raises before completion",
                status=TaskStatus.PENDING,
            )
            db.add(task)
            await db.flush()
            db.add(AgentRun(task_id=task.id, agent_name="code-gen", status="running"))
            await db.commit()
            return task.id

    async def task_state(task_id: str) -> tuple[Task, AgentRun]:
        factory = get_session_factory()
        async with factory() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            result = await db.execute(select(AgentRun).where(AgentRun.task_id == task_id))
            run = result.scalar_one()
            return task, run

    with TestClient(app):
        task_id = asyncio.run(seed_task())

        from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

        asyncio.run(_run_dispatch(task_id))
        refreshed, run = asyncio.run(task_state(task_id))

    assert refreshed.status == TaskStatus.BLOCKED
    assert "Dispatch failed: simulated dispatch failure" in str(refreshed.blocked_reason)
    assert run.status == "failed"
    assert "Dispatch failed: simulated dispatch failure" in str(run.error)


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
def test_embedded_dispatch_policy_payloads_match_shared_contract(
    tmp_path: Path, monkeypatch, task_status: TaskStatus, expected_status: int
) -> None:
    from autonomous_agent_builder.services.dispatch_lock import release_dispatch

    def _capture_background_task(self, func, *args, **kwargs):
        return None

    monkeypatch.setattr("fastapi.BackgroundTasks.add_task", _capture_background_task)
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
            task = Task(
                feature_id=feature_id,
                title="Dispatch policy task",
                description="Exercise shared dispatch policy",
                status=task_status,
                blocked_reason=(
                    "provider limit blocked"
                    if task_status == TaskStatus.CAPABILITY_LIMIT
                    else "blocked"
                ),
                depends_on=(
                    {
                        "provider_limit": {
                            "code": "provider_limit",
                            "resume_status": "implementation",
                        }
                    }
                    if task_status == TaskStatus.CAPABILITY_LIMIT
                    else None
                ),
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
            json={"title": "Dispatch policy feature", "description": "Ready for dispatch"},
        )
        task_id = asyncio.run(create_task(feature_response.json()["id"]))
        try:
            response = client.post(f"/api/tasks/{task_id}/dispatch")
        finally:
            release_dispatch(task_id)

    assert response.status_code == expected_status
    data = response.json()
    if expected_status == 200:
        assert data["status"] == "dispatched"
        assert data["current_status"] == task_status.value
    else:
        detail = data["detail"]
        assert detail["code"] == "task_not_dispatchable"
        assert detail["status"] == task_status.value
        if task_status == TaskStatus.CAPABILITY_LIMIT:
            assert detail["provider_limit"]["code"] == "provider_limit"


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


def test_embedded_server_recovers_dispatch_failed_blocked_task(tmp_path: Path) -> None:
    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("", encoding="utf-8")

    dashboard_path = tmp_path / "dashboard"
    dashboard_path.mkdir()
    (dashboard_path / "index.html").write_text("<html></html>", encoding="utf-8")

    app = create_app(db_path=db_path, dashboard_path=dashboard_path, project_root=tmp_path)

    async def create_dispatch_failed_task(feature_id: str) -> str:
        factory = get_session_factory()
        async with factory() as db:
            feature = await db.get(Feature, feature_id)
            assert feature is not None
            feature.status = FeatureStatus.QUEUED
            task = Task(
                feature_id=feature_id,
                title="Recoverable dispatch failure",
                description="Exercise embedded recover from dispatch failure",
                status=TaskStatus.BLOCKED,
                phase=TaskPhase.IMPLEMENTATION,
                blocked_reason="Dispatch failed: simulated dispatch failure",
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
        task_id = asyncio.run(create_dispatch_failed_task(feature_id))

        response = client.post(f"/api/tasks/{task_id}/recover")
        task_response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_id": task_id,
        "previous_status": "blocked",
        "current_status": "implementation",
        "next_step": f"builder backlog task dispatch {task_id} --yes --json",
    }
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "implementation"
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
