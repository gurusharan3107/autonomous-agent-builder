"""Sprint-PR refactor (Phase B) — sprint branch lifecycle and per-task integration target."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    Sprint,
    SprintPhase,
)
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")


@pytest.fixture
def orchestrator():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return Orchestrator(get_settings(), db)


def test_sprint_branch_name_is_deterministic(orchestrator):
    sprint = Sprint(id="abcdef0123456789", project_id="p", label="Sprint 1")
    assert orchestrator._sprint_branch_name(sprint) == "sprint/abcdef01-sprint-1"


def test_sprint_branch_name_handles_blank_label(orchestrator):
    sprint = Sprint(id="zzz12345", project_id="p", label="")
    name = orchestrator._sprint_branch_name(sprint)
    assert name.startswith("sprint/zzz12345-")
    assert name.endswith("-sprint")


def test_sprint_branch_name_slugifies_complex_labels(orchestrator):
    sprint = Sprint(id="11111111", project_id="p", label="Sprint #2 — auth flow")
    name = orchestrator._sprint_branch_name(sprint)
    # Non-alphanum runs collapse to single dashes; trailing dashes are trimmed.
    assert name == "sprint/11111111-sprint-2-auth-flow"


@pytest.mark.asyncio
async def test_ensure_sprint_branch_creates_branch_when_missing(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.IMPLEMENTATION,
    )

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    branch = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)

    assert branch == "sprint/abcdef01-sprint-1"
    assert sprint.branch == branch
    branches = _git(repo, "branch", "--list", branch).stdout
    assert branch in branches


@pytest.mark.asyncio
async def test_ensure_sprint_branch_is_idempotent(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.IMPLEMENTATION,
    )

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    first = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    second = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    assert first == second
    # Only one matching branch exists.
    out = _git(repo, "branch", "--list", first).stdout.strip().splitlines()
    assert len(out) == 1


@pytest.mark.asyncio
async def test_ensure_sprint_branch_returns_none_on_unborn_head(tmp_path, orchestrator):
    repo = tmp_path / "unborn"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    sprint = Sprint(id="abcdef01", project_id="p", label="Sprint 1")

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    branch = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    assert branch is None
    assert sprint.branch is None


@pytest.mark.asyncio
async def test_workspace_manager_create_workspace_honors_start_point(tmp_path):
    """The new ``start_point`` parameter must thread through to ``git worktree add``."""
    from autonomous_agent_builder.workspace.manager import WorkspaceManager

    repo = tmp_path / "repo"
    _init_repo(repo)
    # Create a sprint branch ahead of the worktree call.
    _git(repo, "branch", "sprint/test-1")

    workspaces_root = tmp_path / "workspaces"
    manager = WorkspaceManager(str(workspaces_root))

    info = await manager.create_workspace(
        str(repo),
        task_id="task-1",
        start_point="sprint/test-1",
    )

    assert info.is_worktree is True
    assert info.branch == "task/task-1"
    # The new task branch should descend from sprint/test-1, so its merge-base
    # with sprint/test-1 equals the sprint/test-1 commit itself.
    sprint_sha = _git(repo, "rev-parse", "sprint/test-1").stdout.strip()
    base_sha = _git(repo, "merge-base", "task/task-1", "sprint/test-1").stdout.strip()
    assert base_sha == sprint_sha


@pytest.mark.asyncio
async def test_workspace_manager_recreates_missing_task_worktree_from_existing_branch(tmp_path):
    from autonomous_agent_builder.workspace.manager import WorkspaceManager

    repo = tmp_path / "repo"
    _init_repo(repo)
    workspaces_root = tmp_path / "workspaces"
    manager = WorkspaceManager(str(workspaces_root))

    info = await manager.create_workspace(str(repo), task_id="task-1")
    workspace_path = Path(info.path)
    assert workspace_path.exists()

    shutil.rmtree(workspace_path)
    assert not workspace_path.exists()
    assert _git(repo, "branch", "--list", "task/task-1").stdout.strip()

    recreated = await manager.create_workspace(str(repo), task_id="task-1")

    assert recreated.branch == "task/task-1"
    assert Path(recreated.path) == workspace_path
    assert workspace_path.exists()
    assert _git(workspace_path, "branch", "--show-current").stdout.strip() == "task/task-1"


@pytest.mark.asyncio
async def test_untracked_runtime_guidance_does_not_block_task_branch_merge(
    tmp_path, orchestrator
):
    """Builder-owned guidance may be untracked while task branches track the same path."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "checkout", "-b", "task/task-1")
    (repo / "AGENTS.md").write_text("# task codex guidance\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# task guidance\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md", "CLAUDE.md")
    _git(repo, "commit", "-q", "-m", "task adds guidance")
    _git(repo, "checkout", "main")

    (repo / "AGENTS.md").write_text("# builder codex guidance\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# builder guidance\n", encoding="utf-8")

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    snapshot = orchestrator._project_runtime_guidance_snapshot(repo)
    clean_error = await orchestrator._clean_project_runtime_guidance_for_git_operation(
        run_git,
        snapshot,
    )
    assert clean_error is None
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / "CLAUDE.md").exists()

    merge_code, merge_output = await run_git("merge", "--ff-only", "task/task-1")
    assert merge_code == 0, merge_output

    restore_error = await orchestrator._restore_project_runtime_guidance_snapshot(
        repo,
        snapshot,
        run_git,
    )
    assert restore_error is None
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# builder codex guidance\n"
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "# builder guidance\n"
    assert "restore builder runtime guidance" in _git(repo, "log", "--oneline", "-1").stdout


