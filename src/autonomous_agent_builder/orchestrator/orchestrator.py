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
import shutil
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
from autonomous_agent_builder.agents.tools.workspace_tools import compact_workspace_map
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Feature,
    Sprint,
    Task,
    TaskPhase,
    TaskStatus,
    Workspace,
    set_task_status,
)
from autonomous_agent_builder.knowledge.system_docs import (
    format_task_system_doc_guidance,
    validate_task_system_docs,
)
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
    sprint_branch_name,
    task_sprint_execution_payload,
    use_deterministic_build_verifier,
    use_deterministic_evidence_collector,
)
from autonomous_agent_builder.orchestrator.deterministic_verification import (
    record_deterministic_build_verification,
    record_deterministic_evidence,
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
from autonomous_agent_builder.orchestrator.post_ship_cli_probe import (
    _post_ship_optimization_cli_probe as _post_ship_cli_probe_fn,
)
from autonomous_agent_builder.orchestrator.post_ship_cli_probe import (
    _post_ship_probe_summary as _post_ship_probe_summary_fn,
)
from autonomous_agent_builder.orchestrator.post_ship_optimization import (
    _post_ship_post_preflight_decision as _post_ship_post_preflight_decision_fn,
)
from autonomous_agent_builder.orchestrator.post_ship_optimization import (
    _run_post_ship_optimization_agent as _post_ship_run_optimization_agent,
)
from autonomous_agent_builder.orchestrator.post_ship_optimization import (
    _validated_optimization_recommendation_decisions as _post_ship_validated_recommendation_decisions,
)
from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (
    _compact_optimization_payload as _post_ship_compact_optimization_payload,
)
from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (
    _post_ship_observability_payload as _post_ship_observability_payload_fn,
)
from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (
    _refresh_app_runtime_guidance_payload as _post_ship_refresh_app_runtime_guidance,
)
from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (
    _run_app_runtime_guidance_optimization as _post_ship_run_app_runtime_guidance_optimization,
)
from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (
    _run_deterministic_post_ship_optimization as _post_ship_run_deterministic_optimization,
)
from autonomous_agent_builder.orchestrator.quality_gate_runner import (
    run_feature_acceptance_gate as _run_feature_acceptance_gate_fn,
)
from autonomous_agent_builder.orchestrator.quality_gate_runner import (
    run_phase_quality_gates as _run_phase_quality_gates_fn,
)
from autonomous_agent_builder.orchestrator.quality_gate_runner import (
    run_record_feature_acceptance_tests as _run_record_feature_acceptance_tests_fn,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    GitRunner as _GitRunner,
)
from autonomous_agent_builder.orchestrator.runtime_guidance_preservation import (
    clean_project_runtime_guidance_for_git_operation,
    preserve_project_runtime_guidance,
    project_runtime_guidance_snapshot,
    restore_project_runtime_guidance_snapshot,
    tracked_modified_paths,
    untracked_paths,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_changes_summary as _sprint_changes_summary_fn,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_extract_pr_url as _sprint_extract_pr_url,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_mark_shipped as _sprint_mark_shipped,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_maybe_ff_merge as _sprint_maybe_ff_merge,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_open_pr as _sprint_open_pr,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_restore_missing_paths as _sprint_restore_missing_paths,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_stash_dirty_paths as _sprint_stash_dirty_paths,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_verify_clean_after_merge as _sprint_verify_clean_after_merge,
)
from autonomous_agent_builder.orchestrator.sprint_lifecycle import (
    sprint_verify_materialized_checkout as _sprint_verify_materialized_checkout,
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
from autonomous_agent_builder.orchestrator.workspace_integration import (
    ensure_workspace as _ensure_workspace_fn,
)
from autonomous_agent_builder.orchestrator.workspace_integration import (
    sanitize_task_workspace_for_agent as _sanitize_task_workspace_for_agent_fn,
)
from autonomous_agent_builder.orchestrator.workspace_policy import (
    WORKSPACE_COPY_EXCLUDES,
    is_builder_source_repo,
    next_clean_directory_workspace_path,
)
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.services.async_subprocess import run_bounded_subprocess
from autonomous_agent_builder.services.provider_limits import mark_provider_limit
from autonomous_agent_builder.services.sprint_execution import (
    sprint_execution_context,
    task_uses_sprint_design,
    task_uses_sprint_plan,
)
from autonomous_agent_builder.services.workspace_scaffold import (
    build_scaffold_template_vars,
    parse_scaffold_result,
    persist_scaffold_language,
    should_scaffold,
    write_minimal_gate_config,
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
        self.gate_handler = GateFeedbackHandler(settings, db, run_agent=self._run_agent)

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
            # IMP-010: if the handler corrupted the session (e.g. a DB flush error
            # inside run_agent_lifecycle rolled the transaction back), issue an
            # explicit rollback so the session can accept new operations before we
            # flush the blocked-reason state.
            try:
                await self.db.rollback()
            except Exception:
                pass
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
        # Gates-first invariant: ensure the workspace has the language-appropriate
        # lint/test config before dispatching code-gen. The scaffold agent is
        # runtime-decided (it picks the stack from feature intent) and writes
        # only minimum config; it never implements the feature. Skipped
        # deterministically when a language is already detectable.
        scaffold_block = await self._run_workspace_scaffold_if_needed(task, workspace)
        if scaffold_block is not None:
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = scaffold_block
            await self.db.flush()
            return
        # Implementation runs in the task workspace, while design may have run in
        # the repo root. Do not resume across cwd boundaries; pass compact design
        # context explicitly instead.
        scope_reminder = self._build_active_feature_scope_reminder(task)
        _design_ctx = phase_context(task, "design_context")
        # Inject a compact workspace file map so code-gen locates files directly
        # instead of spending turns on list_directory/Read to rediscover the tree —
        # each turn replays the full cached system prompt (IMP-027 context follow-up).
        _ws_map = compact_workspace_map(workspace.path)
        result = await self._run_agent(
            task,
            "code-gen",
            {
                "task_description": task.description,
                "design_context": f"Design: {_design_ctx}\n" if _design_ctx else "",
                "gate_feedback": await self._quality_gate_feedback_context(task),
                "recovery_context": self._recovery_context(task),
                "workspace_path": workspace.path,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
                "scope_reminder": scope_reminder,
                "workspace_map": (
                    "Workspace files (use these exact paths; do not list directories "
                    f"to rediscover them):\n{_ws_map}\n"
                    if _ws_map
                    else ""
                ),
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

    async def _run_workspace_scaffold_if_needed(
        self,
        task: Task,
        workspace: Workspace,
    ) -> str | None:
        """Run the scaffold agent before code-gen when the workspace lacks a
        detectable language. Returns None on success/skip, or an actionable
        `blocked_reason` string when scaffold fails.
        """
        workspace_path = str(getattr(workspace, "path", "") or "")
        if not workspace_path:
            # No workspace_path means _ensure_workspace did not provision one.
            # Do NOT silently succeed — the next dispatch would still hit
            # FileNotFoundError. Surface a real blocked_reason.
            return (
                "scaffold_failed: workspace path is empty — orchestrator did "
                "not provision a worktree for this task"
            )
        if not Path(workspace_path).exists():
            return (
                f"scaffold_failed: workspace path {workspace_path!r} does not "
                "exist on disk — cannot scaffold a missing workspace"
            )
        needs, detected = should_scaffold(workspace_path)
        feature = task.feature
        project = feature.project if feature is not None else None
        # Recovery from "Gate infrastructure error" / FileNotFoundError sets
        # force_scaffold=True in recovery_context. In that case we run scaffold
        # even when a language is already detectable, because the real problem
        # is missing gate binaries (FINDING-20).
        recovery_ctx = self._recovery_context(task)
        force = (
            bool(recovery_ctx.get("force_scaffold")) if isinstance(recovery_ctx, dict) else False
        )
        if not needs and not force:
            # Workspace already has a detectable language. Sync Project.language
            # so the quality gate runner picks up the right binaries.
            if project is not None and detected and project.language != detected:
                await persist_scaffold_language(project, detected, self.db)
            return None
        if project is None:
            return (
                "scaffold_failed: cannot scaffold workspace without a project — "
                "feature has no project association"
            )

        feature_description = (feature.description or feature.title or "").strip()
        template_vars = build_scaffold_template_vars(
            feature_description=feature_description,
            project_name=project.name,
            workspace_path=workspace_path,
        )
        result = await self._run_agent(task, "scaffold", template_vars)

        if result.error:
            return f"scaffold_failed: {result.error}"

        parsed = parse_scaffold_result(result.output_text or "")
        if parsed.action != "scaffolded":
            return parsed.reason or "scaffold_failed: unknown scaffold failure"

        # Verify the agent actually produced the per-language gate config the
        # workspace needs. Re-run the full should_scaffold check — the agent
        # can claim language=python while writing zero files (live FINDING-22).
        # When the model agent fails, fall back to a deterministic writer for
        # the languages we have a safety net for (python, node). Other
        # languages surface a clear scaffold_failed: reason.
        still_needs, verify_detected = should_scaffold(workspace_path)
        if still_needs:
            wrote, written = write_minimal_gate_config(
                workspace_path, parsed.language, project.name
            )
            if wrote:
                log.info(
                    "scaffold_deterministic_fallback_used",
                    language=parsed.language,
                    files=written,
                    reason="model_agent_did_not_write_gate_config",
                )
                still_needs, verify_detected = should_scaffold(workspace_path)
            if still_needs:
                return (
                    "scaffold_failed: agent reported language="
                    f"{parsed.language} but the workspace still lacks the gate "
                    "config required to run code_quality / testing gates "
                    f"(post-scaffold detection: language={verify_detected})"
                )
        await persist_scaffold_language(project, parsed.language, self.db)
        return None

    def _recovery_context(self, task: Task) -> dict[str, Any]:
        depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
        recovery_context = depends_on.get("recovery_context")
        return recovery_context if isinstance(recovery_context, dict) else {}

    async def _ensure_workspace(self, task: Task) -> Workspace:
        return await _ensure_workspace_fn(self, task)

    async def _sanitize_task_workspace_for_agent(
        self,
        workspace_path: str,
        *,
        is_worktree: bool,
    ) -> str | None:
        return await _sanitize_task_workspace_for_agent_fn(workspace_path, is_worktree=is_worktree)

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
        # P20: Steps 1/2 in handle_gate_failure (deterministic + agent remediator)
        # increment retry_count without checking max_retries, so successful-but-
        # ineffective remediation creates an unbounded QUALITY_GATES dispatch loop.
        # After (3 × max_retries) total attempts, block and require operator decision.
        _cap = 3 * self.gate_handler.max_retries
        if int(task.retry_count or 0) >= _cap:
            reason = (
                f"quality_gate_cap_exceeded: task reached {task.retry_count} gate-retry "
                f"attempts (cap={_cap}); remediation loop did not converge. "
                "Operator decision required — inspect gate output and root cause."
            )
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = reason
            log.warning(
                "quality_gate_cap_exceeded",
                task_id=task.id,
                retry_count=task.retry_count,
                cap=_cap,
            )
            await self.db.flush()
            return
        return await _run_phase_quality_gates_fn(self, task)

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
        return await _run_feature_acceptance_gate_fn(self, task, workspace_path)

    async def _record_feature_acceptance_tests(
        self,
        task: Task,
        workspace_path: str,
        feature: Feature,
    ) -> tuple[bool, str]:
        return await _run_record_feature_acceptance_tests_fn(self, task, workspace_path, feature)

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
            try:
                project_root = Path(
                    str(getattr(task.feature.project, "repo_url", "") or "")
                ).expanduser()
                if project_root.exists() and not is_builder_source_repo(project_root):
                    self._refresh_app_runtime_guidance_payload(task, project_root)
            except Exception:
                pass
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
        return await _sprint_mark_shipped(self, task)

    async def _verify_materialized_sprint_checkout(
        self,
        sprint: Sprint,
        task: Task,
        repo_root: Path,
        base_evidence: dict[str, Any],
    ) -> str | None:
        return await _sprint_verify_materialized_checkout(
            self, sprint, task, repo_root, base_evidence
        )

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
        return await _sprint_maybe_ff_merge(sprint, repo_root)

    async def _verify_sprint_checkout_clean_after_merge(
        self,
        run_git: _GitRunner,
    ) -> str | None:
        return await _sprint_verify_clean_after_merge(run_git)

    async def _stash_dirty_head_paths(
        self,
        run_git: _GitRunner,
        status_lines: list[str],
    ) -> list[str]:
        return await _sprint_stash_dirty_paths(run_git, status_lines)

    async def _restore_missing_head_paths(
        self,
        run_git: _GitRunner,
        status_lines: list[str],
    ) -> list[str]:
        return await _sprint_restore_missing_paths(run_git, status_lines)

    @staticmethod
    def _sprint_changes_summary(sprint: Sprint, sprint_tasks: list[Task]) -> str:
        return _sprint_changes_summary_fn(sprint, sprint_tasks)

    async def _open_sprint_pr(
        self,
        sprint: Sprint,
        sprint_tasks: list[Task],
        latest_task: Task,
        repo_root: Path,
        base_evidence: dict[str, Any],
    ) -> str | None:
        return await _sprint_open_pr(
            self, sprint, sprint_tasks, latest_task, repo_root, base_evidence
        )

    @staticmethod
    def _extract_pr_url(output_text: str) -> str | None:
        return _sprint_extract_pr_url(output_text)

    async def _run_post_ship_optimization_agent(
        self,
        task: Task,
        sprint: Sprint,
        sprint_context: dict[str, Any],
    ) -> None:
        return await _post_ship_run_optimization_agent(self, task, sprint, sprint_context)

    def _validated_optimization_recommendation_decisions(
        self,
        decisions: Any,
        command_timeline: list[Any],
    ) -> list[dict[str, Any]]:
        return _post_ship_validated_recommendation_decisions(self, decisions, command_timeline)

    def _post_ship_post_preflight_decision(
        self,
        project_root: Path,
        deterministic_preflight: dict[str, Any],
        recommendations: list[Any],
    ) -> dict[str, Any]:
        return _post_ship_post_preflight_decision_fn(
            self, project_root, deterministic_preflight, recommendations
        )

    def _refresh_app_runtime_guidance_payload(
        self,
        task: Task,
        project_root: Path,
    ) -> dict[str, Any]:
        return _post_ship_refresh_app_runtime_guidance(self, task, project_root)

    async def _run_app_runtime_guidance_optimization(
        self,
        task: Task,
        project_root: Path,
        observability_payload: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any] | None:
        return await _post_ship_run_app_runtime_guidance_optimization(
            self, task, project_root, observability_payload, reason=reason
        )

    async def _run_deterministic_post_ship_optimization(
        self,
        task: Task,
        project_root: Path,
        recommendations: list[Any],
        observability_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return await _post_ship_run_deterministic_optimization(
            self, task, project_root, recommendations, observability_payload
        )

    async def _post_ship_optimization_cli_probe(self, project_root: Path) -> list[dict[str, str]]:
        """Run builder CLI telemetry/log probes before choosing the optimization action."""
        return await _post_ship_cli_probe_fn(self, project_root)

    def _post_ship_probe_summary(
        self,
        label: str,
        returncode: int,
        payload: dict[str, Any],
    ) -> str:
        return _post_ship_probe_summary_fn(self, label, returncode, payload)

    def _post_ship_observability_payload(self) -> dict[str, Any]:
        return _post_ship_observability_payload_fn(self)

    def _compact_optimization_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _post_ship_compact_optimization_payload(self, payload)

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
            from autonomous_agent_builder.db.session import get_session_factory

            # IMP-012: use a short-lived read session instead of the dispatch
            # session so we never start a write transaction on self.db while
            # short-lived update sessions may be active. The committed data from
            # those sessions is visible to any new connection immediately.
            async with get_session_factory()() as read_db:
                await publish_board_snapshot(read_db)
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
