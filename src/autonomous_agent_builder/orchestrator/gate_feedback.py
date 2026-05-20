"""Gate feedback loop — FAIL -> autofix -> retry -> CAPABILITY_LIMIT.

Flow:
  Gate FAIL → remediation_possible?
    YES → semgrep --autofix --dryrun → apply → re-run gate
      PASS → continue
      FAIL → agent-assisted fix
    NO → agent-assisted fix

  agent-assisted fix:
    retry_count < MAX_RETRIES (2)?
      YES → dispatch code-gen with gate feedback
        same error? → CAPABILITY_LIMIT
        different error? → retry loop
      NO → CAPABILITY_LIMIT

  CAPABILITY_LIMIT:
    → mark CAPABILITY_LIMIT with evidence
    → stamp dead_letter_queued_at for downstream/manual handling
    → emit a structured warning for operators
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import GateResult as GateResultModel
from autonomous_agent_builder.db.models import Task, TaskStatus, set_task_status
from autonomous_agent_builder.quality_gates.base import AggregateGateResult

log = structlog.get_logger()


async def quality_gate_feedback_context(db: AsyncSession, task: Task) -> str:
    """Build the latest gate-failure feedback for implementation prompts."""
    blocked_reason = str(task.blocked_reason or "").strip()
    if not blocked_reason and int(task.retry_count or 0) == 0:
        return "No prior gate failures for this implementation pass."

    parts = [blocked_reason] if blocked_reason else []
    result = await db.execute(
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


class GateFeedbackHandler:
    """Handles gate failures with retry logic and capability limits."""

    def __init__(self, settings: Settings, db: AsyncSession):
        self.settings = settings
        self.db = db
        self.max_retries = settings.gate.max_retries

    async def handle_gate_failure(self, task: Task, gate_result: AggregateGateResult) -> None:
        """Process a gate failure — attempt remediation, retry, or escalate."""
        failed_gates = gate_result.failed_gates

        log.info(
            "gate_failure",
            task_id=task.id,
            failed_gates=[g.gate_name for g in failed_gates],
            retry_count=task.retry_count,
        )

        # Step 1: Try auto-remediation for gates that support it
        remediable = gate_result.remediable_gates
        if remediable:
            remediated = await self._attempt_remediation(task, remediable)
            if remediated:
                # Re-run gates after remediation
                set_task_status(task, TaskStatus.QUALITY_GATES)
                return

        # Step 2: Check retry budget
        if task.retry_count >= self.max_retries:
            await self._escalate_to_capability_limit(task, gate_result)
            return

        # Step 3: Agent-assisted fix
        task.retry_count += 1
        set_task_status(task, TaskStatus.IMPLEMENTATION)  # Re-dispatch to code-gen with feedback
        task.blocked_reason = self._format_gate_feedback(gate_result)

        log.info(
            "gate_retry",
            task_id=task.id,
            retry_count=task.retry_count,
            max_retries=self.max_retries,
        )

        await self.db.flush()

    async def _attempt_remediation(self, task: Task, gates: list) -> bool:
        """Attempt auto-remediation for failed gates."""
        workspace_path = task.workspace.path if task.workspace else ""
        any_fixed = False

        for gate_result in gates:
            # Instantiate the gate to call remediate()
            gate = self._get_gate_instance(gate_result.gate_name, task)
            if gate is None:
                continue

            log.info("remediation_attempt", task_id=task.id, gate=gate_result.gate_name)
            try:
                success = await gate.remediate(workspace_path)
                if success:
                    any_fixed = True
                    log.info("remediation_success", task_id=task.id, gate=gate_result.gate_name)
                else:
                    log.info("remediation_failed", task_id=task.id, gate=gate_result.gate_name)
            except Exception as e:
                log.error(
                    "remediation_error",
                    task_id=task.id,
                    gate=gate_result.gate_name,
                    error=str(e),
                )

        return any_fixed

    async def _escalate_to_capability_limit(
        self, task: Task, gate_result: AggregateGateResult
    ) -> None:
        """Escalate to CAPABILITY_LIMIT — agent can't fix this."""
        feedback = self._format_gate_feedback(gate_result)
        set_task_status(task, TaskStatus.CAPABILITY_LIMIT)
        task.capability_limit_at = datetime.now(UTC)
        task.capability_limit_reason = feedback
        task.blocked_reason = feedback
        task.dead_letter_queued_at = datetime.now(UTC)

        log.warning(
            "capability_limit",
            task_id=task.id,
            retry_count=task.retry_count,
            failed_gates=[g.gate_name for g in gate_result.failed_gates],
        )

        await self.db.flush()

    def _format_gate_feedback(self, gate_result: AggregateGateResult) -> str:
        """Format gate results into actionable feedback for the agent."""
        parts = ["Quality gate failures:\n"]
        for r in gate_result.failed_gates:
            parts.append(f"- {r.gate_name}: {r.status.value}")
            if r.error_code:
                parts.append(f"  Error: {r.error_code}")
            if r.evidence:
                # Extract key findings
                findings = r.evidence.get("findings", [])
                if isinstance(findings, list):
                    for f in findings[:5]:
                        if isinstance(f, dict):
                            msg = f.get("message", f.get("check_id", str(f)))
                            parts.append(f"  - {msg}")
                checks = r.evidence.get("checks", [])
                if isinstance(checks, list):
                    for check in checks[:3]:
                        if not isinstance(check, dict):
                            continue
                        command = str(check.get("command", "") or "<unknown command>")
                        exit_code = check.get("exit_code", "")
                        output = str(check.get("output", "") or "").strip()
                        parts.append(f"  Command: {command} exit_code={exit_code}")
                        if output:
                            parts.append(f"  Output: {output[:1200]}")
                output = str(r.evidence.get("output", "") or "").strip()
                if output:
                    parts.append(f"  Output: {output[:1200]}")
            parts.append("")
        return "\n".join(parts)

    def _get_gate_instance(self, gate_name: str, task: Task):
        """Get a gate instance by name for remediation."""
        language = task.feature.project.language if task.feature else "python"

        from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
        from autonomous_agent_builder.quality_gates.security import SecurityGate
        from autonomous_agent_builder.quality_gates.testing import TestingGate

        gate_map = {
            "code_quality": lambda: CodeQualityGate(language=language),
            "security": lambda: SecurityGate(),
            "testing": lambda: TestingGate(language=language),
        }

        factory = gate_map.get(gate_name)
        return factory() if factory else None
