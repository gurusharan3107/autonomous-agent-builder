from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    AgentRunEvent,
    DesignDocument,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    Workspace,
)
from autonomous_agent_builder.orchestrator.build_verification import build_verifier_failure
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.services.runtime_guidance import render_project_runtime_guidance
from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_DESIGN_DOC_TYPE,
    SPRINT_EXECUTION_KEY,
    SPRINT_PLAN_DOC_TYPE,
    persist_sprint_execution_artifacts,
)


@pytest.mark.asyncio
async def test_sprint_execution_artifacts_annotate_queued_tasks(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="ShipCheck", language="python")
        db.add(project)
        await db.flush()
        first = Feature(
            project_id=project.id,
            title="Release Candidate Management",
            description="Create RCs with SQLite persistence",
            priority=100,
            acceptance_criteria=["Create and activate an RC"],
        )
        second = Feature(
            project_id=project.id,
            title="Validation Checks",
            description="Add validation checks and JSON routes",
            priority=90,
            dependencies=[first.id],
            acceptance_criteria=["Add a check with status"],
        )
        db.add_all([first, second])
        await db.flush()
        result = await db.execute(
            select(Feature)
            .options(selectinload(Feature.tasks))
            .where(Feature.project_id == project.id)
            .order_by(Feature.priority.desc())
        )
        features = list(result.scalars().all())

        artifacts = await persist_sprint_execution_artifacts(db, project, features)

        assert artifacts["plan"]["mode"] == "sprint_task_breakdown"
        assert artifacts["plan"]["single_sprint_plan"] is True
        assert artifacts["plan"]["single_sprint_design"] is True
        assert artifacts["plan"]["parallelism"]["strategy"] == (
            "single shared plan/design with dependency-batch execution"
        )
        assert artifacts["plan"]["context_strategy"]
        assert artifacts["plan"]["runtime_decision_summary"]["runtime"] == "claude_agent_sdk"
        assert len(artifacts["plan"]["phase_runtime_decisions"]) == 7
        assert [batch["id"] for batch in artifacts["plan"]["batches"]] == [
            "batch-001",
            "batch-002",
            "batch-003",
            "batch-004",
            "batch-005",
            "batch-006",
        ]
        assert artifacts["plan"]["batches"][0]["execution_mode"] == "parallel"
        assert artifacts["plan"]["batches"][0]["parallel_group"] == "independent-core-app-behavior"
        assert artifacts["plan"]["batches"][1]["depends_on_batches"] == ["batch-001"]
        assert artifacts["plan"]["batches"][3]["depends_on_batches"] == []
        assert artifacts["design"]["generated_app_acceptance"]
        assert artifacts["design"]["implementation_orchestration"]["single_plan"] is True
        assert artifacts["design"]["implementation_orchestration"]["single_design"] is True

        task_result = await db.execute(select(Task).order_by(Task.title))
        tasks = list(task_result.scalars().all())
        assert len(tasks) == 6
        for task in tasks:
            sprint_execution = task.depends_on[SPRINT_EXECUTION_KEY]
            assert sprint_execution["skip_task_planning"] is True
            assert sprint_execution["skip_task_design"] is True
            assert sprint_execution["recommended_model"] == "sonnet"
            assert sprint_execution["recommended_effort"] in {"medium", "high"}
            assert sprint_execution["execution_mode"] in {"parallel", "sequential"}
            assert "orchestration_reason" in sprint_execution
            assert sprint_execution["context_strategy"]
            assert sprint_execution["runtime_tool_strategy"]
            assert sprint_execution["runtime_decision"]["phase"] == "implementation"
            assert sprint_execution["implementation_brief"]
            assert task.depends_on["phase_context"]["planning_context"]

        sprint = (await db.execute(select(Sprint))).scalar_one()
        assert sprint.phase == "implementation"
        assert sprint.approved_feature_ids == [first.id, second.id]
        assert len(sprint.generated_task_ids) == 6
        assert first.status == FeatureStatus.SPRINT_PLANNED
        assert second.status == FeatureStatus.SPRINT_PLANNED

        doc_result = await db.execute(select(DesignDocument).order_by(DesignDocument.doc_type))
        docs = list(doc_result.scalars().all())
        assert {doc.doc_type for doc in docs} == {SPRINT_PLAN_DOC_TYPE, SPRINT_DESIGN_DOC_TYPE}
        assert json.loads(docs[0].content)["schema_version"] == "1"


