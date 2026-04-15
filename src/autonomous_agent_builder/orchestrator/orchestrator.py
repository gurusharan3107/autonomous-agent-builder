"""Deterministic orchestrator — owns all routing decisions.

Event-driven dispatch: state changes trigger deterministic phase transitions.
Agents never decide their own next phase. The orchestrator reads task status
and dispatches accordingly.

Phase chain: planning → design_review → implementation → quality_gates →
pr_creation → review → build_verify
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.db.models import (
    GateResult as GateResultModel,
)
from autonomous_agent_builder.orchestrator.gate_feedback import GateFeedbackHandler
from autonomous_agent_builder.quality_gates.base import (
    GateStatus,
    run_quality_gates,
)
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate

log = structlog.get_logger()

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

        result = await self._run_agent(
            task,
            "planner",
            {
                "feature_description": task.description,
                "project_name": task.feature.project.name,
                "language": task.feature.project.language,
            },
        )

        if result.error:
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
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

        result = await self._run_agent(
            task,
            "designer",
            {
                "task_description": task.description,
                "project_name": task.feature.project.name,
                "language": task.feature.project.language,
            },
            resume_session=resume_session,
        )

        if result.error:
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        else:
            task.status = TaskStatus.IMPLEMENTATION

        await self.db.flush()

    async def _phase_implementation(self, task: Task) -> None:
        """Run code-gen agent in workspace, then trigger quality gates."""
        task.status = TaskStatus.IMPLEMENTATION
        await self.db.flush()

        # Get design session_id for context chaining
        design_run = await self._get_last_run(task, "designer")
        resume_session = design_run.session_id if design_run else None

        workspace_path = task.workspace.path if task.workspace else ""
        result = await self._run_agent(
            task,
            "code-gen",
            {
                "task_description": task.description,
                "design_context": "",  # filled from design output
                "workspace_path": workspace_path,
                "language": task.feature.project.language,
            },
            resume_session=resume_session,
        )

        if result.error:
            task.status = TaskStatus.FAILED
            task.blocked_reason = result.error
        elif result.hit_capability_limit:
            await self._mark_capability_limit(task, f"SDK limit: {result.stop_reason}")
        else:
            task.status = TaskStatus.QUALITY_GATES

        await self.db.flush()

    async def _phase_quality_gates(self, task: Task) -> None:
        """Run concurrent quality gates with AND aggregation."""
        workspace_path = task.workspace.path if task.workspace else ""
        language = task.feature.project.language

        # Pre-integration gates: Ruff + pytest
        pre_gates = [
            CodeQualityGate(language=language),
            TestingGate(language=language),
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

        if gate_result.status == GateStatus.PASS:
            task.status = TaskStatus.PR_CREATION
        elif gate_result.status == GateStatus.WARN:
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
