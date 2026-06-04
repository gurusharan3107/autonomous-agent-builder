from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.db.models import (
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.routes.dashboard import (
    _build_sprint_summary,
    _build_task_item,
    _compact_sprint_plan_summary,
    _generated_sprint_tasks_from_plan,
    _serialize_task_run,
    approval_stream,
    board_stream,
)


class _ConnectedRequest:
    def __init__(self, project_root=None):
        self.app = SimpleNamespace(state=SimpleNamespace(project_root=project_root))

    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_embedded_board_stream_returns_sse_response(test_db, tmp_path):
    _, factory = test_db
    assert isinstance(factory, async_sessionmaker)

    async with factory() as db:
        response = await board_stream(_ConnectedRequest(tmp_path), db)

    assert isinstance(response, EventSourceResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_embedded_approval_stream_raises_404_for_unknown_gate(test_db):
    _, factory = test_db

    async with factory() as db:
        with pytest.raises(HTTPException) as exc:
            await approval_stream("missing-gate", _ConnectedRequest(), db)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Approval gate not found"


def test_embedded_task_run_summary_includes_agent_policy_budget():
    run = SimpleNamespace(
        id="run-1",
        session_id="session-1",
        agent_name="code-gen",
        runtime_sdk="claude",
        provider="claude_agent_sdk",
        model="sonnet",
        effort=None,
        cost_usd=0.4,
        tokens_input=10,
        tokens_output=20,
        tokens_cached=0,
        num_turns=2,
        duration_ms=1000,
        stop_reason="end_turn",
        status="completed",
        error=None,
        confidence=None,
        diff_summary=None,
        observability=None,
        started_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
    )

    assert _serialize_task_run(run).max_budget_usd == pytest.approx(5.0)


def test_embedded_task_run_summary_bounds_diff_and_observability_payloads():
    run = SimpleNamespace(
        id="run-1",
        session_id="session-1",
        agent_name="code-gen",
        runtime_sdk="codex_sdk",
        provider="openai",
        model="gpt-5.5",
        effort="medium",
        cost_usd=0.4,
        tokens_input=10,
        tokens_output=20,
        tokens_cached=0,
        num_turns=2,
        duration_ms=1000,
        stop_reason="end_turn",
        status="completed",
        error=None,
        confidence=None,
        diff_summary={
            "files": [
                {
                    "path": f"src/file_{index}.tsx",
                    "status": "M",
                    "added_lines": index,
                    "removed_lines": 0,
                }
                for index in range(75)
            ],
            "hunks": [
                {"file": f"src/file_{index}.tsx", "preview": "x" * 1000}
                for index in range(75)
            ],
        },
        observability={"stdout": "x" * 20_000, "events": list(range(75))},
        started_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
    )

    summary = _serialize_task_run(run)

    assert summary.diff_summary is not None
    assert len(summary.diff_summary["files"]) == 50
    assert len(summary.diff_summary["hunks"]) == 50
    assert summary.diff_summary["bounded"] is True
    assert summary.diff_summary["truncated"] is True
    assert "stdout" not in summary.observability
    assert len(summary.observability["events"]) == 51


def test_embedded_task_card_compacts_sprint_execution_payload():
    feature = SimpleNamespace(
        id="feature-1",
        title="Compact feature",
        description="",
        priority=1,
        item_type="feature",
        acceptance_criteria=[],
        dependencies=[],
    )
    task = SimpleNamespace(
        id="task-1",
        title="Compact task",
        description="",
        status="pending",
        phase="planning",
        feature=feature,
        depends_on={
            "sprint_execution": {
                "sprint_id": "sprint-1",
                "plan_id": "plan-1",
                "task_key": "ui-shell",
                "recommended_model": "gpt-5.5",
                "recommended_effort": "medium",
                "implementation_brief": "x" * 20_000,
                "file_ownership_hint": "frontend/src/App.tsx",
                "runtime_tool_strategy": {
                    "runtime_sdk": "codex_sdk",
                    "primary_tools": ["exec_command"],
                    "telemetry": "summary",
                    "avoid": ["full transcript echo"],
                },
            }
        },
        agent_runs=[],
        approval_gates=[],
        blocked_reason="",
        updated_at=None,
    )

    item = _build_task_item(task)

    assert item.sprint_execution is not None
    assert item.sprint_execution["sprint_id"] == "sprint-1"
    assert item.sprint_execution["recommended_model"] == "gpt-5.5"
    assert item.sprint_execution["runtime_tool_strategy"] == {
        "runtime_sdk": "codex_sdk",
        "primary_tools": ["exec_command"],
        "telemetry": "summary",
    }
    assert "implementation_brief" not in item.sprint_execution
    assert "file_ownership_hint" not in item.sprint_execution
    assert "avoid" not in item.sprint_execution["runtime_tool_strategy"]


def test_embedded_task_card_limits_historical_run_summaries():
    feature = SimpleNamespace(
        id="feature-1",
        title="Run history feature",
        description="",
        priority=1,
        item_type="feature",
        acceptance_criteria=[],
        dependencies=[],
    )
    runs = [
        SimpleNamespace(
            id=f"run-{index}",
            session_id=f"session-{index}",
            agent_name="code-gen",
            runtime_sdk="codex_sdk",
            provider="openai",
            model="gpt-5.5",
            effort="medium",
            cost_usd=0.1,
            tokens_input=10,
            tokens_output=20,
            tokens_cached=0,
            num_turns=1,
            duration_ms=1000,
            stop_reason="end_turn",
            status="completed",
            error=None,
            confidence=None,
            diff_summary={
                "files": [
                    {"path": f"src/file_{file_index}.tsx", "status": "M"}
                    for file_index in range(25)
                ]
            },
            observability=None,
            events=[],
            started_at=datetime(2026, 4, 23, 12, index, tzinfo=UTC),
            completed_at=datetime(2026, 4, 23, 12, index, 1, tzinfo=UTC),
        )
        for index in range(12)
    ]
    task = SimpleNamespace(
        id="task-1",
        title="Run history task",
        description="",
        status="done",
        phase="complete",
        feature=feature,
        depends_on={},
        agent_runs=runs,
        approval_gates=[],
        blocked_reason="",
        updated_at=None,
    )

    item = _build_task_item(task)

    assert len(item.agent_runs) == 10
    assert [run.id for run in item.agent_runs][0] == "run-2"
    assert [run.id for run in item.agent_runs][-1] == "run-11"
    assert item.agent_runs[-1].diff_summary is not None
    assert len(item.agent_runs[-1].diff_summary["files"]) == 10
    assert item.agent_runs[-1].diff_summary["truncated"] is True


def test_embedded_generated_sprint_tasks_compact_execution_payloads():
    items = _generated_sprint_tasks_from_plan(
        ["task-1"],
        {
            "sprint_id": "sprint-1",
            "plan_id": "plan-1",
            "mode": "sprint_task_breakdown",
            "planning_model": "gpt-5.5",
            "planning_effort": "medium",
            "runtime_tool_strategy": {
                "runtime_sdk": "codex_sdk",
                "primary_tools": ["exec_command"],
                "telemetry": "summary",
                "avoid": ["full transcript echo"],
            },
            "batches": [
                {
                    "id": "batch-1",
                    "task_key": "ui-shell",
                    "recommended_model": "gpt-5.5",
                    "implementation_brief": "x" * 20_000,
                    "file_ownership_hint": "frontend/src/App.tsx",
                }
            ],
            "task_specs": [
                {
                    "task_key": "ui-shell",
                    "title": "Build UI shell",
                    "implementation_brief": "x" * 20_000,
                    "file_ownership_hint": "frontend/src/App.tsx",
                }
            ],
        },
    )

    assert items[0].description == ""
    assert items[0].sprint_execution["sprint_id"] == "sprint-1"
    assert "implementation_brief" not in items[0].sprint_execution
    assert "file_ownership_hint" not in items[0].sprint_execution
    assert "avoid" not in items[0].sprint_execution["runtime_tool_strategy"]


def test_embedded_sprint_plan_summary_compacts_plan_and_design_details():
    summary = _compact_sprint_plan_summary(
        SimpleNamespace(
            content=json.dumps(
                {
                    "schema_version": "1",
                    "plan_id": "plan-1",
                    "mode": "sprint_task_breakdown",
                    "planning_model": "gpt-5.5",
                    "planning_effort": "medium",
                    "runtime_tool_strategy": {
                        "runtime_sdk": "codex_sdk",
                        "primary_tools": ["exec_command"],
                        "telemetry": "summary",
                        "avoid": ["full transcript echo"],
                    },
                    "parallelism": {
                        "strategy": "sequential",
                        "sequential_batches": ["batch-1"],
                        "raw_notes": "x" * 20_000,
                    },
                    "task_specs": [{"implementation_brief": "x" * 20_000}],
                    "batches": [{"id": "batch-1", "implementation_brief": "x" * 20_000}],
                }
            )
        ),
        SimpleNamespace(
            content=json.dumps(
                {
                    "design_id": "design-1",
                    "plan_id": "plan-1",
                    "shared_architecture_decisions": ["Keep one route."],
                    "task_file_ownership_hints": [{"ownership": "x" * 20_000}],
                }
            )
        ),
    )

    assert summary is not None
    assert "task_specs" not in summary.plan_details
    assert "batches" not in summary.plan_details
    assert "avoid" not in summary.runtime_tool_strategy
    assert "raw_notes" not in summary.plan_details["parallelism"]
    assert summary.design_details["shared_concerns"] == ["Keep one route."]
    assert "task_file_ownership_hints" not in summary.design_details


@pytest.mark.asyncio
async def test_embedded_sprint_summary_keeps_blocked_integration_visible_when_tasks_done(
    test_db,
):
    _, factory = test_db

    async with factory() as db:
        project = Project(name="todo-app", language="typescript")
        db.add(project)
        await db.flush()
        feature = Feature(
            id="feature-due-dates",
            project_id=project.id,
            title="Add due dates and Today attention view",
            status=FeatureStatus.SPRINT_PLANNED,
        )
        db.add(feature)
        await db.flush()
        tasks = [
            Task(
                id=f"task-{index}",
                feature_id=feature.id,
                title=f"Task {index}",
                status=TaskStatus.DONE,
                depends_on={"sprint_execution": {"sprint_id": "sprint-1"}},
            )
            for index in range(1, 3)
        ]
        db.add_all(tasks)
        sprint = Sprint(
            id="sprint-1",
            project_id=project.id,
            label="Sprint 1",
            phase="blocked",
            approved_feature_ids=[feature.id],
            generated_task_ids=[task.id for task in tasks],
            verification_status="blocked",
            verification_evidence={
                "status": "passed",
                "sprint_merge_error": "local app checkout still has tracked non-guidance changes",
            },
        )
        db.add(sprint)
        await db.commit()

        summary = await _build_sprint_summary(db, sprint, tasks)

    assert summary is not None
    assert summary.active_phase == "blocked"
    assert summary.verification_status == "blocked"