@pytest.mark.asyncio
async def test_sprint_execution_creates_next_sprint_after_previous_ships(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="SprintTwo", language="typescript")
        db.add(project)
        await db.flush()
        first = Feature(
            project_id=project.id,
            title="Todo Creation And Editing",
            description="Create and edit local todos",
            priority=100,
            acceptance_criteria=["Create a todo"],
        )
        second = Feature(
            project_id=project.id,
            title="Local Browser Persistence",
            description="Preserve todos after refresh",
            priority=90,
            dependencies=[first.id],
            acceptance_criteria=["Todos remain after refresh"],
        )
        db.add_all([first, second])
        await db.flush()

        sprint_one = await persist_sprint_execution_artifacts(db, project, [first])
        sprint_one["sprint"].phase = SprintPhase.SHIPPED
        sprint_one["sprint"].verification_status = "passed"
        first.status = FeatureStatus.DONE
        await db.flush()

        sprint_two = await persist_sprint_execution_artifacts(db, project, [second])

        sprints = list((await db.execute(select(Sprint).order_by(Sprint.created_at))).scalars().all())
        assert [sprint.label for sprint in sprints] == ["Sprint 1", "Sprint 2"]
        assert sprints[0].approved_feature_ids == [first.id]
        assert sprints[1].approved_feature_ids == [second.id]
        assert sprint_two["sprint"].label == "Sprint 2"
        assert second.status == FeatureStatus.SPRINT_PLANNED


@pytest.mark.asyncio
async def test_verify_task_runs_durable_feature_tests_before_agentic_verifier(
    test_db,
    tmp_path,
) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="VerifierFirst", language="typescript", repo_url=str(tmp_path))
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Due dates",
            description="Set optional due dates on todos",
            priority=100,
            acceptance_criteria=["Users can set and edit a due date"],
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify Due dates for shipping",
            description="Run final acceptance",
            status=TaskStatus.BUILD_VERIFY,
            depends_on={
                SPRINT_EXECUTION_KEY: {
                    "task_key": "browser-verification",
                    "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
                }
            },
        )
        db.add(task)
        await db.flush()
        task.workspace = Workspace(path=str(tmp_path), branch="main", is_worktree=False)
        await db.flush()

        order: list[str] = []
        orchestrator = Orchestrator(get_settings(), db)

        async def acceptance_tests(*args, **kwargs):
            order.append("feature-acceptance-tests")
            return True, "Feature acceptance tests PASS"

        async def build_verify(*args, **kwargs):
            order.append("build-verifier")
            return True, "build ok"

        orchestrator._run_agent = AsyncMock()
        orchestrator._record_feature_acceptance_tests = AsyncMock(side_effect=acceptance_tests)
        orchestrator._record_deterministic_build_verification = AsyncMock(side_effect=build_verify)
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        orchestrator._maybe_mark_sprint_shipped = AsyncMock()

        await orchestrator._phase_build_verify(task)

        assert order == ["feature-acceptance-tests", "build-verifier"]
        assert task.status == TaskStatus.DONE
        orchestrator._run_agent.assert_not_awaited()
        orchestrator._maybe_mark_sprint_shipped.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_existing_feature_tests_run_first_then_trigger_verifier_on_failure(
    test_db,
    tmp_path,
) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="VerifierRetry", language="typescript", repo_url=str(tmp_path))
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Due dates",
            description="Set optional due dates on todos",
            priority=100,
            acceptance_criteria=["Due dates persist after reload"],
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify Due dates for shipping",
            status=TaskStatus.BUILD_VERIFY,
            depends_on={
                SPRINT_EXECUTION_KEY: {
                    "task_key": "browser-verification",
                    "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
                }
            },
        )
        db.add(task)
        await db.flush()
        db.add(
            AgentRun(
                task_id=task.id,
                agent_name="feature-verifier",
                runtime_sdk="claude",
                status="completed",
            )
        )
        await db.flush()

        order: list[str] = []
        orchestrator = Orchestrator(get_settings(), db)

        async def acceptance_tests(*args, **kwargs):
            order.append("feature-acceptance-tests")
            if order.count("feature-acceptance-tests") == 1:
                return False, "Playwright failed"
            return True, "Feature acceptance tests PASS"

        async def run_agent(*args, **kwargs):
            order.append("feature-verifier")
            return RunResult(output_text='{"status":"pass","recommended_next_action":"rerun tests"}')

        orchestrator._record_feature_acceptance_tests = AsyncMock(side_effect=acceptance_tests)
        orchestrator._run_agent = AsyncMock(side_effect=run_agent)

        ok, output = await orchestrator._run_feature_acceptance_gate(task, str(tmp_path))

        assert ok is True
        assert output == "Feature acceptance tests PASS"
        assert order == [
            "feature-acceptance-tests",
            "feature-verifier",
            "feature-acceptance-tests",
        ]


