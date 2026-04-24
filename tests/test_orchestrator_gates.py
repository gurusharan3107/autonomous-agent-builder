"""Tests for orchestrator quality_gates phase and agent run recording."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import AgentRun, Task, TaskStatus
from autonomous_agent_builder.knowledge.system_docs import (
    format_task_system_doc_guidance,
    reconcile_task_system_docs,
    validate_task_system_docs,
)
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def orchestrator(mock_db):
    return Orchestrator(get_settings(), mock_db)


def _make_task(status: TaskStatus = TaskStatus.QUALITY_GATES) -> Task:
    task = Task(
        id="gate-test",
        feature_id="feat-1",
        title="Gate test",
        description="Testing quality gates",
        status=status,
    )
    project = MagicMock()
    project.name = "test"
    project.language = "python"
    feature = MagicMock()
    feature.project = project
    task.feature = feature
    task.workspace = MagicMock(path="/tmp/ws")
    task.agent_runs = []
    task.approval_gates = []
    task.depends_on = None
    return task


@pytest.mark.asyncio
class TestQualityGatesPhase:
    """Test _phase_quality_gates dispatching."""

    async def test_all_gates_pass_advances_to_pr(self, orchestrator):
        task = _make_task()
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=100,
                ),
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=200,
                ),
            ],
        )
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ), patch.object(
            orchestrator,
            "_run_documentation_refresh_gate",
            AsyncMock(return_value=None),
        ):
            await orchestrator._phase_quality_gates(task)
        assert task.status == TaskStatus.PR_CREATION

    async def test_gate_warn_still_advances(self, orchestrator):
        task = _make_task()
        warn_result = AggregateGateResult(
            status=GateStatus.WARN,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.WARN,
                    findings_count=2,
                    elapsed_ms=100,
                ),
            ],
        )
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=warn_result,
        ), patch.object(
            orchestrator,
            "_run_documentation_refresh_gate",
            AsyncMock(return_value=None),
        ):
            await orchestrator._phase_quality_gates(task)
        assert task.status == TaskStatus.PR_CREATION

    async def test_gate_fail_triggers_feedback(self, orchestrator):
        task = _make_task()
        fail_result = AggregateGateResult(
            status=GateStatus.FAIL,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.FAIL,
                    findings_count=5,
                    elapsed_ms=100,
                    error_code="LINT_FAILED",
                ),
            ],
        )
        orchestrator.gate_handler.handle_gate_failure = AsyncMock()
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=fail_result,
        ):
            await orchestrator._phase_quality_gates(task)
        orchestrator.gate_handler.handle_gate_failure.assert_called_once()

    async def test_missing_required_system_doc_blocks_after_passing_gates(self, orchestrator):
        task = _make_task()
        task.depends_on = {
            "system_docs": {
                "required_docs": ["system-docs/testing-checklist.md"],
            }
        }
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=50,
                )
            ],
        )

        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ):
            await orchestrator._phase_quality_gates(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == (
            "missing required system doc: system-docs/testing-checklist.md"
        )

    async def test_testing_doc_id_is_passed_into_testing_gate(self, orchestrator, tmp_path):
        task = _make_task()
        kb_root = tmp_path / ".agent-builder" / "knowledge"
        doc_path = kb_root / "system-docs" / "feature-testing.md"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(
            "---\n"
            "title: Feature Testing\n"
            "tags: [testing, system-docs]\n"
            "doc_type: testing\n"
            "doc_family: testing\n"
            "feature_id: feat-1\n"
            "task_id: gate-test\n"
            "created: 2026-04-22T00:00:00+00:00\n"
            "updated: 2026-04-22T00:00:00+00:00\n"
            "last_verified_at: 2026-04-22T00:00:00+00:00\n"
            "auto_generated: false\n"
            "version: 1\n"
            "---\n\n"
            "# Feature Testing\n\n"
            "## Overview\n\n"
            "Testing guidance.\n",
            encoding="utf-8",
        )
        task.depends_on = {
            "system_docs": {
                "required_docs": ["system-docs/feature-testing.md"],
            }
        }
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=50,
                )
            ],
        )

        def _fake_testing_gate(*, language: str, testing_doc_id: str | None = None):
            gate = MagicMock()
            gate.name = "testing"
            gate.gate_type = "testing"
            gate.language = language
            gate.testing_doc_id = testing_doc_id
            return gate

        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.validate_task_system_docs",
            side_effect=lambda depends_on, **kwargs: validate_task_system_docs(
                depends_on, kb_root=kb_root, **kwargs
            ),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.TestingGate",
            side_effect=_fake_testing_gate,
        ) as testing_gate, patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ), patch.object(
            orchestrator,
            "_run_documentation_refresh_gate",
            AsyncMock(return_value=None),
        ):
            await orchestrator._phase_quality_gates(task)

        testing_gate.assert_called_once_with(
            language="python",
            testing_doc_id="system-docs/feature-testing.md",
        )
        assert task.status == TaskStatus.PR_CREATION

    async def test_required_system_doc_must_link_to_active_task_or_feature(self, orchestrator, tmp_path):
        task = _make_task()
        kb_root = tmp_path / ".agent-builder" / "knowledge"
        doc_path = kb_root / "system-docs" / "feature-testing.md"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(
            "---\n"
            "title: Feature Testing\n"
            "tags: [testing, system-docs]\n"
            "doc_type: testing\n"
            "doc_family: testing\n"
            "feature_id: other-feature\n"
            "task_id: other-task\n"
            "created: 2026-04-22T00:00:00+00:00\n"
            "updated: 2026-04-22T00:00:00+00:00\n"
            "last_verified_at: 2026-04-22T00:00:00+00:00\n"
            "auto_generated: false\n"
            "version: 1\n"
            "---\n\n"
            "# Feature Testing\n\n"
            "## Overview\n\n"
            "Testing guidance.\n",
            encoding="utf-8",
        )
        task.depends_on = {
            "system_docs": {
                "required_docs": ["system-docs/feature-testing.md"],
            }
        }
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=50,
                )
            ],
        )

        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.validate_task_system_docs",
            side_effect=lambda depends_on, **kwargs: validate_task_system_docs(
                depends_on, kb_root=kb_root, **kwargs
            ),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ):
            await orchestrator._phase_quality_gates(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == (
            "system doc linked to a different task: system-docs/feature-testing.md; "
            "system doc linked to a different feature: system-docs/feature-testing.md; "
            "system doc is not linked to the active task or feature: system-docs/feature-testing.md"
        )


@pytest.mark.asyncio
class TestKnowledgeLifecycleContext:
    async def test_design_phase_passes_task_scoped_knowledge_requirements(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN)
        task.depends_on = {
            "system_docs": {
                "required_docs": ["feature/onboarding.md", "testing/onboarding-browser.md"],
            }
        }
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-design"))

        await orchestrator._phase_design(task)

        orchestrator._run_agent.assert_awaited_once()
        template_vars = orchestrator._run_agent.await_args.args[2]
        assert "feature/onboarding.md: missing" in template_vars["knowledge_requirements"]
        assert "testing/onboarding-browser.md: missing" in template_vars["knowledge_requirements"]
        assert "builder_kb_add or builder_kb_update" in template_vars["knowledge_requirements"]
        assert task.status == TaskStatus.IMPLEMENTATION

    async def test_implementation_phase_passes_knowledge_retrieval_guidance(self, orchestrator):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        task.depends_on = {
            "system_docs": {
                "required_docs": ["feature/onboarding.md"],
            }
        }
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-impl"))

        await orchestrator._phase_implementation(task)

        orchestrator._run_agent.assert_awaited_once()
        template_vars = orchestrator._run_agent.await_args.args[2]
        assert "feature/onboarding.md: missing" in template_vars["knowledge_requirements"]
        assert "builder_kb_search and builder_kb_show" in template_vars["knowledge_requirements"]
        assert task.status == TaskStatus.QUALITY_GATES

    async def test_design_phase_persists_compact_design_context_for_implementation(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN)
        task.depends_on = {"existing": True}
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                session_id="sess-design",
                output_text="ADR: keep bookmark data private and expose profile bookmarks tab.",
            )
        )

        await orchestrator._phase_design(task)

        assert task.status == TaskStatus.IMPLEMENTATION
        assert task.depends_on["phase_context"]["design_context"] == (
            "ADR: keep bookmark data private and expose profile bookmarks tab."
        )

    async def test_implementation_phase_receives_persisted_design_context(self, orchestrator):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        task.depends_on = {
            "phase_context": {
                "design_context": "Use private bookmark records and profile tab navigation."
            }
        }
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-impl"))

        await orchestrator._phase_implementation(task)

        template_vars = orchestrator._run_agent.await_args.args[2]
        assert template_vars["design_context"] == (
            "Use private bookmark records and profile tab navigation."
        )

    async def test_design_phase_can_block_with_structured_operator_decision(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN)
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                session_id="sess-design",
                output_text=(
                    'OPERATOR_DECISION_JSON: {"phase":"design","summary":"Need one UI decision",'
                    '"question":"Should bookmarks live in a profile tab or drawer?",'
                    '"options":["Profile tab","Drawer"],'
                    '"recommended_option":"Profile tab"}'
                ),
            )
        )

        await orchestrator._phase_design(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == (
            "design blocked: Should bookmarks live in a profile tab or drawer?"
        )
        assert task.depends_on["operator_decision"]["recommended_option"] == "Profile tab"

    async def test_implementation_phase_can_block_with_structured_operator_decision(
        self, orchestrator
    ):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                session_id="sess-impl",
                output_text=(
                    'OPERATOR_DECISION_JSON: {"phase":"implementation",'
                    '"summary":"Need one product decision before coding",'
                    '"question":"Should unbookmark support bulk clear?",'
                    '"options":["Individual only","Individual plus clear all"],'
                    '"recommended_option":"Individual only"}'
                ),
            )
        )

        await orchestrator._phase_implementation(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == "implementation blocked: Should unbookmark support bulk clear?"
        assert task.depends_on["operator_decision"]["options"] == [
            "Individual only",
            "Individual plus clear all",
        ]


def test_reconcile_task_system_docs_rewrites_superseded_chain(tmp_path):
    kb_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
    kb_root.mkdir(parents=True)
    (kb_root / "active.md").write_text(
        "---\n"
        "title: Active Doc\n"
        "doc_type: feature\n"
        "doc_family: feature\n"
        "refresh_required: true\n"
        "lifecycle_status: active\n"
        "---\n\n"
        "# Active Doc\n",
        encoding="utf-8",
    )
    (kb_root / "old.md").write_text(
        "---\n"
        "title: Old Doc\n"
        "doc_type: feature\n"
        "doc_family: feature\n"
        "refresh_required: true\n"
        "lifecycle_status: superseded\n"
        "superseded_by: feature/active.md\n"
        "---\n\n"
        "# Old Doc\n",
        encoding="utf-8",
    )

    normalized = reconcile_task_system_docs(
        {"system_docs": {"required_docs": ["feature/old.md", "feature/active.md"]}},
        kb_root=tmp_path / ".agent-builder" / "knowledge",
    )
    assert normalized == {"system_docs": {"required_docs": ["feature/active.md"]}}


def test_validate_task_system_docs_flags_quarantined_doc(tmp_path):
    kb_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
    kb_root.mkdir(parents=True)
    (kb_root / "quarantined.md").write_text(
        "---\n"
        "title: Quarantined Doc\n"
        "doc_type: feature\n"
        "doc_family: feature\n"
        "refresh_required: true\n"
        "lifecycle_status: quarantined\n"
        "---\n\n"
        "# Quarantined Doc\n",
        encoding="utf-8",
    )

    result = validate_task_system_docs(
        {"system_docs": {"required_docs": ["feature/quarantined.md"]}},
        kb_root=tmp_path / ".agent-builder" / "knowledge",
    )
    assert result.passed is False
    assert result.quarantined_docs == ["feature/quarantined.md"]
    assert "feature/quarantined.md: quarantined" in format_task_system_doc_guidance(result)


@pytest.mark.asyncio
class TestDocumentationRefreshGate:
    async def test_blocks_pr_creation_when_documentation_refresh_cannot_clear_gap(
        self, orchestrator
    ):
        task = _make_task()
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=50,
                )
            ],
        )

        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ), patch.object(
            orchestrator,
            "_run_documentation_refresh_gate",
            AsyncMock(
                return_value="documentation refresh gate blocked: claim validation failed"
            ),
        ):
            await orchestrator._phase_quality_gates(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == (
            "documentation refresh gate blocked: claim validation failed"
        )

    async def test_records_bridge_run_and_revalidates_after_refresh(
        self, orchestrator, mock_db, tmp_path
    ):
        task = _make_task()
        task.workspace.path = str(tmp_path)

        validation_fail = {
            "passed": False,
            "summary": "1 freshness issue detected",
            "checks": [{"name": "freshness", "passed": False, "details": {}}],
            "freshness_report": [],
        }
        validation_pass = {
            "passed": True,
            "summary": "Maintained docs are already current.",
            "checks": [],
            "freshness_report": [],
        }
        bridge_payload = {
            "status": "updated_and_verified",
            "summary": "Updated docs.",
            "bridge_invoked": True,
            "run": {
                "session_id": "sdk-doc-bridge",
                "cost_usd": 0.03,
                "tokens_input": 42,
                "tokens_output": 18,
                "num_turns": 2,
                "duration_ms": 250,
                "stop_reason": "stop_sequence",
            },
            "result": {
                "status": "updated_and_verified",
                "updated_doc_ids": ["feature/onboarding"],
                "validation_status": "pass",
            },
            "remaining_gap": "",
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(side_effect=[validation_fail, validation_pass]),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
            return_value=bridge_payload,
        ):
            gap = await orchestrator._run_documentation_refresh_gate(task, str(tmp_path))

        assert gap is None
        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], AgentRun)
        ]
        assert len(added_runs) == 1
        assert added_runs[0].agent_name == "documentation-bridge"
        assert added_runs[0].session_id == "sdk-doc-bridge"
        assert added_runs[0].status == "completed"

    async def test_blocks_when_post_refresh_validation_still_fails(
        self, orchestrator, tmp_path
    ):
        task = _make_task()
        task.workspace.path = str(tmp_path)

        validation_fail = {
            "passed": False,
            "summary": "1 freshness issue detected",
            "checks": [{"name": "freshness", "passed": False, "details": {}}],
            "freshness_report": [],
        }
        post_validation_fail = {
            "passed": False,
            "summary": "Claim validation still failing.",
            "checks": [{"name": "claim_validation", "passed": False, "details": {}}],
            "freshness_report": [],
        }
        bridge_payload = {
            "status": "updated_and_verified",
            "summary": "Updated docs.",
            "bridge_invoked": True,
            "run": {},
            "result": {"status": "updated_and_verified"},
            "remaining_gap": "",
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(side_effect=[validation_fail, post_validation_fail]),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
            return_value=bridge_payload,
        ):
            gap = await orchestrator._run_documentation_refresh_gate(task, str(tmp_path))

        assert gap == "documentation refresh gate blocked: Claim validation still failing."


@pytest.mark.asyncio
class TestAgentRunRecording:
    """Test _run_agent records AgentRun to DB."""

    async def test_run_agent_saves_agent_run(
        self, orchestrator, mock_db, mock_sdk
    ):
        task = _make_task(TaskStatus.PENDING)
        result = await orchestrator._run_agent(
            task,
            "planner",
            {"feature_description": "test", "project_name": "test", "language": "python"},
        )
        assert result is not None
        assert result.session_id is not None
        # Verify AgentRun was added to DB
        from autonomous_agent_builder.db.models import AgentRun

        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], AgentRun)
        ]
        assert len(added_runs) >= 1
        assert added_runs[0].agent_name == "planner"
        assert added_runs[0].cost_usd > 0

    async def test_run_agent_error_returns_error_result(
        self, orchestrator, mock_db
    ):
        task = _make_task(TaskStatus.PENDING)

        async def _fail(*args, **kwargs):
            raise RuntimeError("SDK error")

        orchestrator.runner._execute_query = _fail
        result = await orchestrator._run_agent(
            task,
            "planner",
            {"feature_description": "test", "project_name": "test", "language": "python"},
        )
        assert result.error is not None
        assert "SDK error" in result.error
