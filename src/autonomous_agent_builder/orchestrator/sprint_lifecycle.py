"""Sprint branch management extracted from orchestrator."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Feature,
    FeatureStatus,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.orchestrator.failure_diagnosis import diagnose_task_failure
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    GitRunner as _GitRunner,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    _status_path,
    clean_project_runtime_guidance_for_git_operation,
    project_runtime_guidance_snapshot,
    restore_project_runtime_guidance_snapshot,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    non_guidance_status_lines as _non_guidance_status_lines,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    is_fast_forward_divergence,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    tracked_overwrite_paths as parse_tracked_overwrite_paths,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    untracked_overwrite_paths as parse_untracked_overwrite_paths,
)
from autonomous_agent_builder.services.async_subprocess import run_bounded_subprocess
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY

log = structlog.get_logger()
_ORCHESTRATOR_GIT_TIMEOUT_SECONDS = 30.0


def _task_status_value(task: Task) -> str:
    status = getattr(task, "status", "")
    return status.value if hasattr(status, "value") else str(status)


async def sprint_project_has_remote(repo_root: Path) -> bool:
    """Return True when ``repo_root`` is a git repo with at least one remote."""
    result = await run_bounded_subprocess(
        "git",
        "remote",
        cwd=str(repo_root),
        timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
        label="orchestrator git remote",
    )
    return result.returncode == 0 and bool(result.stdout.strip())


async def sprint_stash_dirty_paths(
    run_git: _GitRunner,
    status_lines: list[str],
) -> list[str]:
    dirty_paths: list[str] = []
    for line in status_lines:
        if len(line) < 4 or line[:2] in {" D", "D "}:
            continue
        path = _status_path(line)
        if path and path not in dirty_paths:
            dirty_paths.append(path)
    if not dirty_paths:
        return []
    stash_code, stash_output = await run_git(
        "stash",
        "push",
        "-m",
        "builder: preserve local checkout changes after sprint integration",
        "--",
        *dirty_paths,
    )
    if stash_code != 0:
        log.warning(
            "sprint_checkout_stash_dirty_paths_failed",
            paths=dirty_paths,
            output=stash_output.strip(),
        )
        return []
    log.info("sprint_checkout_stashed_dirty_paths", paths=dirty_paths)
    return dirty_paths


async def sprint_restore_missing_paths(
    run_git: _GitRunner,
    status_lines: list[str],
) -> list[str]:
    restorable: list[str] = []
    for line in status_lines:
        if len(line) < 4 or line[:2] not in {" D", "D "}:
            return []
        path = _status_path(line)
        if not path:
            return []
        exists_code, _ = await run_git("cat-file", "-e", f"HEAD:{path}")
        if exists_code != 0:
            return []
        restorable.append(path)
    if not restorable:
        return []
    checkout_code, checkout_output = await run_git("checkout", "--", *restorable)
    if checkout_code != 0:
        log.warning(
            "sprint_checkout_restore_missing_paths_failed",
            paths=restorable,
            output=checkout_output.strip(),
        )
        return []
    log.info("sprint_checkout_restored_missing_paths", paths=restorable)
    return restorable


async def sprint_verify_clean_after_merge(run_git: _GitRunner) -> str | None:
    status_code, status_output = await run_git(
        "status",
        "--short",
        "--untracked-files=no",
    )
    if status_code != 0:
        return (
            "Sprint completion failed: could not inspect post-merge checkout: "
            f"{status_output.strip()}"
        )
    dirty_lines = _non_guidance_status_lines(status_output)
    if not dirty_lines:
        return None
    restored = await sprint_restore_missing_paths(run_git, dirty_lines)
    if restored:
        status_code, status_output = await run_git(
            "status",
            "--short",
            "--untracked-files=no",
        )
        if status_code != 0:
            return (
                "Sprint completion failed: could not inspect restored checkout: "
                f"{status_output.strip()}"
            )
        dirty_lines = _non_guidance_status_lines(status_output)
        if not dirty_lines:
            return None
    stashed = await sprint_stash_dirty_paths(run_git, dirty_lines)
    if stashed:
        status_code, status_output = await run_git(
            "status",
            "--short",
            "--untracked-files=no",
        )
        if status_code != 0:
            return (
                "Sprint completion failed: could not inspect stashed checkout: "
                f"{status_output.strip()}"
            )
        dirty_lines = _non_guidance_status_lines(status_output)
        if not dirty_lines:
            return None
    preview = "; ".join(dirty_lines[:10])
    if len(dirty_lines) > 10:
        preview += f"; ... {len(dirty_lines) - 10} more"
    return (
        "Sprint completion failed: local app checkout still has tracked "
        f"non-guidance changes after sprint merge: {preview}"
    )


async def sprint_maybe_ff_merge(sprint: Sprint, repo_root: Path) -> str | None:
    """Local-app sprint completion: ff-merge sprint branch into main.

    Returns an error string on failure or ``None`` on success / no-op.
    Idempotent — if the sprint branch is already at the same commit as
    main (or no sprint branch exists), this is a no-op.
    """
    branch = sprint.branch
    if not branch or not repo_root.exists():
        return None

    async def run_git(*args: str) -> tuple[int, str]:
        result = await run_bounded_subprocess(
            "git",
            *args,
            cwd=str(repo_root),
            timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
            label="sprint merge git",
        )
        return result.returncode, result.output

    head_code, _ = await run_git("rev-parse", "--verify", "HEAD")
    if head_code != 0:
        return None
    guidance_snapshot = project_runtime_guidance_snapshot(repo_root)
    clean_error = await clean_project_runtime_guidance_for_git_operation(run_git, guidance_snapshot)
    if clean_error:
        return clean_error
    checkout_code, checkout_output = await run_git("checkout", "main")
    if checkout_code != 0:
        return f"Sprint completion failed: could not check out main: {checkout_output.strip()}"

    async def merge_cleaning_untracked() -> tuple[int, str]:
        merge_code, merge_output = await run_git("merge", "--ff-only", branch)
        if merge_code == 0:
            return merge_code, merge_output
        tracked_overwrite_paths = parse_tracked_overwrite_paths(merge_output)
        if tracked_overwrite_paths:
            stash_code, stash_output = await run_git(
                "stash",
                "push",
                "-m",
                f"builder: preserve local changes before integrating {branch}",
                "--",
                *tracked_overwrite_paths,
            )
            if stash_code != 0:
                return stash_code, (
                    "Integration failed: could not preserve local target files "
                    f"before merge: {stash_output.strip()}"
                )
            return await run_git("merge", "--ff-only", branch)
        untracked_overwrite_paths = parse_untracked_overwrite_paths(merge_output)
        if not untracked_overwrite_paths:
            return merge_code, merge_output
        clean_code, clean_output = await run_git(
            "clean",
            "-f",
            "--",
            *untracked_overwrite_paths,
        )
        if clean_code != 0:
            return clean_code, (
                "Sprint completion failed: could not prepare untracked target files "
                f"before merge: {clean_output.strip()}"
            )
        return await run_git("merge", "--ff-only", branch)

    merge_code, merge_output = await merge_cleaning_untracked()
    if merge_code != 0 and is_fast_forward_divergence(merge_output):
        branch_checkout_code, branch_checkout_output = await run_git("checkout", branch)
        if branch_checkout_code != 0:
            return (
                f"Sprint completion failed: could not check out sprint branch "
                f"{branch}: {branch_checkout_output.strip()}"
            )
        rebase_code, rebase_output = await run_git("rebase", "main")
        if rebase_code != 0:
            await run_git("rebase", "--abort")
            return (
                f"Sprint completion failed: could not rebase sprint branch "
                f"{branch} onto main: {rebase_output.strip()}"
            )
        checkout_code, checkout_output = await run_git("checkout", "main")
        if checkout_code != 0:
            return (
                f"Sprint completion failed: could not check out main after rebase: "
                f"{checkout_output.strip()}"
            )
        merge_code, merge_output = await merge_cleaning_untracked()
    if merge_code != 0:
        return (
            f"Sprint completion failed: could not fast-forward main from "
            f"{branch}: {merge_output.strip()}"
        )
    restore_error = await restore_project_runtime_guidance_snapshot(
        repo_root, guidance_snapshot, run_git
    )
    if restore_error:
        return restore_error
    dirty_error = await sprint_verify_clean_after_merge(run_git)
    if dirty_error:
        return dirty_error
    log.info(
        "sprint_branch_ff_merged_to_main",
        sprint_id=sprint.id,
        branch=branch,
    )
    return None


async def sprint_verify_materialized_checkout(
    orchestrator: Any,
    sprint: Sprint,
    task: Task,
    repo_root: Path,
    base_evidence: dict[str, Any],
) -> str | None:
    """Run final deterministic proof in the actual app checkout before shipping."""
    if not repo_root.exists():
        return None
    success, output = await orchestrator._record_deterministic_build_verification(
        task,
        str(repo_root),
    )
    if success:
        base_evidence["materialized_checkout_verification"] = {
            "status": "passed",
            "command": "builder script run build_verify --json",
            "project_root": str(repo_root),
            "output": output,
            "completed_at": datetime.now(UTC).isoformat(),
        }
        return None
    error = f"final_checkout_build_failed: {output}"
    task.status = TaskStatus.BLOCKED
    task.blocked_reason = error
    task.updated_at = datetime.now(UTC)
    sprint.phase = SprintPhase.BLOCKED
    sprint.verification_status = "blocked"
    sprint.verification_evidence = {
        **base_evidence,
        "materialized_checkout_verification": {
            "status": "failed",
            "command": "builder script run build_verify --json",
            "project_root": str(repo_root),
            "output": output,
            "completed_at": datetime.now(UTC).isoformat(),
        },
        "sprint_merge_error": error,
    }
    return error


def sprint_changes_summary(sprint: Sprint, sprint_tasks: list[Task]) -> str:
    """Compose a sprint-level PR description from per-task titles."""
    lines = [
        f"Sprint {sprint.label} — consolidated PR",
        "",
        "Tasks delivered in this sprint:",
    ]
    for sprint_task in sprint_tasks:
        title = (sprint_task.title or "").strip() or sprint_task.id
        lines.append(f"- {title}")
    return "\n".join(lines)


def sprint_extract_pr_url(output_text: str) -> str | None:
    """Pluck the first ``https://github.com/.../pull/N`` URL from agent output."""
    match = re.search(r"https://[^\s)]+/pull/\d+", output_text or "")
    return match.group(0) if match else None


