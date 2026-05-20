"""Workspace manager — git worktree per task.

Each task gets an isolated worktree branched from the target repo.
On failure, the worktree is rolled back. On completion, the branch
is ready for PR creation.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

from autonomous_agent_builder.config import get_settings

log = structlog.get_logger()


class WorkspaceManager:
    """Manages isolated git worktrees for agent tasks."""

    def __init__(self, workspace_root: str | None = None):
        settings = get_settings()
        self.root = Path(workspace_root or settings.workspace_root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def create_workspace(
        self,
        repo_path: str,
        task_id: str,
        branch_name: str | None = None,
        start_point: str | None = None,
    ) -> WorkspaceInfo:
        """Create an isolated worktree for a task.

        Args:
            repo_path: Path to the main repository.
            task_id: Task ID (used for workspace naming).
            branch_name: Branch name (default: task/<task_id>).
            start_point: Optional ref to branch from (default: HEAD). Used by
                the sprint-PR refactor so per-task branches start from the
                sprint integration branch instead of HEAD/main.
        """
        import asyncio

        branch = branch_name or f"task/{task_id}"
        workspace_path = self.root / task_id

        if workspace_path.exists():
            log.warning("workspace_exists", task_id=task_id, path=str(workspace_path))
            return WorkspaceInfo(
                path=str(workspace_path),
                branch=branch,
                is_worktree=True,
            )

        # Temp-backed task worktrees can disappear between runs while git still
        # retains stale admin entries and the task branch itself. Prune first,
        # then reattach the existing branch when present instead of trying to
        # recreate it unconditionally.
        prune_proc = await asyncio.create_subprocess_exec(
            "git",
            "worktree",
            "prune",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await prune_proc.communicate()

        branch_exists_proc = await asyncio.create_subprocess_exec(
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await branch_exists_proc.communicate()
        branch_exists = branch_exists_proc.returncode == 0

        # Create git worktree. ``git worktree add -b <branch> <path> [<start_point>]``
        # branches from HEAD when ``start_point`` is omitted; supplying a sprint
        # branch routes per-task work onto the sprint integration branch. When
        # the task branch already exists, reuse it so resumed tasks can heal a
        # missing temp worktree without losing branch history.
        worktree_args = ["git", "worktree", "add"]
        if branch_exists:
            worktree_args.extend([str(workspace_path), branch])
        else:
            worktree_args.extend(["-b", branch, str(workspace_path)])
            if start_point:
                worktree_args.append(start_point)
        proc = await asyncio.create_subprocess_exec(
            *worktree_args,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error = stderr.decode()
            log.error("workspace_create_failed", task_id=task_id, error=error)
            raise WorkspaceError(f"Failed to create worktree: {error}")

        log.info("workspace_created", task_id=task_id, path=str(workspace_path), branch=branch)

        return WorkspaceInfo(
            path=str(workspace_path),
            branch=branch,
            is_worktree=True,
        )

    async def cleanup_workspace(self, repo_path: str, workspace_path: str) -> None:
        """Remove a worktree and its branch."""
        import asyncio

        # Remove git worktree
        proc = await asyncio.create_subprocess_exec(
            "git",
            "worktree",
            "remove",
            "--force",
            workspace_path,
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Fallback: remove directory if worktree remove fails
        wp = Path(workspace_path)
        if wp.exists():
            shutil.rmtree(wp, ignore_errors=True)

        log.info("workspace_cleaned", path=workspace_path)

    async def reset_workspace(self, workspace_path: str) -> None:
        """Reset workspace to clean state (on gate failure)."""
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            "git",
            "checkout",
            ".",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git",
            "clean",
            "-fd",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        log.info("workspace_reset", path=workspace_path)


class WorkspaceInfo:
    """Info about a created workspace."""

    def __init__(self, path: str, branch: str, is_worktree: bool = True):
        self.path = path
        self.branch = branch
        self.is_worktree = is_worktree


class WorkspaceError(Exception):
    """Workspace operation failed."""