@pytest.mark.asyncio
async def test_integrate_task_workspace_cleans_guidance_before_sprint_checkout(
    tmp_path, orchestrator
):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.IMPLEMENTATION,
        branch="sprint/abcdef01-sprint-1",
    )
    _git(repo, "checkout", "-b", sprint.branch)
    (repo / "AGENTS.md").write_text("# sprint task guidance\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-q", "-m", "track sprint guidance")
    _git(repo, "checkout", "main")
    (repo / "AGENTS.md").write_text("# builder codex guidance\n", encoding="utf-8")
    (repo / ".gitignore").write_text("dist\n", encoding="utf-8")
    (repo / "postcss.config.mjs").write_text("export default {}\n", encoding="utf-8")

    worktree = tmp_path / "task-worktree"
    result = _git(repo, "worktree", "add", "-b", "task/task-1", str(worktree), sprint.branch)
    assert result.returncode == 0, result.stderr
    (worktree / ".gitignore").write_text("dist\nnode_modules\n", encoding="utf-8")
    (worktree / "package.json").write_text(
        '{"scripts":{"test":"node --test"}}\n',
        encoding="utf-8",
    )
    (worktree / "postcss.config.mjs").write_text(
        "export default { plugins: {} }\n",
        encoding="utf-8",
    )
    _git(worktree, "add", ".gitignore", "package.json", "postcss.config.mjs")
    _git(worktree, "commit", "-q", "-m", "task adds package")

    task = SimpleNamespace(
        id="task-1",
        title="Verify generated app",
        depends_on={"sprint_execution": {"sprint_id": sprint.id}},
        workspace=SimpleNamespace(
            path=str(worktree),
            branch="task/task-1",
            is_worktree=True,
        ),
        feature=SimpleNamespace(
            project=SimpleNamespace(repo_url=str(repo)),
        ),
    )
    orchestrator._resolve_sprint_for_task = AsyncMock(return_value=sprint)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert (repo / "package.json").read_text(encoding="utf-8") == (
        '{"scripts":{"test":"node --test"}}\n'
    )
    assert (repo / ".gitignore").read_text(encoding="utf-8") == "dist\nnode_modules\n"
    assert (repo / "postcss.config.mjs").read_text(encoding="utf-8") == (
        "export default { plugins: {} }\n"
    )
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# builder codex guidance\n"
    assert "restore builder runtime guidance" in _git(repo, "log", "--oneline", "-1").stdout