async def sprint_open_pr(
    orchestrator: Any,
    sprint: Sprint,
    sprint_tasks: list[Task],
    latest_task: Task,
    repo_root: Path,
    base_evidence: dict[str, Any],
) -> str | None:
    """Run ``pr-creator`` once on the sprint branch and persist the gate.

    Returns an error string on failure or ``None`` on success.
    """
    if not sprint.branch:
        return "sprint branch is not initialized"
    sprint_workspace_path = str(repo_root)
    summary = sprint_changes_summary(sprint, sprint_tasks)
    result = await orchestrator._run_agent(
        latest_task,
        "pr-creator",
        {
            "task_description": summary,
            "gate_results": "PASS",
            "workspace_path": sprint_workspace_path,
        },
    )
    if result.error:
        return diagnose_task_failure(
            result.error,
            workspace_path=sprint_workspace_path,
            result=result,
        )
    pr_url = sprint_extract_pr_url(result.output_text)
    sprint.pr_url = pr_url
    sprint.phase = SprintPhase.PR_REVIEW
    sprint.verification_evidence = {
        **base_evidence,
        "sprint_pr": {
            "branch": sprint.branch,
            "url": pr_url,
            "opened_at": datetime.now(UTC).isoformat(),
            "summary": summary,
        },
    }
    gate = ApprovalGate(
        task_id=None,
        sprint_id=sprint.id,
        gate_type="sprint_pr",
    )
    orchestrator.db.add(gate)
    log.info(
        "sprint_pr_opened",
        sprint_id=sprint.id,
        branch=sprint.branch,
        pr_url=pr_url,
    )
    return None


