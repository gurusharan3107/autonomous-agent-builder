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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.documentation_bridge import (
    run_documentation_refresh_bridge,
)
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
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
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.orchestrator.active_feature_scope import (
    build_active_feature_scope_reminder,
    sibling_task_ownership_hints,
)
from autonomous_agent_builder.orchestrator.agent_run_lifecycle import run_agent_lifecycle
from autonomous_agent_builder.orchestrator.approval_outcomes import (
    apply_approval_outcome,
    apply_sprint_approval_outcome,
)
from autonomous_agent_builder.orchestrator.build_verification import (
    build_verifier_failure,
    feature_verifier_failure,
    is_sprint_feature_verification_task,
    sprint_branch_name,
    task_sprint_execution_payload,
    use_deterministic_build_verifier,
    use_deterministic_evidence_collector,
)
from autonomous_agent_builder.orchestrator.deterministic_verification import (
    record_deterministic_build_verification,
    record_deterministic_evidence,
    record_feature_acceptance_tests,
    run_builder_script,
)
from autonomous_agent_builder.orchestrator.documentation_refresh_gate import (
    documentation_gate_message,
    forward_engineering_non_actionable_doc_validation,
    forward_engineering_seed_docs_deferred,
    forward_engineering_sprint_doc_hash_drift_advisory,
    load_kb_validation_payload,
    project_has_canonical_head,
    record_documentation_bridge_run,
    resolve_documentation_project_root,
)
from autonomous_agent_builder.orchestrator.failure_diagnosis import (
    diagnose_task_failure,
    workspace_contains_builder_internals,
)
from autonomous_agent_builder.orchestrator.gate_feedback import (
    GateFeedbackHandler,
    quality_gate_feedback_context,
)
from autonomous_agent_builder.orchestrator.operator_decisions import (
    apply_operator_decision_handoff,
    clear_operator_decision_handoff,
    extract_operator_decision,
)
from autonomous_agent_builder.orchestrator.phase_context import (
    compact_phase_output,
    phase_context,
    store_phase_context,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    GitRunner as _GitRunner,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    _status_path,
    clean_project_runtime_guidance_for_git_operation,
    preserve_project_runtime_guidance,
    project_runtime_guidance_snapshot,
    restore_project_runtime_guidance_snapshot,
    tracked_modified_paths,
    untracked_paths,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    non_guidance_status_lines as _non_guidance_status_lines,
)
from autonomous_agent_builder.orchestrator.workspace_integration import (
    commit_task_workspace_changes,
    conflict_markers_remaining,
    integrate_directory_workspace,
    integrate_task_workspace,
    rebase_task_workspace_for_integration,
    remove_generated_artifacts_from_git_checkout,
    run_integration_conflict_resolver,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    WORKSPACE_COPY_EXCLUDES,
    directory_workspace_is_stale,
    is_builder_source_repo,
    is_fast_forward_divergence,
    next_clean_directory_workspace_path,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    tracked_overwrite_paths as parse_tracked_overwrite_paths,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    untracked_overwrite_paths as parse_untracked_overwrite_paths,
)
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
    run_quality_gates,
)
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.services.async_subprocess import run_bounded_subprocess
from autonomous_agent_builder.services.provider_limits import mark_provider_limit
from autonomous_agent_builder.services.runtime_guidance import refresh_project_runtime_guidance
from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_EXECUTION_KEY,
    sprint_execution_context,
    task_uses_sprint_design,
    task_uses_sprint_plan,
)
from autonomous_agent_builder.workspace.manager import WorkspaceInfo, WorkspaceManager

__all__ = [
    "Orchestrator",
    "apply_approval_outcome",
    "apply_sprint_approval_outcome",
]

log = structlog.get_logger()
_ORCHESTRATOR_GIT_TIMEOUT_SECONDS = 30.0
_ORCHESTRATOR_SCRIPT_TIMEOUT_SECONDS = 300.0
_TASK_WORKSPACE_SANITIZE_PATHS = (
    ".agent-builder",
    ".claude/progress",
    ".codex",
    ".playwright-cli",
    "node_modules",
    "dist",
    "build",
    "test-results",
)


def _tracked_modified_paths(status_output: str, paths: list[str]) -> list[str]:
    return tracked_modified_paths(status_output, paths)


