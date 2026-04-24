"""Deterministic orchestrator — owns all routing decisions.

Event-driven dispatch: state changes trigger deterministic phase transitions.
Agents never decide their own next phase. The orchestrator reads task status
and dispatches accordingly.

Phase chain: planning → design_review → implementation → quality_gates →
pr_creation → review → build_verify
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.documentation_bridge import (
    run_documentation_refresh_bridge,
)
from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Task,
    TaskStatus,
    Workspace,
)
from autonomous_agent_builder.db.models import (
    GateResult as GateResultModel,
)
from autonomous_agent_builder.orchestrator.gate_feedback import GateFeedbackHandler
from autonomous_agent_builder.services.builder_tool_service import builder_kb_validate
from autonomous_agent_builder.knowledge.system_docs import (
    format_task_system_doc_guidance,
    validate_task_system_docs,
)
from autonomous_agent_builder.quality_gates.base import (
    GateStatus,
    run_quality_gates,
)
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate
from autonomous_agent_builder.workspace.manager import WorkspaceInfo, WorkspaceManager

log = structlog.get_logger()
_OPERATOR_DECISION_MARKER = "OPERATOR_DECISION_JSON:"

# Deterministic dispatch table: task_status → handler method name
PHASE_DISPATCH: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "_phase_planning",
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
            task.status = TaskStatus.FAILED
            task.blocked_reason = str(e)
            await self.db.flush()

    async def _phase_planning(self, task: Task) -> None:
        """Run planning agent, then set DESIGN_REVIEW for approval."""
        task.status = TaskStatus.PLANNING
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
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        else:
            task.status = TaskStatus.DESIGN_REVIEW
            # Create approval gate
            approval = ApprovalGate(task_id=task.id, gate_type="planning")
            self.db.add(approval)

        await self.db.flush()

    async def _phase_design(self, task: Task) -> None:
        """Run design agent with context chained from planning session."""
        task.status = TaskStatus.DESIGN
        await self.db.flush()

        # Get planning session_id for context chaining
        planning_run = await self._get_last_run(task, "planner")
        resume_session = planning_run.session_id if planning_run else None
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
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        else:
            await self._ensure_workspace(task)
            self._store_phase_context(task, "design_context", self._compact_phase_output(result.output_text))
            task.status = TaskStatus.IMPLEMENTATION

        await self.db.flush()

    async def _phase_implementation(self, task: Task) -> None:
        """Run code-gen agent in workspace, then trigger quality gates."""
        task.status = TaskStatus.IMPLEMENTATION
        await self.db.flush()

        # Get design session_id for context chaining
        design_run = await self._get_last_run(task, "designer")
        resume_session = design_run.session_id if design_run else None
        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

        workspace = await self._ensure_workspace(task)
        result = await self._run_agent(
            task,
            "code-gen",
            {
                "task_description": task.description,
                "design_context": self._phase_context(task, "design_context"),
                "workspace_path": workspace.path,
                "language": task.feature.project.language,
                "knowledge_requirements": format_task_system_doc_guidance(doc_requirements),
            },
            resume_session=resume_session,
        )

        if result.error:
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        elif self._apply_operator_decision_handoff(task, result.output_text):
            pass
        elif result.hit_capability_limit:
            await self._mark_capability_limit(task, f"SDK limit: {result.stop_reason}")
        else:
            task.status = TaskStatus.QUALITY_GATES

        await self.db.flush()

    async def _ensure_workspace(self, task: Task) -> Workspace:
        """Provision and persist a task workspace when the task enters code-mutating phases."""
        existing = getattr(task, "workspace", None)
        existing_path = getattr(existing, "path", "") if existing else ""
        if existing and existing_path:
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
            shutil.rmtree(workspace_path, ignore_errors=True)
        shutil.copytree(repo_root, workspace_path)
        return WorkspaceInfo(path=str(workspace_path), branch="", is_worktree=False)

    async def _phase_quality_gates(self, task: Task) -> None:
        """Run concurrent quality gates with AND aggregation."""
        workspace_path = task.workspace.path if task.workspace else ""
        language = task.feature.project.language
        doc_requirements = validate_task_system_docs(
            task.depends_on,
            task_id=task.id,
            feature_id=task.feature_id,
        )

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
            task.status = TaskStatus.BLOCKED
            task.blocked_reason = "; ".join(doc_requirements.issues)
        elif gate_result.status == GateStatus.PASS:
            documentation_gap = await self._run_documentation_refresh_gate(task, workspace_path)
            if documentation_gap:
                task.status = TaskStatus.BLOCKED
                task.blocked_reason = documentation_gap
            else:
                task.status = TaskStatus.PR_CREATION
        elif gate_result.status == GateStatus.WARN:
            documentation_gap = await self._run_documentation_refresh_gate(task, workspace_path)
            if documentation_gap:
                task.status = TaskStatus.BLOCKED
                task.blocked_reason = documentation_gap
            else:
                task.status = TaskStatus.PR_CREATION  # advisory, continue
        else:
            # FAIL — enter gate feedback loop
            await self.gate_handler.handle_gate_failure(task, gate_result)

        await self.db.flush()

    async def _phase_pr_creation(self, task: Task) -> None:
        """Create PR and set REVIEW_PENDING."""
        workspace_path = task.workspace.path if task.workspace else ""

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
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        else:
            task.status = TaskStatus.REVIEW_PENDING
            approval = ApprovalGate(task_id=task.id, gate_type="pr")
            self.db.add(approval)

        await self.db.flush()

    async def _phase_build_verify(self, task: Task) -> None:
        """Verify post-merge build."""
        workspace_path = task.workspace.path if task.workspace else ""

        result = await self._run_agent(
            task,
            "build-verifier",
            {
                "branch": task.workspace.branch if task.workspace else "main",
                "workspace_path": workspace_path,
            },
        )

        if result.error:
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        else:
            task.status = TaskStatus.DONE

        await self.db.flush()

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

        prompt = agent_def.prompt_template.format(**template_vars)

        result = await self.runner.run_phase(
            agent_name=agent_name,
            prompt=prompt,
            workspace_path=template_vars.get("workspace_path", ""),
            resume_session=resume_session,
        )

        # Save to agent_runs table
        run = AgentRun(
            task_id=task.id,
            agent_name=agent_name,
            session_id=result.session_id,
            cost_usd=result.cost_usd,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            tokens_cached=result.tokens_cached,
            num_turns=result.num_turns,
            duration_ms=result.duration_ms,
            stop_reason=result.stop_reason,
            status="completed" if not result.error else "failed",
            error=result.error,
            completed_at=datetime.now(UTC),
        )
        self.db.add(run)
        await self.db.flush()

        return result

    async def _run_documentation_refresh_gate(
        self,
        task: Task,
        workspace_path: str,
    ) -> str | None:
        """Block PR creation until maintained docs are current."""
        project_root = Path(workspace_path or ".").resolve()
        validation_payload = await self._load_kb_validation_payload(project_root)
        if bool(validation_payload.get("passed", False)):
            return None

        bridge_payload = await run_documentation_refresh_bridge(
            validation_payload,
            project_root=project_root,
        )
        await self._record_documentation_bridge_run(task, bridge_payload)

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
            cost_usd=float(run_payload.get("cost_usd", 0.0) or 0.0),
            tokens_input=int(run_payload.get("tokens_input", 0) or 0),
            tokens_output=int(run_payload.get("tokens_output", 0) or 0),
            tokens_cached=0,
            num_turns=int(run_payload.get("num_turns", 0) or 0),
            duration_ms=int(run_payload.get("duration_ms", 0) or 0),
            stop_reason=str(run_payload.get("stop_reason", "") or "") or None,
            status="completed" if status != "bridge_failed" else "failed",
            error=error,
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
        task.status = TaskStatus.BLOCKED
        phase = str(payload.get("phase", "") or "phase").strip() or "phase"
        question = str(payload.get("question", "") or "").strip()
        summary = str(payload.get("summary", "") or "").strip()
        detail = question or summary or "operator decision required"
        task.blocked_reason = f"{phase} blocked: {detail}"
        return True

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

    async def _mark_capability_limit(self, task: Task, reason: str) -> None:
        """Mark task as CAPABILITY_LIMIT — agent hit its ceiling."""
        task.status = TaskStatus.CAPABILITY_LIMIT
        task.capability_limit_at = datetime.now(UTC)
        task.capability_limit_reason = reason
        log.warning("capability_limit", task_id=task.id, reason=reason)
