"""Tests for dashboard API — board/metrics/approval JSON shapes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_DESIGN_DOC_TYPE,
    SPRINT_PLAN_DOC_TYPE,
)

_BOARD_LANES = ("pending", "active", "review", "done", "blocked")


def test_generated_sprint_tasks_use_live_task_statuses() -> None:
    from autonomous_agent_builder.embedded.server.routes.dashboard import (
        _generated_sprint_tasks_from_plan,
    )

    items = _generated_sprint_tasks_from_plan(
        ["task-active"],
        {"task_specs": [{"title": "Verify shipped feature"}]},
        task_statuses={"task-active": "implementation"},
    )

    assert items[0].status == "implementation"


def test_dashboard_sprint_phase_statuses_do_not_skip_review_or_build() -> None:
    from autonomous_agent_builder.api.routes import dashboard_api
    from autonomous_agent_builder.embedded.server.routes import dashboard as embedded_dashboard

    for module in (dashboard_api, embedded_dashboard):
        assert module._phase_statuses("verify") == {
            "plan": "complete",
            "design": "complete",
            "implementation": "complete",
            "verify": "active",
            "pr_review": "pending",
            "build": "pending",
            "shipped": "pending",
        }
        assert module._phase_statuses("pr_review")["pr_review"] == "active"
        assert module._phase_statuses("build")["build"] == "active"
        shipped = module._phase_statuses("shipped")
        assert shipped["pr_review"] == "complete"
        assert shipped["build"] == "complete"
        assert shipped["shipped"] == "active"


@pytest.mark.asyncio
class TestBoardEndpoint:
    """Test /api/dashboard/board response shape."""

    async def test_board_empty(self, client, test_db):
        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert "active" in data
        assert "review" in data
        assert "done" in data
        assert "blocked" in data
        assert all(isinstance(data[key], list) for key in _BOARD_LANES)
        assert data["sprint_plan"] is None
        assert data["current_sprint"] is None

    async def test_board_pending_task(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "board-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Board feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Board task"},
        )
        resp = await client.get("/api/dashboard/board")
        data = resp.json()
        assert len(data["pending"]) == 1
        task_item = data["pending"][0]
        assert task_item["title"] == "Board task"
        assert task_item["status"] == "pending"
        assert task_item["feature_id"] == feat.json()["id"]
        assert "feature_title" in task_item
        assert "feature_priority" in task_item
        assert "feature_item_type" in task_item
        assert "cost_usd" in task_item
        assert "total_cost" in task_item

    async def test_board_stream_publish_refreshes_stale_session_state(self, test_db, monkeypatch):
        _, factory = test_db
        from autonomous_agent_builder.api.routes import dashboard_api
        from autonomous_agent_builder.db.models import (
            AgentRun,
            Feature,
            FeatureStatus,
            Project,
            Task,
            TaskPhase,
            TaskStatus,
        )

        published: list[dict] = []

        class FakeDashboardStreamHub:
            async def publish_board(self, payload: dict) -> None:
                published.append(payload)

        monkeypatch.setattr(
            dashboard_api,
            "get_dashboard_stream_hub",
            lambda: FakeDashboardStreamHub(),
        )

        async with factory() as stale_session:
            project = Project(name="stream-refresh", language="typescript")
            stale_session.add(project)
            await stale_session.flush()
            feature = Feature(
                project_id=project.id,
                title="Live board feature",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            stale_session.add(feature)
            await stale_session.flush()
            task = Task(
                feature_id=feature.id,
                title="Run live board task",
                status=TaskStatus.QUEUED,
                phase=TaskPhase.PLANNING,
            )
            stale_session.add(task)
            await stale_session.commit()

            stale_task = await stale_session.get(Task, task.id)
            assert stale_task is not None
            assert stale_task.status == TaskStatus.QUEUED

            async with factory() as update_session:
                fresh_task = await update_session.get(Task, task.id)
                assert fresh_task is not None
                fresh_task.status = TaskStatus.IMPLEMENTATION
                fresh_task.phase = TaskPhase.IMPLEMENTATION
                update_session.add(
                    AgentRun(task_id=task.id, agent_name="code-gen", status="running")
                )
                await update_session.commit()

            assert stale_task.status == TaskStatus.QUEUED

            await dashboard_api.publish_board_snapshot(stale_session)

        assert published
        assert [item["id"] for item in published[0]["active"]] == [task.id]
        assert published[0]["active"][0]["latest_run_status"] == "running"
        assert task.id not in {item["id"] for item in published[0]["pending"]}

    async def test_board_stream_publish_does_not_expire_live_task_relationships(
        self, test_db, monkeypatch
    ):
        _, factory = test_db
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from autonomous_agent_builder.api.routes import dashboard_api
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Task,
            TaskPhase,
            TaskStatus,
            Workspace,
        )

        published: list[dict] = []

        class FakeDashboardStreamHub:
            async def publish_board(self, payload: dict) -> None:
                published.append(payload)

        monkeypatch.setattr(
            dashboard_api,
            "get_dashboard_stream_hub",
            lambda: FakeDashboardStreamHub(),
        )

        async with factory() as session:
            project = Project(name="stream-live-task", language="typescript")
            session.add(project)
            await session.flush()
            feature = Feature(
                project_id=project.id,
                title="Live task feature",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            session.add(feature)
            await session.flush()
            task = Task(
                feature_id=feature.id,
                title="Live task",
                status=TaskStatus.IMPLEMENTATION,
                phase=TaskPhase.IMPLEMENTATION,
            )
            session.add(task)
            await session.flush()
            session.add(Workspace(task_id=task.id, path="/tmp/live-task", branch="task-branch"))
            await session.commit()

            result = await session.execute(
                select(Task)
                .where(Task.id == task.id)
                .options(selectinload(Task.workspace))
                .execution_options(populate_existing=True)
            )
            live_task = result.scalar_one()
            assert live_task.workspace is not None
            assert live_task.workspace.branch == "task-branch"

            await dashboard_api.publish_board_snapshot(session)

            assert published
            assert live_task.workspace is not None
            assert live_task.workspace.branch == "task-branch"

    async def test_board_prefers_current_planned_delivery_over_seeded_completed_project(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Task,
            TaskStatus,
        )

        async with factory() as session:
            old_project = Project(name="seeded-todos", language="typescript")
            current_project = Project(name="current-todos", language="typescript")
            session.add_all([old_project, current_project])
            await session.flush()
            session.add_all(
                [
                    Feature(
                        id="feature-01",
                        project_id=old_project.id,
                        title="Todo Creation And Editing",
                        status=FeatureStatus.DONE,
                    ),
                    Feature(
                        id="feature-03",
                        project_id=old_project.id,
                        title="Today List View",
                        status=FeatureStatus.BACKLOG,
                    ),
                ]
            )
            current_feature = Feature(
                project_id=current_project.id,
                title="Todo filters and counts",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            session.add(current_feature)
            await session.flush()
            session.add(
                Task(
                    feature_id=current_feature.id,
                    title="Implement core app behavior for Todo filters and counts",
                    status=TaskStatus.PENDING,
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        assert [task["title"] for task in data["pending"]] == [
            "Implement core app behavior for Todo filters and counts"
        ]
        assert data["done"] == []

    async def test_board_prefers_project_with_latest_sprint_activity(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Sprint,
            SprintPhase,
        )

        async with factory() as session:
            setup_project = Project(name="setup-project", language="typescript")
            sprint_project = Project(name="sprint-project", language="typescript")
            session.add_all([setup_project, sprint_project])
            await session.flush()
            session.add(
                Feature(
                    project_id=setup_project.id,
                    title="Setup planning",
                    status=FeatureStatus.PLANNING,
                    priority=100,
                )
            )
            shipped = Feature(
                id="feature-04",
                project_id=sprint_project.id,
                title="Completion Workflow",
                status=FeatureStatus.DONE,
                priority=70,
            )
            session.add(shipped)
            await session.flush()
            session.add(
                Sprint(
                    project_id=sprint_project.id,
                    label="Sprint 4",
                    phase=SprintPhase.SHIPPED,
                    approved_feature_ids=[shipped.id],
                    created_at=datetime(2026, 5, 5, tzinfo=UTC),
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_sprint"]["label"] == "Sprint 4"

    async def test_board_accepts_queued_task_and_sprint_state(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Sprint,
            SprintPhase,
            Task,
            TaskPhase,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="queued-sprint", language="typescript")
            session.add(project)
            await session.flush()
            feature = Feature(
                project_id=project.id,
                title="Local Browser Persistence",
                status=FeatureStatus.SPRINT_PLANNED,
                priority=90,
            )
            session.add(feature)
            await session.flush()
            task = Task(
                feature_id=feature.id,
                title="Wire browser storage hydration and saves",
                status=TaskStatus.QUEUED,
                phase=TaskPhase.IMPLEMENTATION,
            )
            session.add(task)
            await session.flush()
            session.add(
                Sprint(
                    project_id=project.id,
                    label="Sprint 2",
                    phase=SprintPhase.QUEUED,
                    approved_feature_ids=[feature.id],
                    generated_task_ids=[task.id],
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"][0]["status"] == "queued"
        assert data["current_sprint"]["label"] == "Sprint 2"
        assert data["current_sprint"]["active_phase"] == "implementation"
        assert data["current_sprint"]["phase_statuses"]["implementation"] == "active"
        assert data["current_sprint"]["generated_tasks"]

    async def test_board_current_sprint_shows_build_after_review(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            GateResult,
            GateStatus,
            Project,
            Sprint,
            SprintPhase,
            Task,
            TaskPhase,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="build-phase-sprint", language="typescript")
            session.add(project)
            await session.flush()
            feature = Feature(
                project_id=project.id,
                title="Search todos",
                status=FeatureStatus.SPRINT_PLANNED,
                priority=90,
            )
            session.add(feature)
            await session.flush()
            task = Task(
                feature_id=feature.id,
                title="Verify search build",
                status=TaskStatus.BUILD_VERIFY,
                phase=TaskPhase.INTEGRATION,
            )
            session.add(task)
            await session.flush()
            session.add(
                GateResult(
                    task_id=task.id,
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    evidence={"summary": "pytest passed"},
                    elapsed_ms=1200,
                )
            )
            session.add(
                Sprint(
                    project_id=project.id,
                    label="Sprint 3",
                    phase=SprintPhase.VERIFY,
                    approved_feature_ids=[feature.id],
                    generated_task_ids=[task.id],
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        sprint = data["current_sprint"]
        assert sprint["active_phase"] == "build"
        assert sprint["phase_statuses"]["verify"] == "complete"
        assert sprint["phase_statuses"]["pr_review"] == "complete"
        assert sprint["phase_statuses"]["build"] == "active"
        assert sprint["phase_statuses"]["shipped"] == "pending"
        task_item = next(
            item
            for lane in ("pending", "active", "review", "done", "blocked")
            for item in data[lane]
            if item["title"] == "Verify search build"
        )
        assert task_item["gate_results"][0]["gate_name"] == "testing"
        assert task_item["gate_results"][0]["status"] == "pass"

    async def test_board_feature_slices_keep_parent_sprint_identity(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Sprint,
            SprintPhase,
            Task,
            TaskPhase,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="multi-feature-sprint", language="typescript")
            session.add(project)
            await session.flush()
            feature_one = Feature(
                project_id=project.id,
                title="First feature",
                status=FeatureStatus.SPRINT_PLANNED,
                priority=90,
            )
            feature_two = Feature(
                project_id=project.id,
                title="Second feature",
                status=FeatureStatus.SPRINT_PLANNED,
                priority=80,
            )
            shipped_feature = Feature(
                project_id=project.id,
                title="Later sprint feature",
                status=FeatureStatus.DONE,
                priority=70,
            )
            session.add_all([feature_one, feature_two, shipped_feature])
            await session.flush()
            done_task = Task(
                feature_id=feature_one.id,
                title="Completed slice task",
                status=TaskStatus.DONE,
                phase=TaskPhase.COMPLETE,
            )
            active_task = Task(
                feature_id=feature_two.id,
                title="Active slice task",
                status=TaskStatus.IMPLEMENTATION,
                phase=TaskPhase.IMPLEMENTATION,
            )
            shipped_task = Task(
                feature_id=shipped_feature.id,
                title="Persisted sprint task",
                status=TaskStatus.DONE,
                phase=TaskPhase.COMPLETE,
            )
            session.add_all([done_task, active_task, shipped_task])
            await session.flush()
            session.add_all(
                [
                    Sprint(
                        project_id=project.id,
                        label="Sprint 1",
                        phase=SprintPhase.BLOCKED,
                        verification_status="blocked",
                        approved_feature_ids=[feature_one.id, feature_two.id],
                        generated_task_ids=[done_task.id, active_task.id],
                    ),
                    Sprint(
                        project_id=project.id,
                        label="Sprint 2",
                        phase=SprintPhase.SHIPPED,
                        verification_status="passed",
                        approved_feature_ids=[shipped_feature.id],
                        generated_task_ids=[shipped_task.id],
                    ),
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        labels = [sprint["label"] for sprint in data["sprints"]]

        assert labels.count("Sprint 2") == 1
        assert "Sprint 1 / Feature 1" in labels
        assert "Sprint 1 / Feature 2" in labels
        assert "Sprint 4" not in labels
        active_slice = next(
            sprint for sprint in data["sprints"] if sprint["label"] == "Sprint 1 / Feature 2"
        )
        assert active_slice["active_phase"] == "implementation"
        assert all(sprint["active_phase"] != "blocked" for sprint in data["sprints"])

    async def test_board_keeps_dispatchable_phase_task_in_pending_until_run_starts(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Task,
            TaskPhase,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="recoverable-work", language="typescript")
            session.add(project)
            await session.flush()
            feature = Feature(
                project_id=project.id,
                title="Local persistence",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            session.add(feature)
            await session.flush()
            task = Task(
                feature_id=feature.id,
                title="Verify localStorage persistence",
                status=TaskStatus.BUILD_VERIFY,
                phase=TaskPhase.INTEGRATION,
            )
            session.add(task)
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()

        assert [task["status"] for task in data["pending"]] == ["build_verify"]
        assert data["active"] == []

    async def test_embedded_board_keeps_failed_latest_run_out_of_active_lane(
        self, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            AgentRun,
            Feature,
            FeatureStatus,
            Project,
            Task,
            TaskStatus,
        )
        from autonomous_agent_builder.embedded.server.routes.dashboard import (
            load_board_response as load_embedded_board_response,
        )

        async with factory() as session:
            project = Project(name="todo-app", language="typescript")
            session.add(project)
            await session.flush()
            feature = Feature(
                project_id=project.id,
                title="Deterministic tests",
                status=FeatureStatus.SPRINT_PLANNED,
            )
            session.add(feature)
            await session.flush()
            task = Task(
                feature_id=feature.id,
                title="Verify Deterministic tests and build script for shipping",
                status=TaskStatus.IMPLEMENTATION,
            )
            session.add(task)
            await session.flush()
            session.add(
                AgentRun(
                    task_id=task.id,
                    agent_name="code-gen",
                    status="failed",
                    error="interrupted",
                    started_at=datetime(2026, 5, 8, 20, 40, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 8, 21, 7, tzinfo=UTC),
                )
            )
            await session.commit()

            board = await load_embedded_board_response(session)

        assert board.active == []
        assert [item.id for item in board.pending] == [task.id]

    async def test_board_task_item_shape(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "shape-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Shape feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Shape task"},
        )
        resp = await client.get("/api/dashboard/board")
        task_item = resp.json()["pending"][0]
        expected_fields = {
            "id", "title", "description", "status", "phase", "feature_id",
            "feature_title", "feature_description", "feature_priority",
            "feature_item_type", "acceptance_criteria", "dependencies",
            "sprint_execution",
            "agent_name", "runtime_sdk", "provider", "model", "effort",
            "cost_usd", "total_cost", "tokens_input", "tokens_output", "tokens_cached",
            "num_turns", "duration_ms", "approval_gate_id",
            "approval_gate_type", "pending_approval_count",
            "blocked_reason", "can_recover", "latest_run_status", "observability",
            "gate_results", "agent_runs", "activity_timeline", "updated_at",
        }
        assert set(task_item.keys()) == expected_fields

    async def test_board_task_activity_timeline_shows_file_actions(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "activity-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Activity feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Activity task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun, AgentRunEvent

        async with factory() as session:
            run = AgentRun(
                task_id=task_id,
                agent_name="code-gen",
                runtime_sdk="claude",
                provider="claude_agent_sdk",
                model="sonnet",
                started_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                completed_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
                cost_usd=0.01,
                num_turns=1,
                duration_ms=1000,
                status="completed",
                diff_summary={
                    "files_changed": 2,
                    "insertions": 18,
                    "deletions": 4,
                    "files": [
                        {
                            "path": "src/domain.py",
                            "status": "A",
                            "added_lines": 12,
                            "removed_lines": 0,
                        },
                        {
                            "path": "tests/test_domain.py",
                            "status": "M",
                            "added_lines": 6,
                            "removed_lines": 4,
                        },
                    ],
                },
            )
            session.add(run)
            await session.flush()
            session.add(
                AgentRunEvent(
                    run_id=run.id,
                    event_type="agent_output",
                    output_preview="Implementing the domain model now.",
                    timestamp=datetime(2026, 4, 23, 12, 0, 30, tzinfo=UTC),
                )
            )
            session.add(
                AgentRunEvent(
                    run_id=run.id,
                    event_type="thinking",
                    output_preview="Checking how search should compose with the active filter.",
                    timestamp=datetime(2026, 4, 23, 12, 0, 35, tzinfo=UTC),
                )
            )
            session.add(
                AgentRunEvent(
                    run_id=run.id,
                    event_type="tool_use",
                    tool_name="Edit",
                    tool_input={"file_path": "src/domain.py"},
                    output_preview="Updated search state",
                    timestamp=datetime(2026, 4, 23, 12, 0, 40, tzinfo=UTC),
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        task_item = resp.json()["pending"][0]
        runs = task_item["agent_runs"]
        assert [run["agent_name"] for run in runs] == ["code-gen"]
        assert runs[0]["runtime_sdk"] == "claude"
        assert runs[0]["status"] == "completed"
        assert runs[0]["max_budget_usd"] == pytest.approx(5.0)
        timeline = task_item["activity_timeline"]
        actions = [event["action"] for event in timeline]
        assert {event["runtime_sdk"] for event in timeline} == {"claude"}
        assert {event["provider"] for event in timeline} == {"claude_agent_sdk"}
        assert "Started code-gen" in actions
        assert "Implementing the domain model now." in actions
        assert "Thinking: Checking how search should compose with the active filter." in actions
        assert "Used Edit on src/domain.py" in actions
        assert "Created src/domain.py (+12/-0)" in actions
        assert "Updated tests/test_domain.py (+6/-4)" in actions
        assert actions.index("Started code-gen") < actions.index("Implementing the domain model now.")
        assert actions.index("Implementing the domain model now.") < actions.index("Thinking: Checking how search should compose with the active filter.")
        assert actions.index("Thinking: Checking how search should compose with the active filter.") < actions.index("Used Edit on src/domain.py")
        assert actions.index("Used Edit on src/domain.py") < actions.index("Created src/domain.py (+12/-0)")
        assert all("full transcript" not in action.lower() for action in actions)

    async def test_board_includes_sprint_execution_summary(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "sprint-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Sprint feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Sprint task"},
        )

        _, factory = test_db
        from autonomous_agent_builder.db.models import DesignDocument

        async with factory() as session:
            session.add_all(
                [
                    DesignDocument(
                        task_id=task.json()["id"],
                        doc_type=SPRINT_PLAN_DOC_TYPE,
                        title="Sprint execution plan",
                        content=json.dumps(
                            {
                                "plan_id": "sprint-plan-123",
                                "mode": "sequential_dependency_batches",
                                "planning_model": "gpt-5.5",
                                "planning_effort": "medium",
                                "single_sprint_plan": True,
                                "single_sprint_design": True,
                                "parallelism": {
                                    "strategy": "sequential_dependency_batches",
                                    "sequential_batches": ["batch-001"],
                                    "parallel_batches": [],
                                },
                                "context_strategy": "Use one shared sprint plan/design.",
                                "runtime_tool_strategy": {
                                    "runtime_sdk": "codex_sdk",
                                    "primary_tools": ["Codex app-server JSON-RPC events"],
                                },
                                "batches": [
                                    {
                                        "id": "batch-001",
                                        "titles": ["Sprint feature"],
                                        "execution_mode": "sequential",
                                        "recommended_model": "gpt-5.5",
                                        "recommended_effort": "medium",
                                    }
                                ],
                            }
                        ),
                    ),
                    DesignDocument(
                        task_id=task.json()["id"],
                        doc_type=SPRINT_DESIGN_DOC_TYPE,
                        title="Sprint shared design",
                        content=json.dumps({"design_id": "sprint-design-123"}),
                    ),
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        plan = resp.json()["sprint_plan"]
        assert plan["plan_id"] == "sprint-plan-123"
        assert plan["design_id"] == "sprint-design-123"
        assert plan["sprint_number"] == 1
        assert plan["model"] == "gpt-5.5"
        assert plan["single_plan"] is True
        assert plan["single_design"] is True
        assert plan["batch_count"] == 1
        assert plan["sequential_count"] == 1
        assert plan["parallel_count"] == 0
        assert plan["runtime_tool_strategy"]["runtime_sdk"] == "codex_sdk"
        assert plan["batches"][0]["title"] == "Sprint feature"

    async def test_board_normalizes_legacy_sprint_batch_model_labels(
        self, client, test_db, monkeypatch
    ):
        monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
        monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
        monkeypatch.setenv("RUNTIME_MODEL", "gpt-5.5")
        proj = await client.post(
            "/api/projects/", json={"name": "legacy-sprint-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Legacy sprint feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Legacy sprint task"},
        )

        _, factory = test_db
        from autonomous_agent_builder.db.models import DesignDocument, Task

        async with factory() as session:
            db_task = await session.get(Task, task.json()["id"])
            assert db_task is not None
            db_task.depends_on = {
                "sprint_execution": {
                    "recommended_model": "opus",
                    "recommended_effort": "high",
                    "batch_id": "batch-001",
                }
            }
            session.add(
                DesignDocument(
                    task_id=task.json()["id"],
                    doc_type=SPRINT_PLAN_DOC_TYPE,
                    title="Sprint execution plan",
                    content=json.dumps(
                        {
                            "plan_id": "legacy-plan",
                            "mode": "sequential_dependency_batches",
                            "batches": [
                                {
                                    "id": "batch-001",
                                    "titles": ["Legacy sprint feature"],
                                    "recommended_model": "opus",
                                    "recommended_effort": "high",
                                }
                            ],
                        }
                    ),
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        plan = resp.json()["sprint_plan"]
        assert plan["model"] == "gpt-5.5"
        assert plan["batches"][0]["model"] == "gpt-5.5"
        assert resp.json()["pending"][0]["sprint_execution"]["recommended_model"] == "gpt-5.5"

    async def test_board_compacts_sprint_execution_payload_for_operator_snapshot(
        self, client, test_db
    ):
        proj = await client.post(
            "/api/projects/", json={"name": "compact-board-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Compact board feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Compact board task"},
        )

        _, factory = test_db
        from autonomous_agent_builder.db.models import Task

        async with factory() as session:
            db_task = await session.get(Task, task.json()["id"])
            assert db_task is not None
            db_task.depends_on = {
                "sprint_execution": {
                    "sprint_id": "sprint-1",
                    "plan_id": "plan-1",
                    "task_key": "code-gen",
                    "recommended_model": "gpt-5.5",
                    "recommended_effort": "medium",
                    "implementation_brief": "x" * 20_000,
                    "file_ownership_hint": "src/App.tsx and tests",
                    "runtime_tool_strategy": {
                        "runtime_sdk": "claude",
                        "primary_tools": ["Edit", "Bash"],
                        "telemetry": "summary",
                        "avoid": ["large transcript echo"],
                    },
                }
            }
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        sprint_execution = resp.json()["pending"][0]["sprint_execution"]
        assert sprint_execution["sprint_id"] == "sprint-1"
        assert sprint_execution["recommended_model"] == "gpt-5.5"
        assert sprint_execution["runtime_tool_strategy"] == {
            "runtime_sdk": "claude",
            "primary_tools": ["Edit", "Bash"],
            "telemetry": "summary",
        }
        assert "implementation_brief" not in sprint_execution
        assert "file_ownership_hint" not in sprint_execution
        assert "avoid" not in sprint_execution["runtime_tool_strategy"]

    async def test_board_splits_multi_feature_sprint_into_visible_sprint_slices(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Sprint,
            Task,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="visible-sprints", language="typescript")
            session.add(project)
            await session.flush()
            features = [
                Feature(
                    id=f"feature-0{index}",
                    project_id=project.id,
                    title=f"Feature {index}",
                    status=FeatureStatus.DONE,
                    priority=100 - index,
                )
                for index in range(1, 5)
            ]
            session.add_all(features)
            await session.flush()
            generated_task_ids: list[str] = []
            for index, feature in enumerate(features, start=1):
                task = Task(
                    id=f"task-{index}",
                    feature_id=feature.id,
                    title=f"Verify Feature {index}",
                    status=TaskStatus.DONE if index < 4 else TaskStatus.CAPABILITY_LIMIT,
                    depends_on={
                        "sprint_execution": {
                            "sprint_id": "stored-sprint",
                            "batch_index": index,
                        }
                    },
                )
                session.add(task)
                generated_task_ids.append(task.id)
            session.add(
                Sprint(
                    id="stored-sprint",
                    project_id=project.id,
                    label="Sprint 1",
                    phase="blocked",
                    approved_feature_ids=[feature.id for feature in features],
                    generated_task_ids=generated_task_ids,
                    verification_status="blocked",
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()

        assert [sprint["label"] for sprint in data["sprints"]] == [
            "Sprint 1 / Feature 4",
            "Sprint 1 / Feature 1",
            "Sprint 1 / Feature 2",
            "Sprint 1 / Feature 3",
        ]
        assert data["current_sprint"]["label"] == "Sprint 1 / Feature 4"
        assert data["current_sprint"]["active_phase"] == "blocked"
        completed_sprints = [
            sprint
            for sprint in data["sprints"]
            if sprint["label"] != "Sprint 1 / Feature 4"
        ]
        assert all(sprint["active_phase"] == "shipped" for sprint in completed_sprints)
        assert all(len(sprint["generated_task_ids"]) == 1 for sprint in data["sprints"])

    async def test_board_keeps_integration_block_visible_when_all_sprint_tasks_done(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            Feature,
            FeatureStatus,
            Project,
            Sprint,
            Task,
            TaskStatus,
        )

        async with factory() as session:
            project = Project(name="visible-sprints", language="typescript")
            session.add(project)
            await session.flush()
            features = [
                Feature(
                    id=f"feature-0{index}",
                    project_id=project.id,
                    title=f"Feature {index}",
                    status=FeatureStatus.DONE,
                    priority=100 - index,
                )
                for index in range(1, 3)
            ]
            session.add_all(features)
            await session.flush()
            generated_task_ids: list[str] = []
            for index, feature in enumerate(features, start=1):
                task = Task(
                    id=f"task-{index}",
                    feature_id=feature.id,
                    title=f"Verify Feature {index}",
                    status=TaskStatus.DONE,
                    depends_on={
                        "sprint_execution": {
                            "sprint_id": "stored-sprint",
                            "batch_index": index,
                        }
                    },
                )
                session.add(task)
                generated_task_ids.append(task.id)
            session.add(
                Sprint(
                    id="stored-sprint",
                    project_id=project.id,
                    label="Sprint 1",
                    phase="blocked",
                    approved_feature_ids=[feature.id for feature in features],
                    generated_task_ids=generated_task_ids,
                    verification_status="blocked",
                    verification_evidence={
                        "status": "passed",
                        "sprint_merge_error": "fatal: Not possible to fast-forward, aborting.",
                    },
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()

        assert data["current_sprint"]["label"] == "Sprint 1 / Feature 1"
        assert data["current_sprint"]["active_phase"] == "blocked"
        assert all(sprint["active_phase"] == "blocked" for sprint in data["sprints"])


@pytest.mark.asyncio
class TestMetricsEndpoint:
    """Test /api/dashboard/metrics response shape."""

    async def test_metrics_empty(self, client, test_db):
        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0
        assert data["total_tokens"] == 0
        assert data["total_runs"] == 0
        assert data["gate_pass_rate"] == 0
        assert data["runs"] == []

    async def test_metrics_response_shape(self, client, test_db):
        resp = await client.get("/api/dashboard/metrics")
        data = resp.json()
        expected_fields = {
            "total_cost", "total_estimated_cost_usd", "total_estimated_codex_credits", "total_tokens", "total_runs",
            "gate_pass_rate", "optimization_summary", "optimization_decision", "runtime_decision_summary",
            "deterministic_script_candidates", "voice_ledger", "context_budget", "runs",
        }
        assert set(data.keys()) == expected_fields
        assert data["optimization_summary"]["primary_score"] == "raw_tokens"
        assert isinstance(data["optimization_decision"], dict)
        assert isinstance(data["runtime_decision_summary"], dict)
        assert isinstance(data["deterministic_script_candidates"], list)
        assert data["voice_ledger"]["totals"]["responses"] == 0
        assert data["context_budget"]["available"] is False

    async def test_metrics_observability_reports_degraded_when_project_db_missing(
        self, client, test_db
    ):
        resp = await client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["optimization_decision"]["status"] == "degraded"
        assert data["runtime_decision_summary"]["status"] == "degraded"
        assert data["context_budget"]["status"] == "degraded"
        assert data["deterministic_script_candidates"][0]["code"] == "observability_unavailable"

    async def test_metrics_api_and_embedded_loaders_share_payload_contract(
        self, monkeypatch, tmp_path, test_db
    ):
        from autonomous_agent_builder.api.routes import dashboard_api
        from autonomous_agent_builder.db.models import (
            AgentRun,
            ChatEvent,
            ChatSession,
            Feature,
            GateResult,
            GateStatus,
            Project,
            Task,
        )
        from autonomous_agent_builder.embedded.server.routes import dashboard as embedded_dashboard

        project_root = tmp_path / "project"
        db_path = project_root / ".agent-builder" / "agent_builder.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("", encoding="utf-8")
        captured_paths: list[str] = []

        def fake_observability_summary(path):
            captured_paths.append(str(path))
            return {
                "runtime_decision_summary": {"available": True, "source": "shared-contract"},
                "optimization_decision": {"available": True, "source": "shared-contract"},
                "deterministic_script_candidates": [{"code": "shared_contract_candidate"}],
                "runtime_aggregates": {
                    "context_budget": {"available": True, "source": "shared-contract"}
                },
            }

        monkeypatch.setattr(
            dashboard_api,
            "dashboard_observability_summary",
            fake_observability_summary,
        )
        monkeypatch.setattr(
            embedded_dashboard,
            "dashboard_observability_summary",
            fake_observability_summary,
        )

        _, factory = test_db
        base_time = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)
        async with factory() as session:
            project = Project(name="metrics-contract", language="python")
            session.add(project)
            await session.flush()
            feature = Feature(project_id=project.id, title="Metrics contract")
            session.add(feature)
            await session.flush()
            task = Task(feature_id=feature.id, title="Measure shared metrics")
            chat = ChatSession()
            session.add_all([task, chat])
            await session.flush()
            session.add_all(
                [
                    AgentRun(
                        task_id=task.id,
                        agent_name="code-gen",
                        runtime_sdk="codex_sdk",
                        provider="codex_subscription",
                        model="gpt-5.5",
                        effort="medium",
                        cost_usd=0.0,
                        tokens_input=100,
                        tokens_output=20,
                        tokens_cached=40,
                        num_turns=1,
                        duration_ms=1500,
                        status="completed",
                        started_at=base_time,
                        completed_at=base_time + timedelta(seconds=2),
                    ),
                    GateResult(
                        task_id=task.id,
                        gate_name="pytest",
                        status=GateStatus.PASS,
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={"running": True, "runtime_sdk": "codex_sdk"},
                        status="running",
                        created_at=base_time + timedelta(seconds=3),
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={
                            "running": False,
                            "runtime_sdk": "codex_sdk",
                            "provider": "codex_subscription",
                            "model": "gpt-5.5",
                            "effort": "low",
                            "cost_usd": 0.2,
                            "tokens_input": 50,
                            "tokens_output": 10,
                            "tokens_cached": 15,
                            "current_turn": 2,
                        },
                        status="completed",
                        created_at=base_time + timedelta(seconds=5),
                    ),
                ]
            )
            await session.commit()

            api_response = await dashboard_api._load_metrics_response(session, project_root)
            embedded_response = await embedded_dashboard._load_metrics_response(
                session, project_root
            )

        def dump_metrics(response):
            if hasattr(response, "model_dump"):
                return response.model_dump(mode="json")
            return json.loads(response.json())

        assert dump_metrics(api_response) == dump_metrics(embedded_response)
        assert captured_paths == [str(db_path), str(db_path)]

    async def test_metrics_observability_uses_app_project_root(
        self, monkeypatch, tmp_path, test_db
    ):
        from httpx import ASGITransport, AsyncClient

        from autonomous_agent_builder.api.app import create_app
        from autonomous_agent_builder.api.routes import dashboard_api

        project_root = tmp_path / "project"
        db_path = project_root / ".agent-builder" / "agent_builder.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("", encoding="utf-8")
        other_cwd = tmp_path / "other-cwd"
        other_cwd.mkdir()
        monkeypatch.setenv("AAB_PROJECT_ROOT", str(project_root))
        monkeypatch.chdir(other_cwd)

        captured: dict[str, str] = {}

        def fake_observability_summary(path):
            captured["path"] = str(path)
            return {
                "runtime_decision_summary": {"available": True, "source": "project-root"},
                "optimization_decision": {"available": True, "source": "project-root"},
                "deterministic_script_candidates": [{"code": "project_candidate"}],
                "runtime_aggregates": {
                    "context_budget": {"available": True, "source": "project-root"}
                },
            }

        monkeypatch.setattr(
            dashboard_api,
            "dashboard_observability_summary",
            fake_observability_summary,
        )
        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert captured["path"] == str(db_path)
        assert data["optimization_decision"]["source"] == "project-root"
        assert data["context_budget"]["source"] == "project-root"
        assert data["deterministic_script_candidates"][0]["code"] == "project_candidate"

    async def test_metrics_estimate_codex_subscription_cost_and_model_effort(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "metrics-cost-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Metrics cost feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Metrics cost task"},
        )
        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun

        async with factory() as session:
            session.add(
                AgentRun(
                    task_id=task.json()["id"],
                    agent_name="code-gen",
                    runtime_sdk="codex_sdk",
                    provider="codex_subscription",
                    model="gpt-5.5",
                    effort="medium",
                    tokens_input=10_000,
                    tokens_cached=8_000,
                    tokens_output=500,
                    cost_usd=0.0,
                    num_turns=1,
                    duration_ms=1000,
                    status="completed",
                    diff_summary={
                        "files": [
                            {"path": "src/app.js", "status": "M"},
                            {"path": "node_modules/vite/index.js", "status": "A"},
                        ],
                        "hunks": [
                            {"path": "build/assets/index.js", "added_lines": 500},
                            {"path": "src/app.js", "added_lines": 5},
                        ],
                    },
                    observability={
                        "command": "builder script run feature_acceptance --json",
                        "data": {
                            "command": [
                                "/tmp/aab-workspaces/demo/node_modules/.bin/playwright",
                                "test",
                            ],
                            "checks": [
                                {
                                    "command": [
                                        "/tmp/aab-workspaces/demo/node_modules/.bin/playwright",
                                        "test",
                                    ],
                                    "status": "passed",
                                    "preview": "large package-lock preview with node_modules",
                                    "stderr": "verbose raw output",
                                }
                            ],
                            "raw": "raw forensic payload",
                        },
                    },
                    started_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 3, 12, 1, tzinfo=UTC),
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0
        assert data["total_estimated_cost_usd"] == pytest.approx(0.029)
        assert data["total_estimated_codex_credits"] == pytest.approx(0.725)
        run = data["runs"][0]
        assert run["model"] == "gpt-5.5"
        assert run["effort"] == "medium"
        assert run["estimated_cost_usd"] == pytest.approx(0.029)
        assert run["estimated_codex_credits"] == pytest.approx(0.725)
        assert run["cost_source"] == "estimated_from_codex_subscription_tokens"
        assert run["diff_summary"]["bounded"] is True
        assert run["diff_summary"]["omitted_generated_paths"] == 2
        assert run["diff_summary"]["files"] == [{"path": "src/app.js", "status": "M"}]
        assert run["diff_summary"]["hunks"] == [{"path": "src/app.js", "added_lines": 5}]
        assert run["observability"]["command"] == "builder script run feature_acceptance --json"
        assert run["observability"]["data"]["command"] == ["test"]
        assert run["observability"]["data"]["checks"] == [
            {"command": ["test"], "status": "passed"}
        ]
        serialized_observability = json.dumps(run["observability"])
        assert "node_modules" not in serialized_observability
        assert "preview" not in serialized_observability
        assert "stderr" not in serialized_observability
        assert "raw forensic payload" not in serialized_observability

    async def test_metrics_include_agent_chat_runs(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import ChatEvent, ChatSession

        async with factory() as session:
            chat = ChatSession()
            session.add(chat)
            await session.flush()
            session.add_all(
                [
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={
                            "running": True,
                            "current_turn": 0,
                            "tokens_used": 0,
                            "cost_usd": 0.0,
                        },
                        status="running",
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={
                            "running": False,
                            "current_turn": 3,
                            "tokens_used": 321,
                            "tokens_input": 300,
                            "tokens_output": 21,
                            "tokens_cached": 240,
                            "noncached_plus_output_tokens": 81,
                            "cost_usd": 0.42,
                        },
                        status="completed",
                    ),
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == pytest.approx(0.42)
        assert data["total_tokens"] == 321
        assert data["total_runs"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["agent_name"] == "agent-chat"
        assert data["runs"][0]["task_id"]
        assert data["runs"][0]["num_turns"] == 3
        assert data["runs"][0]["status"] == "completed"
        assert data["runs"][0]["tokens_input"] == 300
        assert data["runs"][0]["tokens_output"] == 21
        assert data["runs"][0]["tokens_cached"] == 240

    async def test_metrics_totals_use_aggregates_while_display_rows_are_bounded(
        self, client, test_db
    ):
        proj = await client.post(
            "/api/projects/", json={"name": "metrics-scale-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Metrics scale feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Metrics scale task"},
        )
        task_id = task.json()["id"]
        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun, ChatEvent, ChatSession, GateResult

        base_time = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
        async with factory() as session:
            chat = ChatSession()
            session.add(chat)
            await session.flush()
            session.add_all(
                [
                    AgentRun(
                        task_id=task_id,
                        agent_name="code-gen",
                        cost_usd=0.01,
                        tokens_input=1,
                        tokens_output=1,
                        num_turns=1,
                        duration_ms=10,
                        status="completed",
                        started_at=base_time + timedelta(seconds=index),
                        completed_at=base_time + timedelta(seconds=index, milliseconds=10),
                    )
                    for index in range(1005)
                ]
            )
            session.add_all(
                [
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        status="completed",
                        payload_json={
                            "running": False,
                            "tokens_input": 1,
                            "tokens_output": 2,
                            "cost_usd": 0.02,
                        },
                        created_at=base_time + timedelta(seconds=index),
                    )
                    for index in range(1005)
                ]
            )
            session.add_all(
                [
                    GateResult(
                        task_id=task_id,
                        gate_name=f"gate-{index}",
                        status="pass" if index % 2 == 0 else "fail",
                    )
                    for index in range(1000)
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 2010
        assert data["total_cost"] == pytest.approx(30.15)
        assert data["total_tokens"] == 5025
        assert data["gate_pass_rate"] == pytest.approx(50.0)
        assert len(data["runs"]) <= 600

    async def test_metrics_include_voice_cost_and_delegation_ledger(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import ChatEvent, ChatSession

        async with factory() as session:
            chat = ChatSession()
            session.add(chat)
            await session.flush()
            session.add_all(
                [
                    ChatEvent(
                        session_id=chat.id,
                        event_type="voice_usage",
                        payload_json={
                            "voice_call_id": "rtc_metrics",
                            "response_id": "resp_1",
                            "input_tokens": 80,
                            "output_tokens": 20,
                            "total_tokens": 100,
                            "cost_source": "usage_without_realtime_rate_card",
                        },
                        status="completed",
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="user_message",
                        payload_json={"content": "Ship it", "source": "realtime_voice"},
                        status="completed",
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="voice_action_prepared",
                        payload_json={"prepared_status": "executed"},
                        status="answered",
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="voice_wait",
                        payload_json={"reason": "background audio", "source": "realtime_voice"},
                        status="completed",
                    ),
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        ledger = resp.json()["voice_ledger"]
        assert ledger["totals"]["responses"] == 1
        assert ledger["totals"]["total_tokens"] == 100
        assert ledger["totals"]["delegated_messages"] == 1
        assert ledger["totals"]["delegation_ratio"] == 1.0
        assert ledger["totals"]["prepared_actions"] == 1
        assert ledger["totals"]["confirmed_actions"] == 1
        assert ledger["totals"]["failed_tool_outputs"] == 0
        assert ledger["totals"]["wait_events"] == 1
        assert ledger["usage"][0]["voice_call_id"] == "rtc_metrics"

    async def test_metrics_active_run_injects_diagnostic_note(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "active-run-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Active run feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Active run task"},
        )
        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun

        async with factory() as session:
            session.add(
                AgentRun(
                    task_id=task.json()["id"],
                    agent_name="code-gen",
                    cost_usd=0.0,
                    tokens_input=0,
                    tokens_output=0,
                    num_turns=3,
                    duration_ms=0,
                    status="running",
                    started_at=datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        summary = data["optimization_summary"]
        assert summary["active_runs"] == 1
        assert "token data not yet available" in summary["active_runs_note"]


@pytest.mark.asyncio
class TestObservabilityEndpoint:
    async def test_observability_response_shape(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
        monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        agent_builder = tmp_path / ".agent-builder"
        agent_builder.mkdir()
        db_path = agent_builder / "agent_builder.db"
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            create table agent_runs (
                id text primary key,
                task_id text,
                agent_name text,
                runtime_sdk text,
                provider text,
                model text,
                effort text,
                cost_usd real,
                tokens_input integer,
                tokens_output integer,
                tokens_cached integer,
                num_turns integer,
                duration_ms integer,
                stop_reason text,
                observability text
            );
            create table agent_run_events (
                id text primary key,
                run_id text,
                event_type text,
                tool_name text
            );
            create table approval_gates (
                id text primary key,
                task_id text,
                gate_type text,
                status text,
                created_at text,
                resolved_at text
            );
            create table tasks (
                id text primary key,
                status text,
                depends_on text
            );
            create table chat_events (
                id text primary key,
                session_id text,
                event_type text,
                status text,
                content text,
                payload_json text
            );
            """
        )
        conn.execute(
            """
            insert into agent_runs
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "task-1",
                "code-gen",
                "codex_sdk",
                "codex_subscription",
                "gpt-5.5",
                "medium",
                0.0,
                1000,
                100,
                500,
                1,
                1000,
                "completed",
                "{}",
            ),
        )
        conn.execute(
            """
            insert into agent_runs
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-2",
                "task-2",
                "agent-chat",
                "claude",
                "claude_agent_sdk",
                "haiku",
                "medium",
                0.01,
                25,
                50,
                0,
                1,
                1000,
                "end_turn",
                json.dumps(
                    {
                        "resume_retry": {
                            "fallback": "fresh_model_turn",
                            "reason": "Process error (exit 1): stale resume session",
                        }
                    }
                ),
            ),
        )
        conn.commit()
        conn.close()

        from httpx import ASGITransport, AsyncClient

        from autonomous_agent_builder.api.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/dashboard/observability")

        assert resp.status_code == 200
        data = resp.json()
        assert data["runtime"]["selected_runtime_sdk"] == "codex_sdk"
        assert data["observability_coverage"]["mode"] == "codex_app_server"
        assert "runtime_aggregates" in data
        assert "recommendations" in data
        assert data["runtime_aggregates"]["runtime_recovery"]["resume_retry_count"] == 1
        recommendation_codes = {
            item["code"]
            for item in data["observability_coverage"]["deterministic_recommendations"]
        }
        resolved_codes = {
            item["code"] for item in data["observability_coverage"]["resolved_recommendations"]
        }
        assert "runtime_resume_recovered" not in recommendation_codes
        assert "runtime_resume_recovered" in resolved_codes
        assert data["runtime_capability_matrix"]["runtime"] == "codex_sdk"
        assert data["phase_runtime_decisions"][0]["phase"] == "requirements"