def _untracked_paths(status_output: str, paths: list[str]) -> list[str]:
    return untracked_paths(status_output, paths)


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
            store_phase_context(task, "planning_context", sprint_execution_context(task))
            if task_uses_sprint_design(task):
                store_phase_context(
                    task,
                    "design_context",
                    phase_context(task, "design_context"),
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
            task.blocked_reason = diagnose_task_failure(
                result.error,
                workspace_path=task.workspace.path if task.workspace else "",
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
            task.blocked_reason = diagnose_task_failure(
                result.error,
                workspace_path=task.workspace.path if task.workspace else "",
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
            store_phase_context(
                task,
                "design_context",
                compact_phase_output(result.output_text),
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
                "design_context": phase_context(task, "design_context"),
                "gate_feedback": await self._quality_gate_feedback_context(task),
                "recovery_context": self._recovery_context(task),
                "workspace_path": workspace.path,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
                "scope_reminder": scope_reminder,
            },
        )

        if result.error:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = diagnose_task_failure(
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

    def _recovery_context(self, task: Task) -> dict[str, Any]:
        depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
        recovery_context = depends_on.get("recovery_context")
        return recovery_context if isinstance(recovery_context, dict) else {}

    async def _ensure_workspace(self, task: Task) -> Workspace:
        """Provision and persist a task workspace when the task enters code-mutating phases."""
        existing = getattr(task, "workspace", None)
        existing_path = getattr(existing, "path", "") if existing else ""
        if existing and existing_path:
            project = getattr(getattr(task, "feature", None), "project", None)
            repo_url_value = getattr(project, "repo_url", "")
            if repo_url_value and not isinstance(repo_url_value, str):
                return existing
            existing_path_obj = Path(existing_path)
            if not existing_path_obj.exists():
                log.warning(
                    "task_workspace_path_missing_reprovisioning",
                    task_id=task.id,
                    path=existing_path,
                    is_worktree=bool(getattr(existing, "is_worktree", False)),
                )
            elif not getattr(
                existing, "is_worktree", False
            ) and workspace_contains_builder_internals(existing_path):
                log.warning(
                    "task_workspace_polluted_reprovisioning",
                    task_id=task.id,
                    path=existing_path,
                )
            elif not getattr(existing, "is_worktree", False) and directory_workspace_is_stale(
                existing_path,
                task.feature.project.repo_url if task.feature and task.feature.project else "",
            ):
                log.warning(
                    "task_workspace_stale_reprovisioning",
                    task_id=task.id,
                    path=existing_path,
                )
            else:
                sanitize_error = await self._sanitize_task_workspace_for_agent(
                    existing_path,
                    is_worktree=bool(getattr(existing, "is_worktree", False)),
                )
                if sanitize_error:
                    raise RuntimeError(sanitize_error)
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
        # Sprint-PR refactor (Phase B): when the task is part of a sprint,
        # branch the per-task worktree off the sprint branch so all task
        # commits roll up into a single sprint-level integration head.
        sprint_start_point: str | None = None
        sprint = await self._resolve_sprint_for_task(task)
        if sprint is not None:

            async def run_git(*args: str) -> tuple[int, str]:
                result = await run_bounded_subprocess(
                    "git",
                    *args,
                    cwd=str(repo_root),
                    timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
                    label="orchestrator git",
                )
                return result.returncode, result.output

            sprint_start_point = await self._ensure_sprint_branch(sprint, repo_root, run_git)
        workspace_info = await self._provision_workspace_info(
            manager, repo_root, task.id, start_point=sprint_start_point
        )

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
        store_phase_context(
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
        sanitize_error = await self._sanitize_task_workspace_for_agent(
            workspace_info.path,
            is_worktree=workspace_info.is_worktree,
        )
        if sanitize_error:
            raise RuntimeError(sanitize_error)
        await self.db.flush()
        return workspace

    async def _sanitize_task_workspace_for_agent(
        self,
        workspace_path: str,
        *,
        is_worktree: bool,
    ) -> str | None:
        """Remove Builder/runtime artifacts before an agent receives the workspace."""
        if not workspace_path:
            return "Task workspace sanitization failed: workspace path is missing"
        workspace = Path(workspace_path).expanduser()
        if not workspace.exists():
            return f"Task workspace sanitization failed: workspace does not exist at {workspace}"

        existing_paths = [
            relative
            for relative in _TASK_WORKSPACE_SANITIZE_PATHS
            if (workspace / relative).exists()
        ]
        if not existing_paths:
            return None

        if is_worktree:
            result = await run_bounded_subprocess(
                "git",
                "rm",
                "-r",
                "--ignore-unmatch",
                "--",
                *existing_paths,
                cwd=str(workspace),
                timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
                label="workspace sanitization git rm",
            )
            if result.returncode != 0:
                output = result.output.strip()
                return f"Task workspace sanitization failed: could not untrack runtime artifacts: {output}"

        for relative in existing_paths:
            path = workspace / relative
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()

        if is_worktree:
            result = await run_bounded_subprocess(
                "git",
                "clean",
                "-fd",
                "--",
                *existing_paths,
                cwd=str(workspace),
                timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
                label="workspace sanitization git clean",
            )
            if result.returncode != 0:
                output = result.output.strip()
                return f"Task workspace sanitization failed: could not clean runtime artifacts: {output}"

        remaining = [
            relative
            for relative in _TASK_WORKSPACE_SANITIZE_PATHS
            if (workspace / relative).exists()
        ]
        if remaining:
            return (
                "Task workspace sanitization failed: runtime artifacts remain in workspace: "
                + ", ".join(remaining)
            )
        log.info(
            "task_workspace_sanitized_for_agent",
            workspace_path=str(workspace),
            paths=existing_paths,
            is_worktree=is_worktree,
        )
        return None

    async def _provision_workspace_info(
        self,
        manager: WorkspaceManager,
        repo_root: Path,
        task_id: str,
        *,
        start_point: str | None = None,
    ) -> WorkspaceInfo:
        """Create a git worktree by default, with an explicit directory fallback.

        ``start_point`` lets the sprint-PR refactor branch task worktrees off
        the sprint integration branch instead of HEAD.
        """
        git_dir = repo_root / ".git"
        if git_dir.exists():
            return await manager.create_workspace(str(repo_root), task_id, start_point=start_point)

        workspace_path = Path(self.settings.workspace_root) / task_id
        if workspace_path.exists():
            workspace_path = next_clean_directory_workspace_path(workspace_path)
        shutil.copytree(
            repo_root,
            workspace_path,
            ignore=shutil.ignore_patterns(*WORKSPACE_COPY_EXCLUDES),
        )
        return WorkspaceInfo(path=str(workspace_path), branch="", is_worktree=False)

    async def _phase_quality_gates(self, task: Task) -> None:
        """Run concurrent quality gates with AND aggregation."""
        try:
            workspace = await self._ensure_workspace(task)
        except RuntimeError as exc:
            existing = getattr(task, "workspace", None)
            workspace_path = str(getattr(existing, "path", "") or "")
            gate = GateResult(
                gate_name="workspace_provisioning",
                status=GateStatus.ERROR,
                findings_count=1,
                error_code="WORKSPACE_PROVISIONING_FAILED",
                evidence={
                    "summary": str(exc),
                    "workspace_path": workspace_path,
                },
                remediation_possible=False,
            )
            self.db.add(
                GateResultModel(
                    task_id=task.id,
                    gate_name=gate.gate_name,
                    status=gate.status.value,
                    evidence=gate.evidence,
                    findings_count=gate.findings_count,
                    elapsed_ms=0,
                    error_code=gate.error_code,
                    timeout=False,
                    remediation_attempted=False,
                    remediation_succeeded=False,
                )
            )
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = f"Workspace provisioning failed before quality gates: {str(exc)}"
            await self.db.flush()
            return
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
        workspace = await self._ensure_workspace(task)
        workspace_path = workspace.path

        # Deterministic-first: no git required. `_record_deterministic_evidence`
        # invokes the `change_evidence` script and advances to BUILD_VERIFY.
        if use_deterministic_evidence_collector(task):
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
            task.blocked_reason = diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        else:
            set_task_status(task, TaskStatus.REVIEW_PENDING)
            approval = ApprovalGate(task_id=task.id, gate_type="pr")
            self.db.add(approval)

        await self.db.flush()

    async def _resolve_sprint_for_task(self, task: Task) -> Sprint | None:
        """Return the ``Sprint`` row attached to ``task`` (via ``depends_on``)."""
        sprint_payload = task_sprint_execution_payload(task)
        sprint_id = str(sprint_payload.get("sprint_id") or "").strip()
        if not sprint_id:
            return None
        return await self.db.get(Sprint, sprint_id)

    @staticmethod
    def _sprint_branch_name(sprint: Sprint) -> str:
        return sprint_branch_name(sprint)

    async def _ensure_sprint_branch(
        self,
        sprint: Sprint,
        repo_root: Path,
        run_git: _GitRunner,
    ) -> str | None:
        """Lazy-create the per-sprint integration branch.

        Returns the branch name on success, or ``None`` when the repo has no
        commits yet (unborn HEAD — caller falls back to today's behavior).
        Persists ``sprint.branch`` so subsequent tasks reuse the same branch.
        """
        if sprint.branch:
            return sprint.branch
        head_code, _ = await run_git("rev-parse", "--verify", "HEAD")
        if head_code != 0:
            # Unborn HEAD — sprint branch can't fork from anything yet. Caller
            # uses the legacy main-targeting integration path, which still
            # initializes main from the first task commit.
            return None
        branch_name = sprint_branch_name(sprint)
        # ``git branch -f`` is intentional: if a stale branch from an aborted
        # earlier attempt exists at the same ref, this resets it to current
        # HEAD. Only fires when ``sprint.branch`` is None, so this never
        # rewrites a branch we have already accepted as the integration head.
        verify_code, _ = await run_git("rev-parse", "--verify", branch_name)
        if verify_code != 0:
            create_code, create_output = await run_git("branch", branch_name, "HEAD")
            if create_code != 0:
                log.warning(
                    "sprint_branch_create_failed",
                    sprint_id=sprint.id,
                    branch=branch_name,
                    output=create_output.strip(),
                )
                return None
        sprint.branch = branch_name
        return branch_name

    async def _run_builder_script(
        self,
        script_name: str,
        workspace_path: str,
        extra_args: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any], str, str]:
        return await run_builder_script(
            script_name,
            workspace_path,
            extra_args,
            timeout_seconds=_ORCHESTRATOR_SCRIPT_TIMEOUT_SECONDS,
        )

    async def _record_deterministic_evidence(self, task: Task, workspace_path: str) -> None:
        await record_deterministic_evidence(
            self.db,
            task,
            workspace_path,
            self._run_builder_script,
            self._publish_realtime_board_snapshot,
        )

    async def _record_deterministic_build_verification(
        self,
        task: Task,
        workspace_path: str,
    ) -> tuple[bool, str]:
        return await record_deterministic_build_verification(
            self.db,
            task,
            workspace_path,
            self._publish_realtime_board_snapshot,
        )

    async def _run_feature_acceptance_gate(
        self,
        task: Task,
        workspace_path: str,
    ) -> tuple[bool, str]:
        if not is_sprint_feature_verification_task(task):
            return True, ""

        feature = await self.db.get(Feature, task.feature_id)
        if feature is None:
            return False, "feature_acceptance_failed: feature record not found"

        test_success, existing_result = await self._record_feature_acceptance_tests(
            task,
            workspace_path,
            feature,
        )
        if test_success:
            return True, existing_result

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
            return False, diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        if verifier_failure := feature_verifier_failure(result.output_text):
            return False, verifier_failure

        test_success, test_output = await self._record_feature_acceptance_tests(
            task,
            workspace_path,
            feature,
        )
        if test_success:
            return True, test_output
        return False, f"feature_acceptance_failed: {test_output}"

    async def _record_feature_acceptance_tests(
        self,
        task: Task,
        workspace_path: str,
        feature: Feature,
    ) -> tuple[bool, str]:
        return await record_feature_acceptance_tests(
            self.db,
            task,
            workspace_path,
            feature,
            self._publish_realtime_board_snapshot,
        )

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
        workspace = await self._ensure_workspace(task)
        workspace_path = workspace.path

        feature_success, feature_output = await self._run_feature_acceptance_gate(
            task,
            workspace_path,
        )
        if not feature_success:
            set_task_status(task, TaskStatus.FAILED)
            task.blocked_reason = feature_output
            await self.db.flush()
            return

        if use_deterministic_build_verifier(task):
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
            task.blocked_reason = diagnose_task_failure(
                result.error,
                workspace_path=workspace_path,
                result=result,
            )
        elif verifier_failure := build_verifier_failure(result.output_text):
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
        if any(
            _task_status_value(sprint_task) != TaskStatus.DONE.value for sprint_task in sprint_tasks
        ):
            return

        acceptance_result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.task_id.in_(generated_ids))
            .where(AgentRun.agent_name.in_(["feature-verifier", "feature-acceptance-tests"]))
            .order_by(AgentRun.started_at)
        )
        acceptance_runs = list(acceptance_result.scalars().all())
        acceptance_run_ids = [run.id for run in acceptance_runs if run.status == "completed"]
        approved_feature_ids = [
            str(feature_id) for feature_id in (sprint.approved_feature_ids or [])
        ]

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

        # Sprint-PR refactor (Phase C): decide remote-PR vs local-merge before
        # flipping the sprint to SHIPPED. The remote path opens a single
        # sprint-level PR and parks the sprint at PR_REVIEW pending human
        # approval; the local path ff-merges the sprint branch into main and
        # ships immediately. Both paths share the verification-evidence base.
        repo_url = str(getattr(task.feature.project, "repo_url", "") or "").strip()
        repo_root = Path(repo_url).expanduser() if repo_url else Path()
        if repo_url:
            if sprint.branch and repo_root.exists() and await self._project_has_remote(repo_root):
                sprint_pr_error = await self._open_sprint_pr(
                    sprint, sprint_tasks, task, repo_root, base_evidence
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

            merge_error = await self._maybe_ff_merge_sprint_branch(sprint, repo_root)
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

            final_verify_error = await self._verify_materialized_sprint_checkout(
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

    async def _verify_materialized_sprint_checkout(
        self,
        sprint: Sprint,
        task: Task,
        repo_root: Path,
        base_evidence: dict[str, Any],
    ) -> str | None:
        """Run final deterministic proof in the actual app checkout before shipping."""
        if not repo_root.exists():
            return None
        success, output = await self._record_deterministic_build_verification(
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

    @staticmethod
    async def _project_has_remote(repo_root: Path) -> bool:
        """Return True when ``repo_root`` is a git repo with at least one remote."""
        result = await run_bounded_subprocess(
            "git",
            "remote",
            cwd=str(repo_root),
            timeout_seconds=_ORCHESTRATOR_GIT_TIMEOUT_SECONDS,
            label="orchestrator git remote",
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    async def _maybe_ff_merge_sprint_branch(self, sprint: Sprint, repo_root: Path) -> str | None:
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
        guidance_snapshot = self._project_runtime_guidance_snapshot(repo_root)
        clean_error = await self._clean_project_runtime_guidance_for_git_operation(
            run_git, guidance_snapshot
        )
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
        restore_error = await self._restore_project_runtime_guidance_snapshot(
            repo_root, guidance_snapshot, run_git
        )
        if restore_error:
            return restore_error
        dirty_error = await self._verify_sprint_checkout_clean_after_merge(run_git)
        if dirty_error:
            return dirty_error
        log.info(
            "sprint_branch_ff_merged_to_main",
            sprint_id=sprint.id,
            branch=branch,
        )
        return None

    async def _verify_sprint_checkout_clean_after_merge(
        self,
        run_git: _GitRunner,
    ) -> str | None:
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
        restored = await self._restore_missing_head_paths(run_git, dirty_lines)
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
        stashed = await self._stash_dirty_head_paths(run_git, dirty_lines)
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

    async def _stash_dirty_head_paths(
        self,
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

    async def _restore_missing_head_paths(
        self,
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

    @staticmethod
    def _sprint_changes_summary(sprint: Sprint, sprint_tasks: list[Task]) -> str:
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

    async def _open_sprint_pr(
        self,
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
        summary = self._sprint_changes_summary(sprint, sprint_tasks)
        result = await self._run_agent(
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
        pr_url = self._extract_pr_url(result.output_text)
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
        self.db.add(gate)
        log.info(
            "sprint_pr_opened",
            sprint_id=sprint.id,
            branch=sprint.branch,
            pr_url=pr_url,
        )
        return None

    @staticmethod
    def _extract_pr_url(output_text: str) -> str | None:
        """Pluck the first ``https://github.com/.../pull/N`` URL from agent output."""
        match = re.search(r"https://[^\s)]+/pull/\d+", output_text or "")
        return match.group(0) if match else None

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
        recommendations = observability_payload.get("observability_coverage", {}).get(
            "deterministic_recommendations", []
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

        if deterministic_preflight is None and not is_builder_source_repo(project_root):
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
                "failed" if result.error else str(output_payload.get("status") or "completed")
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
            "recommendation_decisions": (recommendation_decisions),
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
                "analysis_source": "builder logs analyze --session <latest-session> --json",
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
        implemented_codes.update(
            recommendation_codes(deterministic_preflight.get("selected_recommendations"))
        )
        observability = deterministic_preflight.get("observability")
        guidance = (
            observability.get("app_runtime_guidance") if isinstance(observability, dict) else {}
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
            if isinstance(item, dict) and str(item.get("code") or "") not in implemented_codes
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
        target_scope = (
            "builder_source" if is_builder_source_repo(project_root) else "generated_app"
        )
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
        builder_source_residual_codes = {
            "agent_chat_readonly_intent_budget",
            "context_retrieval_policy_review",
            "runtime_error_trend",
            "runtime_token_budget_over_target",
            "telemetry_collector_blocked",
            "tool_event_instrumentation_gap",
        }
        deferred_builder_source_codes: set[str] = set()
        for item in residual_recommendations:
            if target_scope != "generated_app":
                continue
            code = str(item.get("code") or "")
            owner_lane = str(item.get("owner_lane") or "")
            next_actor = str(item.get("next_actor") or "")
            if (
                owner_lane == "builder_source"
                or next_actor == "builder"
                or code in builder_source_residual_codes
            ):
                recommendation_decisions.append(
                    {
                        "code": code,
                        "lifecycle_status": "deferred",
                        "reason": (
                            "Builder-owned optimization surfaced during a generated-app "
                            "shipment; keep the generated-app post-ship lane deterministic "
                            "and route this follow-up to the Builder source backlog."
                        ),
                    }
                )
                deferred_builder_source_codes.add(code)
        actionable_residual_recommendations = [
            item
            for item in residual_recommendations
            if str(item.get("code") or "") not in auto_resolved_codes
            and str(item.get("code") or "") not in deferred_builder_source_codes
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
                "analysis_source": "builder logs analyze --session <latest-session> --json",
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
            str(item.get("code") or ""): item for item in recommendations if isinstance(item, dict)
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
                else "; ".join(
                    failure_parts or summary_parts or ["deterministic script optimization failed"]
                )
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
                "analysis_source": "builder logs analyze --session <latest-session> --json",
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
            else "; ".join(
                failure_parts or [str(guidance.get("error") or "script optimization failed")]
            ),
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
                "builder logs analyze --session <latest-session> --json",
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
        return await integrate_task_workspace(self, task)

    async def _commit_task_workspace_changes(self, task: Task) -> str | None:
        return await commit_task_workspace_changes(self, task)

    async def _remove_generated_artifacts_from_git_checkout(
        self,
        checkout_root: Path,
        run_git: _GitRunner,
        commit_message: str,
    ) -> str | None:
        return await remove_generated_artifacts_from_git_checkout(
            checkout_root,
            run_git,
            commit_message,
        )

    async def _integrate_directory_workspace(self, task: Task) -> str | None:
        return await integrate_directory_workspace(self, task)

    async def _rebase_task_workspace_for_integration(
        self,
        task: Task,
        workspace_path: str,
        branch: str,
        target_branch: str = "main",
    ) -> str | None:
        return await rebase_task_workspace_for_integration(
            self,
            task,
            workspace_path,
            branch,
            target_branch,
        )

    async def _run_integration_conflict_resolver(
        self,
        task: Task,
        workspace_path: str,
        branch: str,
        conflict_files: list[str],
        rebase_output: str,
    ) -> str | None:
        return await run_integration_conflict_resolver(
            self,
            task,
            workspace_path,
            branch,
            conflict_files,
            rebase_output,
        )

    def _conflict_markers_remaining(self, workspace: Path, conflict_files: list[str]) -> str | None:
        return conflict_markers_remaining(workspace, conflict_files)

    def _project_runtime_guidance_snapshot(self, repo_root: Path) -> dict[str, bytes]:
        return project_runtime_guidance_snapshot(repo_root)

    async def _clean_project_runtime_guidance_for_git_operation(
        self,
        run_git: _GitRunner,
        snapshot: dict[str, bytes],
    ) -> str | None:
        return await clean_project_runtime_guidance_for_git_operation(run_git, snapshot)

    async def _restore_project_runtime_guidance_snapshot(
        self,
        repo_root: Path,
        snapshot: dict[str, bytes],
        run_git: _GitRunner,
    ) -> str | None:
        return await restore_project_runtime_guidance_snapshot(repo_root, snapshot, run_git)

    async def _preserve_project_runtime_guidance(
        self,
        task: Task,
        workspace_path: str,
    ) -> str | None:
        return await preserve_project_runtime_guidance(task, workspace_path)

    def _build_active_feature_scope_reminder(self, task: Task) -> str:
        return build_active_feature_scope_reminder(
            task,
            task_sprint_execution_payload(task),
        )

    def _sibling_task_ownership_hints(self, task: Task, own_key: str) -> list[str]:
        return sibling_task_ownership_hints(task, own_key)

    async def _run_agent(
        self,
        task: Task,
        agent_name: str,
        template_vars: dict[str, str],
        resume_session: str | None = None,
    ) -> RunResult:
        return await run_agent_lifecycle(
            task=task,
            agent_name=agent_name,
            template_vars=template_vars,
            settings=self.settings,
            db=self.db,
            runner=self.runner,
            create_runtime=create_runtime,
            publish_board_snapshot=self._publish_realtime_board_snapshot,
            resume_session=resume_session,
        )

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
        return resolve_documentation_project_root(task, workspace_path)

    async def _load_kb_validation_payload(self, project_root: Path) -> dict[str, object]:
        return await load_kb_validation_payload(project_root)

    async def _project_has_canonical_head(self, project_root: Path) -> bool:
        return await project_has_canonical_head(project_root)

    def _forward_engineering_seed_docs_deferred(
        self,
        project_root: Path,
        validation_payload: dict[str, object],
    ) -> bool:
        return forward_engineering_seed_docs_deferred(project_root, validation_payload)

    def _forward_engineering_sprint_doc_hash_drift_advisory(
        self,
        task: Task,
        project_root: Path,
        validation_payload: dict[str, object],
    ) -> bool:
        return forward_engineering_sprint_doc_hash_drift_advisory(
            task,
            project_root,
            validation_payload,
        )

    def _forward_engineering_non_actionable_doc_validation(
        self,
        project_root: Path,
        bridge_payload: dict[str, object],
    ) -> bool:
        return forward_engineering_non_actionable_doc_validation(project_root, bridge_payload)

    async def _record_documentation_bridge_run(
        self,
        task: Task,
        bridge_payload: dict[str, object],
    ) -> None:
        await record_documentation_bridge_run(self.db, task, bridge_payload)

    def _documentation_gate_message(self, payload: dict[str, object]) -> str:
        return documentation_gate_message(payload)

    async def _quality_gate_feedback_context(self, task: Task) -> str:
        return await quality_gate_feedback_context(self.db, task)

    def _apply_operator_decision_handoff(self, task: Task, output_text: str) -> bool:
        return apply_operator_decision_handoff(task, output_text)

    def _clear_operator_decision_handoff(self, task: Task) -> None:
        clear_operator_decision_handoff(task)

    def _extract_operator_decision(self, output_text: str) -> dict[str, object] | None:
        return extract_operator_decision(output_text)

    async def _get_last_run(self, task: Task, agent_name: str) -> AgentRun | None:
        """Get the most recent successful run for a task+agent."""
        for run in reversed(task.agent_runs):
            if run.agent_name == agent_name and run.status == "completed":
                return run
        return None

    def _run_has_context(self, run: AgentRun) -> bool:
        return (
            any(
                int(getattr(run, field, 0) or 0) > 0
                for field in ("tokens_input", "tokens_output", "tokens_cached")
            )
            or float(getattr(run, "cost_usd", 0.0) or 0.0) > 0.0
        )

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
