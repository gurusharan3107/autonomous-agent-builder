"""End-to-end pipeline validation — FT-017.

Validates the full SDLC pipeline: PENDING → planning → design_review → (approval)
→ design → implementation → quality_gates → pr_creation → review_pending → (approval)
→ build_verify → DONE.

Uses mocked SDK calls but exercises real:
- API routes (CRUD, dispatch, approval)
- Orchestrator dispatch logic (all phase transitions)
- Quality gates on real files (ruff + pytest on synthetic project)
- Approval flow (create gate, submit decision, advance status)
- Cost tracking (AgentRun records with USD values)
- Dashboard endpoints (board sections, metrics aggregation)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    Feature,
    HarnessAction,
    Task,
    Workspace,
)
from autonomous_agent_builder.harness.harnessability import score_project
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

SYNTHETIC_PROJECT = Path(__file__).parent / "synthetic_project"


# ── Helpers ──


async def _load_task(factory, task_id: str) -> Task:
    """Load a task with all relationships for orchestrator dispatch."""
    async with factory() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.feature).selectinload(Feature.project),
                selectinload(Task.workspace),
                selectinload(Task.agent_runs),
                selectinload(Task.approval_gates),
            )
        )
        return result.scalar_one()


async def _dispatch(factory, task_id: str) -> str:
    """Load task, dispatch via orchestrator, commit, return new status."""
    async with factory() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.feature).selectinload(Feature.project),
                selectinload(Task.workspace),
                selectinload(Task.agent_runs),
                selectinload(Task.approval_gates),
            )
        )
        task = result.scalar_one()
        orchestrator = Orchestrator(get_settings(), session)
        await orchestrator.dispatch(task)
        await session.commit()
        return task.status.value


# ── Tests ──


class TestHarnessability:
    """Validate harnessability scorer on the synthetic project."""

    def test_synthetic_project_scores_at_least_5(self):
        result = score_project(str(SYNTHETIC_PROJECT), "python")
        assert result.score >= 5, f"Expected >= 5, got {result.score}: {result.checks}"

    def test_routing_action_is_proceed(self):
        result = score_project(str(SYNTHETIC_PROJECT), "python")
        assert result.routing_action == HarnessAction.PROCEED

    def test_all_checks_present(self):
        result = score_project(str(SYNTHETIC_PROJECT), "python")
        expected = {
            "has_type_annotations",
            "has_linting_config",
            "has_test_suite",
            "has_module_boundaries",
            "has_api_contracts",
        }
        assert set(result.checks.keys()) == expected


class TestAPIEntityCreation:
    """Validate project/feature/task creation via REST API."""

    @pytest.mark.asyncio
    async def test_create_project(self, client, test_db):
        resp = await client.post(
            "/api/projects/",
            json={"name": "e2e-test-project", "language": "python", "repo_url": "/tmp/fake"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "e2e-test-project"
        assert data["language"] == "python"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_feature(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "feat-test", "language": "python"}
        )
        resp = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Add greeting endpoint", "description": "New endpoint"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Add greeting endpoint"

    @pytest.mark.asyncio
    async def test_create_task(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "task-test", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Feature A"},
        )
        resp = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={
                "title": "Implement /greet",
                "description": "Add a /greet/{name} endpoint",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"


class TestFullPipeline:
    """Full SDLC pipeline: PENDING → ... → DONE.

    This is the core FT-017 validation. Each step exercises the real orchestrator,
    real quality gates, real approval flow, and mock SDK calls.
    """

    @pytest.mark.asyncio
    async def test_pipeline_end_to_end(self, client, test_db, workspace_path, mock_sdk):
        engine, factory = test_db

        # ── Step 1: Create entities via API ──

        resp = await client.post(
            "/api/projects/",
            json={
                "name": "e2e-pipeline",
                "language": "python",
                "repo_url": str(workspace_path),
            },
        )
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/features",
            json={
                "title": "Add greeting endpoint",
                "description": "Implement a /greet/{name} endpoint returning JSON",
            },
        )
        assert resp.status_code == 201
        feature_id = resp.json()["id"]

        resp = await client.post(
            f"/api/features/{feature_id}/tasks",
            json={
                "title": "Implement /greet endpoint",
                "description": "Add a /greet/{name} endpoint that returns a greeting",
            },
        )
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        # ── Step 2: Create workspace record ──

        async with factory() as session:
            ws = Workspace(
                task_id=task_id,
                path=str(workspace_path),
                branch="task/e2e-test",
                is_worktree=False,
            )
            session.add(ws)
            await session.commit()

        # ── Phase 1: Planning → DESIGN_REVIEW ──

        status = await _dispatch(factory, task_id)
        assert status == "design_review", f"Expected design_review after planning, got {status}"

        # Verify approval gate was created
        resp = await client.get(f"/api/tasks/{task_id}/approvals")
        assert resp.status_code == 200
        gates = resp.json()
        planning_gate = next((g for g in gates if g["gate_type"] == "planning"), None)
        assert planning_gate is not None, "Planning approval gate not created"
        assert planning_gate["status"] == "pending"

        # ── Approve planning ──

        resp = await client.post(
            f"/api/approval-gates/{planning_gate['id']}/approve",
            json={
                "approver_email": "e2e@test.com",
                "decision": "approve",
                "comment": "Plan looks good",
            },
        )
        assert resp.status_code == 200

        # Verify task advanced to DESIGN
        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.json()["status"] == "design", "Task should advance to design after approval"

        # ── Phase 2: Design → IMPLEMENTATION ──

        status = await _dispatch(factory, task_id)
        assert status == "implementation", f"Expected implementation, got {status}"

        # ── Phase 3: Implementation → QUALITY_GATES ──

        status = await _dispatch(factory, task_id)
        assert status == "quality_gates", f"Expected quality_gates, got {status}"

        # ── Phase 4: Quality Gates → PR_CREATION ──
        # Quality gates run on real files in the synthetic workspace

        status = await _dispatch(factory, task_id)
        assert status in ("pr_creation", "implementation"), (
            f"Expected pr_creation (gates pass) or implementation (retry), got {status}"
        )

        # If gates triggered a retry, dispatch again
        if status == "implementation":
            status = await _dispatch(factory, task_id)
            assert status == "quality_gates"
            status = await _dispatch(factory, task_id)
            assert status == "pr_creation", f"Gates should pass on clean code, got {status}"

        # ── Phase 5: PR Creation → REVIEW_PENDING ──

        status = await _dispatch(factory, task_id)
        assert status == "review_pending", f"Expected review_pending, got {status}"

        # Find PR approval gate
        resp = await client.get(f"/api/tasks/{task_id}/approvals")
        gates = resp.json()
        pr_gate = next((g for g in gates if g["gate_type"] == "pr"), None)
        assert pr_gate is not None, "PR approval gate not created"

        # ── Approve PR ──

        resp = await client.post(
            f"/api/approval-gates/{pr_gate['id']}/approve",
            json={
                "approver_email": "e2e@test.com",
                "decision": "approve",
                "comment": "Ship it",
            },
        )
        assert resp.status_code == 200

        # Verify task advanced to BUILD_VERIFY
        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.json()["status"] == "build_verify"

        # ── Phase 6: Build Verify → DONE ──

        status = await _dispatch(factory, task_id)
        assert status == "done", f"Expected done, got {status}"

        # ── Validation: Cost Tracking ──

        resp = await client.get(f"/api/tasks/{task_id}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        agent_names = [r["agent_name"] for r in runs]
        assert "planner" in agent_names
        assert "designer" in agent_names
        assert "code-gen" in agent_names
        assert "pr-creator" in agent_names
        assert "build-verifier" in agent_names

        total_cost = sum(r["cost_usd"] for r in runs)
        assert total_cost > 0, "Cost tracking should show real USD values"

        total_tokens = sum(r["tokens_input"] + r["tokens_output"] for r in runs)
        assert total_tokens > 0, "Token tracking should show values"

        # Every run should have a session_id
        for run in runs:
            assert run["session_id"] is not None, f"Run {run['agent_name']} missing session_id"
            assert run["status"] == "completed"

        # ── Validation: Dashboard Board ──

        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        board = resp.json()
        done_ids = [t["id"] for t in board["done"]]
        assert task_id in done_ids, "Completed task should appear in board 'done' section"

        # Other sections should be empty for this task
        other_ids = (
            [t["id"] for t in board["pending"]]
            + [t["id"] for t in board["active"]]
            + [t["id"] for t in board["review"]]
            + [t["id"] for t in board["blocked"]]
        )
        assert task_id not in other_ids, "Task should only be in 'done'"

        # ── Validation: Dashboard Metrics ──

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert metrics["total_runs"] >= 5
        assert metrics["total_cost"] > 0
        assert metrics["total_tokens"] > 0

        # ── Validation: Gate Results ──

        resp = await client.get(f"/api/tasks/{task_id}/gates")
        assert resp.status_code == 200
        gate_results = resp.json()
        assert len(gate_results) >= 1, "At least one quality gate should have run"
        gate_names = [g["gate_name"] for g in gate_results]
        assert "code_quality" in gate_names, "Code quality gate should have run"


class TestQualityGatesStandalone:
    """Validate quality gates execute correctly on the synthetic project."""

    @pytest.mark.asyncio
    async def test_code_quality_gate_passes(self, workspace_path):
        from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate

        gate = CodeQualityGate(language="python")
        result = await gate.run(str(workspace_path))
        assert result.status.value in ("pass", "warn"), (
            f"Code quality gate should pass on clean code: {result.evidence}"
        )

    @pytest.mark.asyncio
    async def test_testing_gate_passes(self, workspace_path):
        from autonomous_agent_builder.quality_gates.testing import TestingGate

        gate = TestingGate(language="python")
        result = await gate.run(str(workspace_path))
        assert result.status.value in ("pass", "warn"), (
            f"Testing gate should pass on synthetic project: {result.evidence}"
        )


class TestApprovalFlow:
    """Validate approval submission and task advancement."""

    @pytest.mark.asyncio
    async def test_reject_blocks_task(self, client, test_db, workspace_path, mock_sdk):
        _, factory = test_db

        # Create entities
        proj = await client.post(
            "/api/projects/",
            json={"name": "reject-test", "language": "python"},
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Feature X"},
        )
        task_resp = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Task X", "description": "Test rejection"},
        )
        task_id = task_resp.json()["id"]

        # Create workspace
        async with factory() as session:
            ws = Workspace(
                task_id=task_id,
                path=str(workspace_path),
                branch="task/reject-test",
                is_worktree=False,
            )
            session.add(ws)
            await session.commit()

        # Dispatch to get approval gate
        await _dispatch(factory, task_id)

        # Find gate and reject
        resp = await client.get(f"/api/tasks/{task_id}/approvals")
        gate = resp.json()[0]
        resp = await client.post(
            f"/api/approval-gates/{gate['id']}/approve",
            json={
                "approver_email": "e2e@test.com",
                "decision": "reject",
                "comment": "Needs rework",
            },
        )
        assert resp.status_code == 200

        # Task should be blocked
        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.json()["status"] == "blocked"
        assert "Needs rework" in resp.json()["blocked_reason"]

    @pytest.mark.asyncio
    async def test_double_approval_rejected(self, client, test_db, workspace_path, mock_sdk):
        _, factory = test_db

        proj = await client.post(
            "/api/projects/", json={"name": "double-approve", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features", json={"title": "Feature Y"}
        )
        task_resp = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Task Y", "description": "Test double approval"},
        )
        task_id = task_resp.json()["id"]

        async with factory() as session:
            ws = Workspace(
                task_id=task_id,
                path=str(workspace_path),
                branch="task/double-test",
                is_worktree=False,
            )
            session.add(ws)
            await session.commit()

        await _dispatch(factory, task_id)

        resp = await client.get(f"/api/tasks/{task_id}/approvals")
        gate_id = resp.json()[0]["id"]

        # First approval succeeds
        resp = await client.post(
            f"/api/approval-gates/{gate_id}/approve",
            json={"approver_email": "e2e@test.com", "decision": "approve", "comment": "OK"},
        )
        assert resp.status_code == 200

        # Second approval on same gate should fail
        resp = await client.post(
            f"/api/approval-gates/{gate_id}/approve",
            json={"approver_email": "e2e@test.com", "decision": "approve", "comment": "Again"},
        )
        assert resp.status_code == 400


class TestDashboardEndpoints:
    """Validate dashboard JSON API responses."""

    @pytest.mark.asyncio
    async def test_empty_board(self, client, test_db):
        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        board = resp.json()
        assert board["pending"] == []
        assert board["active"] == []
        assert board["review"] == []
        assert board["done"] == []
        assert board["blocked"] == []

    @pytest.mark.asyncio
    async def test_empty_metrics(self, client, test_db):
        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert metrics["total_cost"] == 0
        assert metrics["total_runs"] == 0
        assert metrics["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_approval_details_404(self, client, test_db):
        resp = await client.get("/api/dashboard/approvals/nonexistent")
        assert resp.status_code == 404
