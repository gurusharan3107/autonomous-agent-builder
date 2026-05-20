"""Shared task lifecycle recovery helpers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot
from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Feature,
    Sprint,
    Task,
    TaskPhase,
    TaskStatus,
    set_task_status,
)
from autonomous_agent_builder.embedded.scripts.build_verify import BuildVerifyScript
from autonomous_agent_builder.services.provider_limits import (
    clear_provider_limit,
    provider_limit_target_status,
)

_DOC_GATE_BLOCK_PREFIX = "documentation refresh gate blocked:"
_DISPATCH_FAILED_BLOCK_PREFIX = "Dispatch failed:"
_SPRINT_EXECUTION_KEY = "sprint_execution"


def _verifier_output_has_failed_check(output_text: str) -> bool:
    return any(
        "FAIL" in line.split(":", 1)[0] or " FAIL" in line
        for line in str(output_text or "").splitlines()
    )


async def _latest_verifier_reported_failed_check(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(AgentRun.output_text)
        .where(AgentRun.task_id == task.id)
        .where(AgentRun.agent_name == "build-verifier")
        .where(AgentRun.status == "completed")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    output_text = result.scalar_one_or_none()
    return _verifier_output_has_failed_check(str(output_text or ""))


async def _has_completed_build_verifier(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(AgentRun.id)
        .where(AgentRun.task_id == task.id)
        .where(AgentRun.agent_name == "build-verifier")
        .where(AgentRun.status == "completed")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _has_pr_change_request_gate(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(ApprovalGate.id)
        .where(ApprovalGate.task_id == task.id)
        .where(ApprovalGate.gate_type == "pr")
        .where(ApprovalGate.status == "request_changes")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _blocked_sprint_merge_error(task: Task, db: AsyncSession) -> str:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    sprint_payload = depends_on.get(_SPRINT_EXECUTION_KEY)
    if not isinstance(sprint_payload, dict):
        return ""
    sprint_id = str(sprint_payload.get("sprint_id") or "").strip()
    if not sprint_id:
        return ""
    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        return ""
    sprint_phase = sprint.phase.value if hasattr(sprint.phase, "value") else str(sprint.phase or "")
    verification_status = str(sprint.verification_status or "").strip()
    if sprint_phase != "blocked" and verification_status != "blocked":
        return ""
    evidence = sprint.verification_evidence if isinstance(sprint.verification_evidence, dict) else {}
    merge_error = str(evidence.get("sprint_merge_error") or "").strip()
    if not merge_error:
        return ""
    source_task_id = str(evidence.get("source_task_id") or "").strip()
    if source_task_id and source_task_id != task.id:
        return ""
    return merge_error


async def _recovery_target_status(task: Task, db: AsyncSession) -> tuple[str, TaskStatus]:
    task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
    blocked_reason = str(task.blocked_reason or "").strip()

    task_phase = task.phase if isinstance(task.phase, TaskPhase) else TaskPhase(str(task.phase))

    if task_status == TaskStatus.FAILED.value:
        if task_phase == TaskPhase.INTEGRATION:
            return task_status, TaskStatus.BUILD_VERIFY
        if task_phase == TaskPhase.COMPLETE and await _has_completed_build_verifier(task, db):
            return task_status, TaskStatus.BUILD_VERIFY
        if task_phase == TaskPhase.IMPLEMENTATION:
            return task_status, TaskStatus.IMPLEMENTATION
        if task_phase == TaskPhase.VERIFICATION:
            return task_status, TaskStatus.QUALITY_GATES
        return task_status, TaskStatus.PENDING

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        _DOC_GATE_BLOCK_PREFIX
    ):
        return task_status, TaskStatus.QUALITY_GATES

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        _DISPATCH_FAILED_BLOCK_PREFIX
    ):
        if task_phase == TaskPhase.INTEGRATION:
            return task_status, TaskStatus.BUILD_VERIFY
        if task_phase == TaskPhase.VERIFICATION:
            return task_status, TaskStatus.QUALITY_GATES
        if task_phase == TaskPhase.IMPLEMENTATION:
            return task_status, TaskStatus.IMPLEMENTATION
        if task_phase == TaskPhase.DESIGN:
            return task_status, TaskStatus.DESIGN
        return task_status, TaskStatus.PENDING

    if task_status == TaskStatus.BLOCKED.value and await _has_pr_change_request_gate(task, db):
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        "implementation blocked:"
    ):
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        "final_checkout_build_failed:"
    ):
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        "scaffold_failed:"
    ):
        # Scaffold runs at the entry of IMPLEMENTATION; re-running implementation
        # invokes scaffold again deterministically (it skips if a language is
        # already detectable).
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.BLOCKED.value and (
        "FileNotFoundError" in blocked_reason
        or "Gate infrastructure error" in blocked_reason
    ):
        # Legacy gate-infrastructure blocked state from dispatches that pre-date
        # the workspace_scaffold step. Recovering routes back through
        # IMPLEMENTATION, which now runs scaffold first and registers the
        # appropriate gate set before code-gen retries. Closes the "Gate
        # infrastructure error" → 409 Recover dead end (FINDING-15/-16).
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.DONE.value and await _latest_verifier_reported_failed_check(
        task, db
    ):
        return task_status, TaskStatus.BUILD_VERIFY

    if task_status == TaskStatus.DONE.value and await _blocked_sprint_merge_error(task, db):
        return task_status, TaskStatus.BUILD_VERIFY

    if task_status == TaskStatus.PENDING.value and await _has_completed_build_verifier(task, db):
        return task_status, TaskStatus.BUILD_VERIFY

    if task_status == TaskStatus.CAPABILITY_LIMIT.value:
        return task_status, provider_limit_target_status(task)

    raise HTTPException(
        status_code=409,
        detail={
            "code": "task_not_recoverable",
            "task_id": task.id,
            "status": task_status,
            "blocked_reason": task.blocked_reason,
            "message": (
                "Only failed tasks, capability-limit tasks, documentation-gate blocked tasks, "
                "dispatch-failed blocked tasks, scaffold-failed blocked tasks, "
                "gate-infrastructure-error blocked tasks, invalid pending verifier tasks, "
                "or PR change-request blocked tasks can be recovered. "
                "Dispatchable tasks should be dispatched directly."
            ),
        },
    )


async def _enriched_final_checkout_failure(task: Task, db: AsyncSession) -> str:
    result = await db.execute(
        select(Task)
        .where(Task.id == task.id)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .execution_options(populate_existing=True)
    )
    task_with_project = result.scalar_one_or_none()
    project = getattr(getattr(task_with_project, "feature", None), "project", None)
    repo_url = str(getattr(project, "repo_url", "") or "").strip()
    if not repo_url:
        return str(task.blocked_reason or "").strip()
    payload = BuildVerifyScript().run(project_root=repo_url)
    return _build_verify_failure_output(payload) or str(task.blocked_reason or "").strip()


def _build_verify_failure_output(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    checks = data.get("checks") if isinstance(data, dict) else []
    lines: list[str] = []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            command = check.get("command")
            command_text = (
                " ".join(str(part) for part in command)
                if isinstance(command, list)
                else str(command or check.get("code") or "check")
            )
            status = "PASS" if check.get("status") == "passed" else "FAIL"
            stderr = str(check.get("stderr_tail") or "").strip()
            stdout = str(check.get("stdout_tail") or "").strip()
            detail = stderr or stdout
            lines.append(f"{command_text} {status}{': ' + detail[:1800] if detail else ''}")
    return "\n".join(lines)


async def recover_failed_task(task: Task, db: AsyncSession) -> dict[str, str]:
    """Reset a recoverable task so the operator can re-dispatch it."""
    task_status, target_status = await _recovery_target_status(task, db)
    blocked_reason = str(task.blocked_reason or "").strip()

    set_task_status(task, target_status)
    if task_status == TaskStatus.CAPABILITY_LIMIT.value:
        clear_provider_limit(task)
    else:
        merge_error = await _blocked_sprint_merge_error(task, db)
        if merge_error:
            depends_on = dict(task.depends_on) if isinstance(task.depends_on, dict) else {}
            depends_on["recovery_context"] = {
                "reason": f"sprint_merge_error: {merge_error}",
                "target_status": target_status.value,
                "instruction": (
                    "Retry final sprint shipping; Builder should preserve local checkout "
                    "changes, rerun final verification, and update sprint/backlog state."
                ),
            }
            task.depends_on = depends_on
        if (
            "FileNotFoundError" in blocked_reason
            or "Gate infrastructure error" in blocked_reason
            or blocked_reason.startswith("scaffold_failed:")
        ):
            # Force the orchestrator to run scaffold even if a language is
            # already detectable — the actual problem is missing gate tool
            # binaries (ruff/pytest/eslint/etc.), not missing language config.
            # Tracks FINDING-20: should_scaffold's language check isn't
            # sufficient when partial deps exist.
            depends_on = dict(task.depends_on) if isinstance(task.depends_on, dict) else {}
            depends_on["recovery_context"] = {
                "reason": f"force_scaffold: {blocked_reason[:200]}",
                "target_status": target_status.value,
                "force_scaffold": True,
                "instruction": (
                    "A quality gate failed with FileNotFoundError, meaning the "
                    "gate binary is missing. Re-run scaffold to ensure all gate "
                    "tools (ruff/pytest for python, eslint/jest for node, etc.) "
                    "are installed and runnable before retrying code-gen."
                ),
            }
            task.depends_on = depends_on
        if blocked_reason.startswith("final_checkout_build_failed:"):
            enriched_reason = await _enriched_final_checkout_failure(task, db)
            depends_on = dict(task.depends_on) if isinstance(task.depends_on, dict) else {}
            depends_on["recovery_context"] = {
                "reason": f"final_checkout_build_failed: {enriched_reason}",
                "target_status": target_status.value,
                "instruction": (
                    "Fix the generated app source/configuration so the final "
                    "materialized checkout passes npm run build in its real path."
                ),
            }
            task.depends_on = depends_on
        task.blocked_reason = None
        task.blocked_at = None
        task.capability_limit_at = None
        task.capability_limit_reason = None
        task.dead_letter_queued_at = None
        if isinstance(task.depends_on, dict) and "operator_decision" in task.depends_on:
            depends_on = dict(task.depends_on)
            depends_on.pop("operator_decision", None)
            task.depends_on = depends_on
    await db.flush()
    await db.refresh(task)
    await db.commit()
    await publish_board_snapshot(db)
    return {
        "status": "ok",
        "task_id": task.id,
        "previous_status": task_status,
        "current_status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "next_step": f"builder backlog task dispatch {task.id} --yes --json",
    }