@pytest.mark.asyncio
async def test_integrate_task_workspace_commits_dirty_existing_task_branch(
    tmp_path, orchestrator
):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "branch", "sprint/test-1")
    worktree = tmp_path / "task-worktree"
    result = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "task/task-1",
        str(worktree),
        "sprint/test-1",
    )
    assert result.returncode == 0, result.stderr
    (worktree / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
    (worktree / "src").mkdir()
    (worktree / "src" / "index.js").write_text("export const ok = true;\n", encoding="utf-8")

    task = SimpleNamespace(
        id="task-1",
        title="Verify generated app",
        depends_on={},
        workspace=SimpleNamespace(
            path=str(worktree),
            branch="task/task-1",
            is_worktree=True,
        ),
        feature=SimpleNamespace(
            project=SimpleNamespace(repo_url=str(repo)),
        ),
    )

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert (repo / "package.json").read_text(encoding="utf-8") == (
        '{"scripts":{"test":"node --test"}}\n'
    )
    assert (repo / "src" / "index.js").read_text(encoding="utf-8") == "export const ok = true;\n"
    assert "feat: Verify generated app" in _git(repo, "log", "--oneline", "-1").stdout


@pytest.mark.asyncio
async def test_integrate_task_workspace_does_not_commit_generated_artifacts(
    tmp_path, orchestrator
):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "branch", "sprint/test-1")
    worktree = tmp_path / "task-worktree"
    result = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "task/task-1",
        str(worktree),
        "sprint/test-1",
    )
    assert result.returncode == 0, result.stderr
    (worktree / "package.json").write_text('{"scripts":{"build":"vite build"}}\n', encoding="utf-8")
    (worktree / "dist").mkdir()
    (worktree / "dist" / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (worktree / "node_modules").mkdir()
    (worktree / "node_modules" / "vite.js").write_text("module.exports = {}\n", encoding="utf-8")

    task = SimpleNamespace(
        id="task-1",
        title="Verify generated app",
        depends_on={},
        workspace=SimpleNamespace(
            path=str(worktree),
            branch="task/task-1",
            is_worktree=True,
        ),
        feature=SimpleNamespace(
            project=SimpleNamespace(repo_url=str(repo)),
        ),
    )

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    tracked = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
    assert "package.json" in tracked
    assert "dist/index.html" not in tracked
    assert "node_modules/vite.js" not in tracked


@pytest.mark.asyncio
async def test_generated_artifact_cleanup_tolerates_missing_artifact_path(
    tmp_path, orchestrator
):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "dist").mkdir()
    (repo / "dist" / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    _git(repo, "add", "dist/index.html")
    _git(repo, "commit", "-q", "-m", "accidentally commit build output")

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    error = await orchestrator._remove_generated_artifacts_from_git_checkout(
        repo,
        run_git,
        "chore: remove generated build artifacts",
    )

    assert error is None
    tracked = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
    assert "dist/index.html" not in tracked


@pytest.mark.asyncio
async def test_sprint_completion_restores_missing_tracked_app_files(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
    _git(repo, "add", "package.json")
    _git(repo, "commit", "-q", "-m", "add app")
    _git(repo, "branch", "sprint/test-1")
    (repo / "package.json").unlink()

    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.VERIFY,
        branch="sprint/test-1",
    )

    error = await orchestrator._maybe_ff_merge_sprint_branch(sprint, repo)

    assert error is None
    assert (repo / "package.json").is_file()


@pytest.mark.asyncio
async def test_sprint_completion_rebases_sprint_branch_when_main_diverged(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "checkout", "-b", "sprint/test-1")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-q", "-m", "add sprint feature")
    _git(repo, "checkout", "main")
    (repo / "README.md").write_text("# test\n\nmain change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "main moves")

    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.VERIFY,
        branch="sprint/test-1",
    )

    error = await orchestrator._maybe_ff_merge_sprint_branch(sprint, repo)

    assert error is None
    assert (repo / "feature.txt").read_text(encoding="utf-8") == "feature\n"
    assert "main change" in (repo / "README.md").read_text(encoding="utf-8")
    assert _git(repo, "rev-parse", "main").stdout.strip() == _git(
        repo,
        "rev-parse",
        "sprint/test-1",
    ).stdout.strip()


@pytest.mark.asyncio
async def test_sprint_completion_blocks_modified_app_checkout(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
    _git(repo, "add", "package.json")
    _git(repo, "commit", "-q", "-m", "add app")
    _git(repo, "branch", "sprint/test-1")
    (repo / "package.json").write_text('{"scripts":{"test":"broken"}}\n', encoding="utf-8")

    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.VERIFY,
        branch="sprint/test-1",
    )

    error = await orchestrator._maybe_ff_merge_sprint_branch(sprint, repo)

    assert error is not None
    assert "local app checkout still has tracked non-guidance changes" in error
    assert "M package.json" in error


@pytest.mark.asyncio
async def test_rebase_task_workspace_uses_sprint_branch_target(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "branch", "sprint/test-1")

    first = tmp_path / "first-worktree"
    first_result = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "task/first",
        str(first),
        "sprint/test-1",
    )
    assert first_result.returncode == 0, first_result.stderr
    second = tmp_path / "second-worktree"
    second_result = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "task/second",
        str(second),
        "sprint/test-1",
    )
    assert second_result.returncode == 0, second_result.stderr

    (first / "src").mkdir()
    (first / "src" / "a.js").write_text("export const a = true;\n", encoding="utf-8")
    _git(first, "add", "src/a.js")
    _git(first, "commit", "-q", "-m", "first task")
    (second / "src").mkdir()
    (second / "src" / "b.js").write_text("export const b = true;\n", encoding="utf-8")
    _git(second, "add", "src/b.js")
    _git(second, "commit", "-q", "-m", "second task")

    _git(repo, "checkout", "sprint/test-1")
    first_merge = _git(repo, "merge", "--ff-only", "task/first")
    assert first_merge.returncode == 0, first_merge.stderr
    second_merge = _git(repo, "merge", "--ff-only", "task/second")
    assert second_merge.returncode != 0

    error = await orchestrator._rebase_task_workspace_for_integration(
        SimpleNamespace(description=""),
        str(second),
        "task/second",
        "sprint/test-1",
    )

    assert error is None
    retried_merge = _git(repo, "merge", "--ff-only", "task/second")
    assert retried_merge.returncode == 0, retried_merge.stderr
    assert (repo / "src" / "a.js").is_file()
    assert (repo / "src" / "b.js").is_file()


