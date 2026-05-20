from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from autonomous_agent_builder.api.routes import dashboard_api


def _task(*, status: str = "quality_gates", blocked_reason: str = "", runs=None):
    feature = SimpleNamespace(
        id="feature-01",
        title="Todo CRUD",
        description="Add, edit, delete todos.",
        priority=100,
        item_type="feature",
        acceptance_criteria=[],
        dependencies=[],
    )
    return SimpleNamespace(
        id="task-01",
        title="Cover persistence and tests",
        description="",
        status=status,
        phase="verification",
        feature=feature,
        sprint_execution={},
        depends_on={},
        agent_runs=runs or [],
        approval_gates=[],
        blocked_reason=blocked_reason,
        updated_at=None,
    )


def _run(runtime_sdk: str, *, status: str = "completed", seconds: int = 0):
    return SimpleNamespace(
        id=f"run-{runtime_sdk}-{seconds}",
        agent_name="code-gen" if runtime_sdk != "deterministic" else "build-verifier",
        runtime_sdk=runtime_sdk,
        provider="claude_agent_sdk" if runtime_sdk == "claude" else "builder",
        model="sonnet" if runtime_sdk == "claude" else "",
        effort="medium",
        cost_usd=0.25 if runtime_sdk == "claude" else 0,
        estimated_cost_usd=0,
        tokens_input=10 if runtime_sdk == "claude" else 0,
        tokens_output=20 if runtime_sdk == "claude" else 0,
        tokens_cached=0,
        num_turns=3 if runtime_sdk == "claude" else 0,
        duration_ms=1000,
        status=status,
        error=None,
        started_at=datetime(2026, 5, 9, tzinfo=UTC) + timedelta(seconds=seconds),
        completed_at=datetime(2026, 5, 9, tzinfo=UTC) + timedelta(seconds=seconds + 1),
        observability=None,
        diff_summary={},
        events=[],
    )


def test_quality_gate_failure_routes_to_review_not_active_or_pending():
    task = _task(
        blocked_reason="Quality gate failures: code_quality: fail Error: NO_LINT_SCRIPT",
        runs=[_run("claude", status="completed")],
    )

    assert dashboard_api._needs_review_lane_task(task)
    assert not dashboard_api._is_active_lane_task(task)
    assert not dashboard_api._is_pending_lane_task(task)


def test_task_card_summary_prefers_agent_runtime_over_deterministic_followup():
    task = _task(
        status="done",
        runs=[
            _run("claude", seconds=0),
            _run("deterministic", seconds=10),
        ],
    )

    item = dashboard_api._build_task_item(task)

    assert item.runtime_sdk == "claude"
    assert item.agent_name == "code-gen"
    assert item.latest_run_status == "completed"
