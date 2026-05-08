"""Tests for orchestrator quality_gates phase and agent run recording."""

# ruff: noqa: ASYNC221

from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import AgentRun, Task, TaskStatus, Workspace
from autonomous_agent_builder.db.models import GateResult as GateResultModel
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
    task.retry_count = 0
    task.blocked_reason = None
    return task


@pytest.mark.asyncio
class TestQualityGatesPhase:
    """Test _phase_quality_gates dispatching."""

    @pytest.fixture(autouse=True)
    def _skip_workspace_delta_check(self, orchestrator):
        orchestrator._workspace_has_task_changes = AsyncMock(return_value=True)

    async def test_all_gates_pass_advances_to_pr(self, orchestrator):
        task = _make_task()
        task.blocked_reason = "stale lint failure"
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
        assert task.blocked_reason is None

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

    async def test_required_system_doc_must_link_to_active_task_or_feature(
        self, orchestrator, tmp_path
    ):
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

    async def test_design_phase_does_not_resume_empty_planner_run(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN)
        task.agent_runs = [
            AgentRun(
                task_id=task.id,
                agent_name="planner",
                session_id="empty-planner",
                status="completed",
                num_turns=1,
                tokens_input=0,
                tokens_output=0,
                tokens_cached=0,
                cost_usd=0.0,
            )
        ]
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-design"))

        await orchestrator._phase_design(task)

        assert orchestrator._run_agent.await_args.kwargs["resume_session"] is None

    async def test_design_phase_marks_provider_limit_as_capability_limit(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN)
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                session_id="limit",
                output_text="You've hit your limit - resets later",
                stop_reason="provider_limit",
            )
        )

        await orchestrator._phase_design(task)

        assert task.status == TaskStatus.CAPABILITY_LIMIT
        assert task.capability_limit_reason == "SDK limit: provider_limit"
        assert task.blocked_reason is not None
        assert task.blocked_reason.startswith("provider limit blocked:")
        assert task.depends_on is not None
        assert task.depends_on["provider_limit"]["resume_status"] == "design"

    async def test_planning_phase_uses_sprint_execution_without_agent_run(self, orchestrator):
        task = _make_task(TaskStatus.PENDING)
        task.depends_on = {
            "sprint_execution": {
                "skip_task_planning": True,
                "skip_task_design": True,
                "batch_id": "batch-001",
                "batch_index": 1,
                "risk_flags": ["routine"],
                "recommended_model": "sonnet",
                "recommended_effort": "medium",
                "implementation_brief": "Build the first sprint batch.",
                "file_ownership_hint": "app files and tests",
            },
            "phase_context": {
                "design_context": "{\"generated_app_acceptance\":[\"visible navigation\"]}"
            },
        }
        orchestrator._run_agent = AsyncMock()

        await orchestrator._phase_planning(task)

        orchestrator._run_agent.assert_not_called()
        assert task.status == TaskStatus.IMPLEMENTATION
        assert task.depends_on["phase_context"]["planning_context"]
        assert task.depends_on["phase_context"]["design_context"]

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

    async def test_design_phase_persists_compact_design_context_for_implementation(
        self, orchestrator
    ):
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

    async def test_implementation_phase_receives_latest_gate_feedback(self, orchestrator):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        task.retry_count = 1
        task.blocked_reason = "Quality gate failures:\n- code_quality: fail"
        gate = GateResultModel(
            task_id=task.id,
            gate_name="code_quality",
            status="fail",
            error_code="LINT_FAILED",
            evidence={
                "checks": [
                    {
                        "command": "npm run lint",
                        "exit_code": 127,
                        "output": "sh: eslint: command not found",
                    }
                ]
            },
        )
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = [gate]
        orchestrator.db.execute = AsyncMock(return_value=execute_result)
        orchestrator._get_last_run = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-impl"))

        await orchestrator._phase_implementation(task)

        template_vars = orchestrator._run_agent.await_args.args[2]
        assert "npm run lint" in template_vars["gate_feedback"]
        assert "sh: eslint: command not found" in template_vars["gate_feedback"]

    async def test_implementation_phase_does_not_resume_across_workspace_boundary(
        self, orchestrator
    ):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        orchestrator._get_last_run = AsyncMock()
        orchestrator._run_agent = AsyncMock(return_value=RunResult(session_id="sess-impl"))

        await orchestrator._phase_implementation(task)

        orchestrator._get_last_run.assert_not_awaited()
        assert "resume_session" not in orchestrator._run_agent.await_args.kwargs

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
        assert (
            task.blocked_reason
            == "implementation blocked: Should unbookmark support bulk clear?"
        )
        assert task.depends_on["operator_decision"]["options"] == [
            "Individual only",
            "Individual plus clear all",
        ]