@pytest.mark.asyncio
async def test_rebase_conflict_resolution_stages_full_workspace(
    tmp_path, orchestrator, monkeypatch
):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "app.js").write_text("export const value = 'base';\n", encoding="utf-8")
    _git(repo, "add", "app.js")
    _git(repo, "commit", "-q", "-m", "app base")
    _git(repo, "branch", "sprint/test-1")

    worktree = tmp_path / "task-worktree"
    result = _git(
        repo,
        "worktree",
        "add",
        "-b",
        "task/task-1",
        str(worktree),
        "sprint/test-1",
    )
    assert result.returncode == 0, result.stderr
    (repo / "app.js").write_text("export const value = 'sprint';\n", encoding="utf-8")
    _git(repo, "add", "app.js")
    _git(repo, "commit", "-q", "-m", "sprint edit")
    _git(repo, "branch", "-f", "sprint/test-1", "HEAD")
    (worktree / "app.js").write_text("export const value = 'task';\n", encoding="utf-8")
    _git(worktree, "add", "app.js")
    _git(worktree, "commit", "-q", "-m", "task edit")

    async def resolve_conflict(*_args):
        (worktree / "app.js").write_text("export const value = 'resolved';\n", encoding="utf-8")
        (worktree / "resolver-note.txt").write_text("resolved together\n", encoding="utf-8")
        return None

    monkeypatch.setattr(
        orchestrator,
        "_run_integration_conflict_resolver",
        resolve_conflict,
    )

    error = await orchestrator._rebase_task_workspace_for_integration(
        SimpleNamespace(description=""),
        str(worktree),
        "task/task-1",
        "sprint/test-1",
    )

    assert error is None
    assert (worktree / "app.js").read_text(encoding="utf-8") == (
        "export const value = 'resolved';\n"
    )
    assert "resolver-note.txt" in _git(worktree, "show", "--name-only", "--format=", "HEAD").stdout