@pytest.mark.asyncio
class TestApprovalDetailsEndpoint:
    """Test /api/dashboard/approvals/{gate_id} response shape."""

    async def test_approval_not_found(self, client, test_db):
        resp = await client.get("/api/dashboard/approvals/bad-id")
        assert resp.status_code == 404

    async def test_approval_details_shape(self, client, test_db):
        """Create entities to test approval details endpoint."""
        # Create project → feature → task
        proj = await client.post(
            "/api/projects/",
            json={"name": "approval-proj", "language": "python"},
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Approval feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Approval task"},
        )
        task_id = task.json()["id"]

        # Create an approval gate directly via DB
        _, factory = test_db
        from autonomous_agent_builder.db.models import ApprovalGate

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="planning")
            session.add(gate)
            await session.flush()
            gate_id = gate.id
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        data = resp.json()

        expected_fields = {
            "gate_id", "gate_type", "gate_status",
            "task_id", "task_title", "task_status", "task_description",
            "feature_title", "project_name",
            "thread", "runs", "gate_results",
            # Sprint-PR refactor adds optional sprint metadata; per-task gates
            # surface them as empty strings.
            "sprint_id", "sprint_label", "sprint_pr_url", "sprint_changes_summary",
        }
        assert set(data.keys()) == expected_fields
        assert data["gate_type"] == "planning"
        assert data["task_title"] == "Approval task"
        assert isinstance(data["thread"], list)
        assert isinstance(data["runs"], list)
        assert isinstance(data["gate_results"], list)
        # Per-task gate: sprint fields default empty.
        assert data["sprint_id"] == ""
        assert data["sprint_label"] == ""
        assert data["sprint_pr_url"] == ""

    async def test_approval_details_show_latest_gate_result_per_gate(self, client, test_db):
        proj = await client.post(
            "/api/projects/",
            json={"name": "approval-proj", "language": "python"},
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Approval feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Approval task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import ApprovalGate, GateResult, GateStatus

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="pr")
            session.add(gate)
            await session.flush()
            gate_id = gate.id
            session.add_all(
                [
                    GateResult(
                        task_id=task_id,
                        gate_name="code_quality",
                        status=GateStatus.WARN,
                        error_code="UNSUPPORTED_LANGUAGE",
                        created_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                    ),
                    GateResult(
                        task_id=task_id,
                        gate_name="testing",
                        status=GateStatus.WARN,
                        error_code="UNSUPPORTED_LANGUAGE",
                        created_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
                    ),
                    GateResult(
                        task_id=task_id,
                        gate_name="code_quality",
                        status=GateStatus.PASS,
                        created_at=datetime(2026, 4, 23, 12, 2, tzinfo=UTC),
                    ),
                    GateResult(
                        task_id=task_id,
                        gate_name="testing",
                        status=GateStatus.PASS,
                        created_at=datetime(2026, 4, 23, 12, 3, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        gate_results = resp.json()["gate_results"]
        assert [(item["gate_name"], item["status"]) for item in gate_results] == [
            ("code_quality", "pass"),
            ("testing", "pass"),
        ]
        assert all(item["error_code"] is None for item in gate_results)

    async def test_approval_details_tolerates_mixed_datetime_awareness(self, client, test_db):
        proj = await client.post(
            "/api/projects/",
            json={"name": "approval-proj", "language": "python"},
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Approval feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Approval task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            AgentRun,
            Approval,
            ApprovalDecision,
            ApprovalGate,
        )

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="planning")
            session.add(gate)
            await session.flush()
            session.add(
                AgentRun(
                    task_id=task_id,
                    agent_name="planner",
                    started_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
                    cost_usd=0.01,
                    num_turns=1,
                    duration_ms=1000,
                    status="completed",
                    output_text="Planner recommended a small Flask validation-run CRUD slice.",
                )
            )
            session.add(
                Approval(
                    approval_gate_id=gate.id,
                    approver_email="operator@example.com",
                    decision=ApprovalDecision.APPROVE,
                    comment="Looks good",
                    created_at=datetime(2026, 4, 23, 12, 2),
                )
            )
            gate_id = gate.id
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert [entry["role"] for entry in data["thread"]] == ["agent", "human"]
        assert "Planner recommended a small Flask validation-run CRUD slice." in data["thread"][0]["content"]


@pytest.mark.asyncio
class TestDashboardUtilityEndpoints:
    async def test_shell_summary_includes_pending_gate_and_questions(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "shell-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Shell feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Shell task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import ApprovalGate, ChatEvent, ChatSession

        async with factory() as session:
            chat_session = ChatSession(repo_identity="repo", workspace_cwd="cwd")
            session.add(chat_session)
            await session.flush()
            session.add(ApprovalGate(task_id=task_id, gate_type="planning", status="pending"))
            session.add(
                ChatEvent(
                    session_id=chat_session.id,
                    event_type="ask_user_question",
                    status="pending",
                    payload_json={"question": "Need approval?"},
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/shell-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_approvals"] == 1
        assert data["pending_questions"] == 1
        assert "running_label" in data
        assert isinstance(data["todo_snapshots"], list)

    async def test_shell_summary_returns_latest_todo_snapshot_per_recent_session(
        self, client, test_db
    ):
        _, factory = test_db
        from autonomous_agent_builder.db.models import ChatEvent, ChatSession

        base_time = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
        async with factory() as session:
            sessions = [ChatSession() for _ in range(5)]
            session.add_all(sessions)
            await session.flush()
            for session_index, chat_session in enumerate(sessions):
                for snapshot_index in range(4):
                    session.add(
                        ChatEvent(
                            session_id=chat_session.id,
                            event_type="todo_snapshot",
                            payload_json={
                                "pending_count": snapshot_index,
                                "in_progress_count": 0,
                                "completed_count": session_index,
                                "todos": [
                                    {
                                        "content": f"session-{session_index}-snapshot-{snapshot_index}",
                                        "status": "pending",
                                    }
                                ],
                            },
                            created_at=base_time
                            + timedelta(seconds=session_index * 10 + snapshot_index),
                        )
                    )
            await session.commit()

        resp = await client.get("/api/dashboard/shell-summary")

        assert resp.status_code == 200
        snapshots = resp.json()["todo_snapshots"]
        assert len(snapshots) == 3
        assert [item["pending_count"] for item in snapshots] == [3, 3, 3]
        assert [item["todos"][0]["content"] for item in snapshots] == [
            "session-4-snapshot-3",
            "session-3-snapshot-3",
            "session-2-snapshot-3",
        ]

    async def test_inbox_returns_latest_run_context(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "inbox-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Inbox feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Inbox task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun, ApprovalGate

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="design", status="pending")
            session.add(gate)
            session.add(
                AgentRun(
                    task_id=task_id,
                    agent_name="designer",
                    status="completed",
                    num_turns=3,
                    duration_ms=2400,
                    cost_usd=0.02,
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/inbox")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["gate_type"] == "design"
        assert data[0]["latest_run_agent"] == "designer"
        assert data[0]["approval_url"].startswith("/approvals/")

    async def test_compare_returns_both_runs(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "compare-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Compare feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Compare task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun

        async with factory() as session:
            left = AgentRun(task_id=task_id, agent_name="baseline", status="completed", cost_usd=0.01, num_turns=2)
            right = AgentRun(task_id=task_id, agent_name="variant", status="completed", cost_usd=0.03, num_turns=4)
            session.add_all([left, right])
            await session.flush()
            left_id = left.id
            right_id = right.id
            await session.commit()

        resp = await client.get(
            f"/api/dashboard/compare?left_run_id={left_id}&right_run_id={right_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["same_task"] is True
        assert data["left"]["agent_name"] == "baseline"
        assert data["right"]["agent_name"] == "variant"

    async def test_command_index_returns_routes_and_task_actions(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "command-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Command feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch me"},
        )

        resp = await client.get("/api/dashboard/command-index")
        assert resp.status_code == 200
        data = resp.json()
        labels = {item["label"] for item in data["items"]}
        assert "Agent" in labels
        assert "Board" in labels
        assert "Compare" in labels
        assert "Dispatch me" in labels


class TestSprintPrApprovalDetails:
    """Sprint-PR refactor: approval-details endpoint surfaces sprint metadata."""

    async def test_sprint_pr_gate_returns_sprint_metadata(self, client, test_db):
        """A gate keyed on sprint_id (no task_id) renders sprint label, PR URL, and summary."""
        proj = await client.post(
            "/api/projects/",
            json={"name": "sprint-pr-proj", "language": "python"},
        )
        project_id = proj.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import (
            ApprovalGate,
            Sprint,
            SprintPhase,
        )

        async with factory() as session:
            sprint = Sprint(
                project_id=project_id,
                label="Sprint 1",
                phase=SprintPhase.PR_REVIEW,
                branch="sprint/abcd-sprint-1",
                pr_url="https://github.com/owner/repo/pull/42",
                generated_task_ids=[],
            )
            sprint.verification_evidence = {
                "sprint_pr": {
                    "branch": "sprint/abcd-sprint-1",
                    "url": "https://github.com/owner/repo/pull/42",
                    "summary": "Sprint 1 — consolidated PR\n\nTasks delivered:\n- Hello",
                }
            }
            session.add(sprint)
            await session.flush()
            gate = ApprovalGate(
                task_id=None,
                sprint_id=sprint.id,
                gate_type="sprint_pr",
            )
            session.add(gate)
            await session.flush()
            gate_id = gate.id
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["gate_type"] == "sprint_pr"
        assert data["task_id"] == ""
        assert data["sprint_label"] == "Sprint 1"
        assert data["sprint_pr_url"] == "https://github.com/owner/repo/pull/42"
        assert "consolidated PR" in data["sprint_changes_summary"]
        # Project name still resolves through the sprint→project relationship.
        assert data["project_name"] == "sprint-pr-proj"
        # Task fields fall back to sprint label/summary so per-task widgets do
        # not crash on a sprint gate.
        assert data["task_title"] == "Sprint 1"