@pytest.mark.asyncio
async def test_shipped_sprint_runs_deterministic_post_ship_optimization(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="OptimizeAfterShip", language="typescript")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Local Browser Persistence",
            description="Preserve todos after refresh",
            priority=100,
        )
        db.add(feature)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.VERIFY,
            approved_feature_ids=[feature.id],
        )
        db.add(sprint)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify feature",
            description="Final verifier",
            status=TaskStatus.DONE,
            depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": sprint.id}},
        )
        db.add(task)
        await db.flush()
        sprint.generated_task_ids = [task.id]
        await db.flush()

        orchestrator = Orchestrator(get_settings(), db)
        orchestrator._post_ship_observability_payload = lambda: {
            "observability_coverage": {
                "deterministic_recommendations": [
                    {
                        "code": "script_candidate_build_verify_script",
                        "severity": "high",
                        "recommendation": "Create deterministic proof command.",
                    }
                ],
                "telemetry_health": {},
            },
            "runtime_aggregates": {"runtime_recovery": {}, "tool_observability": {}, "totals": {}},
            "optimization_decision": {"next_action": "convert_repeated_operations_to_deterministic_scripts"},
            "runtime": {"selected_runtime_sdk": "claude_agent_sdk"},
        }
        orchestrator._run_deterministic_post_ship_optimization = AsyncMock(
            return_value={
                "status": "implemented",
                "agent_name": "optimization-agent",
                "runtime_sdk": "deterministic",
                "selected_recommendation": "script_candidate_build_verify_script",
                "commands": [
                    {"command": "builder script run build_verify --json", "result": "pass"}
                ],
            }
        )
        orchestrator._run_agent = AsyncMock()

        await orchestrator._maybe_mark_sprint_shipped(task)

        assert sprint.phase == SprintPhase.SHIPPED
        assert sprint.verification_status == "passed"
        assert feature.status == FeatureStatus.DONE
        orchestrator._run_deterministic_post_ship_optimization.assert_awaited_once()
        orchestrator._run_agent.assert_not_awaited()
        payload = sprint.verification_evidence["optimization_agent"]
        assert payload["status"] == "implemented"
        assert payload["runtime_sdk"] == "deterministic"
        assert payload["commands"][0]["command"] == "builder script run build_verify --json"
        assert payload["post_preflight_decision"]["model_backed_review_required"] is False


