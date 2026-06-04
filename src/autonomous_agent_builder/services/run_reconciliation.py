"""Recover persisted run state after a builder server restart."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    AgentRun,
    AgentRunEvent,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    utcnow,
)
from autonomous_agent_builder.embedded.scripts.build_verify import BuildVerifyScript
from autonomous_agent_builder.services.async_subprocess import run_bounded_subprocess
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY

_ACTIVE_TASK_STATUSES = {
    TaskStatus.PLANNING,
    TaskStatus.DESIGN,
    TaskStatus.IMPLEMENTATION,
    TaskStatus.QUALITY_GATES,
    TaskStatus.PR_CREATION,
    TaskStatus.BUILD_VERIFY,
}
_RUNTIME_GUIDANCE_PATHS = {"CLAUDE.md", ".claude/CLAUDE.md"}
_IGNORED_UNINTEGRATED_PREFIXES = (
    ".agent-builder/",
    ".claude/",
    ".playwright-cli/",
    ".venv/",
    "build/",
    "dist/",
    "htmlcov/",
    "node_modules/",
    "venv/",
)
_IGNORED_UNINTEGRATED_PATHS = {
    ".coverage",
    ".DS_Store",
    ".env",
    "package-lock.json",
}
_UNINTEGRATED_WORKSPACE_REASON_PREFIX = (
    "Task workspace still has unintegrated changes after Builder marked the task done"
)
_SPRINT_BLOCKING_EVIDENCE_KEYS = {
    "sprint_merge_error",
    "sprint_pr_error",
    "unintegrated_task_workspace",
}
_RECONCILIATION_GIT_TIMEOUT_SECONDS = 30.0


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int:
    if started_at is None:
        return 0
    start = started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return max(int((completed_at - start.astimezone(UTC)).total_seconds() * 1000), 0)


async def reconcile_orphaned_running_agent_runs(db: AsyncSession) -> int:
    """Mark DB-persisted running agent runs as recoverable after startup.

    Agent runs execute inside the server process. After a process restart there
    is no in-memory dispatcher capable of completing rows left in ``running``.
    Leaving them untouched makes the Board show fake active work forever.
    """
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.status == "running")
        .options(selectinload(AgentRun.task).selectinload(Task.agent_runs))
    )
    runs = list(result.scalars().all())
    if not runs:
        return 0

    completed_at = utcnow()
    count = 0
    for run in runs:
        run.status = "failed"
        run.error = (
            "Agent run was interrupted by a builder server restart before it "
            "reported runtime evidence."
        )
        run.completed_at = completed_at
        run.duration_ms = run.duration_ms or _duration_ms(run.started_at, completed_at)
        db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="run_status",
                tool_name="builder",
                tool_input={"reconciled_on_startup": True},
                output_preview=run.error,
                timestamp=completed_at,
            )
        )
        task = run.task
        if task is not None:
            status = (
                task.status if isinstance(task.status, TaskStatus) else TaskStatus(str(task.status))
            )
            latest_run = max(
                list(task.agent_runs or []),
                key=lambda item: item.started_at or datetime.min.replace(tzinfo=UTC),
            )
            if latest_run.id == run.id and status in _ACTIVE_TASK_STATUSES:
                task.status = TaskStatus.FAILED
                task.blocked_reason = run.error
                task.blocked_at = completed_at
        count += 1

    await db.flush()
    return count


async def mark_task_running_agent_runs_failed(
    db: AsyncSession,
    task_id: str,
    reason: str,
    *,
    event_reason: str,
) -> int:
    """Fail running AgentRun rows for a task when dispatch can no longer own them."""
    result = await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).where(AgentRun.status == "running")
    )
    runs = list(result.scalars().all())
    if not runs:
        return 0

    completed_at = utcnow()
    for run in runs:
        run.status = "failed"
        run.error = reason
        run.completed_at = completed_at
        run.duration_ms = run.duration_ms or _duration_ms(run.started_at, completed_at)
        db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="run_status",
                tool_name="builder",
                tool_input={event_reason: True},
                output_preview=reason,
                timestamp=completed_at,
            )
        )
    await db.flush()
    return len(runs)


def _current_status_path(line: str) -> str:
    if len(line) < 4:
        return ""
    return line[3:].strip().split(" -> ")[-1].strip().strip('"')


def _unintegrated_workspace_lines(status_output: str) -> list[str]:
    lines: list[str] = []
    for line in status_output.splitlines():
        path = _current_status_path(line)
        if not path or path in _RUNTIME_GUIDANCE_PATHS:
            continue
        if path in _IGNORED_UNINTEGRATED_PATHS:
            continue
        if any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in _IGNORED_UNINTEGRATED_PREFIXES
        ):
            continue
        lines.append(line)
    return lines


async def _workspace_status(path: str) -> tuple[int, str]:
    result = await run_bounded_subprocess(
        "git",
        "status",
        "--short",
        cwd=path,
        timeout_seconds=_RECONCILIATION_GIT_TIMEOUT_SECONDS,
        label="reconciliation git status",
    )
    return result.returncode, result.output


async def _run_git(repo_root: Path, *args: str) -> tuple[int, str]:
    result = await run_bounded_subprocess(
        "git",
        *args,
        cwd=str(repo_root),
        timeout_seconds=_RECONCILIATION_GIT_TIMEOUT_SECONDS,
        label="reconciliation git",
    )
    return result.returncode, result.output


def _non_guidance_tracked_status_lines(status_output: str) -> list[str]:
    lines: list[str] = []
    for line in status_output.splitlines():
        path = _current_status_path(line)
        if path and path not in _RUNTIME_GUIDANCE_PATHS:
            lines.append(line)
    return lines


async def _restore_missing_head_paths(repo_root: Path, status_lines: list[str]) -> bool:
    restorable: list[str] = []
    for line in status_lines:
        if len(line) < 4 or line[:2] not in {" D", "D "}:
            return False
        path = _current_status_path(line)
        if not path:
            return False
        exists_code, _ = await _run_git(repo_root, "cat-file", "-e", f"HEAD:{path}")
        if exists_code != 0:
            return False
        restorable.append(path)
    if not restorable:
        return False
    checkout_code, _ = await _run_git(repo_root, "checkout", "--", *restorable)
    return checkout_code == 0


def _sprint_id_for_task(task: Task) -> str:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    payload = depends_on.get(SPRINT_EXECUTION_KEY)
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("sprint_id") or "").strip()


async def reconcile_completed_tasks_with_unintegrated_workspace_changes(
    db: AsyncSession,
) -> int:
    """Block completed tasks whose worktree still contains unintegrated output.

    A task cannot be considered shipped if its task worktree still has source or
    package changes after completion. That means Builder failed to commit and
    integrate the agent output before marking the task done.
    """
    result = await db.execute(
        select(Task)
        .where(
            (Task.status == TaskStatus.DONE)
            | (
                (Task.status == TaskStatus.FAILED)
                & Task.blocked_reason.startswith(_UNINTEGRATED_WORKSPACE_REASON_PREFIX)
            )
        )
        .options(selectinload(Task.workspace))
    )
    tasks = list(result.scalars().all())
    if not tasks:
        return 0

    reconciled_at = utcnow()
    count = 0
    for task in tasks:
        workspace = task.workspace
        if workspace is None or workspace.is_worktree is not True:
            continue
        workspace_path = str(workspace.path or "").strip()
        if not workspace_path or not Path(workspace_path).exists():
            continue
        status_code, status_output = await _workspace_status(workspace_path)
        if status_code != 0:
            continue
        dirty_lines = _unintegrated_workspace_lines(status_output)
        if not dirty_lines:
            if task.status == TaskStatus.FAILED and (task.blocked_reason or "").startswith(
                _UNINTEGRATED_WORKSPACE_REASON_PREFIX
            ):
                task.status = TaskStatus.DONE
                task.blocked_reason = None
                task.blocked_at = None
                count += 1
            continue

        preview = "; ".join(dirty_lines[:10])
        if len(dirty_lines) > 10:
            preview += f"; ... {len(dirty_lines) - 10} more"
        reason = f"{_UNINTEGRATED_WORKSPACE_REASON_PREFIX}: {preview}"
        task.status = TaskStatus.FAILED
        task.blocked_reason = reason
        task.blocked_at = reconciled_at

        sprint_id = _sprint_id_for_task(task)
        if sprint_id:
            sprint = await db.get(Sprint, sprint_id)
            if sprint is not None and sprint.phase == SprintPhase.SHIPPED:
                evidence = sprint.verification_evidence
                if not isinstance(evidence, dict):
                    evidence = {}
                sprint.phase = SprintPhase.BLOCKED
                sprint.verification_status = "blocked"
                sprint.verification_evidence = {
                    **evidence,
                    "status": "blocked",
                    "unintegrated_task_workspace": {
                        "task_id": task.id,
                        "workspace_path": workspace_path,
                        "status_lines": dirty_lines[:20],
                        "reconciled_at": reconciled_at.isoformat(),
                    },
                }
        count += 1

    await db.flush()
    return count


async def reconcile_blocked_sprints_with_materialized_main(db: AsyncSession) -> int:
    """Clear stale blocked sprint state when durable evidence proves shipment.

    Older integration code could fast-forward ``main`` but leave the checkout
    with tracked deletions, causing a false blocked sprint with no task-level
    recovery left. If all generated tasks are done and ``main`` equals the
    sprint branch, materialize the missing HEAD files and restore shipped state.

    Some older runs also persisted ``phase=blocked`` after all generated tasks
    finished while the verification evidence already recorded ``status=passed``.
    That stale state confuses agent answers even when the dashboard projection
    can infer a shipped phase from task rows, so reconcile it here too.
    """
    result = await db.execute(
        select(Sprint)
        .where(Sprint.phase == SprintPhase.BLOCKED)
        .options(selectinload(Sprint.project))
    )
    sprints = list(result.scalars().all())
    count = 0
    for sprint in sprints:
        evidence = (
            sprint.verification_evidence if isinstance(sprint.verification_evidence, dict) else {}
        )
        task_ids = [str(task_id) for task_id in (sprint.generated_task_ids or []) if str(task_id)]
        if evidence.get("status") == "passed" and task_ids:
            blocking_evidence = any(evidence.get(key) for key in _SPRINT_BLOCKING_EVIDENCE_KEYS)
            materialized = evidence.get("materialized_checkout_verification")
            materialized_failed = (
                isinstance(materialized, dict) and materialized.get("status") == "failed"
            )
            task_result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
            tasks = list(task_result.scalars().all())
            if (
                not blocking_evidence
                and not materialized_failed
                and len(tasks) == len(set(task_ids))
                and all(task.status == TaskStatus.DONE for task in tasks)
            ):
                sprint.phase = SprintPhase.SHIPPED
                sprint.verification_status = "passed"
                sprint.verification_evidence = {
                    **evidence,
                    "status": "passed",
                    "stale_blocked_state_reconciled_at": utcnow().isoformat(),
                }
                count += 1
                continue

        merge_error = str(evidence.get("sprint_merge_error") or "")
        if "local app checkout still has tracked non-guidance changes" not in merge_error:
            continue
        if not sprint.branch or not sprint.generated_task_ids:
            continue
        repo_url = str(getattr(sprint.project, "repo_url", "") or "").strip()
        repo_root = Path(repo_url).expanduser()
        if not repo_root.exists():
            continue
        main_code, main_sha = await _run_git(repo_root, "rev-parse", "main")
        branch_code, branch_sha = await _run_git(repo_root, "rev-parse", sprint.branch)
        if main_code != 0 or branch_code != 0 or main_sha.strip() != branch_sha.strip():
            continue
        task_result = await db.execute(select(Task).where(Task.id.in_(sprint.generated_task_ids)))
        tasks = list(task_result.scalars().all())
        if len(tasks) != len(set(sprint.generated_task_ids)):
            continue
        if any(task.status != TaskStatus.DONE for task in tasks):
            continue
        status_code, status_output = await _run_git(
            repo_root,
            "status",
            "--short",
            "--untracked-files=no",
        )
        if status_code != 0:
            continue
        dirty_lines = _non_guidance_tracked_status_lines(status_output)
        if dirty_lines and not await _restore_missing_head_paths(repo_root, dirty_lines):
            continue
        status_code, status_output = await _run_git(
            repo_root,
            "status",
            "--short",
            "--untracked-files=no",
        )
        if status_code != 0 or _non_guidance_tracked_status_lines(status_output):
            continue
        sprint.phase = SprintPhase.SHIPPED
        sprint.verification_status = "passed"
        sprint.verification_evidence = {
            **evidence,
            "status": "passed",
            "sprint_merge_error": None,
            "checkout_materialized_at": utcnow().isoformat(),
        }
        count += 1

    await db.flush()
    return count


async def reconcile_shipped_sprints_with_failed_materialized_checkout(
    db: AsyncSession,
) -> int:
    """Re-block shipped sprints when the actual app checkout no longer verifies."""
    result = await db.execute(
        select(Sprint)
        .where(Sprint.phase == SprintPhase.SHIPPED)
        .options(selectinload(Sprint.project))
    )
    sprints = list(result.scalars().all())
    count = 0
    for sprint in sprints:
        evidence = (
            sprint.verification_evidence if isinstance(sprint.verification_evidence, dict) else {}
        )
        materialized = evidence.get("materialized_checkout_verification")
        if isinstance(materialized, dict) and materialized.get("status") == "passed":
            continue
        repo_url = str(getattr(sprint.project, "repo_url", "") or "").strip()
        repo_root = Path(repo_url).expanduser()
        if not repo_root.exists():
            continue
        task_ids = [str(task_id) for task_id in (sprint.generated_task_ids or []) if str(task_id)]
        if not task_ids:
            continue
        task_result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
        tasks = list(task_result.scalars().all())
        if len(tasks) != len(set(task_ids)):
            continue
        if any(task.status != TaskStatus.DONE for task in tasks):
            continue
        payload = BuildVerifyScript().run(project_root=str(repo_root))
        if bool(payload.get("success", False)):
            evidence["materialized_checkout_verification"] = {
                "status": "passed",
                "command": "builder script run build_verify --json",
                "project_root": str(repo_root),
                "completed_at": utcnow().isoformat(),
            }
            sprint.verification_evidence = evidence
            continue
        output = _build_verify_reconciliation_output(payload)
        source_task_id = str(evidence.get("source_task_id") or task_ids[-1])
        task = next((item for item in tasks if item.id == source_task_id), tasks[-1])
        reason = f"final_checkout_build_failed: {output}"
        task.status = TaskStatus.BLOCKED
        task.blocked_reason = reason
        task.blocked_at = utcnow()
        sprint.phase = SprintPhase.BLOCKED
        sprint.verification_status = "blocked"
        sprint.verification_evidence = {
            **evidence,
            "status": "blocked",
            "materialized_checkout_verification": {
                "status": "failed",
                "command": "builder script run build_verify --json",
                "project_root": str(repo_root),
                "output": output,
                "completed_at": utcnow().isoformat(),
            },
            "sprint_merge_error": reason,
        }
        count += 1

    await db.flush()
    return count


def _build_verify_reconciliation_output(payload: dict) -> str:
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
    return "\n".join(lines) or str(payload.get("error") or "build_verify failed")
