"""Approval outcome state transitions for task and sprint gates."""

from __future__ import annotations

from datetime import UTC, datetime

from autonomous_agent_builder.db.models import (
    ApprovalDecision,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    set_task_status,
)


def apply_approval_outcome(
    task: Task,
    gate_type: str,
    decision: ApprovalDecision,
    *,
    reason: str | None = None,
) -> bool:
    """Apply an approval outcome to a task and report whether to dispatch."""
    if decision == ApprovalDecision.APPROVE:
        if gate_type == "planning":
            set_task_status(task, TaskStatus.DESIGN)
        elif gate_type == "design":
            set_task_status(task, TaskStatus.IMPLEMENTATION)
        elif gate_type == "ui_preview":
            # IMP-034b: operator approved the UI prototype preview → proceed to build.
            set_task_status(task, TaskStatus.IMPLEMENTATION)
        elif gate_type == "pr":
            set_task_status(task, TaskStatus.BUILD_VERIFY)
        else:
            return False
        task.blocked_reason = None
        task.blocked_at = None
        return True

    if decision == ApprovalDecision.REQUEST_CHANGES and gate_type == "pr":
        message = reason or "PR changes requested"
        depends_on = dict(task.depends_on or {})
        phase_context = dict(depends_on.get("phase_context") or {})
        phase_context["pr_change_request"] = message
        depends_on["phase_context"] = phase_context
        task.depends_on = depends_on
        task.blocked_reason = None
        set_task_status(task, TaskStatus.IMPLEMENTATION)
        return True

    if decision in (ApprovalDecision.REJECT, ApprovalDecision.REQUEST_CHANGES):
        set_task_status(task, TaskStatus.BLOCKED)
        task.blocked_reason = reason or "Approval rejected"
    return False


def apply_sprint_approval_outcome(
    sprint: Sprint,
    decision: ApprovalDecision,
    *,
    reason: str | None = None,
    sprint_tasks: list[Task] | None = None,
) -> bool:
    """Apply a sprint-level approval outcome and report whether follow-up runs."""
    evidence = dict(sprint.verification_evidence or {})

    if decision == ApprovalDecision.APPROVE:
        sprint.phase = SprintPhase.SHIPPED
        evidence["sprint_pr_approved_at"] = datetime.now(UTC).isoformat()
        if reason:
            evidence["sprint_pr_approval_reason"] = reason
        sprint.verification_evidence = evidence
        return True

    if decision == ApprovalDecision.REQUEST_CHANGES:
        sprint.phase = SprintPhase.VERIFY
        evidence["pr_change_request"] = reason or "PR changes requested"
        evidence["pr_change_request_at"] = datetime.now(UTC).isoformat()
        sprint.verification_evidence = evidence
        for task in sprint_tasks or []:
            set_task_status(task, TaskStatus.IMPLEMENTATION)
            task.blocked_reason = reason or "Sprint PR changes requested"
            task.blocked_at = None
        return True

    if decision == ApprovalDecision.REJECT:
        sprint.phase = SprintPhase.BLOCKED
        evidence["sprint_pr_rejected_at"] = datetime.now(UTC).isoformat()
        evidence["sprint_pr_rejection_reason"] = reason or "Sprint PR rejected"
        sprint.verification_evidence = evidence
    return False