@pytest.mark.asyncio
async def test_post_ship_optimization_probe_summarizes_cli_evidence(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        orchestrator = Orchestrator(get_settings(), db)

        metrics = orchestrator._post_ship_probe_summary(
            "builder metrics show --json --full",
            0,
            {
                "optimization_decision": {
                    "next_action": "use_available_deterministic_script"
                },
                "optimization_summary": {"raw_token_total": 12345},
            },
        )
        logs = orchestrator._post_ship_probe_summary(
            "builder logs --info --compact --json",
            0,
            {"items": [{"event_type": "tool_result"}, {"event_type": "run_status"}]},
        )
        analysis = orchestrator._post_ship_probe_summary(
            "builder logs analyze --session <latest-session> --json",
            0,
            {
                "observability_coverage": {
                    "counts": {"tools": 4, "errors": 1},
                    "missing_signals": ["hook_span_timeline"],
                }
            },
        )

    assert metrics == "candidate=use_available_deterministic_script; raw_tokens=12345"
    assert logs == "compact_log_events=2"
    assert analysis == "tools=4; errors=1; missing=hook_span_timeline"


@pytest.mark.asyncio
async def test_optimization_recommendation_applied_requires_exact_command_evidence(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        orchestrator = Orchestrator(get_settings(), db)

        decisions = orchestrator._validated_optimization_recommendation_decisions(
            [
                {
                    "code": "script_candidate_build_verify_script",
                    "lifecycle_status": "applied",
                    "reason": "scripts/build.mjs exists",
                },
                {
                    "code": "deterministic_baseline_ready",
                    "lifecycle_status": "observed",
                    "reason": "info-only signal",
                },
            ],
            [{"command": "npm run build", "result": "pass"}],
        )

    assert decisions[0]["lifecycle_status"] == "deferred"
    assert "builder script run build_verify" in decisions[0]["reason"]
    assert decisions[1]["lifecycle_status"] == "observed"


@pytest.mark.asyncio
async def test_optimization_recommendation_keeps_applied_with_exact_command(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        orchestrator = Orchestrator(get_settings(), db)

        decisions = orchestrator._validated_optimization_recommendation_decisions(
            [
                {
                    "code": "script_candidate_change_evidence_collector",
                    "lifecycle_status": "applied",
                    "reason": "exact builder command passed",
                }
            ],
            [{"command": "builder script run change_evidence --json", "result": "pass"}],
        )

    assert decisions[0]["lifecycle_status"] == "applied"


@pytest.mark.asyncio
async def test_post_ship_optimization_refreshes_generated_app_sdk_guidance(
    test_db,
    tmp_path,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dev": "vite --host 127.0.0.1",
                    "test": "vitest run",
                    "lint": "eslint .",
                    "build": "vite build",
                },
                "dependencies": {"vite": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        render_project_runtime_guidance(
            project_name="Generated Todo",
            sdk="codex_sdk",
            mode="forward_engineering",
            language="unknown",
        ),
        encoding="utf-8",
    )

    _, factory = test_db
    async with factory() as db:
        project = Project(
            name="Generated Todo",
            repo_url=str(tmp_path),
            language="node",
        )
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Add due dates",
            description="Add due dates to todos",
            priority=100,
        )
        feature.project = project
        db.add(feature)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.SHIPPED,
            approved_feature_ids=[feature.id],
        )
        db.add(sprint)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify feature",
            description="Final verifier",
            status=TaskStatus.DONE,
            depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": sprint.id}},
        )
        task.feature = feature
        db.add(task)
        await db.flush()

        orchestrator = Orchestrator(get_settings(), db)
        orchestrator._post_ship_observability_payload = lambda: {
            "observability_coverage": {
                "deterministic_recommendations": [],
                "telemetry_health": {},
            },
            "optimization_decision": {"next_action": "no_script_candidate"},
        }
        orchestrator._post_ship_optimization_cli_probe = AsyncMock(
            return_value=[
                {"command": "builder metrics show --json --full", "result": "pass"},
                {"command": "builder logs --info --compact --json", "result": "pass"},
                {"command": "builder logs analyze --session <latest-session> --json", "result": "pass"},
            ]
        )
        orchestrator._run_agent = AsyncMock()

        await orchestrator._run_post_ship_optimization_agent(task, sprint, {})

        orchestrator._run_agent.assert_not_awaited()
        payload = sprint.verification_evidence["optimization_agent"]
        assert payload["status"] == "implemented"
        assert payload["runtime_sdk"] == "deterministic"
        assert payload["selected_recommendation"] == "app_runtime_guidance_refresh"
        assert payload["files_changed"] == ["AGENTS.md"]
        assert payload["commands"][-1]["command"] == "builder runtime guidance refresh"
        text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "- Test: `npm run test`" in text
        assert "- Build: `npm run build`" in text


