"""DB-query state helpers for the agent board."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    Approval,
    ApprovalDecision,
    ApprovalGate,
    ApprovalLog,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Sprint,
    Task,
    TaskStatus,
    set_task_status,
    utcnow,
)
from autonomous_agent_builder.embedded.server.agent_workspace_surface import (
    has_generated_app_surface as _has_generated_app_surface,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    normalized_follow_up_message,
)
from autonomous_agent_builder.onboarding import load_onboarding_state
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    load_readiness_status,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_dispatch_sort_key,
    task_is_dispatchable,
)


def _feature_list_path(project_root: Path) -> Path:
    return project_root / ".claude" / "progress" / "feature-list.json"


async def _has_builder_work_state(db: AsyncSession) -> bool:
    for model in (Task, Feature):
        result = await db.execute(select(model.id).limit(1))
        if result.scalar_one_or_none() is not None:
            return True
    return False


async def _has_dispatchable_task_state(db: AsyncSession) -> bool:
    return await _first_dispatchable_task(db) is not None


async def _has_recoverable_task_state(db: AsyncSession) -> bool:
    return await _first_recoverable_task(db) is not None


async def _has_ready_delivery_feature_state(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Feature.id)
        .where(Feature.item_type == BacklogItemType.FEATURE)
        .where(
            Feature.status.in_(
                [
                    FeatureStatus.BACKLOG,
                    FeatureStatus.SPRINT_BACKLOG,
                    FeatureStatus.SPRINT_CANDIDATE,
                    FeatureStatus.SPRINT_PLANNED,
                ]
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _first_dispatchable_task(db: AsyncSession) -> Task | None:
    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.generated_task_ids.is_not(None))
        .order_by(Sprint.created_at.desc())
    )
    for sprint in sprint_result.scalars().all():
        generated_task_ids = [
            str(task_id).strip()
            for task_id in (sprint.generated_task_ids or [])
            if str(task_id).strip()
        ]
        if not generated_task_ids:
            continue
        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.feature).selectinload(Feature.project))
            .where(Task.id.in_(generated_task_ids))
        )
        tasks_by_id = {task.id: task for task in task_result.scalars().all()}
        for task_id in generated_task_ids:
            task = tasks_by_id.get(task_id)
            if task is None or task.status == TaskStatus.DONE:
                continue
            if task_is_dispatchable(task):
                return task
            break

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .order_by(Task.updated_at.desc(), Task.created_at.desc())
    )
    dispatchable_tasks = sorted(
        [task for task in result.scalars().all() if task_is_dispatchable(task)],
        key=task_dispatch_sort_key,
    )
    return dispatchable_tasks[0] if dispatchable_tasks else None


async def _first_recoverable_task(db: AsyncSession) -> Task | None:
    recoverable_statuses = [
        TaskStatus.BLOCKED,
        TaskStatus.CAPABILITY_LIMIT,
        TaskStatus.FAILED,
    ]
    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.generated_task_ids.is_not(None))
        .order_by(Sprint.created_at.desc())
    )
    for sprint in sprint_result.scalars().all():
        generated_task_ids = [
            str(task_id).strip()
            for task_id in (sprint.generated_task_ids or [])
            if str(task_id).strip()
        ]
        if not generated_task_ids:
            continue
        generated_task_order = {task_id: index for index, task_id in enumerate(generated_task_ids)}
        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.feature).selectinload(Feature.project))
            .where(Task.id.in_(generated_task_ids))
            .where(Task.status.in_(recoverable_statuses))
        )
        recoverable_tasks = sorted(
            task_result.scalars().all(),
            key=lambda task: generated_task_order.get(task.id, len(generated_task_order)),
        )
        if recoverable_tasks:
            return recoverable_tasks[0]

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .where(Task.status.in_(recoverable_statuses))
        .order_by(Task.updated_at.desc(), Task.created_at.desc())
    )
    return result.scalars().first()


async def _first_pending_review_approval(db: AsyncSession) -> tuple[ApprovalGate, Task] | None:
    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.generated_task_ids.is_not(None))
        .order_by(Sprint.created_at.desc())
    )
    for sprint in sprint_result.scalars().all():
        generated_task_ids = [
            str(task_id).strip()
            for task_id in (sprint.generated_task_ids or [])
            if str(task_id).strip()
        ]
        if not generated_task_ids:
            continue
        gate_result = await db.execute(
            select(ApprovalGate)
            .options(selectinload(ApprovalGate.task))
            .where(
                ApprovalGate.status == "pending",
                ApprovalGate.gate_type == "pr",
                ApprovalGate.task_id.in_(generated_task_ids),
            )
        )
        gates_by_task_id = {gate.task_id: gate for gate in gate_result.scalars().all()}
        for task_id in generated_task_ids:
            gate = gates_by_task_id.get(task_id)
            if gate is not None and gate.task is not None:
                return gate, gate.task

    result = await db.execute(
        select(ApprovalGate)
        .options(selectinload(ApprovalGate.task))
        .where(ApprovalGate.status == "pending", ApprovalGate.gate_type == "pr")
        .order_by(ApprovalGate.created_at.asc())
        .limit(1)
    )
    gate = result.scalar_one_or_none()
    if gate is None or gate.task is None:
        return None
    return gate, gate.task


async def _approve_review_gate_for_continuation(db: AsyncSession) -> Task | None:
    gate_and_task = await _first_pending_review_approval(db)
    if gate_and_task is None:
        return None
    gate, task = gate_and_task
    approval = Approval(
        approval_gate_id=gate.id,
        approver_email="agent-chat@local",
        decision=ApprovalDecision.APPROVE,
        comment="Approved from Agent chat continuation intent.",
    )
    db.add(approval)
    db.add(
        ApprovalLog(
            task_id=task.id,
            approver_email="agent-chat@local",
            decision=ApprovalDecision.APPROVE,
            reason="Approved from Agent chat continuation intent.",
        )
    )
    gate.status = ApprovalDecision.APPROVE.value
    gate.resolved_at = utcnow()
    set_task_status(task, TaskStatus.BUILD_VERIFY)
    task.blocked_reason = None
    task.blocked_at = None
    await db.flush()
    return task


async def _needs_init_project_bootstrap(project_root: Path, db: AsyncSession) -> bool:
    state = load_onboarding_state(project_root)
    readiness = load_readiness_status(project_root)
    return (
        bool(state.get("ready"))
        and state.get("onboarding_mode") == "forward_engineering"
        and readiness.get("state") == READY_STATE
        and not _feature_list_path(project_root).exists()
        and not await _has_builder_work_state(db)
        and not _has_generated_app_surface(project_root)
    )


def _stream_deltas_are_user_visible(runtime_name: str) -> bool:
    """Return whether runtime chunk deltas should be shown in the Agent transcript.

    The dashboard contract is to show Builder-owned, user-facing transcript text
    without leaking SDK-specific reasoning. Codex app-server deltas can surface
    draft/planning content before the final assistant message is settled, so the
    Agent page should wait for the completed assistant message instead.
    """

    return runtime_name != "codex_sdk"


def _normalized_follow_up_message(user_message: str) -> str:
    return normalized_follow_up_message(user_message)