@pytest.mark.asyncio
async def test_integrates_first_task_branch_into_unborn_main(orchestrator, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "--orphan", "task/t1"], cwd=repo, check=True)
    (repo / "package.json").write_text('{"name":"generated"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "package.json"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.local",
            "commit",
            "-m",
            "feat: scaffold",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=repo, check=True)
    task = _make_task(TaskStatus.BUILD_VERIFY)
    task.workspace = Workspace(task_id=task.id, path=str(repo), branch="task/t1", is_worktree=True)
    task.feature.project.repo_url = str(repo)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    task_head = subprocess.run(
        ["git", "rev-parse", "--verify", "task/t1"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == task_head
    assert (repo / "package.json").read_text(encoding="utf-8") == '{"name":"generated"}\n'


@pytest.mark.asyncio
async def test_integrates_uncommitted_worktree_changes_into_unborn_main(
    orchestrator, tmp_path
):
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", "task/t1", str(workspace)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (workspace / "package.json").write_text('{"name":"generated"}\n', encoding="utf-8")

    task = _make_task(TaskStatus.BUILD_VERIFY)
    task.workspace = Workspace(
        task_id=task.id,
        path=str(workspace),
        branch="task/t1",
        is_worktree=True,
    )
    task.feature.project.repo_url = str(repo)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    task_head = subprocess.run(
        ["git", "rev-parse", "--verify", "task/t1"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == task_head
    assert (repo / "package.json").read_text(encoding="utf-8") == '{"name":"generated"}\n'


@pytest.mark.asyncio
async def test_integration_preserves_project_runtime_guidance(orchestrator, tmp_path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.local"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    builder_guidance = "# Builder Runtime Guidance\n\n## Builder Contract\n"
    (repo / "CLAUDE.md").write_text(builder_guidance, encoding="utf-8")
    subprocess.run(["git", "add", "CLAUDE.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: builder guidance"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-b", "task/t1", str(workspace)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (workspace / "CLAUDE.md").write_text("# Generated App Notes\n", encoding="utf-8")
    (workspace / "app.py").write_text("print('ship')\n", encoding="utf-8")
    subprocess.run(["git", "add", "CLAUDE.md", "app.py"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: app slice"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    updated_guidance = "# Builder Runtime Guidance\n\n## Builder Contract\nUpdated.\n"
    (repo / "CLAUDE.md").write_text(updated_guidance, encoding="utf-8")

    task = _make_task(TaskStatus.BUILD_VERIFY)
    task.workspace = Workspace(
        task_id=task.id,
        path=str(workspace),
        branch="task/t1",
        is_worktree=True,
    )
    task.feature.project.repo_url = str(repo)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == updated_guidance
    assert (repo / "app.py").read_text(encoding="utf-8") == "print('ship')\n"


@pytest.mark.asyncio
async def test_integration_rebases_diverged_task_branch(orchestrator, tmp_path):
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.local"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "CLAUDE.md").write_text("# Builder Runtime Guidance\n", encoding="utf-8")
    (repo / "app.py").write_text("features = []\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: baseline"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-b", "task/t2", str(workspace)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (workspace / "edit.py").write_text("edit = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "edit.py"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: edit details"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    (repo / "board.py").write_text("board = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "board.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: board"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    task = _make_task(TaskStatus.BUILD_VERIFY)
    task.workspace = Workspace(
        task_id=task.id,
        path=str(workspace),
        branch="task/t2",
        is_worktree=True,
    )
    task.feature.project.repo_url = str(repo)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert (repo / "board.py").read_text(encoding="utf-8") == "board = True\n"
    assert (repo / "edit.py").read_text(encoding="utf-8") == "edit = True\n"


@pytest.mark.asyncio
async def test_integration_uses_resolver_for_rebase_conflicts(
    orchestrator,
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.local"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "app.py").write_text("features = ['base']\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: baseline"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-b", "task/t3", str(workspace)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (workspace / "app.py").write_text("features = ['base', 'edit']\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: edit"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    (repo / "app.py").write_text("features = ['base', 'board']\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: board"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    async def fake_run_agent(task, agent_name, template_vars, resume_session=None):
        assert agent_name == "integration-resolver"
        assert "app.py" in template_vars["conflict_files"]
        assert str(workspace) == template_vars["workspace_path"]
        (workspace / "app.py").write_text(
            "features = ['base', 'board', 'edit']\n",
            encoding="utf-8",
        )
        return RunResult(output_text="resolved rebase conflict")

    monkeypatch.setattr(orchestrator, "_run_agent", fake_run_agent)
    task = _make_task(TaskStatus.BUILD_VERIFY)
    task.workspace = Workspace(
        task_id=task.id,
        path=str(workspace),
        branch="task/t3",
        is_worktree=True,
    )
    task.feature.project.repo_url = str(repo)

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert (repo / "app.py").read_text(encoding="utf-8") == (
        "features = ['base', 'board', 'edit']\n"
    )


@pytest.mark.asyncio
async def test_workspace_has_task_changes_detects_noop_branch(orchestrator, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "package.json").write_text('{"name":"base"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "package.json"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.local",
            "commit",
            "-m",
            "feat: base",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "task/noop"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    assert await orchestrator._workspace_has_task_changes(str(repo)) is False

    (repo / "src.ts").write_text("export {}\n", encoding="utf-8")
    assert await orchestrator._workspace_has_task_changes(str(repo)) is True


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
    async def test_validates_project_root_not_task_workspace(
        self, orchestrator, tmp_path
    ):
        task = _make_task()
        project_root = tmp_path / "repo"
        workspace_path = tmp_path / "workspace"
        project_root.mkdir()
        workspace_path.mkdir()
        task.feature.project.repo_url = str(project_root)
        task.workspace.path = str(workspace_path)

        load_validation = AsyncMock(
            return_value={
                "passed": True,
                "summary": "Maintained docs are already current.",
                "checks": [],
                "freshness_report": [],
            }
        )

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            load_validation,
        ):
            gap = await orchestrator._run_documentation_refresh_gate(
                task,
                str(workspace_path),
            )

        assert gap is None
        load_validation.assert_awaited_once_with(project_root.resolve())

    async def test_documentation_refresh_is_advisory_for_unborn_greenfield_repo(
        self, orchestrator, tmp_path
    ):
        task = _make_task()
        project_root = tmp_path / "repo"
        workspace_path = tmp_path / "workspace"
        project_root.mkdir()
        workspace_path.mkdir()
        subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        task.feature.project.repo_url = str(project_root)
        task.workspace.path = str(workspace_path)

        validation_fail = {
            "passed": False,
            "summary": "Missing blocking docs and unable to resolve main head.",
            "checks": [{"name": "completeness", "passed": False, "details": {}}],
            "freshness_report": [
                {
                    "doc_id": "testing-patterns",
                    "status": "blocked",
                    "stale_reason": "unable to resolve main head",
                    "blocking": True,
                }
            ],
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(return_value=validation_fail),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
        ) as bridge:
            gap = await orchestrator._run_documentation_refresh_gate(
                task,
                str(workspace_path),
            )

        assert gap is None
        bridge.assert_not_awaited()

    async def test_documentation_refresh_is_advisory_for_forward_deferred_seed_docs(
        self, orchestrator, tmp_path
    ):
        from autonomous_agent_builder import onboarding
        from autonomous_agent_builder.services.readiness import assess_readiness

        task = _make_task()
        project_root = tmp_path / "repo"
        workspace_path = tmp_path / "workspace"
        project_root.mkdir()
        workspace_path.mkdir()
        subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        (project_root / "CLAUDE.md").write_text("# Runtime guidance\n", encoding="utf-8")
        (project_root / ".agent-builder").mkdir()
        (project_root / ".agent-builder" / "config.yaml").write_text(
            "project:\n  name: test\n",
            encoding="utf-8",
        )
        (project_root / ".agent-builder" / "agent_builder.db").write_text("", encoding="utf-8")
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        state = onboarding.default_onboarding_state(project_root)
        state["onboarding_mode"] = "forward_engineering"
        state["current_phase"] = "ready"
        state["ready"] = True
        for phase in state["phases"]:
            phase["status"] = "passed"
        onboarding.save_onboarding_state(project_root, state)
        assess_readiness(project_root, onboarding_state=state, write=True)
        task.feature.project.repo_url = str(project_root)
        task.workspace.path = str(workspace_path)

        validation_fail = {
            "passed": False,
            "summary": "Missing seed docs.",
            "claim_failures": [
                {"doc": "system-architecture", "reason": "missing_document"},
                {"doc": "dependencies", "reason": "missing_document"},
            ],
            "checks": [
                {"name": "claim_validation", "passed": False, "details": {}},
                {"name": "freshness", "passed": True, "details": {}},
            ],
            "freshness_report": [],
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(return_value=validation_fail),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
        ) as bridge:
            gap = await orchestrator._run_documentation_refresh_gate(task, str(workspace_path))

        assert gap is None
        bridge.assert_not_awaited()

    async def test_forward_engineering_sprint_doc_hash_drift_is_advisory(
        self, orchestrator, tmp_path
    ):
        task = _make_task()
        task.depends_on = {
            "sprint_execution": {
                "mode": "sprint_task_breakdown",
                "task_key": "core-app-behavior",
            }
        }
        project_root = tmp_path / "repo"
        workspace_path = tmp_path / "workspace"
        project_root.mkdir()
        workspace_path.mkdir()
        task.feature.project.repo_url = str(project_root)
        task.workspace.path = str(workspace_path)

        validation_fail = {
            "passed": False,
            "summary": "Deterministic KB validation failed for blocking docs.",
            "claim_failures": [],
            "checks": [
                {"name": "completeness", "passed": True, "details": {}},
                {
                    "name": "citation_validity",
                    "passed": False,
                    "details": {
                        "issues": [
                            "system-architecture: Dependency hash does not match current dependency contents."
                        ]
                    },
                },
                {
                    "name": "freshness",
                    "passed": False,
                    "details": {
                        "issues": ["system-architecture: dependency hash mismatch"],
                        "maintained_docs": [],
                    },
                },
            ],
            "freshness_report": [],
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(return_value=validation_fail),
        ), patch(
            "autonomous_agent_builder.onboarding.load_onboarding_state",
            return_value={"onboarding_mode": "forward_engineering"},
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
        ) as bridge:
            gap = await orchestrator._run_documentation_refresh_gate(
                task,
                str(workspace_path),
            )

        assert gap is None
        bridge.assert_not_awaited()

    async def test_forward_engineering_non_actionable_doc_validation_is_advisory(
        self, orchestrator, tmp_path
    ):
        from autonomous_agent_builder import onboarding
        from autonomous_agent_builder.services.readiness import assess_readiness

        task = _make_task()
        project_root = tmp_path / "repo"
        workspace_path = tmp_path / "workspace"
        project_root.mkdir()
        workspace_path.mkdir()
        subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        (project_root / "CLAUDE.md").write_text("# Runtime guidance\n", encoding="utf-8")
        (project_root / ".agent-builder").mkdir()
        (project_root / ".agent-builder" / "config.yaml").write_text(
            "project:\n  name: test\n",
            encoding="utf-8",
        )
        (project_root / ".agent-builder" / "agent_builder.db").write_text("", encoding="utf-8")
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        state = onboarding.default_onboarding_state(project_root)
        state["onboarding_mode"] = "forward_engineering"
        state["current_phase"] = "ready"
        state["ready"] = True
        for phase in state["phases"]:
            phase["status"] = "passed"
        onboarding.save_onboarding_state(project_root, state)
        assess_readiness(project_root, onboarding_state=state, write=True)
        task.feature.project.repo_url = str(project_root)
        task.workspace.path = str(workspace_path)

        validation_fail = {
            "passed": False,
            "summary": "Validation failed without actionable maintained docs.",
            "checks": [{"name": "completeness", "passed": False, "details": {}}],
            "freshness_report": [],
        }
        bridge_payload = {
            "status": "manual_attention",
            "summary": "No actionable maintained docs.",
            "bridge_invoked": False,
            "actionable_doc_ids": [],
            "manual_attention_reasons": [
                "validation failed without actionable stale maintained docs"
            ],
            "remaining_gap": "validation failed without actionable stale maintained docs",
            "run": {},
            "result": {},
        }

        with patch.object(
            orchestrator,
            "_load_kb_validation_payload",
            AsyncMock(return_value=validation_fail),
        ), patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_documentation_refresh_bridge",
            new_callable=AsyncMock,
            return_value=bridge_payload,
        ) as bridge:
            gap = await orchestrator._run_documentation_refresh_gate(task, str(workspace_path))

        assert gap is None
        bridge.assert_awaited_once()

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
            "_workspace_has_task_changes",
            AsyncMock(return_value=True),
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

    async def test_run_agent_passes_role_effort_to_runtime(self, orchestrator):
        task = _make_task(TaskStatus.PENDING)
        runtime = MagicMock()
        runtime.run = AsyncMock(return_value=RunResult(session_id="sess-effort"))

        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.create_runtime",
            return_value=runtime,
        ):
            await orchestrator._run_agent(
                task,
                "planner",
                {
                    "feature_description": "test",
                    "project_name": "test",
                    "language": "python",
                },
            )

        runtime.run.assert_awaited_once()
        assert runtime.run.await_args.kwargs["effort"] == "high"

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

    async def test_agent_runner_falls_back_from_empty_opus_result(self):
        runner = AgentRunner(get_settings())
        calls = []

        async def _fake_execute(**kwargs):
            calls.append(kwargs["agent_def"].model)
            if len(calls) == 1:
                return RunResult(session_id="empty", stop_reason="stop_sequence", num_turns=1)
            return RunResult(
                session_id="fallback",
                output_text="Fallback completed.",
                tokens_input=10,
                tokens_output=5,
                cost_usd=0.01,
            )

        runner._execute_query = _fake_execute

        result = await runner.run_phase("planner", "prompt", "/tmp")

        assert result.error is None
        assert result.output_text == "Fallback completed."
        assert calls == ["opus", "sonnet"]

    async def test_agent_runner_maps_provider_limit_text(self):
        runner = AgentRunner(get_settings())

        async def _fake_execute(**kwargs):
            return RunResult(
                session_id="limit",
                output_text="You're out of extra usage · resets 11:10pm (Asia/Calcutta)",
                stop_reason="stop_sequence",
                num_turns=1,
            )

        runner._execute_query = _fake_execute

        result = await runner.run_phase("code-gen", "prompt", "/tmp")

        assert result.error is None
        assert result.stop_reason == "provider_limit"
        assert result.hit_capability_limit is True
        assert result.provider_limit is not None
        assert result.provider_limit["reset_hint"] == "resets 11:10pm"


# ── Council 2026-05-08 — Item 3: orchestrator.apply_approval_outcome ──
from autonomous_agent_builder.db.models import (
    ApprovalDecision as _Decision,
)
from autonomous_agent_builder.orchestrator.orchestrator import (
    apply_approval_outcome as _apply,
)


def _approval_task(status: TaskStatus = TaskStatus.DESIGN_REVIEW) -> Task:
    task = Task(
        id="task-approval",
        feature_id="feat-1",
        title="t",
        description="d",
        status=status,
    )
    task.depends_on = None
    task.blocked_reason = "stale"
    task.blocked_at = None
    return task


class TestApplyApprovalOutcome:
    def test_approve_planning_advances_to_design_and_dispatches(self):
        task = _approval_task(TaskStatus.DESIGN_REVIEW)
        should_dispatch = _apply(task, "planning", _Decision.APPROVE)
        assert task.status == TaskStatus.DESIGN
        assert task.blocked_reason is None
        assert should_dispatch is True

    def test_approve_design_advances_to_implementation(self):
        task = _approval_task(TaskStatus.DESIGN_REVIEW)
        should_dispatch = _apply(task, "design", _Decision.APPROVE)
        assert task.status == TaskStatus.IMPLEMENTATION
        assert should_dispatch is True

    def test_approve_pr_advances_to_build_verify(self):
        task = _approval_task(TaskStatus.REVIEW_PENDING)
        should_dispatch = _apply(task, "pr", _Decision.APPROVE)
        assert task.status == TaskStatus.BUILD_VERIFY
        assert should_dispatch is True

    def test_request_changes_on_pr_loops_back_to_implementation_with_context(self):
        task = _approval_task(TaskStatus.REVIEW_PENDING)
        should_dispatch = _apply(
            task, "pr", _Decision.REQUEST_CHANGES, reason="please fix tests"
        )
        assert task.status == TaskStatus.IMPLEMENTATION
        assert task.depends_on is not None
        assert (
            task.depends_on["phase_context"]["pr_change_request"]
            == "please fix tests"
        )
        assert should_dispatch is True

    def test_reject_blocks_the_task_and_records_reason(self):
        task = _approval_task(TaskStatus.DESIGN_REVIEW)
        should_dispatch = _apply(
            task, "planning", _Decision.REJECT, reason="scope unclear"
        )
        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == "scope unclear"
        assert should_dispatch is False

    def test_reject_default_reason_when_none_provided(self):
        task = _approval_task(TaskStatus.DESIGN_REVIEW)
        should_dispatch = _apply(task, "planning", _Decision.REJECT)
        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason == "Approval rejected"
        assert should_dispatch is False

    def test_request_changes_on_non_pr_falls_through_to_block(self):
        task = _approval_task(TaskStatus.DESIGN_REVIEW)
        should_dispatch = _apply(task, "planning", _Decision.REQUEST_CHANGES)
        assert task.status == TaskStatus.BLOCKED
        assert should_dispatch is False


# ── Sprint-PR refactor (Phase A) — apply_sprint_approval_outcome ──
from autonomous_agent_builder.db.models import (
    Sprint as _Sprint,
    SprintPhase as _SprintPhase,
)
from autonomous_agent_builder.orchestrator.orchestrator import (
    apply_sprint_approval_outcome as _apply_sprint,
)


def _sprint(phase: _SprintPhase = _SprintPhase.PR_REVIEW) -> _Sprint:
    sprint = _Sprint(
        id="sprint-1",
        project_id="proj-1",
        label="Sprint 1",
        phase=phase,
    )
    sprint.verification_evidence = {}
    return sprint


def _sprint_task(status: TaskStatus = TaskStatus.DONE) -> Task:
    task = Task(
        id=f"task-{id(status)}",
        feature_id="feat-1",
        title="t",
        description="d",
        status=status,
    )
    task.depends_on = None
    task.blocked_reason = None
    task.blocked_at = None
    return task


class TestApplySprintApprovalOutcome:
    def test_approve_marks_sprint_shipped_and_records_evidence(self):
        sprint = _sprint(_SprintPhase.PR_REVIEW)
        should_followup = _apply_sprint(
            sprint, _Decision.APPROVE, reason="ship it"
        )
        assert sprint.phase == _SprintPhase.SHIPPED
        assert should_followup is True
        evidence = sprint.verification_evidence or {}
        assert "sprint_pr_approved_at" in evidence
        assert evidence.get("sprint_pr_approval_reason") == "ship it"

    def test_request_changes_resets_tasks_to_implementation_and_keeps_sprint_at_verify(self):
        sprint = _sprint(_SprintPhase.PR_REVIEW)
        tasks = [_sprint_task(TaskStatus.DONE), _sprint_task(TaskStatus.DONE)]
        should_followup = _apply_sprint(
            sprint,
            _Decision.REQUEST_CHANGES,
            reason="please add tests",
            sprint_tasks=tasks,
        )
        assert sprint.phase == _SprintPhase.VERIFY
        assert should_followup is True
        assert all(task.status == TaskStatus.IMPLEMENTATION for task in tasks)
        assert all(task.blocked_reason == "please add tests" for task in tasks)
        evidence = sprint.verification_evidence or {}
        assert evidence.get("pr_change_request") == "please add tests"
        assert "pr_change_request_at" in evidence

    def test_request_changes_default_reason_when_none(self):
        sprint = _sprint(_SprintPhase.PR_REVIEW)
        should_followup = _apply_sprint(sprint, _Decision.REQUEST_CHANGES)
        assert sprint.phase == _SprintPhase.VERIFY
        evidence = sprint.verification_evidence or {}
        assert evidence.get("pr_change_request") == "PR changes requested"
        assert should_followup is True

    def test_reject_blocks_sprint_and_records_reason(self):
        sprint = _sprint(_SprintPhase.PR_REVIEW)
        should_followup = _apply_sprint(
            sprint, _Decision.REJECT, reason="scope mismatch"
        )
        assert sprint.phase == _SprintPhase.BLOCKED
        assert should_followup is False
        evidence = sprint.verification_evidence or {}
        assert evidence.get("sprint_pr_rejection_reason") == "scope mismatch"
        assert "sprint_pr_rejected_at" in evidence

    def test_reject_default_reason_when_none(self):
        sprint = _sprint(_SprintPhase.PR_REVIEW)
        _apply_sprint(sprint, _Decision.REJECT)
        evidence = sprint.verification_evidence or {}
        assert evidence.get("sprint_pr_rejection_reason") == "Sprint PR rejected"