def test_post_preflight_decision_routes_generated_app_residuals_to_model_review(
    tmp_path,
) -> None:
    orchestrator = Orchestrator(get_settings(), db=None)

    decision = orchestrator._post_ship_post_preflight_decision(
        tmp_path,
        {
            "status": "implemented",
            "selected_recommendation": "script_candidate_change_evidence_collector",
            "observability": {
                "app_runtime_guidance": {
                    "status": "updated",
                    "updated_files": ["AGENTS.md"],
                }
            },
        },
        [
            {
                "code": "script_candidate_change_evidence_collector",
                "severity": "high",
                "recommendation": "Use deterministic change evidence.",
            },
            {
                "code": "tool_permission_tightening",
                "severity": "medium",
                "recommendation": "Tighten tools.",
            },
        ],
    )

    assert decision["target_scope"] == "generated_app"
    assert decision["model_backed_review_required"] is True
    assert decision["deterministic_actions_applied"] == [
        "app_runtime_guidance_refresh",
        "script_candidate_change_evidence_collector",
    ]
    assert decision["residual_recommendations"][0]["code"] == "tool_permission_tightening"
    assert "apply, reject, or defer" in decision["reason"]
    assert "AGENTS.md" in decision["sdk_alignment"]["codex_sdk"]


def test_post_preflight_decision_defers_builder_owned_generated_app_residuals(
    tmp_path,
) -> None:
    orchestrator = Orchestrator(get_settings(), db=None)

    decision = orchestrator._post_ship_post_preflight_decision(
        tmp_path,
        {
            "status": "implemented",
            "selected_recommendation": "app_runtime_guidance_refresh",
            "observability": {
                "app_runtime_guidance": {
                    "status": "updated",
                    "updated_files": ["AGENTS.md"],
                }
            },
        },
        [
            {
                "code": "runtime_token_budget_over_target",
                "severity": "high",
                "recommendation": "Cut the largest runtime token driver.",
                "owner_lane": "builder_source",
                "next_actor": "builder",
            },
            {
                "code": "agent_chat_readonly_intent_budget",
                "severity": "medium",
                "recommendation": "Fix Builder Agent routing.",
                "owner_lane": "builder_source",
                "next_actor": "builder",
            },
        ],
    )

    assert decision["target_scope"] == "generated_app"
    assert decision["model_backed_review_required"] is False
    assert decision["residual_recommendations"] == []
    by_code = {
        item["code"]: item for item in decision["recommendation_decisions"]
    }
    assert by_code["runtime_token_budget_over_target"]["lifecycle_status"] == "deferred"
    assert by_code["agent_chat_readonly_intent_budget"]["lifecycle_status"] == "deferred"
    assert "generated-app optimization is resolved" in decision["reason"]


def test_post_preflight_decision_treats_current_guidance_as_resolved(tmp_path) -> None:
    orchestrator = Orchestrator(get_settings(), db=None)

    decision = orchestrator._post_ship_post_preflight_decision(
        tmp_path,
        {
            "status": "skipped",
            "selected_recommendation": "app_runtime_guidance_refresh",
            "observability": {
                "app_runtime_guidance": {
                    "status": "unchanged",
                    "updated_files": [],
                }
            },
        },
        [],
    )

    assert decision["model_backed_review_required"] is False
    assert "generated-app optimization is resolved" in decision["reason"]


