"""Task workspace integration flows for the orchestrator."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.db.models import Task
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import GitRunner
from autonomous_agent_builder.orchestrator.workspace_policy import (
    is_fast_forward_divergence,
    workspace_copy_excluded,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    tracked_overwrite_paths as parse_tracked_overwrite_paths,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    untracked_overwrite_paths as parse_untracked_overwrite_paths,
)

log = structlog.get_logger()

GENERATED_ARTIFACT_PATHS = ("node_modules", "dist", "build")


def git_runner(cwd: Path | str) -> GitRunner:
    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        return proc.returncode, output

    return run_git


async def integrate_task_workspace(orchestrator: Any, task: Task) -> str | None:
    workspace = getattr(task, "workspace", None)
    if not workspace:
        return None
    if getattr(workspace, "is_worktree", False) is not True:
        return await orchestrator._integrate_directory_workspace(task)
    branch = str(getattr(workspace, "branch", "") or "").strip()
    repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
    if not branch or not repo_url:
        return None

    repo_root = Path(repo_url).expanduser()
    if not repo_root.exists():
        return f"Integration failed: repo root does not exist at {repo_root}"

    run_git = git_runner(repo_root)
    guidance_snapshot = orchestrator._project_runtime_guidance_snapshot(repo_root)
    clean_error = await orchestrator._clean_project_runtime_guidance_for_git_operation(
        run_git,
        guidance_snapshot,
    )
    if clean_error:
        return clean_error

    async def fail_after_guidance_clean(message: str) -> str:
        restore_error = await orchestrator._restore_project_runtime_guidance_snapshot(
            repo_root,
            guidance_snapshot,
            run_git,
        )
        if restore_error:
            return f"{message}; additionally {restore_error}"
        return message

    # Sprint integration branches are merged into main once the whole sprint
    # ships; individual tasks fast-forward into the sprint branch first.
    sprint = await orchestrator._resolve_sprint_for_task(task)
    target_branch: str | None = None
    if sprint is not None:
        sprint_branch = await orchestrator._ensure_sprint_branch(sprint, repo_root, run_git)
        if sprint_branch:
            target_branch = sprint_branch
            checkout_code, checkout_output = await run_git("checkout", sprint_branch)
            if checkout_code != 0:
                return await fail_after_guidance_clean(
                    f"Integration failed: could not check out sprint branch "
                    f"{sprint_branch}: {checkout_output.strip()}"
                )
            cleanup_error = await orchestrator._remove_generated_artifacts_from_git_checkout(
                repo_root,
                run_git,
                "chore: remove generated build artifacts from sprint branch",
            )
            if cleanup_error:
                return cleanup_error

    owner_surface_error = await orchestrator._preserve_project_runtime_guidance(
        task,
        str(getattr(workspace, "path", "") or ""),
    )
    if owner_surface_error:
        return owner_surface_error

    async def merge_preserving_local_target_changes() -> tuple[int, str]:
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
            "clean", "-f", "--", *untracked_overwrite_paths
        )
        if clean_code != 0:
            return clean_code, (
                "Integration failed: could not prepare untracked target files "
                f"before merge: {clean_output.strip()}"
            )
        return await run_git("merge", "--ff-only", branch)

    commit_error = await orchestrator._commit_task_workspace_changes(task)
    if commit_error:
        return await fail_after_guidance_clean(commit_error)

    branch_code, branch_output = await run_git("rev-parse", "--verify", branch)
    if branch_code != 0:
        return await fail_after_guidance_clean(
            f"Integration failed: task branch {branch} is missing: {branch_output.strip()}"
        )
    branch_commit = branch_output.strip().splitlines()[0]

    target_ref = target_branch or "main"
    target_ref_path = f"refs/heads/{target_ref}"
    target_code, _ = await run_git("show-ref", "--verify", target_ref_path)
    if target_code != 0:
        update_code, update_output = await run_git("update-ref", target_ref_path, branch_commit)
        if update_code != 0:
            return await fail_after_guidance_clean(
                f"Integration failed: could not initialize {target_ref}: {update_output.strip()}"
            )
        reset_code, reset_output = await run_git("reset", "--hard", target_ref)
        if reset_code != 0:
            return await fail_after_guidance_clean(
                f"Integration failed: could not materialize {target_ref}: {reset_output.strip()}"
            )
        restore_error = await orchestrator._restore_project_runtime_guidance_snapshot(
            repo_root,
            guidance_snapshot,
            run_git,
        )
        if restore_error:
            return restore_error
        log.info("workspace_integrated_unborn_main", task_id=task.id, branch=branch)
        return None

    merge_code, merge_output = await merge_preserving_local_target_changes()
    if merge_code != 0 and is_fast_forward_divergence(merge_output):
        rebase_error = await orchestrator._rebase_task_workspace_for_integration(
            task,
            str(getattr(workspace, "path", "") or ""),
            branch,
            target_branch or "main",
        )
        if rebase_error:
            return await fail_after_guidance_clean(rebase_error)
        owner_surface_error = await orchestrator._preserve_project_runtime_guidance(
            task,
            str(getattr(workspace, "path", "") or ""),
        )
        if owner_surface_error:
            return await fail_after_guidance_clean(owner_surface_error)
        merge_code, merge_output = await merge_preserving_local_target_changes()
    if merge_code != 0:
        return await fail_after_guidance_clean(
            f"Integration failed: could not fast-forward {branch}: {merge_output.strip()}"
        )
    restore_error = await orchestrator._restore_project_runtime_guidance_snapshot(
        repo_root,
        guidance_snapshot,
        run_git,
    )
    if restore_error:
        return restore_error
    log.info(
        "workspace_integrated_fast_forward",
        task_id=task.id,
        branch=branch,
        target=target_branch or "main",
    )
    return None


async def commit_task_workspace_changes(orchestrator: Any, task: Task) -> str | None:
    workspace = getattr(task, "workspace", None)
    workspace_path = str(getattr(workspace, "path", "") or "").strip()
    if not workspace_path:
        return None

    run_workspace_git = git_runner(workspace_path)
    branch = str(getattr(workspace, "branch", "") or "").strip()
    if branch:
        branch_code, branch_output = await run_workspace_git(
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        )
        repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
        workspace_is_repo_root = (
            bool(repo_url)
            and Path(workspace_path).resolve() == Path(repo_url).expanduser().resolve()
        )
        if branch_code != 0 and workspace_is_repo_root:
            return None
        if branch_code == 0 and branch_output.strip() != branch:
            return None

    cleanup_error = await orchestrator._remove_generated_artifacts_from_git_checkout(
        Path(workspace_path),
        run_workspace_git,
        "chore: remove generated build artifacts from task branch",
    )
    if cleanup_error:
        return cleanup_error

    status_code, status_output = await run_workspace_git("status", "--short")
    if status_code != 0:
        return (
            "Integration failed: could not inspect task workspace changes: "
            f"{status_output.strip()}"
        )
    if not status_output.strip():
        return None

    add_code, add_output = await run_workspace_git("add", "--all")
    if add_code != 0:
        return (
            f"Integration failed: could not stage task workspace changes: {add_output.strip()}"
        )

    title = str(getattr(task, "title", "") or "task changes").strip()
    commit_code, commit_output = await run_workspace_git(
        "-c",
        "user.name=Autonomous Agent Builder",
        "-c",
        "user.email=builder@example.local",
        "commit",
        "-m",
        f"feat: {title}",
    )
    if commit_code != 0:
        return (
            "Integration failed: could not commit task workspace changes: "
            f"{commit_output.strip()}"
        )
    return None


async def remove_generated_artifacts_from_git_checkout(
    checkout_root: Path,
    run_git: GitRunner,
    commit_message: str,
) -> str | None:
    removed_paths: list[str] = []
    for relative in GENERATED_ARTIFACT_PATHS:
        path = checkout_root / relative
        if path.is_dir():
            shutil.rmtree(path)
            removed_paths.append(relative)
        elif path.exists():
            path.unlink()
            removed_paths.append(relative)

    rm_code, rm_output = await run_git(
        "rm",
        "-r",
        "--cached",
        "--ignore-unmatch",
        "--",
        *GENERATED_ARTIFACT_PATHS,
    )
    if rm_code != 0:
        return (
            "Integration failed: could not untrack generated build artifacts: "
            f"{rm_output.strip()}"
        )

    status_code, status_output = await run_git(
        "status",
        "--short",
        "--",
        *GENERATED_ARTIFACT_PATHS,
    )
    if status_code != 0:
        return (
            "Integration failed: could not inspect generated artifact cleanup: "
            f"{status_output.strip()}"
        )
    if not status_output.strip():
        return None

    commit_code, commit_output = await run_git(
        "-c",
        "user.name=Autonomous Agent Builder",
        "-c",
        "user.email=builder@example.local",
        "commit",
        "-m",
        commit_message,
    )
    if commit_code != 0:
        return (
            "Integration failed: could not commit generated artifact cleanup: "
            f"{commit_output.strip()}"
        )
    log.info(
        "generated_artifacts_removed_from_checkout",
        checkout_root=str(checkout_root),
        paths=removed_paths or list(GENERATED_ARTIFACT_PATHS),
    )
    return None


async def integrate_directory_workspace(orchestrator: Any, task: Task) -> str | None:
    workspace = getattr(task, "workspace", None)
    workspace_path = Path(str(getattr(workspace, "path", "") or "")).expanduser()
    repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
    if not repo_url:
        return "Integration failed: project repo_url is empty"
    repo_root = Path(repo_url).expanduser()
    if not workspace_path.exists():
        return f"Integration failed: task workspace does not exist at {workspace_path}"
    if not repo_root.exists():
        return f"Integration failed: repo root does not exist at {repo_root}"

    copied = 0
    for source in workspace_path.rglob("*"):
        rel = source.relative_to(workspace_path)
        if workspace_copy_excluded(rel):
            continue
        target = repo_root / rel
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if source.resolve() == target.resolve():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1

    log.info(
        "directory_workspace_integrated",
        task_id=task.id,
        workspace=str(workspace_path),
        repo_root=str(repo_root),
        files_copied=copied,
    )
    return None


async def rebase_task_workspace_for_integration(
    orchestrator: Any,
    task: Task,
    workspace_path: str,
    branch: str,
    target_branch: str = "main",
) -> str | None:
    if not workspace_path:
        return "Integration failed: task workspace path is missing for rebase"
    workspace = Path(workspace_path)
    if not workspace.exists():
        return f"Integration failed: task workspace does not exist at {workspace}"

    run_git = git_runner(workspace)
    checkout_code, checkout_output = await run_git("checkout", branch)
    if checkout_code != 0:
        return (
            f"Integration failed: could not checkout task branch {branch}: "
            f"{checkout_output.strip()}"
        )

    rebase_code, rebase_output = await run_git("rebase", target_branch)
    attempts = 0
    while rebase_code != 0:
        conflict_code, conflict_output = await run_git(
            "diff",
            "--name-only",
            "--diff-filter=U",
        )
        conflict_files = [line.strip() for line in conflict_output.splitlines() if line.strip()]
        if conflict_code != 0 or not conflict_files or attempts >= 2:
            await run_git("rebase", "--abort")
            return (
                "Integration failed: task branch could not rebase onto "
                f"{target_branch}: "
                f"{rebase_output.strip()}"
            )
        attempts += 1
        resolver_error = await orchestrator._run_integration_conflict_resolver(
            task,
            str(workspace),
            branch,
            conflict_files,
            rebase_output,
        )
        if resolver_error:
            await run_git("rebase", "--abort")
            return resolver_error
        marker_error = orchestrator._conflict_markers_remaining(workspace, conflict_files)
        if marker_error:
            await run_git("rebase", "--abort")
            return marker_error
        add_code, add_output = await run_git("add", "--all")
        if add_code != 0:
            await run_git("rebase", "--abort")
            return (
                "Integration failed: could not stage resolved workspace conflicts: "
                f"{add_output.strip()}"
            )
        rebase_code, rebase_output = await run_git(
            "-c",
            "core.editor=true",
            "rebase",
            "--continue",
        )
        if rebase_code != 0:
            log.info(
                "workspace_rebase_continue_waiting",
                branch=branch,
                workspace_path=workspace_path,
                output=rebase_output.strip(),
            )
    log.info("workspace_rebased_for_integration", branch=branch, workspace_path=workspace_path)
    return None


async def run_integration_conflict_resolver(
    orchestrator: Any,
    task: Task,
    workspace_path: str,
    branch: str,
    conflict_files: list[str],
    rebase_output: str,
) -> str | None:
    result = await orchestrator._run_agent(
        task,
        "integration-resolver",
        {
            "task_description": task.description,
            "workspace_path": workspace_path,
            "branch": branch,
            "conflict_files": "\n".join(f"- {path}" for path in conflict_files),
            "rebase_output": rebase_output.strip()[:6000],
        },
    )
    if result.error:
        return f"Integration failed: conflict resolver failed: {result.error}"
    return None


def conflict_markers_remaining(workspace: Path, conflict_files: list[str]) -> str | None:
    marker_pattern = re.compile(r"^(<<<<<<<|=======|>>>>>>>)")
    remaining: list[str] = []
    for relative_file in conflict_files:
        path = workspace / relative_file
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker_pattern.match(line) for line in text.splitlines()):
            remaining.append(relative_file)
    if remaining:
        return (
            "Integration failed: conflict resolver left git conflict markers in "
            + ", ".join(remaining)
        )
    return None
