"""Deterministic orchestrator — owns all routing decisions.

Event-driven dispatch: state changes trigger deterministic phase transitions.
Agents never decide their own next phase. The orchestrator reads task status
and dispatches accordingly.

Phase chain: planning → design_review → implementation → quality_gates →
pr_creation → review → build_verify
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import unquote, urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.documentation_bridge import (
    run_documentation_refresh_bridge,
)
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult, capture_workspace_diff
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    AgentRunEvent,
    ApprovalGate,
    Feature,
    FeatureStatus,
    Sprint,
    SprintPhase,
    Task,
    TaskPhase,
    TaskStatus,
    Workspace,
    set_task_status,
)
from autonomous_agent_builder.db.models import (
    GateResult as GateResultModel,
)
from autonomous_agent_builder.knowledge.system_docs import (
    format_task_system_doc_guidance,
    validate_task_system_docs,
)
from autonomous_agent_builder.observability.runtime_optimization import runtime_decision_summary
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.orchestrator.gate_feedback import GateFeedbackHandler
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
    run_quality_gates,
)
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate
from autonomous_agent_builder.runtime import create_runtime, resolve_runtime_config
from autonomous_agent_builder.runtime.managed_agents_outcome import build_feature_outcome
from autonomous_agent_builder.services.builder_tool_service import builder_kb_validate
from autonomous_agent_builder.services.codex_optimization import (
    codex_run_optimization_summary,
    prompt_budget_breakdown,
)
from autonomous_agent_builder.services.provider_limits import mark_provider_limit
from autonomous_agent_builder.services.runtime_guidance import refresh_project_runtime_guidance
from autonomous_agent_builder.services.runtime_settings import resolve_project_runtime_config
from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_EXECUTION_KEY,
    sprint_execution_context,
    task_uses_sprint_design,
    task_uses_sprint_plan,
)
from autonomous_agent_builder.workspace.manager import WorkspaceInfo, WorkspaceManager

log = structlog.get_logger()
_OPERATOR_DECISION_MARKER = "OPERATOR_DECISION_JSON:"
_PROJECT_RUNTIME_GUIDANCE_PATHS = (
    Path("CLAUDE.md"),
    Path(".claude") / "CLAUDE.md",
)
_GitRunner = Callable[..., Awaitable[tuple[int, str]]]
_CODEX_CHUNK_LIMIT_FRAGMENT = "separator is not found"
_SPRINT_FEATURE_VERIFY_TASK_KEYS = {"browser-verification", "tests-browser-proof"}
_CODEX_CHUNK_LIMIT_DETAIL = "chunk exceed"
_WORKSPACE_COPY_EXCLUDES = (
    ".agent-builder",
    ".claude",
    ".git",
    ".env",
    ".env.*",
    ".coverage",
    ".DS_Store",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "htmlcov",
    "node_modules",
    "dist",
    "build",
)


def _is_codex_chunk_limit_error(error: str) -> bool:
    lower = error.lower()
    return _CODEX_CHUNK_LIMIT_FRAGMENT in lower and _CODEX_CHUNK_LIMIT_DETAIL in lower


def _workspace_contains_builder_internals(workspace_path: str) -> bool:
    if not workspace_path:
        return False
    workspace = Path(workspace_path)
    return any(
        (workspace / path).exists()
        for path in (
            ".agent-builder",
            ".agent-builder/dashboard",
            ".agent-builder/server",
            ".agent-builder/agent_builder.db",
            ".claude/progress",
        )
    )


def _directory_workspace_is_stale(workspace_path: str, repo_url: str) -> bool:
    if not workspace_path or not repo_url:
        return False
    workspace = Path(workspace_path)
    repo_root = Path(repo_url).expanduser()
    return (repo_root / "package.json").exists() and not (workspace / "package.json").exists()


def _is_builder_source_repo(path: Path) -> bool:
    """Return true when post-ship optimization can safely edit builder internals."""

    return (path / "src" / "autonomous_agent_builder").is_dir() and (
        path / "frontend" / "src"
    ).is_dir()


def _next_clean_directory_workspace_path(base_path: Path) -> Path:
    for index in range(1, 100):
        candidate = base_path.with_name(f"{base_path.name}-clean-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate clean task workspace path near {base_path}")


def _workspace_copy_excluded(path: Path) -> bool:
    for pattern in _WORKSPACE_COPY_EXCLUDES:
        if pattern.endswith(".*"):
            prefix = pattern[:-1]
            if any(part.startswith(prefix) for part in path.parts):
                return True
            continue
        if pattern in path.parts:
            return True
    return False


def _is_fast_forward_divergence(output: str) -> bool:
    lower = output.lower()
    return "not possible to fast-forward" in lower or "diverging branches" in lower


def _task_status_value(task: Task) -> str:
    status = getattr(task, "status", "")
    return status.value if hasattr(status, "value") else str(status)


def _sqlite_path_from_sync_url(sync_url: str) -> Path | None:
    value = str(sync_url or "")
    parsed = urlparse(value)
    if parsed.scheme != "sqlite" or not value.startswith("sqlite:///"):
        return None
    return Path(unquote(value.removeprefix("sqlite:///"))).expanduser()


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_object_from_text(text: str) -> dict[str, Any]:
    value = _json_object(text)
    if value:
        return value
    raw = str(text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    return _json_object(raw[start : end + 1])


# Deterministic dispatch table: task_status → handler method name
PHASE_DISPATCH: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "_phase_planning",
    TaskStatus.QUEUED: "_phase_planning",
    TaskStatus.PLANNING: "_phase_planning",
    TaskStatus.DESIGN: "_phase_design",
    TaskStatus.IMPLEMENTATION: "_phase_implementation",
    TaskStatus.QUALITY_GATES: "_phase_quality_gates",
    TaskStatus.PR_CREATION: "_phase_pr_creation",
    TaskStatus.BUILD_VERIFY: "_phase_build_verify",
}

# Statuses that block dispatch — require human action
BLOCKED_STATUSES = {
    TaskStatus.DESIGN_REVIEW,
    TaskStatus.REVIEW_PENDING,
    TaskStatus.BLOCKED,
    TaskStatus.CAPABILITY_LIMIT,
    TaskStatus.DONE,
    TaskStatus.FAILED,
}


class Orchestrator:
    """Deterministic orchestrator — dispatches tasks through SDLC phases."""

    def __init__(self, settings: Settings, db: AsyncSession):
        self.settings = settings
        self.db = db
        self.runner = AgentRunner(settings)
        self.gate_handler = GateFeedbackHandler(settings, db)

    async def dispatch(self, task: Task) -> None:
        """Dispatch a task to its next phase based on current status."""
        if task.status in BLOCKED_STATUSES:
            log.info("task_blocked", task_id=task.id, status=task.status.value)
            return
        if task.status == TaskStatus.QUEUED:
            if task.phase == TaskPhase.VERIFICATION:
                set_task_status(task, TaskStatus.QUALITY_GATES)
            elif task.phase == TaskPhase.IMPLEMENTATION:
                set_task_status(task, TaskStatus.IMPLEMENTATION)
            else:
                set_task_status(task, TaskStatus.PENDING)
            await self.db.flush()

        handler_name = PHASE_DISPATCH.get(task.status)
        if not handler_name:
            log.warning("no_dispatch_handler", task_id=task.id, status=task.status.value)
            return

        handler = getattr(self, handler_name)
        log.info("dispatch_phase", task_id=task.id, phase=handler_name, status=task.status.value)

        try:
            await handler(task)
        except Exception as e:
            log.error("phase_error", task_id=task.id, phase=handler_name, error=str(e))
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = str(e)
            await self.db.flush()

    async def _phase_planning(self, task: Task) -> None:
        """Run planning agent, then set DESIGN_REVIEW for approval."""
        if task_uses_sprint_plan(task):
            self._store_phase_context(task, "planning_context", sprint_execution_context(task))
            if task_uses_sprint_design(task):
                self._store_phase_context(
                    task,
                    "design_context",
                    self._phase_context(task, "design_context"),
                )
                set_task_status(task, TaskStatus.IMPLEMENTATION)
            else:
                set_task_status(task, TaskStatus.DESIGN)
            await self.db.flush()
            return

        set_task_status(task, TaskStatus.PLANNING)
        await self.db.flush()

        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

        result = await self._run_agent(
            task,
            "planner",
            {
                "feature_description": task.description,
                "project_name": task.feature.project.name,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
            },
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = self._diagnose_task_failure(
                result.error,
                workspace_path=workspace.path,
                result=result,
            )
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        elif result.hit_capability_limit:
            await self._mark_capability_limit(
                task,
                f"SDK limit: {result.stop_reason}",
                output_text=result.output_text,
            )
        else:
            set_task_status(task, TaskStatus.DESIGN_REVIEW)
            # Create approval gate
            approval = ApprovalGate(task_id=task.id, gate_type="planning")
            self.db.add(approval)

        await self.db.flush()

    async def _phase_design(self, task: Task) -> None:
        """Run design agent with context chained from planning session."""
        if task_uses_sprint_design(task):
            set_task_status(task, TaskStatus.IMPLEMENTATION)
            await self.db.flush()
            return

        set_task_status(task, TaskStatus.DESIGN)
        await self.db.flush()

        # Get planning session_id for context chaining
        planning_run = await self._get_last_run(task, "planner")
        resume_session = (
            planning_run.session_id
            if planning_run and self._run_has_context(planning_run)
            else None
        )
        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

        result = await self._run_agent(
            task,
            "designer",
            {
                "task_description": task.description,
                "project_name": task.feature.project.name,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
            },
            resume_session=resume_session,
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = self._diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        elif result.hit_capability_limit:
            await self._mark_capability_limit(
                task,
                f"SDK limit: {result.stop_reason}",
                output_text=result.output_text,
            )
        else:
            await self._ensure_workspace(task)
            self._store_phase_context(
                task,
                "design_context",
                self._compact_phase_output(result.output_text),
            )
            set_task_status(task, TaskStatus.IMPLEMENTATION)

        await self.db.flush()

    async def _phase_implementation(self, task: Task) -> None:
        """Run code-gen agent in workspace, then trigger quality gates."""
        set_task_status(task, TaskStatus.IMPLEMENTATION)
        self._clear_operator_decision_handoff(task)
        await self.db.flush()

        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

        workspace = await self._ensure_workspace(task)
        # Implementation runs in the task workspace, while design may have run in
        # the repo root. Do not resume across cwd boundaries; pass compact design
        # context explicitly instead.
        scope_reminder = self._build_active_feature_scope_reminder(task)
        result = await self._run_agent(
            task,
            "code-gen",
            {
                "task_description": task.description,
                "design_context": self._phase_context(task, "design_context"),
                "gate_feedback": await self._quality_gate_feedback_context(task),
                "workspace_path": workspace.path,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
                "scope_reminder": scope_reminder,
            },
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = self._diagnose_task_failure(
                result.error,
                workspace_path=workspace.path,
                result=result,
            )
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        elif result.hit_capability_limit:
            await self._mark_capability_limit(
                task,
                f"SDK limit: {result.stop_reason}",
                output_text=result.output_text,
            )
        else:
            set_task_status(task, TaskStatus.QUALITY_GATES)

        await self.db.flush()

    async def _ensure_workspace(self, task: Task) -> Workspace:
        """Provision and persist a task workspace when the task enters code-mutating phases."""
        existing = getattr(task, "workspace", None)
        existing_path = getattr(existing, "path", "") if existing else ""
        if existing and existing_path:
            if not getattr(existing, "is_worktree", False) and _workspace_contains_builder_internals(
                existing_path
            ):
                log.warning(
                    "task_workspace_polluted_reprovisioning",
                    task_id=task.id,
                    path=existing_path,
                )
            elif not getattr(existing, "is_worktree", False) and _directory_workspace_is_stale(
                existing_path,
                task.feature.project.repo_url if task.feature and task.feature.project else "",
            ):
                log.warning(
                    "task_workspace_stale_reprovisioning",
                    task_id=task.id,
                    path=existing_path,
                )
            else:
                return existing

        repo_url = task.feature.project.repo_url or ""
        if not repo_url.strip():
            raise RuntimeError("Task workspace cannot be provisioned: project repo_url is empty")
        repo_root = Path(repo_url).expanduser()
        if not repo_root.exists():
            raise RuntimeError(
                f"Task workspace cannot be provisioned: repo root does not exist at {repo_root}"
            )

        manager = WorkspaceManager(self.settings.workspace_root)
        workspace_info = await self._provision_workspace_info(manager, repo_root, task.id)

        if existing and existing_path:
            workspace = existing
            workspace.path = workspace_info.path
            workspace.branch = workspace_info.branch
            workspace.is_worktree = workspace_info.is_worktree
        else:
            workspace = Workspace(
                task_id=task.id,
                path=workspace_info.path,
                branch=workspace_info.branch,
                is_worktree=workspace_info.is_worktree,
            )
            self.db.add(workspace)
        task.workspace = workspace
        self._store_phase_context(
            task,
            "workspace_backend",
            "worktree" if workspace_info.is_worktree else "directory",
        )
        owner_surface_error = await self._preserve_project_runtime_guidance(
            task,
            workspace_info.path,
        )
        if owner_surface_error:
            raise RuntimeError(owner_surface_error)
        await self.db.flush()
        return workspace

    async def _provision_workspace_info(
        self, manager: WorkspaceManager, repo_root: Path, task_id: str
    ) -> WorkspaceInfo:
        """Create a git worktree by default, with an explicit directory fallback."""
        git_dir = repo_root / ".git"
        if git_dir.exists():
            return await manager.create_workspace(str(repo_root), task_id)

        workspace_path = Path(self.settings.workspace_root) / task_id
        if workspace_path.exists():
            workspace_path = _next_clean_directory_workspace_path(workspace_path)
        shutil.copytree(
            repo_root,
            workspace_path,
            ignore=shutil.ignore_patterns(*_WORKSPACE_COPY_EXCLUDES),
        )
        return WorkspaceInfo(path=str(workspace_path), branch="", is_worktree=False)

    async def _phase_quality_gates(self, task: Task) -> None:
        """Run concurrent quality gates with AND aggregation."""
        # Avoid lazy-loading the relationship from this post-ship hook. The
        # shipped task may have no workspace, and async lazy loads can fail
        # outside SQLAlchemy's greenlet context.
        workspace = task.__dict__.get("workspace")
        workspace_path = str(getattr(workspace, "path", "") or "")
        language = task.feature.project.language
        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

        if not await self._workspace_has_task_changes(workspace_path):
            no_delta = GateResult(
                gate_name="implementation_delta",
                status=GateStatus.FAIL,
                findings_count=1,
                error_code="NO_TASK_CHANGES",
                evidence={
                    "summary": "Task workspace has no changes relative to main.",
                    "workspace_path": workspace_path,
                },
                remediation_possible=False,
            )
            self.db.add(
                GateResultModel(
                    task_id=task.id,
                    gate_name=no_delta.gate_name,
                    status=no_delta.status.value,
                    evidence=no_delta.evidence,
                    findings_count=no_delta.findings_count,
                    elapsed_ms=0,
                    error_code=no_delta.error_code,
                    timeout=False,
                    remediation_attempted=False,
                    remediation_succeeded=False,
                )
            )
            await self.gate_handler.handle_gate_failure(
                task,
                AggregateGateResult(status=GateStatus.FAIL, results=[no_delta]),
            )
            await self.db.flush()
            return

        # Pre-integration gates: Ruff + pytest
        pre_gates = [
            CodeQualityGate(language=language),
            TestingGate(language=language, testing_doc_id=doc_requirements.testing_doc_id),
        ]

        gate_result = await run_quality_gates(workspace_path, pre_gates)

        # Save gate results to DB
        for r in gate_result.results:
            db_result = GateResultModel(
                task_id=task.id,
                gate_name=r.gate_name,
                status=r.status.value,
                evidence=r.evidence,
                findings_count=r.findings_count,
                elapsed_ms=r.elapsed_ms,
                error_code=r.error_code,
                timeout=r.timeout,
                remediation_attempted=False,
                remediation_succeeded=False,
            )
            self.db.add(db_result)

        if gate_result.status in {GateStatus.PASS, GateStatus.WARN} and not doc_requirements.passed:
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = "; ".join(doc_requirements.issues)
        elif gate_result.status == GateStatus.PASS:
            documentation_gap = await self._run_documentation_refresh_gate(task, workspace_path)
            if documentation_gap:
                set_task_status(task, TaskStatus.BLOCKED)
                task.blocked_reason = documentation_gap
            else:
                task.blocked_reason = None
                set_task_status(task, TaskStatus.PR_CREATION)
        elif gate_result.status == GateStatus.WARN:
            documentation_gap = await self._run_documentation_refresh_gate(task, workspace_path)
            if documentation_gap:
                set_task_status(task, TaskStatus.BLOCKED)
                task.blocked_reason = documentation_gap
            else:
                task.blocked_reason = None
                set_task_status(task, TaskStatus.PR_CREATION)  # advisory, continue
        elif gate_result.status == GateStatus.ERROR:
            # Gate infrastructure error (e.g., FileNotFoundError on a missing
            # lint config in a freshly-generated workspace). Distinct from
            # FAIL: agent-assisted fix doesn't help, the workspace bootstrap
            # or gate config is what's wrong. Hard block — operator inspects
            # and re-runs after fixing the config.
            error_codes = sorted({r.error_code for r in gate_result.results if r.error_code})
            erroring = sorted(
                {r.gate_name for r in gate_result.results if r.status == GateStatus.ERROR}
            )
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = (
                "Gate infrastructure error in "
                f"{', '.join(erroring) or 'unknown gate'} "
                f"({', '.join(error_codes) or 'unknown error'}). "
                "Configure the gate or bootstrap the workspace before retrying."
            )
        else:
            # FAIL — enter gate feedback loop
            await self.gate_handler.handle_gate_failure(task, gate_result)

        await self.db.flush()

    async def _workspace_has_task_changes(self, workspace_path: str) -> bool:
        if not workspace_path:
            return True

        async def run_git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, (
                stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )

        status_code, status_output = await run_git("status", "--short")
        if status_code != 0 or status_output.strip():
            return True

        main_code, _ = await run_git("rev-parse", "--verify", "main")
        if main_code != 0:
            return True

        ahead_code, ahead_output = await run_git("rev-list", "--count", "main..HEAD")
        if ahead_code != 0:
            return True
        try:
            return int(ahead_output.strip() or "0") > 0
        except ValueError:
            return True

    async def _phase_pr_creation(self, task: Task) -> None:
        """Create PR and set REVIEW_PENDING.

        For local generated-app workspaces (no git target), the deterministic
        evidence collector path runs first. The owner-surface-protection guard
        below requires `git` and is only meaningful when there is a real PR
        target — running it on a no-git workspace fails with
        "fatal: not a git repository". CLAUDE.md already mandates this
        deterministic-first behavior for the Codex lane; the same rule applies
        to the Claude SDK lane.
        """
        workspace_path = task.workspace.path if task.workspace else ""

        # Deterministic-first: no git required. `_record_deterministic_evidence`
        # invokes the `change_evidence` script and advances to BUILD_VERIFY.
        if self._use_deterministic_evidence_collector(task):
            await self._record_deterministic_evidence(task, workspace_path)
            set_task_status(task, TaskStatus.BUILD_VERIFY)
            await self.db.flush()
            return

        # Real-PR path only — owner-surface protection requires `git`.
        owner_surface_error = await self._preserve_project_runtime_guidance(
            task,
            workspace_path,
        )
        if owner_surface_error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = owner_surface_error
            await self.db.flush()
            return

        result = await self._run_agent(
            task,
            "pr-creator",
            {
                "task_description": task.description,
                "gate_results": "PASS",
                "workspace_path": workspace_path,
            },
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = self._diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        else:
            set_task_status(task, TaskStatus.REVIEW_PENDING)
            approval = ApprovalGate(task_id=task.id, gate_type="pr")
            self.db.add(approval)

        await self.db.flush()

    def _use_deterministic_evidence_collector(self, task: Task) -> bool:
        sprint_payload = self._task_sprint_execution_payload(task)
        if not sprint_payload:
            return False
        workspace = getattr(task, "workspace", None)
        if not workspace or not getattr(workspace, "path", ""):
            return False
        return True

    def _use_deterministic_build_verifier(self, task: Task) -> bool:
        sprint_payload = self._task_sprint_execution_payload(task)
        if not sprint_payload:
            return False
        workspace = getattr(task, "workspace", None)
        if not workspace or not getattr(workspace, "path", ""):
            return False
        return True

    def _is_sprint_feature_verification_task(self, task: Task) -> bool:
        sprint_payload = self._task_sprint_execution_payload(task)
        task_key = str(sprint_payload.get("task_key") or "").strip()
        return task_key in _SPRINT_FEATURE_VERIFY_TASK_KEYS

    def _task_sprint_execution_payload(self, task: Task) -> dict:
        depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
        payload = depends_on.get(SPRINT_EXECUTION_KEY)
        return payload if isinstance(payload, dict) else {}

    async def _run_builder_script(
        self,
        script_name: str,
        workspace_path: str,
        extra_args: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any], str, str]:
        script_args: dict[str, Any] = {"project_root": workspace_path}
        if extra_args:
            script_args.update(extra_args)
        args = json.dumps(script_args, ensure_ascii=True)
        command = [
            sys.executable,
            "-m",
            "autonomous_agent_builder.cli.main",
            "script",
            "run",
            script_name,
            "--args",
            args,
            "--json",
        ]
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace_path or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")
        payload = _json_object(stdout_text)
        return (
            proc.returncode == 0 and bool(payload.get("success", False)),
            payload,
            stdout_text,
            stderr_text,
        )

    async def _record_deterministic_evidence(self, task: Task, workspace_path: str) -> None:
        success, payload, _stdout, stderr = await self._run_builder_script(
            "change_evidence",
            workspace_path,
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        diff_summary = data if success and data else capture_workspace_diff(workspace_path)
        changed_files = [
            str(item.get("path") or item.get("file") or "")
            for item in (diff_summary or {}).get("files", [])
            if str(item.get("path") or item.get("file") or "").strip()
        ]
        if not changed_files:
            changed_files = [
                str(item.get("file", ""))
                for item in (diff_summary or {}).get("hunks", [])
                if str(item.get("file", "")).strip()
            ]
        output = (
            "Deterministic evidence collector completed without model-backed PR creation.\n"
            f"Changed files: {', '.join(changed_files) if changed_files else 'none detected'}.\n"
            "Next: sprint-level build verification."
        )
        run = AgentRun(
            task_id=task.id,
            agent_name="evidence-collector",
            runtime_sdk="deterministic",
            provider="builder",
            model="none",
            effort="none",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            tokens_cached=0,
            num_turns=0,
            duration_ms=0,
            stop_reason="deterministic_evidence",
            status="completed",
            output_text=output,
            diff_summary=diff_summary,
            observability={
                "command": "builder script run change_evidence --json",
                "success": success,
                "error": "" if success else str(payload.get("error") or stderr or "change_evidence failed"),
                "optimization_summary": {
                    "schema_version": "1",
                    "primary_score": "raw_tokens",
                    "token_accounting": {
                        "raw_total_tokens": 0,
                        "noncached_plus_output_tokens": 0,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "cache_ratio": 0.0,
                    },
                    "avoidable_cost_flags": [],
                    "avoidable_token_estimate": 0,
                    "deterministic_evidence": True,
                }
            },
            completed_at=datetime.now(UTC),
        )
        self.db.add(run)
        await self.db.flush()
        self.db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="tool_use",
                tool_name="builder_script",
                tool_input={
                    "command": "builder script run change_evidence --json",
                    "workspace_path": workspace_path,
                    "result": "pass" if success else "fail",
                },
                output_preview=output[:500],
                timestamp=datetime.now(UTC),
            )
        )
        await self._publish_realtime_board_snapshot()

    async def _record_deterministic_build_verification(
        self,
        task: Task,
        workspace_path: str,
    ) -> tuple[bool, str]:
        started_at = datetime.now(UTC)
        from autonomous_agent_builder.embedded.scripts.build_verify import BuildVerifyScript

        payload = BuildVerifyScript().run(project_root=workspace_path)
        success = bool(payload.get("success", False))
        stderr = ""
        completed_at = datetime.now(UTC)
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
                    else str(command or check.get("name") or "")
                ).strip()
                status = "PASS" if check.get("status") == "passed" else "FAIL"
                lines.append(f"{command_text or 'check'} {status}")
        output = "\n".join(lines) or (
            "builder script run build_verify --json PASS"
            if success
            else str(payload.get("error") or stderr or "build_verify failed")
        )
        run = AgentRun(
            task_id=task.id,
            agent_name="build-verifier",
            runtime_sdk="deterministic",
            provider="builder",
            model="none",
            effort="none",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            tokens_cached=0,
            num_turns=0,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            stop_reason="deterministic_build_verify",
            status="completed" if success else "failed",
            error=None if success else str(payload.get("error") or stderr or "build_verify failed"),
            output_text=output,
            observability={
                "command": "builder script run build_verify --json",
                "success": success,
                "optimization_summary": {
                    "schema_version": "1",
                    "primary_score": "raw_tokens",
                    "token_accounting": {
                        "raw_total_tokens": 0,
                        "noncached_plus_output_tokens": 0,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "cache_ratio": 0.0,
                    },
                },
            },
            started_at=started_at,
            completed_at=completed_at,
        )
        self.db.add(run)
        await self.db.flush()
        self.db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="tool_use",
                tool_name="builder_script",
                tool_input={
                    "command": "builder script run build_verify --json",
                    "workspace_path": workspace_path,
                    "result": "pass" if success else "fail",
                },
                output_preview=output[:500],
                timestamp=completed_at,
            )
        )
        await self._publish_realtime_board_snapshot()
        return success, output

    async def _run_feature_acceptance_gate(
        self,
        task: Task,
        workspace_path: str,
    ) -> tuple[bool, str]:
        if not self._is_sprint_feature_verification_task(task):
            return True, ""

        feature = await self.db.get(Feature, task.feature_id)
        if feature is None:
            return False, "feature_acceptance_failed: feature record not found"

        prior_verifier = await self._has_completed_agent_run(task, "feature-verifier")
        existing_result = "not_run_first_time_agentic_verification_required"
        if prior_verifier:
            test_success, existing_result = await self._record_feature_acceptance_tests(
                task,
                workspace_path,
                feature,
            )
            if test_success:
                return True, existing_result

        # Phase D2: when this project is on the claude_managed runtime, run
        # feature-verifier through MA Outcomes (rubric-graded iterate loop)
        # instead of the standard message-based agent path. The grader writes
        # a terminal verdict to stop_reason that we map to a gate_results row.
        if await self._task_runtime_is_claude_managed(task):
            ok, message = await self._run_feature_verifier_outcome(
                task,
                feature,
                workspace_path,
            )
            if not ok:
                return False, message
        else:
            result = await self._run_agent(
                task,
                "feature-verifier",
                {
                    "feature_title": feature.title,
                    "feature_description": feature.description or "",
                    "acceptance_criteria": json.dumps(
                        feature.acceptance_criteria or [],
                        ensure_ascii=True,
                    ),
                    "existing_feature_test_result": existing_result,
                    "workspace_path": workspace_path,
                },
            )
            if result.error:
                return False, self._diagnose_task_failure(
                    result.error,
                    workspace_path=workspace_path,
                    result=result,
                )
            if verifier_failure := self._feature_verifier_failure(result.output_text):
                return False, verifier_failure

        test_success, test_output = await self._record_feature_acceptance_tests(
            task,
            workspace_path,
            feature,
        )
        if test_success:
            return True, test_output
        return False, f"feature_acceptance_failed: {test_output}"

    async def _task_runtime_is_claude_managed(self, task: Task) -> bool:
        """Return True when the task's project resolves to claude_managed.

        Phase D2 routing predicate: feature-verifier dispatches through
        Outcomes only on this lane. Falls back to False on any resolution
        error so the standard agent path keeps working.
        """
        try:
            project = getattr(task.feature, "project", None)
            project_root = Path(str(getattr(project, "repo_url", "") or "")).expanduser()
            if not project_root.exists():
                return False
            config = resolve_project_runtime_config(project_root)
            return str(config.get("sdk") or "") == "claude_managed"
        except Exception as exc:
            log.debug("claude_managed_routing_check_failed", error=str(exc))
            return False

    async def _run_feature_verifier_outcome(
        self,
        task: Task,
        feature: Feature,
        workspace_path: str,
    ) -> tuple[bool, str]:
        """Run feature-verifier through MA Outcomes for the claude_managed lane.

        Synthesises a rubric from `Feature.acceptance_criteria`, calls
        `runtime.run_outcome`, and persists the verdict as both an `agent_runs`
        row (runtime attribution) and a `gate_results` row (rubric verdict
        + iteration count). The orchestrator's gate caller routes on the
        returned (success, message) pair.
        """
        project = getattr(feature, "project", None)
        project_root = Path(str(getattr(project, "repo_url", "") or "")).expanduser()
        runtime_config = (
            resolve_project_runtime_config(project_root)
            if project_root.exists()
            else resolve_runtime_config(self.settings)
        )
        runtime = create_runtime(**runtime_config)
        run_outcome = getattr(runtime, "run_outcome", None)
        if run_outcome is None:
            return (
                False,
                "feature_acceptance_failed: runtime does not support run_outcome "
                "(claude_managed lane required)",
            )

        outcome = build_feature_outcome(
            feature_title=feature.title,
            feature_description=feature.description or "",
            acceptance_criteria=feature.acceptance_criteria or [],
            max_iterations_cap=int(getattr(self.settings.gate, "max_retries", 5) or 5),
        )

        run = AgentRun(
            task_id=task.id,
            agent_name="feature-verifier",
            runtime_sdk=str(runtime_config.get("sdk") or "claude_managed"),
            provider=str(runtime_config.get("provider") or ""),
            model=str(runtime_config.get("model") or ""),
            effort="none",
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.commit()
        await self._publish_realtime_board_snapshot()

        started = datetime.now(UTC)
        try:
            result = await run_outcome(
                agent="feature-verifier",
                description=outcome.description,
                rubric=outcome.rubric,
                max_iterations=outcome.max_iterations,
                workspace_path=workspace_path,
            )
        except Exception as exc:
            log.error("feature_verifier_outcome_failed", error=str(exc))
            run.status = "failed"
            run.error = f"managed_agents outcome error: {exc}"
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            return False, f"feature_acceptance_failed: managed_agents outcome error: {exc}"

        observability = dict(result.observability or {})
        ma_obs = observability.get("managed_agents") or {}
        verdict_payload = ma_obs.get("outcome") or {}
        verdict = str(verdict_payload.get("result") or "")
        iterations = int(ma_obs.get("outcome_iterations") or 0)
        explanation = str(verdict_payload.get("explanation") or "")

        run.session_id = result.session_id
        run.cost_usd = result.cost_usd
        run.tokens_input = result.tokens_input
        run.tokens_output = result.tokens_output
        run.tokens_cached = result.tokens_cached
        run.num_turns = result.num_turns
        run.duration_ms = result.duration_ms
        run.stop_reason = result.stop_reason
        run.output_text = result.output_text
        run.observability = observability
        run.completed_at = datetime.now(UTC)
        run.status = "completed" if not result.error else "failed"
        run.error = result.error

        gate_status = (
            GateStatus.PASS
            if verdict == "satisfied"
            else GateStatus.FAIL
        )
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        self.db.add(
            GateResultModel(
                task_id=task.id,
                gate_name="feature-verifier-outcome",
                status=gate_status,
                evidence={
                    "verdict": verdict,
                    "iterations": iterations,
                    "max_iterations": outcome.max_iterations,
                    "explanation": explanation,
                    "session_id": result.session_id,
                    "stop_reason": result.stop_reason,
                },
                findings_count=0 if verdict == "satisfied" else 1,
                elapsed_ms=elapsed_ms,
                error_code=None if verdict == "satisfied" else (verdict or "unknown"),
            )
        )
        await self.db.commit()
        await self._publish_realtime_board_snapshot()

        if verdict == "satisfied":
            return True, ""
        message = explanation.strip() or f"verdict={verdict or 'unknown'}"
        return False, f"feature_acceptance_failed: managed_agents outcome {message}"

    async def _record_feature_acceptance_tests(
        self,
        task: Task,
        workspace_path: str,
        feature: Feature,
    ) -> tuple[bool, str]:
        started_at = datetime.now(UTC)
        from autonomous_agent_builder.embedded.scripts.feature_acceptance import (
            FeatureAcceptanceScript,
        )

        payload = FeatureAcceptanceScript().run(
            project_root=workspace_path,
            feature_title=feature.title,
            feature_description=feature.description or "",
            acceptance_criteria=feature.acceptance_criteria or [],
        )
        success = bool(payload.get("success", False))
        stderr = ""
        completed_at = datetime.now(UTC)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        output = self._feature_acceptance_output(data, payload, stderr, success=success)
        run = AgentRun(
            task_id=task.id,
            agent_name="feature-acceptance-tests",
            runtime_sdk="deterministic",
            provider="builder",
            model="none",
            effort="none",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            tokens_cached=0,
            num_turns=0,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            stop_reason="deterministic_feature_acceptance",
            status="completed" if success else "failed",
            error=None if success else str(payload.get("error") or stderr or "feature_acceptance failed"),
            output_text=output,
            observability={
                "command": "builder script run feature_acceptance --json",
                "success": success,
                "data": data,
            },
            started_at=started_at,
            completed_at=completed_at,
        )
        self.db.add(run)
        await self.db.flush()
        self.db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="tool_use",
                tool_name="builder_script",
                tool_input={
                    "command": "builder script run feature_acceptance --json",
                    "workspace_path": workspace_path,
                    "feature_id": feature.id,
                    "result": "pass" if success else "fail",
                },
                output_preview=output[:500],
                timestamp=completed_at,
            )
        )
        await self._publish_realtime_board_snapshot()
        return success, output

    def _feature_acceptance_output(
        self,
        data: dict[str, Any],
        payload: dict[str, Any],
        stderr: str,
        *,
        success: bool,
    ) -> str:
        status = str(data.get("status") or ("passed" if success else "failed"))
        command = data.get("command")
        command_text = (
            " ".join(str(part) for part in command)
            if isinstance(command, list)
            else str(command or "")
        ).strip()
        coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
        matched_files = coverage.get("matched_files") if isinstance(coverage, dict) else []
        criteria = data.get("acceptance_criteria") if isinstance(data.get("acceptance_criteria"), list) else []
        lines = [
            f"Feature acceptance tests {'PASS' if success else 'FAIL'} ({status}).",
        ]
        if command_text:
            lines.append(f"Command: `{command_text}`.")
        if criteria:
            lines.append("Acceptance criteria: " + "; ".join(str(item) for item in criteria[:5]))
        if isinstance(matched_files, list) and matched_files:
            lines.append("Matched test files: " + ", ".join(str(item) for item in matched_files[:5]))
        if not success:
            lines.append(str(payload.get("error") or stderr or "feature_acceptance failed"))
        return "\n".join(lines)

    async def _has_completed_agent_run(self, task: Task, agent_name: str) -> bool:
        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task.id)
            .where(AgentRun.agent_name == agent_name)
            .where(AgentRun.status == "completed")
        )
        return result.scalars().first() is not None

    async def _phase_build_verify(self, task: Task) -> None:
        """Verify post-merge build."""
        workspace_path = task.workspace.path if task.workspace else ""

        feature_success, feature_output = await self._run_feature_acceptance_gate(
            task,
            workspace_path,
        )
        if not feature_success:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = feature_output
            await self.db.flush()
            return

        if self._use_deterministic_build_verifier(task):
            success, output_text = await self._record_deterministic_build_verification(
                task,
                workspace_path,
            )
            if not success:
                set_task_status(task, TaskStatus.FAILED)
                task.blocked_reason = f"build_verification_failed: {output_text}"
                await self.db.flush()
                return
            integration_error = await self._integrate_task_workspace(task)
            if integration_error:
                set_task_status(task, TaskStatus.FAILED)
                task.blocked_reason = integration_error
                await self.db.flush()
                return
            set_task_status(task, TaskStatus.DONE)
            task.blocked_reason = None
            self._clear_operator_decision_handoff(task)
            await self._maybe_mark_sprint_shipped(task)
            await self.db.flush()
            return

        result = await self._run_agent(
            task,
            "build-verifier",
            {
                "branch": task.workspace.branch if task.workspace else "main",
                "workspace_path": workspace_path,
            },
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = self._diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        elif verifier_failure := self._build_verifier_failure(result.output_text):
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = verifier_failure
        else:
            integration_error = await self._integrate_task_workspace(task)
            if integration_error:
                set_task_status(task, TaskStatus.FAILED)
                task.blocked_reason = integration_error
                await self.db.flush()
                return
            set_task_status(task, TaskStatus.DONE)
            task.blocked_reason = None
            self._clear_operator_decision_handoff(task)
            await self._maybe_mark_sprint_shipped(task)

        await self.db.flush()

    def _diagnose_task_failure(
        self,
        error: str,
        *,
        workspace_path: str = "",
        result: RunResult | None = None,
    ) -> str:
        issue = "agent_runtime_failure"
        detail = error
        if _is_codex_chunk_limit_error(error):
            issue = "codex_transport_chunk_limit"
            detail = "Codex app-server failed while streaming/parsing a large tool or agent output."
            if _workspace_contains_builder_internals(workspace_path):
                issue = "workspace_pollution_codex_chunk_limit"
                detail = (
                    "Task workspace contains builder internals such as .agent-builder, "
                    "dashboard bundles, copied server routes, or builder DB files; Codex "
                    "hit a transport chunk limit while operating in that polluted workspace."
                )
        evidence = []
        observability = result.observability if result else None
        if isinstance(observability, dict):
            runtime_sdk = str(observability.get("runtime_sdk") or "").strip()
            raw_event_count = observability.get("raw_event_count")
            duration_ms = observability.get("duration_ms")
            if runtime_sdk:
                evidence.append(f"runtime={runtime_sdk}")
            if raw_event_count is not None:
                evidence.append(f"events={raw_event_count}")
            if duration_ms is not None:
                evidence.append(f"duration_ms={duration_ms}")
        if workspace_path:
            evidence.append(f"workspace={workspace_path}")
        suffix = f" ({'; '.join(evidence)})" if evidence else ""
        return f"{issue}: {detail}{suffix}"

    def _build_verifier_failure(self, output_text: str) -> str | None:
        lines = [line.strip() for line in str(output_text or "").splitlines() if line.strip()]
        failing_lines = [
            line
            for line in lines
            if re.search(r"(?:^|`|\s)FAIL(?:\s|:|$)", line.replace("*", " "))
            and not self._is_advisory_verifier_failure(line)
        ]
        if not failing_lines:
            return None
        detail = "; ".join(failing_lines[:3])
        return f"build_verification_failed: {detail}"

    def _feature_verifier_failure(self, output_text: str) -> str | None:
        payload = _json_object_from_text(output_text)
        status = str(payload.get("status") or "").strip().lower()
        if status in {"", "pass", "passed"}:
            return None
        recommended = str(payload.get("recommended_next_action") or "").strip()
        detail = recommended or str(output_text or "").strip()[:500] or "feature verifier failed"
        return f"feature_acceptance_failed: verifier_status={status}: {detail}"

    def _is_advisory_verifier_failure(self, line: str) -> bool:
        lower = line.lower()
        return (
            "git status" in lower
            and "fail" in lower
            and "not a git repository" in lower
        )

    async def _maybe_mark_sprint_shipped(self, task: Task) -> None:
        depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
        sprint_payload = depends_on.get(SPRINT_EXECUTION_KEY)
        if not isinstance(sprint_payload, dict):
            return
        sprint_id = str(sprint_payload.get("sprint_id") or "").strip()
        if not sprint_id:
            return

        sprint = await self.db.get(Sprint, sprint_id)
        if sprint is None:
            return
        generated_ids = [str(task_id) for task_id in (sprint.generated_task_ids or [])]
        if not generated_ids:
            return

        result = await self.db.execute(select(Task).where(Task.id.in_(generated_ids)))
        sprint_tasks = list(result.scalars().all())
        if len(sprint_tasks) != len(set(generated_ids)):
            return
        if any(_task_status_value(sprint_task) != TaskStatus.DONE.value for sprint_task in sprint_tasks):
            return

        acceptance_result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.task_id.in_(generated_ids))
            .where(AgentRun.agent_name.in_(["feature-verifier", "feature-acceptance-tests"]))
            .order_by(AgentRun.started_at)
        )
        acceptance_runs = list(acceptance_result.scalars().all())
        acceptance_run_ids = [run.id for run in acceptance_runs if run.status == "completed"]
        sprint.phase = SprintPhase.SHIPPED
        sprint.verification_status = "passed"
        sprint.verification_evidence = {
            "status": "passed",
            "source_task_id": task.id,
            "generated_task_ids": generated_ids,
            "feature_acceptance_run_ids": acceptance_run_ids,
            "summary": (
                "All generated sprint tasks completed; feature-verifier acceptance, "
                "durable feature tests, and final build verification passed."
            ),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        approved_feature_ids = [str(feature_id) for feature_id in (sprint.approved_feature_ids or [])]
        if approved_feature_ids:
            feature_result = await self.db.execute(
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
            await self._run_post_ship_optimization_agent(task, sprint, sprint_context)
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

    async def _run_post_ship_optimization_agent(
        self,
        task: Task,
        sprint: Sprint,
        sprint_context: dict[str, Any],
    ) -> None:
        """Run a bounded optimization review after a sprint ships."""
        evidence = dict(sprint.verification_evidence or {})
        previous = evidence.get("optimization_agent")
        if isinstance(previous, dict) and previous.get("status") in {
            "completed",
            "implemented",
            "failed",
            "skipped",
            "blocked",
        }:
            return

        project_root = Path(str(getattr(task.feature.project, "repo_url", "") or "")).expanduser()
        observability_payload = self._post_ship_observability_payload()
        recommendations = (
            observability_payload.get("observability_coverage", {})
            .get("deterministic_recommendations", [])
        )
        if not recommendations:
            guidance_result = await self._run_app_runtime_guidance_optimization(
                task,
                project_root,
                observability_payload,
                reason="no_structured_recommendations",
            )
            if guidance_result is not None:
                evidence["optimization_agent"] = guidance_result
                sprint.verification_evidence = evidence
                return
            evidence["optimization_agent"] = {
                "status": "skipped",
                "reason": "no_structured_recommendations",
                "completed_at": datetime.now(UTC).isoformat(),
            }
            sprint.verification_evidence = evidence
            return

        deterministic_preflight = await self._run_deterministic_post_ship_optimization(
            task,
            project_root,
            recommendations,
            observability_payload,
        )
        if deterministic_preflight is not None:
            post_preflight_decision = self._post_ship_post_preflight_decision(
                project_root,
                deterministic_preflight,
                recommendations,
            )
            deterministic_preflight["post_preflight_decision"] = post_preflight_decision
            if not post_preflight_decision["model_backed_review_required"]:
                evidence["optimization_agent"] = deterministic_preflight
                sprint.verification_evidence = evidence
                return

        if deterministic_preflight is None and not _is_builder_source_repo(project_root):
            guidance_result = await self._run_app_runtime_guidance_optimization(
                task,
                project_root,
                observability_payload,
                reason="unsupported_deterministic_recommendation",
            )
            if guidance_result is not None:
                deterministic_preflight = guidance_result
                post_preflight_decision = self._post_ship_post_preflight_decision(
                    project_root,
                    deterministic_preflight,
                    recommendations,
                )
                deterministic_preflight["post_preflight_decision"] = post_preflight_decision
                if not post_preflight_decision["model_backed_review_required"]:
                    evidence["optimization_agent"] = deterministic_preflight
                    sprint.verification_evidence = evidence
                    return

        workspace_path = str(project_root)
        model_payload = dict(self._compact_optimization_payload(observability_payload))
        if deterministic_preflight is not None:
            model_payload["deterministic_preflight"] = deterministic_preflight
        result = await self._run_agent(
            task,
            "optimization-agent",
            {
                "sprint_context": json.dumps(sprint_context, ensure_ascii=True, sort_keys=True),
                "observability_payload": json.dumps(
                    model_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                "workspace_path": workspace_path,
            },
        )
        output_payload = _json_object_from_text(result.output_text or "")
        command_timeline = []
        if isinstance(deterministic_preflight, dict):
            command_timeline.extend(deterministic_preflight.get("commands", []))
        if isinstance(output_payload.get("commands"), list):
            command_timeline.extend(output_payload["commands"])
        recommendation_decisions = self._validated_optimization_recommendation_decisions(
            output_payload.get("recommendation_decisions"),
            command_timeline,
        )
        evidence["optimization_agent"] = {
            "status": (
                "failed"
                if result.error
                else str(output_payload.get("status") or "completed")
            ),
            "agent_name": "optimization-agent",
            "runtime_sdk": "model_backed",
            "session_id": result.session_id,
            "error": result.error or "",
            "summary": str(
                output_payload.get("summary")
                or output_payload.get("why_selected")
                or result.output_text
                or ""
            )[:1000],
            "selected_recommendation": str(output_payload.get("selected_recommendation") or ""),
            "selected_recommendations": (
                output_payload.get("selected_recommendations")
                if isinstance(output_payload.get("selected_recommendations"), list)
                else []
            ),
            "recommendation_decisions": (
                recommendation_decisions
            ),
            "why_selected": str(output_payload.get("why_selected") or ""),
            "benefit": str(output_payload.get("benefit") or ""),
            "files_changed": (
                output_payload.get("files_changed")
                if isinstance(output_payload.get("files_changed"), list)
                else []
            ),
            "commands": command_timeline,
            "deterministic_preflight": deterministic_preflight or {},
            "post_preflight_decision": (
                deterministic_preflight.get("post_preflight_decision")
                if isinstance(deterministic_preflight, dict)
                else {}
            ),
            "observability": {
                "metrics_source": "builder metrics show --json --full",
                "logs_source": "builder logs --info --compact --json",
                "analysis_source": "builder logs analyze --json",
                "optimization_decision": observability_payload.get("optimization_decision", {}),
                "app_scope": str(project_root),
            },
            "completed_at": datetime.now(UTC).isoformat(),
        }
        sprint.verification_evidence = evidence

    def _validated_optimization_recommendation_decisions(
        self,
        decisions: Any,
        command_timeline: list[Any],
    ) -> list[dict[str, Any]]:
        """Prevent unsupported optimization claims from being persisted as applied."""

        if not isinstance(decisions, list):
            return []
        exact_command_requirements = {
            "script_candidate_build_verify_script": "builder script run build_verify",
            "build_verify_script": "builder script run build_verify",
            "script_candidate_change_evidence_collector": "builder script run change_evidence",
            "change_evidence_collector": "builder script run change_evidence",
        }
        passed_commands = []
        for item in command_timeline:
            if not isinstance(item, dict):
                continue
            result = str(item.get("result") or "").lower()
            command = str(item.get("command") or "")
            if result == "pass" and command:
                passed_commands.append(command)

        validated: list[dict[str, Any]] = []
        for raw_decision in decisions:
            if not isinstance(raw_decision, dict):
                continue
            decision = dict(raw_decision)
            code = str(decision.get("code") or "")
            lifecycle = str(decision.get("lifecycle_status") or "").lower()
            required_command = exact_command_requirements.get(code)
            if (
                required_command
                and lifecycle == "applied"
                and not any(required_command in command for command in passed_commands)
            ):
                decision["lifecycle_status"] = "deferred"
                decision["reason"] = (
                    f"Exact command `{required_command}` was not recorded as pass in this "
                    "optimization run, so the builder cannot persist this recommendation as applied."
                )
            validated.append(decision)
        return validated

    def _post_ship_post_preflight_decision(
        self,
        project_root: Path,
        deterministic_preflight: dict[str, Any],
        recommendations: list[Any],
    ) -> dict[str, Any]:
        """Decide whether deterministic preflight fully resolved optimization work."""

        def recommendation_codes(raw: Any) -> set[str]:
            if isinstance(raw, str):
                return {raw} if raw.strip() else set()
            if isinstance(raw, dict):
                code = str(raw.get("code") or "").strip()
                return {code} if code else set()
            if not isinstance(raw, list):
                return set()
            codes: set[str] = set()
            for item in raw:
                if isinstance(item, str) and item.strip():
                    codes.add(item.strip())
                elif isinstance(item, dict) and str(item.get("code") or "").strip():
                    codes.add(str(item.get("code")).strip())
            return codes

        selected = str(deterministic_preflight.get("selected_recommendation") or "")
        implemented_codes = recommendation_codes(selected)
        implemented_codes.update(recommendation_codes(deterministic_preflight.get("selected_recommendations")))
        observability = deterministic_preflight.get("observability")
        guidance = (
            observability.get("app_runtime_guidance")
            if isinstance(observability, dict)
            else {}
        )
        if isinstance(guidance, dict) and guidance.get("status") in {"updated", "unchanged"}:
            implemented_codes.add("app_runtime_guidance_refresh")
        guidance_current = (
            selected == "app_runtime_guidance_refresh"
            and isinstance(guidance, dict)
            and guidance.get("status") in {"updated", "unchanged"}
        )

        residual_recommendations = [
            item
            for item in recommendations
            if isinstance(item, dict)
            and str(item.get("code") or "") not in implemented_codes
        ]
        recommendation_decisions: list[dict[str, Any]] = [
            {
                "code": code,
                "lifecycle_status": "applied",
                "reason": "deterministic preflight applied this recommendation",
            }
            for code in sorted(implemented_codes)
        ]
        if "script_candidate_build_verify_script" in implemented_codes:
            for item in residual_recommendations:
                if str(item.get("code") or "") != "script_candidate_command_sequence_wrapper":
                    continue
                recommendation_decisions.append(
                    {
                        "code": "script_candidate_command_sequence_wrapper",
                        "lifecycle_status": "applied",
                        "reason": (
                            "covered by builder script run build_verify for repeated setup, "
                            "lint, test, build, and app-smoke evidence"
                        ),
                    }
                )
        target_scope = "builder_source" if _is_builder_source_repo(project_root) else "generated_app"
        deterministic_status = str(deterministic_preflight.get("status") or "")
        auto_resolved_codes = {
            str(item.get("code") or "")
            for item in recommendation_decisions
            if item.get("lifecycle_status") in {"applied", "observed", "not_applicable", "rejected"}
        }
        for item in residual_recommendations:
            code = str(item.get("code") or "")
            if code in {"runtime_switch_preserve_history", "runtime_resume_recovered"}:
                recommendation_decisions.append(
                    {
                        "code": code,
                        "lifecycle_status": "observed",
                        "reason": "historical runtime signal; no current optimization action required",
                    }
                )
                auto_resolved_codes.add(code)
        actionable_residual_recommendations = [
            item
            for item in residual_recommendations
            if str(item.get("code") or "") not in auto_resolved_codes
            and str(item.get("code") or "") != "deterministic_baseline_ready"
        ]
        if deterministic_status not in {"implemented", "completed"} and not guidance_current:
            model_required = False
            reason = (
                "deterministic preflight did not complete; preserve the blocker before "
                "spending model tokens"
            )
        elif target_scope == "generated_app" and actionable_residual_recommendations:
            model_required = True
            reason = (
                "generated-app optimization has residual recommendations after deterministic "
                "preflight; route a compact model-backed review to apply, reject, or defer each "
                "remaining code from app-local evidence"
            )
        elif target_scope == "generated_app":
            model_required = False
            reason = (
                "generated-app optimization is resolved through app-local SDK guidance, "
                "deterministic scripts, and persisted recommendation decisions"
            )
        elif actionable_residual_recommendations:
            model_required = True
            reason = (
                "builder-source optimization has residual prompt, tool, model, or "
                "workflow recommendations after deterministic preflight"
            )
        else:
            model_required = False
            reason = "deterministic preflight fully resolved the structured recommendations"

        return {
            "target_scope": target_scope,
            "deterministic_status": deterministic_status,
            "deterministic_actions_applied": sorted(implemented_codes),
            "residual_recommendations": [
                {
                    "code": str(item.get("code") or ""),
                    "severity": str(item.get("severity") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                }
                for item in actionable_residual_recommendations
            ],
            "recommendation_decisions": recommendation_decisions,
            "model_backed_review_required": model_required,
            "reason": reason,
            "sdk_alignment": {
                "claude_agent_sdk": (
                    "use compact preflight evidence with explicit tool permissions, "
                    "subagent boundaries, and CLAUDE.md runtime guidance"
                ),
                "codex_sdk": (
                    "use compact preflight evidence with AGENTS.md project guidance, "
                    "sandbox/approval-aware commands, and Codex-native token/cost signals"
                ),
            },
        }

    def _refresh_app_runtime_guidance_payload(
        self,
        task: Task,
        project_root: Path,
    ) -> dict[str, Any]:
        """Refresh app-local SDK guidance without spending model tokens."""

        project = task.feature.project
        raw_language = str(getattr(project, "language", "") or "").strip()
        language = raw_language if raw_language and raw_language != "unknown" else None
        try:
            return refresh_project_runtime_guidance(
                project_root,
                project_name=str(getattr(project, "name", "") or project_root.name),
                language=language,
            )
        except Exception as exc:
            return {
                "status": "failed",
                "project_root": str(project_root),
                "updated_files": [],
                "unchanged_files": [],
                "skipped_files": [],
                "missing_files": [],
                "commands": {},
                "error": str(exc),
            }

    async def _run_app_runtime_guidance_optimization(
        self,
        task: Task,
        project_root: Path,
        observability_payload: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any] | None:
        """Record an app-scoped optimization when the only safe action is guidance refresh."""

        started_at = datetime.now(UTC)
        telemetry_commands = (
            await self._post_ship_optimization_cli_probe(project_root)
            if project_root.exists()
            else []
        )
        guidance = self._refresh_app_runtime_guidance_payload(task, project_root)
        completed_at = datetime.now(UTC)
        updated_files = [
            str(path) for path in guidance.get("updated_files", []) if str(path).strip()
        ]
        guidance_failed = guidance.get("status") == "failed"
        guidance_command = {
            "command": "builder runtime guidance refresh",
            "result": "fail" if guidance_failed else "pass",
            "summary": (
                str(guidance.get("error") or "failed to refresh app-local runtime guidance")
                if guidance_failed
                else (
                    "updated " + ", ".join(updated_files)
                    if updated_files
                    else "checked app-local runtime guidance"
                )
            ),
        }
        commands: list[dict[str, str]] = [*telemetry_commands, guidance_command]
        status = "blocked" if guidance_failed else "implemented" if updated_files else "skipped"
        summary = (
            "Refreshed the generated app's SDK guidance with discovered setup, run, test, "
            "lint, and build commands from the app workspace."
            if updated_files
            else (
                str(guidance.get("error") or "App-local runtime guidance refresh failed.")
                if guidance_failed
                else "Checked app-local SDK guidance; no builder-generated guidance needed changes."
            )
        )
        optimization = {
            "status": status,
            "agent_name": "optimization-agent",
            "runtime_sdk": "deterministic",
            "selected_recommendation": "app_runtime_guidance_refresh",
            "why_selected": (
                f"{reason}; generated-app optimization should update app-local SDK handoff "
                "surfaces before spending model tokens."
            ),
            "summary": summary,
            "benefit": (
                "Next sprint agents load concrete app commands and validation paths from "
                "CLAUDE.md/AGENTS.md, reducing discovery turns, stale-command drift, and "
                "unnecessary model-backed validation work."
            ),
            "files_changed": updated_files,
            "commands": commands,
            "command_timeline_source": "builder_cli_telemetry_then_runtime_guidance_refresh",
            "observability": {
                "metrics_source": "builder metrics show --json --full",
                "logs_source": "builder logs --info --compact --json",
                "analysis_source": "builder logs analyze --json",
                "optimization_decision": observability_payload.get("optimization_decision", {}),
                "app_runtime_guidance": guidance,
                "app_scope": str(project_root),
            },
            "completed_at": completed_at.isoformat(),
        }
        run = AgentRun(
            task_id=task.id,
            agent_name="optimization-agent",
            runtime_sdk="deterministic",
            provider="builder",
            model="none",
            effort="none",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            tokens_cached=0,
            num_turns=0,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            stop_reason=f"deterministic_{reason}",
            status="failed" if guidance_failed else "completed",
            error=str(guidance.get("error") or "") if guidance_failed else None,
            output_text=json.dumps(optimization, ensure_ascii=True, sort_keys=True),
            observability=optimization["observability"],
            started_at=started_at,
            completed_at=completed_at,
        )
        self.db.add(run)
        await self.db.flush()
        for item in commands:
            self.db.add(
                AgentRunEvent(
                    run_id=run.id,
                    event_type="tool_use",
                    tool_name=(
                        "builder_runtime_guidance"
                        if item["command"] == "builder runtime guidance refresh"
                        else "builder_cli"
                    ),
                    tool_input={"command": item["command"], "result": item["result"]},
                    output_preview=f"{item['result']}: {item['command']}",
                    timestamp=completed_at,
                )
            )
        return optimization

    async def _run_deterministic_post_ship_optimization(
        self,
        task: Task,
        project_root: Path,
        recommendations: list[Any],
        observability_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute known post-ship optimizations without spending model tokens."""

        by_code = {
            str(item.get("code") or ""): item
            for item in recommendations
            if isinstance(item, dict)
        }
        supported_scripts = {
            "script_candidate_build_verify_script": {
                "script": "build_verify",
                "command": "builder script run build_verify --json",
                "target_area": "build_verify_script",
                "summary": (
                    "Checked builder CLI metrics, compact logs, and observability analysis, then "
                    "replaced the post-ship model verification recommendation with builder script "
                    "run build_verify from the project root."
                ),
                "fallback_benefit": "Expected saving: avoids another model-backed build-verifier pass.",
                "savings_label": "model verification work",
            },
            "script_candidate_change_evidence_collector": {
                "script": "change_evidence",
                "command": "builder script run change_evidence --json",
                "target_area": "change_evidence_collector",
                "summary": (
                    "Checked builder CLI metrics, compact logs, and observability analysis, then "
                    "replaced model-backed PR evidence collection with builder script run "
                    "change_evidence from the project root."
                ),
                "fallback_benefit": "Expected saving: avoids another model-backed PR/evidence pass.",
                "savings_label": "model PR/evidence work",
            },
        }
        selected_codes = [code for code in by_code if code in supported_scripts]
        if not selected_codes:
            return None

        telemetry_commands = await self._post_ship_optimization_cli_probe(project_root)
        started_at = datetime.now(UTC)
        commands: list[dict[str, str]] = [*telemetry_commands]
        script_results: list[dict[str, Any]] = []
        summary_parts: list[str] = []
        failure_parts: list[str] = []
        total_estimated_savings = 0
        success = True

        for recommendation_code in selected_codes:
            recommendation = by_code[recommendation_code]
            script = supported_scripts[recommendation_code]
            args = json.dumps({"project_root": str(project_root)}, ensure_ascii=True)
            command = [
                sys.executable,
                "-m",
                "autonomous_agent_builder.cli.main",
                "script",
                "run",
                str(script["script"]),
                "--args",
                args,
                "--json",
            ]
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            stdout_text = stdout.decode(errors="replace")
            stderr_text = stderr.decode(errors="replace")
            payload = _json_object(stdout_text)
            script_success = proc.returncode == 0 and bool(payload.get("success", False))
            success = success and script_success
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            checks = data.get("checks") if isinstance(data, dict) else []
            estimated_savings = int(recommendation.get("estimated_savings_tokens") or 0)
            total_estimated_savings += estimated_savings
            commands.append(
                {
                    "command": str(script["command"]),
                    "result": "pass" if script_success else "fail",
                }
            )
            if isinstance(checks, list):
                for check in checks:
                    if not isinstance(check, dict):
                        continue
                    raw_command = check.get("command")
                    command_text = (
                        " ".join(str(part) for part in raw_command)
                        if isinstance(raw_command, list)
                        else str(raw_command or "")
                    ).strip()
                    if command_text:
                        commands.append(
                            {
                                "command": command_text,
                                "result": "pass" if check.get("status") == "passed" else "fail",
                            }
                        )
            result_summary = (
                str(script["summary"])
                if script_success
                else (payload.get("error") or stderr_text or f"{script['script']} command failed")
            )
            if script_success:
                summary_parts.append(result_summary)
            else:
                failure_parts.append(str(result_summary))
            script_results.append(
                {
                    "code": recommendation_code,
                    "script": str(script["script"]),
                    "status": "implemented" if script_success else "blocked",
                    "estimated_savings_tokens": estimated_savings,
                    "summary": str(result_summary)[:1000],
                }
            )

        guidance = self._refresh_app_runtime_guidance_payload(task, project_root)
        guidance_failed = guidance.get("status") == "failed"
        success = success and not guidance_failed
        updated_guidance_files = [
            str(path) for path in guidance.get("updated_files", []) if str(path).strip()
        ]
        commands.append(
            {
                "command": "builder runtime guidance refresh",
                "result": "fail" if guidance_failed else "pass",
                "summary": (
                    str(guidance.get("error") or "failed to refresh app-local runtime guidance")
                    if guidance_failed
                    else (
                        "updated " + ", ".join(updated_guidance_files)
                        if updated_guidance_files
                        else "checked app-local runtime guidance"
                    )
                ),
            }
        )
        completed_at = datetime.now(UTC)
        guidance_suffix = (
            " Refreshed app-local SDK guidance so the next sprint can load discovered "
            "setup, run, test, lint, and build commands without rediscovery."
            if updated_guidance_files
            else ""
        )
        optimization = {
            "status": "implemented" if success else "blocked",
            "agent_name": "optimization-agent",
            "runtime_sdk": "deterministic",
            "selected_recommendation": selected_codes[0],
            "selected_recommendations": selected_codes,
            "why_selected": "; ".join(
                str(
                    by_code[code].get("trigger")
                    or f"{supported_scripts[code]['target_area']} detected from builder CLI telemetry and logs"
                )
                for code in selected_codes
            ),
            "summary": (
                " ".join(summary_parts) + guidance_suffix
                if success
                else "; ".join(failure_parts or summary_parts or ["deterministic script optimization failed"])
            ),
            "benefit": (
                f"Expected saving: about {total_estimated_savings:,} tokens by replacing repeatable "
                f"model-backed work with deterministic script evidence across "
                f"{len(selected_codes)} recommendation(s). "
                "App-local guidance also reduces command rediscovery during the next SDK run."
                if total_estimated_savings
                else (
                    "Expected saving: replaces repeatable model-backed checks with deterministic "
                    "script evidence. App-local guidance refresh reduces command rediscovery "
                    "during the next SDK run."
                )
            ),
            "files_changed": updated_guidance_files,
            "commands": commands,
            "script_results": script_results,
            "command_timeline_source": "builder_cli_telemetry_then_script_run",
            "observability": {
                "metrics_source": "builder metrics show --json --full",
                "logs_source": "builder logs --info --compact --json",
                "analysis_source": "builder logs analyze --json",
                "raw_token_total": (
                    observability_payload.get("optimization_summary", {})
                    if isinstance(observability_payload.get("optimization_summary"), dict)
                    else {}
                ).get("raw_token_total"),
                "optimization_decision": observability_payload.get("optimization_decision", {}),
                "app_runtime_guidance": guidance,
            },
            "completed_at": completed_at.isoformat(),
        }
        run = AgentRun(
            task_id=task.id,
            agent_name="optimization-agent",
            runtime_sdk="deterministic",
            provider="builder",
            model="none",
            effort="none",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            tokens_cached=0,
            num_turns=0,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            stop_reason="deterministic_post_ship_optimization",
            status="completed" if success else "failed",
            error=None
            if success
            else "; ".join(failure_parts or [str(guidance.get("error") or "script optimization failed")]),
            output_text=json.dumps(optimization, ensure_ascii=True, sort_keys=True),
            observability=optimization["observability"],
            started_at=started_at,
            completed_at=completed_at,
        )
        self.db.add(run)
        await self.db.flush()
        for index, item in enumerate(commands):
            self.db.add(
                AgentRunEvent(
                    run_id=run.id,
                    event_type="tool_use",
                    tool_name=(
                        "builder_script"
                        if item["command"].startswith("builder script run")
                        else "builder_runtime_guidance"
                        if item["command"] == "builder runtime guidance refresh"
                        else "builder_cli"
                    ),
                    tool_input={"command": item["command"], "result": item["result"]},
                    output_preview=f"{item['result']}: {item['command']}",
                    timestamp=completed_at,
                )
        )
        return optimization

    async def _post_ship_optimization_cli_probe(self, project_root: Path) -> list[dict[str, str]]:
        """Run builder CLI telemetry/log probes before choosing the optimization action."""

        commands: list[tuple[str, list[str]]] = [
            (
                "builder metrics show --json --full",
                [
                    sys.executable,
                    "-m",
                    "autonomous_agent_builder.cli.main",
                    "metrics",
                    "show",
                    "--json",
                    "--full",
                ],
            ),
            (
                "builder logs --info --compact --json",
                [
                    sys.executable,
                    "-m",
                    "autonomous_agent_builder.cli.main",
                    "logs",
                    "--info",
                    "--compact",
                    "--json",
                ],
            ),
            (
                "builder logs analyze --json",
                [
                    sys.executable,
                    "-m",
                    "autonomous_agent_builder.cli.main",
                    "logs",
                    "analyze",
                    "--json",
                ],
            ),
        ]
        timeline: list[dict[str, str]] = []
        for label, argv in commands:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            payload = _json_object(stdout.decode(errors="replace"))
            summary = self._post_ship_probe_summary(label, proc.returncode, payload)
            if proc.returncode != 0 and not summary:
                summary = stderr.decode(errors="replace").strip()[:180] or "command failed"
            timeline.append(
                {
                    "command": label,
                    "result": "pass" if proc.returncode == 0 else "fail",
                    "summary": summary,
                }
            )
        return timeline

    def _post_ship_probe_summary(
        self,
        label: str,
        returncode: int,
        payload: dict[str, Any],
    ) -> str:
        if returncode != 0:
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                return str(error.get("message") or error.get("hint") or "command failed")[:180]
            return "command failed"
        if "metrics show" in label:
            decision = payload.get("optimization_decision")
            summary = payload.get("optimization_summary")
            next_action = (
                decision.get("next_action")
                if isinstance(decision, dict)
                else payload.get("next_step")
            )
            raw_tokens = (
                summary.get("raw_token_total")
                if isinstance(summary, dict)
                else payload.get("total_tokens")
            )
            parts = []
            if next_action:
                parts.append(f"candidate={next_action}")
            if raw_tokens:
                parts.append(f"raw_tokens={raw_tokens}")
            return "; ".join(parts) or "metrics inspected"
        if "logs --info" in label:
            items = payload.get("items")
            if isinstance(items, list):
                return f"compact_log_events={len(items)}"
            return "compact logs inspected"
        if "logs analyze" in label:
            counts = payload.get("counts")
            missing = payload.get("missing")
            if not isinstance(counts, dict):
                coverage = payload.get("observability_coverage")
                counts = coverage.get("counts") if isinstance(coverage, dict) else {}
                missing = coverage.get("missing_signals") if isinstance(coverage, dict) else missing
            parts = []
            if isinstance(counts, dict):
                if counts.get("tools") is not None:
                    parts.append(f"tools={counts.get('tools')}")
                if counts.get("errors") is not None:
                    parts.append(f"errors={counts.get('errors')}")
            if isinstance(missing, list) and missing:
                parts.append("missing=" + ",".join(str(item) for item in missing[:3]))
            return "; ".join(parts) or "observability analysis inspected"
        return "inspected"

    def _post_ship_observability_payload(self) -> dict[str, Any]:
        db_path = _sqlite_path_from_sync_url(self.settings.db.sync_url)
        if db_path is None:
            return {
                "ok": False,
                "status": "unavailable",
                "reason": "non_sqlite_db_path",
                "observability_coverage": {"deterministic_recommendations": []},
            }
        return dashboard_observability_summary(db_path)

    def _compact_optimization_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        coverage = payload.get("observability_coverage", {})
        aggregates = payload.get("runtime_aggregates", {})
        return {
            "runtime": payload.get("runtime", {}),
            "recommendations": coverage.get("deterministic_recommendations", []),
            "resolved_recommendations": coverage.get("resolved_recommendations", []),
            "recommendation_lifecycle": coverage.get("recommendation_lifecycle", {}),
            "telemetry_health": coverage.get("telemetry_health", {}),
            "optimization_decision": payload.get("optimization_decision", {}),
            "runtime_recovery": aggregates.get("runtime_recovery", {}),
            "tool_observability": aggregates.get("tool_observability", {}),
            "totals": aggregates.get("totals", {}),
        }

    async def _integrate_task_workspace(self, task: Task) -> str | None:
        workspace = getattr(task, "workspace", None)
        if not workspace:
            return None
        if getattr(workspace, "is_worktree", False) is not True:
            return await self._integrate_directory_workspace(task)
        branch = str(getattr(workspace, "branch", "") or "").strip()
        repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
        if not branch or not repo_url:
            return None

        repo_root = Path(repo_url).expanduser()
        if not repo_root.exists():
            return f"Integration failed: repo root does not exist at {repo_root}"

        async def run_git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, (
                stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )

        owner_surface_error = await self._preserve_project_runtime_guidance(
            task,
            str(getattr(workspace, "path", "") or ""),
        )
        if owner_surface_error:
            return owner_surface_error

        guidance_snapshot = self._project_runtime_guidance_snapshot(repo_root)
        clean_error = await self._clean_project_runtime_guidance_for_git_operation(
            run_git,
            guidance_snapshot,
        )
        if clean_error:
            return clean_error

        branch_code, branch_output = await run_git("rev-parse", "--verify", branch)
        if branch_code != 0:
            commit_error = await self._commit_task_workspace_changes(task)
            if commit_error:
                return commit_error
            branch_code, branch_output = await run_git("rev-parse", "--verify", branch)
            if branch_code != 0:
                return f"Integration failed: task branch {branch} is missing: {branch_output.strip()}"
        branch_commit = branch_output.strip().splitlines()[0]

        head_code, _ = await run_git("rev-parse", "--verify", "HEAD")
        if head_code != 0:
            update_code, update_output = await run_git(
                "update-ref", "refs/heads/main", branch_commit
            )
            if update_code != 0:
                return f"Integration failed: could not initialize main: {update_output.strip()}"
            reset_code, reset_output = await run_git("reset", "--hard", "main")
            if reset_code != 0:
                return f"Integration failed: could not materialize main: {reset_output.strip()}"
            restore_error = await self._restore_project_runtime_guidance_snapshot(
                repo_root,
                guidance_snapshot,
                run_git,
            )
            if restore_error:
                return restore_error
            log.info("workspace_integrated_unborn_main", task_id=task.id, branch=branch)
            return None

        merge_code, merge_output = await run_git("merge", "--ff-only", branch)
        if merge_code != 0 and _is_fast_forward_divergence(merge_output):
            rebase_error = await self._rebase_task_workspace_for_integration(
                task,
                str(getattr(workspace, "path", "") or ""),
                branch,
            )
            if rebase_error:
                return rebase_error
            owner_surface_error = await self._preserve_project_runtime_guidance(
                task,
                str(getattr(workspace, "path", "") or ""),
            )
            if owner_surface_error:
                return owner_surface_error
            merge_code, merge_output = await run_git("merge", "--ff-only", branch)
        if merge_code != 0:
            return f"Integration failed: could not fast-forward {branch}: {merge_output.strip()}"
        restore_error = await self._restore_project_runtime_guidance_snapshot(
            repo_root,
            guidance_snapshot,
            run_git,
        )
        if restore_error:
            return restore_error
        log.info("workspace_integrated_fast_forward", task_id=task.id, branch=branch)
        return None

    async def _commit_task_workspace_changes(self, task: Task) -> str | None:
        workspace = getattr(task, "workspace", None)
        workspace_path = str(getattr(workspace, "path", "") or "").strip()
        if not workspace_path:
            return None

        async def run_workspace_git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, (
                stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )

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
                "Integration failed: could not stage task workspace changes: "
                f"{add_output.strip()}"
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

    async def _integrate_directory_workspace(self, task: Task) -> str | None:
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
            if _workspace_copy_excluded(rel):
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

    async def _rebase_task_workspace_for_integration(
        self,
        task: Task,
        workspace_path: str,
        branch: str,
    ) -> str | None:
        if not workspace_path:
            return "Integration failed: task workspace path is missing for rebase"
        workspace = Path(workspace_path)
        if not workspace.exists():
            return f"Integration failed: task workspace does not exist at {workspace}"

        async def run_git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, (
                stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )

        checkout_code, checkout_output = await run_git("checkout", branch)
        if checkout_code != 0:
            return (
                f"Integration failed: could not checkout task branch {branch}: "
                f"{checkout_output.strip()}"
            )

        rebase_code, rebase_output = await run_git("rebase", "main")
        attempts = 0
        while rebase_code != 0:
            conflict_code, conflict_output = await run_git(
                "diff",
                "--name-only",
                "--diff-filter=U",
            )
            conflict_files = [
                line.strip()
                for line in conflict_output.splitlines()
                if line.strip()
            ]
            if conflict_code != 0 or not conflict_files or attempts >= 2:
                await run_git("rebase", "--abort")
                return (
                    "Integration failed: task branch could not rebase onto current main: "
                    f"{rebase_output.strip()}"
                )
            attempts += 1
            resolver_error = await self._run_integration_conflict_resolver(
                task,
                str(workspace),
                branch,
                conflict_files,
                rebase_output,
            )
            if resolver_error:
                await run_git("rebase", "--abort")
                return resolver_error
            marker_error = self._conflict_markers_remaining(workspace, conflict_files)
            if marker_error:
                await run_git("rebase", "--abort")
                return marker_error
            add_code, add_output = await run_git("add", "--", *conflict_files)
            if add_code != 0:
                await run_git("rebase", "--abort")
                return (
                    "Integration failed: could not stage resolved rebase conflicts: "
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

    async def _run_integration_conflict_resolver(
        self,
        task: Task,
        workspace_path: str,
        branch: str,
        conflict_files: list[str],
        rebase_output: str,
    ) -> str | None:
        result = await self._run_agent(
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

    def _conflict_markers_remaining(self, workspace: Path, conflict_files: list[str]) -> str | None:
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

    def _project_runtime_guidance_snapshot(self, repo_root: Path) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for relative_path in _PROJECT_RUNTIME_GUIDANCE_PATHS:
            path = repo_root / relative_path
            if path.is_file():
                snapshot[str(relative_path)] = path.read_bytes()
        return snapshot

    async def _clean_project_runtime_guidance_for_git_operation(
        self,
        run_git: _GitRunner,
        snapshot: dict[str, bytes],
    ) -> str | None:
        paths = list(snapshot)
        if not paths:
            return None
        head_code, _ = await run_git("rev-parse", "--verify", "HEAD")
        if head_code != 0:
            return None
        status_code, status_output = await run_git("status", "--short", "--", *paths)
        if status_code != 0:
            return (
                "Integration failed: could not inspect runtime guidance before merge: "
                f"{status_output.strip()}"
            )
        if not status_output.strip():
            return None
        checkout_code, checkout_output = await run_git("checkout", "--", *paths)
        if checkout_code != 0:
            return (
                "Integration failed: could not prepare runtime guidance before merge: "
                f"{checkout_output.strip()}"
            )
        return None

    async def _restore_project_runtime_guidance_snapshot(
        self,
        repo_root: Path,
        snapshot: dict[str, bytes],
        run_git: _GitRunner,
    ) -> str | None:
        restored: list[str] = []
        for relative_path, expected in snapshot.items():
            path = repo_root / relative_path
            current = path.read_bytes() if path.is_file() else None
            if current == expected:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
            restored.append(relative_path)
        if not restored:
            return None
        add_code, add_output = await run_git("add", "--", *restored)
        if add_code != 0:
            return (
                "Integration failed: could not restore runtime guidance after merge: "
                f"{add_output.strip()}"
            )
        diff_code, diff_output = await run_git("diff", "--cached", "--name-only", "--", *restored)
        if diff_code != 0:
            return (
                "Integration failed: could not inspect restored runtime guidance: "
                f"{diff_output.strip()}"
            )
        if not diff_output.strip():
            return None
        commit_code, commit_output = await run_git(
            "-c",
            "user.name=Autonomous Builder",
            "-c",
            "user.email=builder@example.local",
            "commit",
            "-m",
            "chore: restore builder runtime guidance",
            "--",
            *restored,
        )
        if commit_code != 0:
            return (
                "Integration failed: could not commit restored runtime guidance: "
                f"{commit_output.strip()}"
            )
        return None

    async def _preserve_project_runtime_guidance(
        self,
        task: Task,
        workspace_path: str,
    ) -> str | None:
        """Keep builder runtime guidance from being replaced by generated app docs."""
        if not workspace_path:
            return None

        repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
        if not repo_url:
            return None
        repo_root = Path(repo_url).expanduser()
        workspace = Path(workspace_path).expanduser()
        if not repo_root.exists() or not workspace.exists():
            return None

        restored: list[str] = []
        for relative_path in _PROJECT_RUNTIME_GUIDANCE_PATHS:
            source = repo_root / relative_path
            target = workspace / relative_path
            if not source.is_file():
                continue
            source_bytes = source.read_bytes()
            target_bytes = target.read_bytes() if target.is_file() else None
            if target_bytes == source_bytes:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes)
            restored.append(str(relative_path))

        if not restored:
            return None

        async def run_git(*args: str) -> tuple[int, str]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, (
                stdout.decode(errors="replace") + stderr.decode(errors="replace")
            )

        add_code, add_output = await run_git("add", "--", *restored)
        if add_code != 0:
            return f"Owner surface protection failed: could not stage runtime guidance: {add_output.strip()}"

        diff_code, diff_output = await run_git("diff", "--cached", "--name-only", "--", *restored)
        if diff_code != 0:
            return f"Owner surface protection failed: could not inspect runtime guidance: {diff_output.strip()}"
        if not diff_output.strip():
            return None

        commit_code, commit_output = await run_git(
            "-c",
            "user.name=Autonomous Builder",
            "-c",
            "user.email=builder@example.local",
            "commit",
            "-m",
            "chore: preserve builder runtime guidance",
            "--",
            *restored,
        )
        if commit_code != 0:
            return f"Owner surface protection failed: could not commit runtime guidance: {commit_output.strip()}"

        log.info(
            "project_runtime_guidance_preserved",
            task_id=task.id,
            paths=restored,
        )
        return None

    def _build_active_feature_scope_reminder(self, task: Task) -> str:
        """Render a ``<system-reminder>`` block describing the active feature.

        Pulls feature description + acceptance criteria from the task's
        feature and formats them as a high-attention reminder. Per
        ``/claude-api`` guidance, mid-session system-prompt edits invalidate
        the prompt cache; per-task variants belong in the user message as a
        ``<system-reminder>`` block so the cached system prefix
        (CLAUDE.md + tools + preset) stays warm across all task dispatches.

        Returns an empty string when no feature is attached, so the prompt
        template's ``{scope_reminder}`` placeholder collapses safely.
        """
        feature = getattr(task, "feature", None)
        if feature is None:
            return ""
        title = str(getattr(feature, "title", "") or "").strip()
        description = str(getattr(feature, "description", "") or "").strip()
        criteria_raw = getattr(feature, "acceptance_criteria", None) or []
        criteria = [str(item).strip() for item in criteria_raw if str(item).strip()]
        if not (title or description or criteria):
            return ""
        lines = ["<system-reminder>"]
        lines.append("Active feature scope (sprint task)")
        if title:
            lines.append(f"Feature: {title}")
        if description:
            lines.append(f"Description: {description}")
        if criteria:
            lines.append("Acceptance criteria (the verifier WILL check these):")
            lines.extend(f"- {item}" for item in criteria)
        lines.append("")
        lines.append(
            "Do not introduce stack choices that contradict CLAUDE.md "
            "## Project Context. If the acceptance criteria conflict with what "
            "you would otherwise build, surface a blocker instead of silently "
            "diverging."
        )
        lines.append("</system-reminder>\n\n")
        return "\n".join(lines)

    async def _run_agent(
        self,
        task: Task,
        agent_name: str,
        template_vars: dict[str, str],
        resume_session: str | None = None,
    ) -> RunResult:
        """Run an agent phase, save run result, return RunResult."""
        agent_def = get_agent_definition(agent_name)

        # Build prompt from template
        from autonomous_agent_builder.agents.tool_registry import ToolRegistry

        registry = ToolRegistry.build(list(agent_def.tools))
        template_vars["tool_context"] = registry.get_tool_prompt_context()
        template_vars.setdefault(
            "knowledge_requirements",
            (
                "No task-scoped repo-local knowledge requirements were provided. "
                "Use builder KB tools for durable KB work and avoid editing KB files directly."
            ),
        )
        # Defensive default so any code path dispatching code-gen (or future
        # agents that adopt the {scope_reminder} placeholder) without a
        # populated reminder still renders a valid prompt instead of a
        # KeyError. Production path (_phase_implementation) always sets this.
        template_vars.setdefault("scope_reminder", "")

        prompt = agent_def.prompt_template.format(**template_vars)
        prompt_budget = prompt_budget_breakdown(
            agent_name=agent_name,
            prompt=prompt,
            template_vars=template_vars,
            agent_definition=agent_def.prompt_template,
        )
        runtime_policy = resolve_agent_runtime_policy(agent_def, self.settings)
        project_root = Path(str(getattr(task.feature.project, "repo_url", "") or "")).expanduser()
        runtime_config = (
            resolve_project_runtime_config(project_root)
            if project_root.exists()
            else resolve_runtime_config(self.settings)
        )

        runtime = create_runtime(**runtime_config)
        if hasattr(runtime, "_runner"):
            runtime._runner = self.runner
        runtime_name_value = getattr(runtime, "name", "")
        runtime_name = runtime_name_value if isinstance(runtime_name_value, str) else "claude_agent_sdk"
        runtime_provider_value = getattr(runtime, "provider", "")
        runtime_provider = runtime_provider_value if isinstance(runtime_provider_value, str) else ""
        run = AgentRun(
            task_id=task.id,
            agent_name=agent_name,
            runtime_sdk=runtime_name,
            provider=runtime_provider,
            model=str(runtime_config.get("model") or runtime_policy.model),
            effort=runtime_policy.effort,
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.commit()
        await self._publish_realtime_board_snapshot()

        output_parts: list[str] = []
        pending_output_parts: list[str] = []
        last_publish_at = 0.0
        workspace_path = template_vars.get("workspace_path", "")
        stop_monitor = asyncio.Event()
        last_diff_signature = ""
        db_write_lock = asyncio.Lock()

        async def persist_realtime_run_update(*objects: object) -> None:
            async with db_write_lock:
                for obj in objects:
                    self.db.add(obj)
                await self.db.flush()
                await self.db.commit()
                await self._publish_realtime_board_snapshot()

        async def record_output_chunk(delta: str) -> None:
            nonlocal last_publish_at
            text = str(delta or "")
            if not text.strip():
                return
            output_parts.append(text)
            pending_output_parts.append(text)
            run.output_text = "".join(output_parts)[-12000:]
            now = asyncio.get_running_loop().time()
            if now - last_publish_at >= 1.0:
                last_publish_at = now
                preview = " ".join("".join(pending_output_parts).strip().split())
                pending_output_parts.clear()
                event = (
                    AgentRunEvent(
                        run_id=run.id,
                        event_type="agent_output",
                        output_preview=preview[:500],
                        timestamp=datetime.now(UTC),
                    )
                    if preview
                    else None
                )
                await persist_realtime_run_update(*([event] if event is not None else []))

        async def record_runtime_event(
            event_payload: dict[str, Any] | None = None,
            *,
            event_type: str | None = None,
            tool_name: str | None = None,
            tool_input: dict[str, Any] | None = None,
            output_preview: str = "",
        ) -> None:
            if isinstance(event_payload, dict):
                event_type = event_type or str(event_payload.get("event_type") or "tool_use")
                tool_name = tool_name or str(event_payload.get("tool_name") or "") or None
                raw_tool_input = event_payload.get("tool_input")
                if tool_input is None and isinstance(raw_tool_input, dict):
                    tool_input = dict(raw_tool_input)
                tool_use_id = str(event_payload.get("tool_use_id") or "").strip()
                if tool_use_id:
                    tool_input = dict(tool_input or {})
                    tool_input.setdefault("tool_use_id", tool_use_id)
                if not output_preview:
                    output_preview = str(
                        event_payload.get("output_preview")
                        or event_payload.get("tool_response")
                        or event_payload.get("tool_result")
                        or ""
                    )
            event_type = event_type or "tool_use"
            event = AgentRunEvent(
                run_id=run.id,
                event_type=event_type,
                tool_name=tool_name,
                tool_input=tool_input,
                output_preview=output_preview[:500],
                timestamp=datetime.now(UTC),
            )
            await persist_realtime_run_update(event)

        async def monitor_workspace_diff() -> None:
            nonlocal last_diff_signature
            while not stop_monitor.is_set():
                await asyncio.sleep(1.0)
                diff_summary = capture_workspace_diff(workspace_path)
                if not diff_summary:
                    continue
                signature = json.dumps(diff_summary, sort_keys=True)
                if signature == last_diff_signature:
                    continue
                last_diff_signature = signature
                run.diff_summary = diff_summary
                await persist_realtime_run_update()

        monitor_task = asyncio.create_task(monitor_workspace_diff()) if workspace_path else None
        result = await runtime.run(
            prompt,
            agent=agent_name,
            workspace_path=workspace_path,
            session=resume_session,
            effort=runtime_policy.effort,
            on_chunk=record_output_chunk,
            on_tool_event=record_runtime_event,
        )
        stop_monitor.set()
        if monitor_task is not None:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task

        diff_summary = result.diff_summary or capture_workspace_diff(workspace_path)
        observability = dict(result.observability or {})
        decision_summary = runtime_decision_summary(
            runtime_name,
            aggregates={},
            optimization=observability.get("optimization_summary") or {},
        )
        phase_name = str(getattr(task, "phase", "") or getattr(task, "status", "") or "")
        observability["runtime_decision_summary"] = decision_summary
        observability["phase_runtime_decision"] = next(
            (
                decision
                for decision in decision_summary.get("phase_decisions", [])
                if str(decision.get("phase")) in phase_name.lower()
            ),
            {
                "phase": phase_name.lower() or "unknown",
                "selected_runtime": decision_summary.get("runtime", runtime_name),
                "model_effort": runtime_policy.effort,
                "tool_route": runtime_policy.context_strategy,
                "subagent_policy": "bounded_sidecar_only",
                "context_strategy": runtime_policy.context_strategy,
                "expected_evidence": "agent run result and task state transition",
                "reason_code": "agent_runtime_policy",
            },
        )
        if runtime_name == "codex_sdk":
            optimization_summary = codex_run_optimization_summary(
                events=result.raw_events or [],
                metrics={
                    "input_tokens": result.tokens_input,
                    "output_tokens": result.tokens_output,
                    "cached_input_tokens": result.tokens_cached,
                    "reasoning_output_tokens": int(
                        (observability.get("optimization_summary") or {})
                        .get("token_accounting", {})
                        .get("reasoning_output_tokens")
                        or observability.get("reasoning_output_tokens")
                        or 0
                    ),
                    "total_tokens": result.tokens_input + result.tokens_output,
                    "turns": result.num_turns,
                },
                agent_name=agent_name,
                prompt_text=prompt,
                output_text=result.output_text,
                status="failed" if result.error else "completed",
                prompt_budget=prompt_budget,
            )
            observability["optimization_summary"] = optimization_summary
            observability["runtime_decision_summary"] = runtime_decision_summary(
                runtime_name,
                aggregates={},
                optimization=optimization_summary,
            )
        run.session_id = result.session_id
        run.runtime_sdk = runtime_name
        run.provider = runtime_provider
        run.model = str(runtime_config.get("model") or runtime_policy.model)
        run.effort = runtime_policy.effort
        run.cost_usd = result.cost_usd
        run.tokens_input = result.tokens_input
        run.tokens_output = result.tokens_output
        run.tokens_cached = result.tokens_cached
        run.num_turns = result.num_turns
        run.duration_ms = result.duration_ms
        run.stop_reason = result.stop_reason
        run.status = "completed" if not result.error else "failed"
        run.error = result.error
        run.output_text = result.output_text or "".join(output_parts)
        preview = " ".join("".join(pending_output_parts).strip().split())
        final_event = (
            AgentRunEvent(
                run_id=run.id,
                event_type="agent_output",
                output_preview=preview[:500],
                timestamp=datetime.now(UTC),
            )
            if preview
            else None
        )
        run.confidence = result.confidence
        run.diff_summary = diff_summary
        run.observability = observability or result.observability
        run.completed_at = datetime.now(UTC)
        await persist_realtime_run_update(*([final_event] if final_event is not None else []))

        return result

    async def _publish_realtime_board_snapshot(self) -> None:
        if not isinstance(self.db, AsyncSession):
            return
        try:
            from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot

            await publish_board_snapshot(self.db)
        except Exception as exc:
            log.debug("dashboard_realtime_publish_failed", error=str(exc))

    async def _run_documentation_refresh_gate(
        self,
        task: Task,
        workspace_path: str,
    ) -> str | None:
        """Block PR creation until maintained docs are current."""
        project_root = self._resolve_documentation_project_root(task, workspace_path)
        validation_payload = await self._load_kb_validation_payload(project_root)
        if bool(validation_payload.get("passed", False)):
            return None
        if not await self._project_has_canonical_head(project_root):
            log.info(
                "documentation_refresh_gate_advisory_unborn_repo",
                task_id=task.id,
                project_root=str(project_root),
                summary=str(validation_payload.get("summary", "") or ""),
            )
            return None
        if self._forward_engineering_seed_docs_deferred(project_root, validation_payload):
            log.info(
                "documentation_refresh_gate_advisory_forward_seed_docs",
                task_id=task.id,
                project_root=str(project_root),
                summary=str(validation_payload.get("summary", "") or ""),
            )
            return None
        if self._forward_engineering_sprint_doc_hash_drift_advisory(
            task,
            project_root,
            validation_payload,
        ):
            log.info(
                "documentation_refresh_gate_advisory_forward_sprint_doc_hash_drift",
                task_id=task.id,
                project_root=str(project_root),
                summary=str(validation_payload.get("summary", "") or ""),
            )
            return None

        bridge_payload = await run_documentation_refresh_bridge(
            validation_payload,
            project_root=project_root,
        )
        await self._record_documentation_bridge_run(task, bridge_payload)
        if self._forward_engineering_non_actionable_doc_validation(
            project_root,
            bridge_payload,
        ):
            log.info(
                "documentation_refresh_gate_advisory_forward_no_actionable_docs",
                task_id=task.id,
                project_root=str(project_root),
                summary=str(bridge_payload.get("summary", "") or ""),
            )
            return None

        bridge_status = str(bridge_payload.get("status", "") or "").strip()
        if bridge_status not in {"already_current", "updated_and_verified"}:
            return self._documentation_gate_message(bridge_payload)

        post_validation_payload = await self._load_kb_validation_payload(project_root)
        if bool(post_validation_payload.get("passed", False)):
            return None
        summary = str(
            post_validation_payload.get("summary", "")
            or "validation still failing after documentation refresh"
        ).strip()
        return f"documentation refresh gate blocked: {summary}"

    def _resolve_documentation_project_root(self, task: Task, workspace_path: str) -> Path:
        """Prefer a real project repo path, falling back to the task workspace."""
        workspace_root = Path(workspace_path or ".").resolve()
        project = getattr(getattr(task, "feature", None), "project", None)
        repo_root = getattr(project, "repo_url", "") if project is not None else ""
        if not isinstance(repo_root, str) or not repo_root.strip() or "://" in repo_root:
            return workspace_root

        candidate = Path(repo_root).expanduser().resolve()
        if candidate.exists():
            return candidate
        return workspace_root

    async def _load_kb_validation_payload(self, project_root: Path) -> dict[str, object]:
        response = await builder_kb_validate(project_root=str(project_root))
        content = response.get("content")
        if not isinstance(content, list) or not content:
            raise RuntimeError("builder_kb_validate returned no content")
        item = content[0]
        if not isinstance(item, dict):
            raise RuntimeError("builder_kb_validate returned invalid content")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("builder_kb_validate returned empty text payload")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise RuntimeError("builder_kb_validate returned a non-object payload")
        return payload

    async def _project_has_canonical_head(self, project_root: Path) -> bool:
        git_dir = project_root / ".git"
        if not git_dir.exists():
            return True
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--verify",
            "HEAD",
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0

    def _forward_engineering_seed_docs_deferred(
        self,
        project_root: Path,
        validation_payload: dict[str, object],
    ) -> bool:
        from autonomous_agent_builder.onboarding import load_onboarding_state

        state = load_onboarding_state(project_root)
        if state.get("onboarding_mode") != "forward_engineering":
            return False
        checks = validation_payload.get("checks")
        if not isinstance(checks, list):
            return False
        freshness = next(
            (
                item
                for item in checks
                if isinstance(item, dict) and item.get("name") == "freshness"
            ),
            None,
        )
        if freshness is not None and not bool(freshness.get("passed", False)):
            return False
        claim_failures = validation_payload.get("claim_failures")
        if not isinstance(claim_failures, list) or not claim_failures:
            return False
        return all(
            isinstance(item, dict) and item.get("reason") == "missing_document"
            for item in claim_failures
        )

    def _forward_engineering_sprint_doc_hash_drift_advisory(
        self,
        task: Task,
        project_root: Path,
        validation_payload: dict[str, object],
    ) -> bool:
        """Do not block generated feature delivery on non-actionable KB hash drift."""
        from autonomous_agent_builder.onboarding import load_onboarding_state

        state = load_onboarding_state(project_root)
        if state.get("onboarding_mode") != "forward_engineering":
            return False
        depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
        sprint_execution = depends_on.get("sprint_execution")
        if not isinstance(sprint_execution, dict):
            return False
        if sprint_execution.get("mode") != "sprint_task_breakdown":
            return False
        if validation_payload.get("claim_failures"):
            return False

        checks = validation_payload.get("checks")
        if not isinstance(checks, list):
            return False
        failed_names = {
            str(check.get("name", "") or "").strip()
            for check in checks
            if isinstance(check, dict) and not bool(check.get("passed", False))
        }
        if not failed_names or not failed_names.issubset({"citation_validity", "freshness"}):
            return False

        freshness = next(
            (
                item
                for item in checks
                if isinstance(item, dict) and item.get("name") == "freshness"
            ),
            None,
        )
        details = freshness.get("details") if isinstance(freshness, dict) else {}
        maintained_docs = (
            details.get("maintained_docs") if isinstance(details, dict) else None
        )
        if isinstance(maintained_docs, list) and maintained_docs:
            return False
        return True

    def _forward_engineering_non_actionable_doc_validation(
        self,
        project_root: Path,
        bridge_payload: dict[str, object],
    ) -> bool:
        from autonomous_agent_builder.onboarding import load_onboarding_state

        state = load_onboarding_state(project_root)
        if state.get("onboarding_mode") != "forward_engineering":
            return False
        if str(bridge_payload.get("status", "") or "").strip() != "manual_attention":
            return False
        actionable_doc_ids = bridge_payload.get("actionable_doc_ids")
        if isinstance(actionable_doc_ids, list) and actionable_doc_ids:
            return False
        reasons = bridge_payload.get("manual_attention_reasons")
        if not isinstance(reasons, list):
            reasons = [str(bridge_payload.get("remaining_gap", "") or "")]
        return any(
            str(reason).strip() == "validation failed without actionable stale maintained docs"
            for reason in reasons
        )

    async def _record_documentation_bridge_run(
        self,
        task: Task,
        bridge_payload: dict[str, object],
    ) -> None:
        if not bool(bridge_payload.get("bridge_invoked", False)):
            return

        run_payload = bridge_payload.get("run")
        if not isinstance(run_payload, dict):
            run_payload = {}

        status = str(bridge_payload.get("status", "") or "").strip()
        error = None
        if status not in {"already_current", "updated_and_verified"}:
            error = self._documentation_gate_message(bridge_payload)

        run = AgentRun(
            task_id=task.id,
            agent_name="documentation-bridge",
            session_id=str(run_payload.get("session_id", "") or "") or None,
            runtime_sdk=str(run_payload.get("runtime_sdk", "") or ""),
            provider=str(run_payload.get("provider", "") or ""),
            model=str(run_payload.get("model", "") or ""),
            effort=str(run_payload.get("effort", "") or "") or None,
            cost_usd=float(run_payload.get("cost_usd", 0.0) or 0.0),
            tokens_input=int(run_payload.get("tokens_input", 0) or 0),
            tokens_output=int(run_payload.get("tokens_output", 0) or 0),
            tokens_cached=0,
            num_turns=int(run_payload.get("num_turns", 0) or 0),
            duration_ms=int(run_payload.get("duration_ms", 0) or 0),
            stop_reason=str(run_payload.get("stop_reason", "") or "") or None,
            status="completed" if status != "bridge_failed" else "failed",
            error=error,
            output_text=str(bridge_payload.get("summary", "") or ""),
            observability=(
                run_payload.get("observability")
                if isinstance(run_payload.get("observability"), dict)
                else None
            ),
            completed_at=datetime.now(UTC),
        )
        self.db.add(run)
        await self.db.flush()

    def _documentation_gate_message(self, payload: dict[str, object]) -> str:
        remaining_gap = str(payload.get("remaining_gap", "") or "").strip()
        summary = str(payload.get("summary", "") or "").strip()
        detail = remaining_gap or summary or "documentation refresh did not complete"
        return f"documentation refresh gate blocked: {detail}"

    def _phase_context(self, task: Task, key: str) -> str:
        if not isinstance(task.depends_on, dict):
            return ""
        phase_context = task.depends_on.get("phase_context")
        if not isinstance(phase_context, dict):
            return ""
        value = phase_context.get(key)
        return str(value or "").strip()

    async def _quality_gate_feedback_context(self, task: Task) -> str:
        blocked_reason = str(task.blocked_reason or "").strip()
        if not blocked_reason and int(task.retry_count or 0) == 0:
            return "No prior gate failures for this implementation pass."

        parts = [blocked_reason] if blocked_reason else []
        result = await self.db.execute(
            select(GateResultModel)
            .where(GateResultModel.task_id == task.id)
            .order_by(GateResultModel.created_at.desc())
            .limit(6)
        )
        rows = list(result.scalars().all())
        failed_rows = [
            row
            for row in rows
            if (row.status.value if hasattr(row.status, "value") else str(row.status))
            in {"fail", "timeout", "error"}
        ]

        if failed_rows:
            parts.append("Latest gate evidence:")
        for row in reversed(failed_rows):
            status = row.status.value if hasattr(row.status, "value") else str(row.status)
            parts.append(f"- {row.gate_name}: {status} {row.error_code or ''}".rstrip())
            evidence = row.evidence if isinstance(row.evidence, dict) else {}
            checks = evidence.get("checks")
            if isinstance(checks, list):
                for check in checks[:3]:
                    if not isinstance(check, dict):
                        continue
                    command = str(check.get("command", "") or "<unknown command>")
                    exit_code = check.get("exit_code", "")
                    output = str(check.get("output", "") or "").strip()
                    parts.append(f"  command: {command} exit_code={exit_code}")
                    if output:
                        parts.append(f"  output: {output[:1200]}")
            output = str(evidence.get("output", "") or "").strip()
            if output:
                parts.append(f"  output: {output[:1200]}")

        return "\n".join(parts) if parts else "No prior gate failures for this implementation pass."

    def _store_phase_context(self, task: Task, key: str, value: str) -> None:
        if not value:
            return
        depends_on = dict(task.depends_on or {})
        phase_context = dict(depends_on.get("phase_context") or {})
        phase_context[key] = value
        depends_on["phase_context"] = phase_context
        task.depends_on = depends_on

    def _compact_phase_output(self, output_text: str, max_chars: int = 2000) -> str:
        compact = " ".join(str(output_text or "").split()).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3].rstrip() + "..."

    def _apply_operator_decision_handoff(self, task: Task, output_text: str) -> bool:
        payload = self._extract_operator_decision(output_text)
        if payload is None:
            return False
        depends_on = dict(task.depends_on or {})
        depends_on["operator_decision"] = payload
        task.depends_on = depends_on
        set_task_status(task, TaskStatus.BLOCKED)
        phase = str(payload.get("phase", "") or "phase").strip() or "phase"
        question = str(payload.get("question", "") or "").strip()
        summary = str(payload.get("summary", "") or "").strip()
        detail = question or summary or "operator decision required"
        task.blocked_reason = f"{phase} blocked: {detail}"
        return True

    def _clear_operator_decision_handoff(self, task: Task) -> None:
        if not isinstance(task.depends_on, dict) or "operator_decision" not in task.depends_on:
            return
        depends_on = dict(task.depends_on)
        depends_on.pop("operator_decision", None)
        task.depends_on = depends_on

    def _extract_operator_decision(self, output_text: str) -> dict[str, object] | None:
        text = str(output_text or "")
        marker_index = text.find(_OPERATOR_DECISION_MARKER)
        if marker_index < 0:
            return None
        raw = text[marker_index + len(_OPERATOR_DECISION_MARKER) :].strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.S)
            if match is None:
                return None
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            return None
        options = payload.get("options")
        normalized = {
            "phase": str(payload.get("phase", "") or "").strip(),
            "summary": str(payload.get("summary", "") or "").strip(),
            "question": str(payload.get("question", "") or "").strip(),
            "options": [str(item).strip() for item in options] if isinstance(options, list) else [],
            "recommended_option": str(payload.get("recommended_option", "") or "").strip(),
        }
        return normalized

    async def _get_last_run(self, task: Task, agent_name: str) -> AgentRun | None:
        """Get the most recent successful run for a task+agent."""
        for run in reversed(task.agent_runs):
            if run.agent_name == agent_name and run.status == "completed":
                return run
        return None

    def _run_has_context(self, run: AgentRun) -> bool:
        return any(
            int(getattr(run, field, 0) or 0) > 0
            for field in ("tokens_input", "tokens_output", "tokens_cached")
        ) or float(getattr(run, "cost_usd", 0.0) or 0.0) > 0.0

    async def _mark_capability_limit(
        self,
        task: Task,
        reason: str,
        *,
        output_text: str | None = None,
    ) -> None:
        """Mark task as provider-limit blocked with phase-preserving resume data."""
        payload = mark_provider_limit(task, reason=reason, output_text=output_text)
        log.warning(
            "capability_limit",
            task_id=task.id,
            reason=reason,
            reset_at=payload.get("reset_at"),
            resume_status=payload.get("resume_status"),
        )