def test_post_preflight_decision_runs_model_review_for_builder_source_residuals(
    tmp_path,
) -> None:
    (tmp_path / "src" / "autonomous_agent_builder").mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    orchestrator = Orchestrator(get_settings(), db=None)

    decision = orchestrator._post_ship_post_preflight_decision(
        tmp_path,
        {
            "status": "implemented",
            "selected_recommendation": "script_candidate_build_verify_script",
        },
        [
            {
                "code": "script_candidate_build_verify_script",
                "severity": "high",
                "recommendation": "Use deterministic build evidence.",
            },
            {
                "code": "phase_prompt_compaction",
                "severity": "medium",
                "recommendation": "Compact phase prompt.",
            },
        ],
    )

    assert decision["target_scope"] == "builder_source"
    assert decision["model_backed_review_required"] is True
    assert decision["residual_recommendations"][0]["code"] == "phase_prompt_compaction"
    assert "CLAUDE.md" in decision["sdk_alignment"]["claude_agent_sdk"]


@pytest.mark.asyncio
async def test_sprint_shipping_blocks_when_materialized_checkout_build_fails(
    test_db,
    tmp_path,
) -> None:
    repo = tmp_path / "generated-app"
    repo.mkdir()
    _, factory = test_db
    async with factory() as db:
        project = Project(name="FinalCheckout", language="typescript", repo_url=str(repo))
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Todo app",
            description="Generated app",
            priority=100,
        )
        feature.project = project
        db.add(feature)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.VERIFY,
            approved_feature_ids=[feature.id],
        )
        db.add(sprint)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify generated app",
            description="Final verifier",
            status=TaskStatus.DONE,
            depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": sprint.id}},
        )
        task.feature = feature
        db.add(task)
        await db.flush()
        sprint.generated_task_ids = [task.id]
        await db.flush()

        orchestrator = Orchestrator(get_settings(), db)
        orchestrator._record_deterministic_build_verification = AsyncMock(
            return_value=(False, "npm run build FAIL")
        )
        orchestrator._run_post_ship_optimization_agent = AsyncMock()

        await orchestrator._maybe_mark_sprint_shipped(task)

        assert sprint.phase == SprintPhase.BLOCKED
        assert sprint.verification_status == "blocked"
        assert task.status == TaskStatus.BLOCKED
        assert "final_checkout_build_failed" in (task.blocked_reason or "")
        evidence = sprint.verification_evidence or {}
        assert evidence["materialized_checkout_verification"]["status"] == "failed"
        assert "npm run build FAIL" in evidence["sprint_merge_error"]
        orchestrator._record_deterministic_build_verification.assert_awaited_once_with(
            task,
            str(repo),
        )
        orchestrator._run_post_ship_optimization_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_ship_optimization_does_not_repeat_after_implemented(test_db) -> None:
    _, factory = test_db
    async with factory() as db:
        project = Project(name="AlreadyOptimized", repo_url="/tmp/generated", language="node")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Add due dates",
            description="Add due dates",
            priority=100,
        )
        feature.project = project
        db.add(feature)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.SHIPPED,
            verification_evidence={
                "optimization_agent": {
                    "status": "implemented",
                    "selected_recommendation": "app_runtime_guidance_refresh",
                }
            },
        )
        db.add(sprint)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify feature",
            description="Final verifier",
            status=TaskStatus.DONE,
            depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": sprint.id}},
        )
        task.feature = feature
        db.add(task)
        await db.flush()

        orchestrator = Orchestrator(get_settings(), db)
        orchestrator._post_ship_observability_payload = AsyncMock()
        orchestrator._run_agent = AsyncMock()

        await orchestrator._run_post_ship_optimization_agent(task, sprint, {})

        orchestrator._post_ship_observability_payload.assert_not_called()
        orchestrator._run_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_sprint_execution_uses_selected_codex_model(test_db, monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_SDK", "codex_sdk")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_MODEL", "gpt-5.5")

    _, factory = test_db
    async with factory() as db:
        project = Project(name="ShipBoard", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Feature Ideas",
            description="Persist ideas in SQLite",
            priority=100,
            acceptance_criteria=["Ideas are persisted"],
        )
        db.add(feature)
        await db.flush()
        result = await db.execute(
            select(Feature)
            .options(selectinload(Feature.tasks))
            .where(Feature.project_id == project.id)
        )
        features = list(result.scalars().all())

        artifacts = await persist_sprint_execution_artifacts(db, project, features)

        assert artifacts["plan"]["planning_model"] == "gpt-5.5"
        assert artifacts["plan"]["runtime_decision_summary"]["runtime"] == "codex_sdk"
        assert artifacts["plan"]["runtime_tool_strategy"]["runtime_sdk"] == "codex_sdk"
        assert artifacts["plan"]["runtime_tool_strategy"]["telemetry"] == (
            "thread/tokenUsage/updated and turn lifecycle events"
        )
        assert artifacts["plan"]["batches"][0]["recommended_model"] == "gpt-5.5"
        task = (await db.execute(select(Task).order_by(Task.created_at))).scalars().first()
        assert task is not None
        assert task.depends_on[SPRINT_EXECUTION_KEY]["recommended_model"] == "gpt-5.5"
        assert task.depends_on[SPRINT_EXECUTION_KEY]["runtime_decision"]["selected_runtime"] == "codex_sdk"
        assert task.depends_on[SPRINT_EXECUTION_KEY]["skip_task_design"] is True


