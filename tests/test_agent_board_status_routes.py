"""Agent board-status route regressions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    AgentRun,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_board_status_uses_dashboard_lane_counts_for_waiting_implementation_task(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Deterministic tests and build script",
            description="Shipping validation work.",
            status=FeatureStatus.DONE,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        db.add(
            Task(
                feature_id=feature.id,
                title="Verify Deterministic tests and build script for shipping",
                description="The active task the operator needs to understand.",
                status=TaskStatus.IMPLEMENTATION,
            )
        )
        await db.commit()

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, *args, **kwargs):
            return RunResult(
                session_id="sdk-board-status",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=16,
                num_turns=1,
                output_text=(
                    "Board status from Builder source of truth: "
                    "Queued 1, in progress 0, needs review 0, shipped 0, blocked 0. "
                    "Backlog features 1/1 done, 0 open. "
                    "`Verify Deterministic tests and build script for shipping` is `implementation`. "
                    "Next safe step: dispatch the first queued Board task."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": (
                    "What's the board status right now? Keep it short: done count, "
                    "blocked count, current task, and what I should do next. Don't change anything."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Board status from Builder source of truth"
            in item["payload"].get("content", ""),
        )

    content = assistant_item["payload"]["content"]
    assert "Queued 1, in progress 0, needs review 0, shipped 0, blocked 0" in content
    assert "Backlog features 1/1 done, 0 open" in content
    assert "`Verify Deterministic tests and build script for shipping` is `implementation`" in content
    assert "Next safe step: dispatch the first queued Board task" in content

@pytest.mark.asyncio
async def test_board_status_names_running_task_as_in_progress(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Deterministic tests and build script",
            description="Shipping validation work.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify Deterministic tests and build script for shipping",
            description="The running task the operator needs to understand.",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add(task)
        await db.flush()
        db.add(
            AgentRun(
                task_id=task.id,
                agent_name="code-gen",
                runtime_sdk="claude",
                status="running",
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, *args, **kwargs):
            return RunResult(
                session_id="sdk-board-running-status",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=16,
                num_turns=1,
                output_text=(
                    "Board status from Builder source of truth: "
                    "Queued 0, in progress 1, needs review 0, shipped 0, blocked 0. "
                    "Next safe step: inspect the active task's run trace."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "what is teh status of the board"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Board status from Builder source of truth"
            in item["payload"].get("content", ""),
        )

    content = assistant_item["payload"]["content"]
    assert "Queued 0, in progress 1, needs review 0, shipped 0, blocked 0" in content
    assert "Next safe step: inspect the active task's run trace" in content

@pytest.mark.asyncio
async def test_board_status_defaults_to_current_sprint_scope(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        older_feature = Feature(
            project_id=project.id,
            title="Deterministic tests and build script",
            description="Older sprint recovery work.",
            status=FeatureStatus.DONE,
            item_type=BacklogItemType.FEATURE,
        )
        current_feature = Feature(
            project_id=project.id,
            title="In-app task completion notifications",
            description="Current sprint shipped feature.",
            status=FeatureStatus.DONE,
            item_type=BacklogItemType.FEATURE,
        )
        db.add_all([older_feature, current_feature])
        await db.flush()
        older_task = Task(
            feature_id=older_feature.id,
            title="Verify Deterministic tests and build script for shipping",
            description="Older sprint verification task.",
            status=TaskStatus.IMPLEMENTATION,
        )
        current_task = Task(
            feature_id=current_feature.id,
            title="Verify In-app task completion notifications for shipping",
            description="Current sprint shipped task.",
            status=TaskStatus.DONE,
        )
        db.add_all([older_task, current_task])
        await db.flush()
        db.add_all(
            [
                Sprint(
                    project_id=project.id,
                    label="Sprint 1",
                    phase="implementation",
                    approved_feature_ids=[older_feature.id],
                    generated_task_ids=[older_task.id],
                    created_at=datetime(2026, 5, 12, tzinfo=UTC),
                ),
                Sprint(
                    project_id=project.id,
                    label="Sprint 2",
                    phase="shipped",
                    verification_status="shipped",
                    approved_feature_ids=[current_feature.id],
                    generated_task_ids=[current_task.id],
                    created_at=datetime(2026, 5, 13, tzinfo=UTC),
                ),
            ]
        )
        await db.commit()

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, *args, **kwargs):
            return RunResult(
                session_id="sdk-current-sprint-status",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=16,
                num_turns=1,
                output_text=(
                    "Current sprint Board status from Builder source of truth (`Sprint 2`): "
                    "Queued 0, in progress 0, needs review 0, shipped 1, blocked 0. "
                    "Current sprint `Sprint 2` is shipped."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "what is the status of the board?"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Board status from Builder source of truth"
            in item["payload"].get("content", ""),
        )

    content = assistant_item["payload"]["content"]
    assert "Current sprint Board status from Builder source of truth (`Sprint 2`):" in content
    assert "Queued 0, in progress 0, needs review 0, shipped 1, blocked 0" in content
    assert "Current sprint `Sprint 2` is shipped." in content
    assert "Verify Deterministic tests and build script for shipping" not in content
    assert "dispatch the first queued Board task" not in content