async def sprint_mark_shipped(orchestrator: Any, task: Task) -> None:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    sprint_payload = depends_on.get(SPRINT_EXECUTION_KEY)
    if not isinstance(sprint_payload, dict):
        return
    sprint_id = str(sprint_payload.get("sprint_id") or "").strip()
    if not sprint_id:
        return

    sprint = await orchestrator.db.get(Sprint, sprint_id)
    if sprint is None:
        return
    generated_ids = [str(task_id) for task_id in (sprint.generated_task_ids or [])]
    if not generated_ids:
        return

    result = await orchestrator.db.execute(select(Task).where(Task.id.in_(generated_ids)))
    sprint_tasks = list(result.scalars().all())
    if len(sprint_tasks) != len(set(generated_ids)):
        return
    if any(
        _task_status_value(sprint_task) != TaskStatus.DONE.value for sprint_task in sprint_tasks
    ):
        return

    acceptance_result = await orchestrator.db.execute(
        select(AgentRun)
        .where(AgentRun.task_id.in_(generated_ids))
        .where(AgentRun.agent_name.in_(["feature-verifier", "feature-acceptance-tests"]))
        .order_by(AgentRun.started_at)
    )
    acceptance_runs = list(acceptance_result.scalars().all())
    acceptance_run_ids = [run.id for run in acceptance_runs if run.status == "completed"]
    approved_feature_ids = [str(feature_id) for feature_id in (sprint.approved_feature_ids or [])]

    verification_summary = (
        "All generated sprint tasks completed; feature-verifier acceptance, "
        "durable feature tests, and final build verification passed."
    )
    sprint.verification_status = "passed"
    base_evidence = {
        "status": "passed",
        "source_task_id": task.id,
        "generated_task_ids": generated_ids,
        "feature_acceptance_run_ids": acceptance_run_ids,
        "summary": verification_summary,
        "completed_at": datetime.now(UTC).isoformat(),
    }

    repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
    repo_root = Path(repo_url).expanduser() if repo_url else Path()
    if repo_url:
        if sprint.branch and repo_root.exists() and await sprint_project_has_remote(repo_root):
            sprint_pr_error = await sprint_open_pr(
                orchestrator, sprint, sprint_tasks, task, repo_root, base_evidence
            )
            if sprint_pr_error:
                evidence = {**base_evidence, "sprint_pr_error": sprint_pr_error}
                sprint.phase = SprintPhase.BLOCKED
                sprint.verification_status = "blocked"
                sprint.verification_evidence = evidence
                log.error(
                    "sprint_pr_open_failed",
                    sprint_id=sprint.id,
                    error=sprint_pr_error,
                )
                return
            return

        merge_error = await sprint_maybe_ff_merge(sprint, repo_root)
        if merge_error:
            sprint.phase = SprintPhase.BLOCKED
            sprint.verification_status = "blocked"
            sprint.verification_evidence = {
                **base_evidence,
                "sprint_merge_error": merge_error,
            }
            log.error(
                "sprint_local_merge_failed",
                sprint_id=sprint.id,
                error=merge_error,
            )
            return

        final_verify_error = await sprint_verify_materialized_checkout(
            orchestrator,
            sprint,
            task,
            repo_root,
            base_evidence,
        )
        if final_verify_error:
            log.error(
                "sprint_materialized_checkout_verify_failed",
                sprint_id=sprint.id,
                task_id=task.id,
                error=final_verify_error,
            )
            return

    sprint.phase = SprintPhase.SHIPPED
    sprint.verification_evidence = base_evidence
    if approved_feature_ids:
        feature_result = await orchestrator.db.execute(
            select(Feature).where(Feature.id.in_(approved_feature_ids))
        )
        for feature in feature_result.scalars().all():
            feature.status = FeatureStatus.DONE
    sprint_context = {
        "sprint_id": sprint.id,
        "sprint_label": sprint.label,
        "source_task_id": task.id,
        "generated_task_ids": generated_ids,
        "approved_feature_ids": approved_feature_ids,
        "phase": SprintPhase.SHIPPED.value,
    }
    try:
        await orchestrator._run_post_ship_optimization_agent(task, sprint, sprint_context)
    except Exception as exc:  # pragma: no cover - defensive shipment guard
        evidence = dict(sprint.verification_evidence or {})
        evidence["optimization_agent"] = {
            "status": "failed",
            "agent_name": "optimization-agent",
            "error": str(exc),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        sprint.verification_evidence = evidence
        log.error(
            "post_ship_optimization_failed",
            sprint_id=sprint.id,
            task_id=task.id,
            error=str(exc),
        )