@pytest.mark.asyncio
async def test_orchestrator_agent_run_uses_project_runtime_settings(test_db, tmp_path, monkeypatch) -> None:
    Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n',
        encoding="utf-8",
    )
    captured: dict[str, str] = {}

    class FakeRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

        async def run(self, *args, **kwargs):
            on_chunk = kwargs.get("on_chunk")
            if on_chunk is not None:
                maybe_await = on_chunk("planning live")
                if hasattr(maybe_await, "__await__"):
                    await maybe_await
            on_tool_event = kwargs.get("on_tool_event")
            if on_tool_event is not None:
                await on_tool_event(
                    event_type="thinking",
                    tool_name="reasoning",
                    tool_input={},
                    output_preview="Choosing the smallest safe implementation.",
                )
                await on_tool_event(
                    {
                        "tool_name": "mcp__workspace__run_command",
                        "tool_input": {"argv": ["npm", "test"]},
                        "tool_response": "40 tests passed",
                        "tool_use_id": "toolu-test",
                    }
                )
            result = RunResult(
                session_id="codex-session",
                tokens_input=10,
                tokens_output=2,
                num_turns=1,
                output_text="planned",
                observability={"runtime_sdk": "codex_sdk"},
            )
            result.raw_events = []
            return result

    def fake_create_runtime(**kwargs):
        captured.update({key: str(value) for key, value in kwargs.items() if value is not None})
        return FakeRuntime()

    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.create_runtime",
        fake_create_runtime,
    )

    _, factory = test_db
    async with factory() as db:
        project = Project(name="ProjectRuntime", language="python", repo_url=str(tmp_path))
        db.add(project)
        await db.flush()
        feature = Feature(project_id=project.id, title="Runtime", description="Use selected runtime", priority=1)
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Plan runtime",
            description="Plan runtime",
            status=TaskStatus.PLANNING,
        )
        db.add(task)
        await db.flush()

        orchestrator = Orchestrator(get_settings(), db)
        result = await orchestrator._run_agent(
            task,
            "planner",
            {
                "feature_description": "Use the selected runtime",
                "project_name": project.name,
                "language": project.language,
            },
        )

        assert result.session_id == "codex-session"
        assert captured["sdk"] == "codex_sdk"
        assert captured["provider"] == "codex_subscription"
        assert captured["model"] == "gpt-5.5"
        added_runs = (
            await db.execute(select(AgentRun).where(AgentRun.task_id == task.id))
        ).scalars().all()
        assert added_runs[-1].runtime_sdk == "codex_sdk"
        assert added_runs[-1].provider == "codex_subscription"
        assert added_runs[-1].model == "gpt-5.5"
        events = (
            await db.execute(select(AgentRunEvent).where(AgentRunEvent.run_id == added_runs[-1].id))
        ).scalars().all()
        event_types = [event.event_type for event in events]
        assert "agent_output" in event_types
        assert "thinking" in event_types
        tool_event = next(event for event in events if event.tool_name == "mcp__workspace__run_command")
        assert tool_event.event_type == "tool_use"
        assert tool_event.tool_input["tool_use_id"] == "toolu-test"
        assert "40 tests passed" in tool_event.output_preview


