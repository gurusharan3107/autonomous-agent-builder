from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
from autonomous_agent_builder.services.autonomous_orchestration import (
    choose_followup_after_dispatch,
)
from autonomous_agent_builder.services.provider_limits import mark_provider_limit


@pytest.mark.asyncio
async def test_choose_followup_dispatches_next_serial_task(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="Orchestration", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Autonomous feature",
            description="Exercise serial followup",
            status=FeatureStatus.QUEUED,
        )
        db.add(feature)
        await db.flush()
        completed = Task(
            feature_id=feature.id,
            title="Done task",
            description="Already shipped",
            status=TaskStatus.DONE,
        )
        pending = Task(
            feature_id=feature.id,
            title="Next task",
            description="Should start next",
            status=TaskStatus.PENDING,
        )
        db.add_all([completed, pending])
        await db.flush()

        decision = await choose_followup_after_dispatch(db, completed)

        assert decision.action == "dispatch"
        assert decision.reason == "next_serial_task"
        assert decision.task_id == pending.id


@pytest.mark.asyncio
async def test_choose_followup_stops_at_feature_boundary(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="Orchestration", language="python")
        db.add(project)
        await db.flush()
        completed_feature = Feature(
            project_id=project.id,
            title="Completed feature",
            description="Done",
            status=FeatureStatus.QUEUED,
            priority=0,
        )
        next_feature = Feature(
            project_id=project.id,
            title="Next feature",
            description="Continue sprint",
            status=FeatureStatus.QUEUED,
            priority=1,
        )
        db.add_all([completed_feature, next_feature])
        await db.flush()
        completed = Task(
            feature_id=completed_feature.id,
            title="Done task",
            description="Already shipped",
            status=TaskStatus.DONE,
        )
        next_task = Task(
            feature_id=next_feature.id,
            title="Next project task",
            description="Should continue sprint",
            status=TaskStatus.PENDING,
        )
        db.add_all([completed, next_task])
        await db.flush()

        decision = await choose_followup_after_dispatch(db, completed)

        assert decision.action == "idle"
        assert decision.reason == "feature_complete"
        assert decision.task_id is None


@pytest.mark.asyncio
async def test_choose_followup_continues_same_task_next_phase(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="Orchestration", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Autonomous feature",
            description="Exercise phase continuation",
            status=FeatureStatus.QUEUED,
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Current task",
            description="Continue into gates",
            status=TaskStatus.QUALITY_GATES,
            phase=TaskPhase.VERIFICATION,
        )
        db.add(task)
        await db.flush()

        decision = await choose_followup_after_dispatch(db, task)

        assert decision.action == "dispatch"
        assert decision.reason == "same_task_next_phase_quality_gates"
        assert decision.task_id == task.id


@pytest.mark.asyncio
async def test_choose_followup_waits_when_feature_has_review_block(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="Orchestration", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Autonomous feature",
            description="Exercise serial followup",
            status=FeatureStatus.QUEUED,
        )
        db.add(feature)
        await db.flush()
        completed = Task(
            feature_id=feature.id,
            title="Done task",
            description="Already shipped",
            status=TaskStatus.DONE,
        )
        review_pending = Task(
            feature_id=feature.id,
            title="Review task",
            description="Needs approval",
            status=TaskStatus.REVIEW_PENDING,
        )
        pending = Task(
            feature_id=feature.id,
            title="Next task",
            description="Should wait",
            status=TaskStatus.PENDING,
        )
        db.add_all([completed, review_pending, pending])
        await db.flush()

        decision = await choose_followup_after_dispatch(db, completed)

        assert decision.action == "idle"
        assert decision.reason == "feature_has_open_task"
        assert decision.task_id is None


