"""Resolve project workspace info into MA `github_repository` resources.

Phase C wiring: when a managed-agents session is created for a task, the
session must run inside a cloud container with the project repo cloned.
MA does this via the `github_repository` resource type — auto-clones at
session start, with auth injected by an Anthropic-side git proxy after
the request leaves the sandbox (so the token never enters the container).

This module reads the host workspace's git remote and assembles the
resource dict. Auth comes from `GITHUB_TOKEN` env (Phase C); a future
phase will source it from a vault for proper rotation.

Sessions on local-only projects (no GitHub remote) are NOT supported on
this lane — `runtime probe` should fail-fast for those projects per
GOAL.md "Local generated-app workspaces without a real Git or PR target
should use deterministic evidence surfaces".
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

# Match SSH (git@github.com:org/repo.git) and HTTPS
# (https://github.com/org/repo[.git]) GitHub remote URLs.
_SSH_REMOTE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
_HTTPS_REMOTE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


class WorkspaceResourceError(RuntimeError):
    """Raised when the workspace can't be translated into a session resource."""


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise WorkspaceResourceError("git not on PATH") from exc
    if proc.returncode != 0:
        raise WorkspaceResourceError(
            f"git {' '.join(args)} (cwd={cwd}) failed [{proc.returncode}]: "
            f"{proc.stderr.strip()[:300]}"
        )
    return proc.stdout.strip()


def detect_github_remote(workspace_path: str | Path) -> tuple[str, str] | None:
    """Return (owner, repo) for a GitHub origin remote, or None.

    Reads `git remote get-url origin` and parses common GitHub URL shapes
    (SSH and HTTPS). Returns None for non-GitHub remotes or when there is
    no `origin` remote.
    """
    cwd = Path(workspace_path).resolve()
    if not cwd.exists():
        return None
    try:
        url = _run_git(["remote", "get-url", "origin"], cwd)
    except WorkspaceResourceError:
        return None
    for pattern in (_SSH_REMOTE, _HTTPS_REMOTE):
        match = pattern.match(url)
        if match:
            return match.group("owner"), match.group("repo")
    return None


def detect_current_branch(workspace_path: str | Path) -> str | None:
    """Return the current git branch name, or None if detached/unreadable."""
    cwd = Path(workspace_path).resolve()
    if not cwd.exists():
        return None
    try:
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    except WorkspaceResourceError:
        return None
    if branch == "HEAD":
        return None  # detached
    return branch or None


def resolve_github_token() -> str | None:
    """Read GITHUB_TOKEN env (Phase C). Returns None if unset.

    Phase D+ may extend this to look up a vault credential as a fallback.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return token if token else None


def build_github_resource(
    *,
    workspace_path: str | Path | None,
    branch_override: str | None = None,
) -> dict[str, Any] | None:
    """Build the MA `github_repository` resource dict for a session.

    Returns None when:
      - workspace_path is missing
      - the workspace has no GitHub remote (local-only project)
      - no GITHUB_TOKEN is configured

    These are *advisory* — the runtime adapter falls back to running the
    session without a workspace mount, which is fine for roles that don't
    need repo access (e.g. planner reading no files; chat). Callers that
    require a workspace (code-gen, build-verifier, pr-creator) should
    detect the None result and surface it as a setup error.
    """
    if workspace_path is None:
        return None
    remote = detect_github_remote(workspace_path)
    if remote is None:
        return None
    owner, repo = remote
    token = resolve_github_token()
    if token is None:
        return None
    branch = branch_override or detect_current_branch(workspace_path)

    resource: dict[str, Any] = {
        "type": "github_repository",
        "url": f"https://github.com/{owner}/{repo}",
        "authorization_token": token,
        "mount_path": f"/workspace/{repo}",
    }
    if branch:
        resource["checkout"] = {"type": "branch", "name": branch}
    return resource


# Roles that genuinely require a workspace mount to do their job. If any
# of these dispatch with no resolvable github_repository, the runtime
# logs a structured warning so operators see why the agent failed.
WORKSPACE_REQUIRED_ROLES: frozenset[str] = frozenset(
    {
        "code-gen",
        "build-verifier",
        "feature-verifier",
        "integration-resolver",
        "pr-creator",
        "designer",
    }
)