def test_build_verifier_failure_detects_markdown_failures() -> None:
    failure = build_verifier_failure("`npm run test` — **FAIL** (1/41)")

    assert failure == "build_verification_failed: `npm run test` — **FAIL** (1/41)"


def test_task_templates_prefer_model_proposed_decomposition() -> None:
    """IMP-027c: when the chat intake agent sizes a trivial item as ONE task, the
    planner must emit exactly that — not the keyword-selected 5/3-task template.
    The description contains 'external' (the substring that wrongly escalated a
    static label to the high-risk 5-task set before this fix)."""
    from autonomous_agent_builder.services.sprint_execution import (
        _model_proposed_templates,
        _risk_flags,
        _task_templates_for_feature,
    )

    trivial = Feature(
        title="Home screen footer version label",
        description="Render a minimal 'v0.1' label in the footer; not tied to any external source.",
        proposed_tasks=[{"title": "Add v0.1 footer label", "purpose": "show the static version"}],
    )
    templates = _task_templates_for_feature(trivial, _risk_flags(trivial))
    assert len(templates) == 1
    assert templates[0]["title"] == "Add v0.1 footer label"
    assert _model_proposed_templates(trivial)[0]["purpose"] == "show the static version"


def test_task_templates_fall_back_to_deterministic_when_no_proposal() -> None:
    """No model proposal → planner keeps its deterministic risk-based templates."""
    from autonomous_agent_builder.services.sprint_execution import (
        _LOW_RISK_SPRINT_TASK_TEMPLATES,
        _SPRINT_TASK_TEMPLATES,
        _risk_flags,
        _task_templates_for_feature,
    )

    plain = Feature(title="Stats dashboard", description="charts and counters", proposed_tasks=[])
    assert _task_templates_for_feature(plain, _risk_flags(plain)) is _LOW_RISK_SPRINT_TASK_TEMPLATES
    risky = Feature(
        title="Login with OAuth",
        description="OAuth login and session handling",
        proposed_tasks=[],
    )
    assert _task_templates_for_feature(risky, _risk_flags(risky)) is _SPRINT_TASK_TEMPLATES


@pytest.mark.asyncio
async def test_proposed_tasks_produce_one_task_for_trivial_item(test_db) -> None:
    """End-to-end IMP-027c: a trivial item with a single model-proposed task creates
    exactly one Task with the model's literal title (no domain-model/persistence/verify
    explosion)."""
    _, factory = test_db
    async with factory() as db:
        project = Project(name="LabelApp", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Home screen footer version label",
            description="Render a minimal 'v0.1' label in the footer; not tied to any external source.",
            priority=100,
            acceptance_criteria=["Footer shows v0.1"],
            proposed_tasks=[
                {"title": "Add v0.1 footer label to home screen", "purpose": "show static version"}
            ],
        )
        db.add(feature)
        await db.flush()
        result = await db.execute(
            select(Feature)
            .options(selectinload(Feature.tasks))
            .where(Feature.project_id == project.id)
        )
        features = list(result.scalars().all())

        await persist_sprint_execution_artifacts(db, project, features)

        tasks = list((await db.execute(select(Task))).scalars().all())
        assert len(tasks) == 1
        assert tasks[0].title == "Add v0.1 footer label to home screen"