@pytest.mark.asyncio
async def test_choose_followup_recovers_ready_provider_limit_task(test_db) -> None:
    _, factory = test_db
    now = datetime(2026, 4, 29, 10, 0, tzinfo=UTC)
    async with factory() as db:
        project = Project(name="Orchestration", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Autonomous feature",
            description="Exercise provider resume",
            status=FeatureStatus.QUEUED,
        )
        db.add(feature)
        await db.flush()
        current = Task(
            feature_id=feature.id,
            title="Current task",
            description="Still blocked",
            status=TaskStatus.QUALITY_GATES,
        )
        limited = Task(
            feature_id=feature.id,
            title="Limited task",
            description="Resume after reset",
            status=TaskStatus.IMPLEMENTATION,
            phase=TaskPhase.IMPLEMENTATION,
        )
        db.add_all([current, limited])
        await db.flush()
        mark_provider_limit(
            limited,
            reason="SDK limit: provider_limit",
            output_text="You've hit your limit - resets in 30 minutes",
            now=now,
        )
        await db.flush()

        decision = await choose_followup_after_dispatch(
            db,
            current,
            now=now + timedelta(minutes=31),
        )

        assert decision.action == "dispatch"
        assert decision.reason == "provider_limit_reset"
        assert decision.task_id == limited.id
        assert limited.status == TaskStatus.IMPLEMENTATION
        assert limited.provider_limit is None


@pytest.mark.asyncio
async def test_choose_followup_marks_sprint_blocked_when_all_tasks_failed(test_db) -> None:
    """P23: sprint stays in implementation after all active tasks fail → must go blocked."""
    _, factory = test_db
    async with factory() as db:
        project = Project(name="Sprint stall test", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="GitHub auth",
            status=FeatureStatus.SPRINT_PLANNED,
        )
        db.add(feature)
        await db.flush()
        # Three tasks that all failed integration
        failed1 = Task(feature_id=feature.id, title="Set up domain model", status=TaskStatus.FAILED)
        failed2 = Task(feature_id=feature.id, title="Build UI shell", status=TaskStatus.FAILED)
        failed3 = Task(feature_id=feature.id, title="Implement core behavior", status=TaskStatus.FAILED)
        # Two tasks still pending (blocked by failed deps)
        pending1 = Task(feature_id=feature.id, title="Wire persistence", status=TaskStatus.PENDING)
        pending2 = Task(feature_id=feature.id, title="Verify feature", status=TaskStatus.PENDING)
        db.add_all([failed1, failed2, failed3, pending1, pending2])
        await db.flush()

        sprint = Sprint(
            project_id=project.id,
            label="Sprint 2",
            phase=SprintPhase.IMPLEMENTATION,
            approved_feature_ids=[feature.id],
            generated_task_ids=[failed1.id, failed2.id, failed3.id, pending1.id, pending2.id],
        )
        db.add(sprint)
        await db.flush()

        # Simulate the last failed task completing build_verify → FAILED
        decision = await choose_followup_after_dispatch(db, failed3)

        assert decision.action == "idle"
        assert decision.reason == "task_status_failed"
        # Sprint must have transitioned to blocked
        assert sprint.phase == SprintPhase.BLOCKED
        assert sprint.verification_status == "blocked"
        assert sprint.verification_evidence is not None
        assert sprint.verification_evidence["blocked_reason"] == "all_active_tasks_failed"
        assert set(sprint.verification_evidence["failed_task_ids"]) == {failed1.id, failed2.id, failed3.id}
        assert set(sprint.verification_evidence["pending_task_ids"]) == {pending1.id, pending2.id}


@pytest.mark.asyncio
async def test_choose_followup_does_not_mark_sprint_stalled_when_task_in_progress(test_db) -> None:
    """P23 guard: sprint should NOT go blocked while another task is still dispatching."""
    _, factory = test_db
    async with factory() as db:
        project = Project(name="In-progress guard", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Notes feature",
            status=FeatureStatus.SPRINT_PLANNED,
        )
        db.add(feature)
        await db.flush()
        failed = Task(feature_id=feature.id, title="Failed task", status=TaskStatus.FAILED)
        in_prog = Task(feature_id=feature.id, title="Still running", status=TaskStatus.IMPLEMENTATION)
        pending = Task(feature_id=feature.id, title="Blocked pending", status=TaskStatus.PENDING)
        db.add_all([failed, in_prog, pending])
        await db.flush()

        sprint = Sprint(
            project_id=project.id,
            label="Sprint 2",
            phase=SprintPhase.IMPLEMENTATION,
            approved_feature_ids=[feature.id],
            generated_task_ids=[failed.id, in_prog.id, pending.id],
        )
        db.add(sprint)
        await db.flush()

        await choose_followup_after_dispatch(db, failed)

        # Sprint must remain in implementation — in_prog task is still running
        assert sprint.phase == SprintPhase.IMPLEMENTATION
