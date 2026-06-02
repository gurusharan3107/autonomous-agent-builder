"""Quality gate runners extracted from orchestrator."""

from __future__ import annotations

import json
from typing import Any

import structlog

from autonomous_agent_builder.db.models import Feature, Task, TaskStatus, set_task_status
from autonomous_agent_builder.db.models import GateResult as GateResultModel
from autonomous_agent_builder.knowledge.system_docs import validate_task_system_docs
from autonomous_agent_builder.orchestrator.build_verification import (
    browser_evidence_tier,
    feature_verifier_failure,
    is_sprint_feature_verification_task,
    is_ui_task,
)

log = structlog.get_logger(__name__)
from autonomous_agent_builder.orchestrator.deterministic_verification import (
    record_feature_acceptance_tests,
)
from autonomous_agent_builder.orchestrator.failure_diagnosis import diagnose_task_failure
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
    run_quality_gates,
)
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate


async def run_phase_quality_gates(orchestrator: Any, task: Task) -> None:
    """Run concurrent quality gates with AND aggregation."""
    try:
        workspace = await orchestrator._ensure_workspace(task)
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
        orchestrator.db.add(
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
        await orchestrator.db.flush()
        return
    workspace_path = str(getattr(workspace, "path", "") or "")
    language = task.feature.project.language
    doc_requirements = validate_task_system_docs(
        task.depends_on,
        task_id=task.id,
        feature_id=task.feature_id,
    )

    if not await orchestrator._workspace_has_task_changes(workspace_path):
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
        orchestrator.db.add(
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
        await orchestrator.gate_handler.handle_gate_failure(
            task,
            AggregateGateResult(status=GateStatus.FAIL, results=[no_delta]),
        )
        await orchestrator.db.flush()
        return

    pre_gates = [
        CodeQualityGate(language=language),
        TestingGate(language=language, testing_doc_id=doc_requirements.testing_doc_id),
    ]

    gate_result = await run_quality_gates(workspace_path, pre_gates)

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
        orchestrator.db.add(db_result)

    if gate_result.status in {GateStatus.PASS, GateStatus.WARN} and not doc_requirements.passed:
        set_task_status(task, TaskStatus.BLOCKED)
        task.blocked_reason = "; ".join(doc_requirements.issues)
    elif gate_result.status == GateStatus.PASS or gate_result.status == GateStatus.WARN:
        documentation_gap = await orchestrator._run_documentation_refresh_gate(task, workspace_path)
        if documentation_gap:
            set_task_status(task, TaskStatus.BLOCKED)
            task.blocked_reason = documentation_gap
        else:
            task.blocked_reason = None
            set_task_status(task, TaskStatus.PR_CREATION)
    elif gate_result.status == GateStatus.ERROR:
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
        await orchestrator.gate_handler.handle_gate_failure(task, gate_result)

    await orchestrator.db.flush()


async def run_feature_acceptance_gate(
    orchestrator: Any,
    task: Task,
    workspace_path: str,
) -> tuple[bool, str]:
    if not is_sprint_feature_verification_task(task):
        return True, ""

    feature = await orchestrator.db.get(Feature, task.feature_id)
    if feature is None:
        return False, "feature_acceptance_failed: feature record not found"

    test_success, existing_result = await orchestrator._record_feature_acceptance_tests(
        task,
        workspace_path,
        feature,
    )
    if test_success:
        return True, existing_result

    result = await orchestrator._run_agent(
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

    # IMP-019: non-blocking real-browser-proof advisory. ALWAYS log the tier
    # (real_browser / jsdom_fallback / no_browser_proof / unavailable / na) so
    # every feature acceptance is observable — a silent real_browser pass is
    # otherwise indistinguishable from the tier never being computed, and the
    # signal is the prerequisite for promoting real-browser proof to a hard gate.
    # ``advisory`` is None for the real_browser tier; it surfaces the gap when a
    # feature was accepted without live browser evidence despite the bridge
    # being available, without blocking headless/CI ships.
    from autonomous_agent_builder.agents.tools.browser_tools import (
        bridge_available,
        browser_close,
    )

    ui_task = is_ui_task(task, feature)
    evidence_tier = browser_evidence_tier(
        result.output_text, bridge_available=bridge_available(), is_ui=ui_task
    )
    log.info(
        "feature_acceptance_browser_evidence_tier",
        tier=evidence_tier["tier"],
        advisory=evidence_tier["advisory"],
        task_id=getattr(task, "id", None),
        is_ui=ui_task,
    )
    # IMP-019: persist the evidence tier as a queryable GateResultModel so
    # ``builder logs analyze`` can read it without re-parsing raw transcripts.
    tier_status = (
        GateStatus.WARN
        if evidence_tier["tier"] in {"no_browser_proof", "unavailable", "jsdom_fallback"}
        else GateStatus.PASS
    )
    orchestrator.db.add(
        GateResultModel(
            task_id=getattr(task, "id", None),
            gate_name="feature_acceptance_browser_evidence_tier",
            status=tier_status.value,
            evidence={
                "browser_evidence_tier": evidence_tier["browser_evidence_tier"],
                "tier": evidence_tier["tier"],
                "advisory": evidence_tier["advisory"],
                "is_ui_task": ui_task,
            },
            findings_count=0,
            elapsed_ms=0,
            error_code=None,
            timeout=False,
            remediation_attempted=False,
            remediation_succeeded=False,
        )
    )
    # IMP-019: tear down the dedicated verification tab the in-process browser
    # tools opened, so a run leaves no orphan tabs in the operator's browser
    # (hermes-chrome closeout). Never let teardown break the gate.
    try:
        await browser_close()
    except Exception:  # noqa: BLE001 - teardown is best-effort
        pass

    test_success, test_output = await orchestrator._record_feature_acceptance_tests(
        task,
        workspace_path,
        feature,
    )
    if test_success:
        return True, test_output
    return False, f"feature_acceptance_failed: {test_output}"


async def run_record_feature_acceptance_tests(
    orchestrator: Any,
    task: Task,
    workspace_path: str,
    feature: Feature,
) -> tuple[bool, str]:
    return await record_feature_acceptance_tests(
        orchestrator.db,
        task,
        workspace_path,
        feature,
        orchestrator._publish_realtime_board_snapshot,
    )
