"""Tests for dashboard API — board/metrics/approval JSON shapes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_DESIGN_DOC_TYPE,
    SPRINT_PLAN_DOC_TYPE,
)

_BOARD_LANES = ("pending", "active", "review", "done", "blocked")


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
            "blocked_reason", "latest_run_status", "observability",
            "agent_runs", "activity_timeline", "updated_at",
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
                provider="claude_code",
                model="anthropic/claude-sonnet-4-6",
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
        timeline = task_item["activity_timeline"]
        actions = [event["action"] for event in timeline]
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
            "deterministic_script_candidates", "runs",
        }
        assert set(data.keys()) == expected_fields
        assert data["optimization_summary"]["primary_score"] == "raw_tokens"
        assert isinstance(data["optimization_decision"], dict)
        assert isinstance(data["runtime_decision_summary"], dict)
        assert isinstance(data["deterministic_script_candidates"], list)

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


@pytest.mark.asyncio
class TestObservabilityEndpoint:
    async def test_observability_response_shape(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
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
                "claude_code",
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
