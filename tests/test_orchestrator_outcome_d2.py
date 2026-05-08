"""Phase D2 — orchestrator routes feature-verifier through MA Outcomes.

Verifies that `_run_feature_acceptance_gate` dispatches to the
`run_outcome` path when the project's resolved runtime is `claude_managed`,
maps a `satisfied` verdict to gate-pass, and a non-satisfied verdict to
gate-fail with the verdict surfaced in the message.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import Feature, Task, TaskStatus
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator


def _make_feature() -> Feature:
    f = Feature(
        id="feat-1",
        project_id="proj-1",
        title="Add export button",
        description="Users can export the current view as CSV",
    )
    f.acceptance_criteria = [
        "Clicking the button downloads a .csv file",
        "Header row matches the visible column titles",
    ]
    return f


def _make_task() -> Task:
    task = Task(
        id="task-1",
        feature_id="feat-1",
        title="Sprint feature verification",
        description="",
        status=TaskStatus.QUALITY_GATES,
    )
    project = MagicMock()
    project.name = "demo"
    project.repo_url = "/tmp/some-managed-repo"
    feature = _make_feature()
    feature.project = project
    task.feature = feature
    task.workspace = MagicMock(path="/tmp/some-managed-repo")
    task.agent_runs = []
    task.approval_gates = []
    task.depends_on = None
    return task


@pytest.fixture
def orchestrator():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return Orchestrator(get_settings(), db)


@pytest.mark.asyncio
async def test_feature_verifier_uses_run_outcome_on_claude_managed(
    orchestrator, monkeypatch
):
    """When sdk=claude_managed, `_run_feature_verifier_outcome` is called."""

    async def fake_predicate(self, task: Task) -> bool:  # noqa: ARG001
        return True

    captured: dict[str, object] = {}

    async def fake_outcome(
        self, task: Task, feature: Feature, workspace_path: str
    ) -> tuple[bool, str]:
        captured["task_id"] = task.id
        captured["feature_title"] = feature.title
        captured["workspace_path"] = workspace_path
        return True, ""

    async def fake_record(self, task, workspace_path, feature):  # noqa: ARG001
        return True, "tests passed"

    async def fake_is_sprint(self, task):  # noqa: ARG001
        return True

    async def fake_has_run(self, task, name):  # noqa: ARG001
        return False

    async def fake_get(model, _id):  # noqa: ARG001
        return _make_feature()

    monkeypatch.setattr(
        Orchestrator, "_task_runtime_is_claude_managed", fake_predicate
    )
    monkeypatch.setattr(
        Orchestrator, "_run_feature_verifier_outcome", fake_outcome
    )
    monkeypatch.setattr(
        Orchestrator, "_record_feature_acceptance_tests", fake_record
    )
    monkeypatch.setattr(
        Orchestrator, "_is_sprint_feature_verification_task", lambda self, t: True
    )
    monkeypatch.setattr(
        Orchestrator, "_has_completed_agent_run", fake_has_run
    )
    orchestrator.db.get = fake_get

    task = _make_task()
    ok, message = await orchestrator._run_feature_acceptance_gate(
        task, "/tmp/some-managed-repo"
    )

    assert ok is True
    assert message == "tests passed"
    assert captured["feature_title"] == "Add export button"
    assert captured["workspace_path"] == "/tmp/some-managed-repo"


@pytest.mark.asyncio
async def test_feature_verifier_outcome_maps_failed_verdict(
    orchestrator, monkeypatch
):
    """A non-satisfied verdict propagates as gate failure with explanation."""

    async def fake_predicate(self, task):  # noqa: ARG001
        return True

    async def fake_outcome(self, task, feature, workspace_path):  # noqa: ARG001
        return False, "feature_acceptance_failed: managed_agents outcome verdict=failed"

    async def fake_record(self, task, workspace_path, feature):  # noqa: ARG001
        raise AssertionError("should not run when outcome failed")

    async def fake_has_run(self, task, name):  # noqa: ARG001
        return False

    async def fake_get(model, _id):  # noqa: ARG001
        return _make_feature()

    monkeypatch.setattr(
        Orchestrator, "_task_runtime_is_claude_managed", fake_predicate
    )
    monkeypatch.setattr(
        Orchestrator, "_run_feature_verifier_outcome", fake_outcome
    )
    monkeypatch.setattr(
        Orchestrator, "_record_feature_acceptance_tests", fake_record
    )
    monkeypatch.setattr(
        Orchestrator, "_is_sprint_feature_verification_task", lambda self, t: True
    )
    monkeypatch.setattr(
        Orchestrator, "_has_completed_agent_run", fake_has_run
    )
    orchestrator.db.get = fake_get

    task = _make_task()
    ok, message = await orchestrator._run_feature_acceptance_gate(
        task, "/tmp/some-managed-repo"
    )

    assert ok is False
    assert "feature_acceptance_failed" in message
    assert "verdict=failed" in message


@pytest.mark.asyncio
async def test_run_feature_verifier_outcome_writes_gate_result(monkeypatch):
    """The helper persists an AgentRun and a GateResult with the verdict."""
    from autonomous_agent_builder.db.models import AgentRun, GateResult
    from autonomous_agent_builder.quality_gates.base import GateStatus

    db = AsyncMock()
    added: list[object] = []
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    orch = Orchestrator(get_settings(), db)

    # Stub realtime publisher to no-op (no FastAPI app stack in tests).
    async def _noop(self):  # noqa: ARG001
        return None

    monkeypatch.setattr(Orchestrator, "_publish_realtime_board_snapshot", _noop)

    # Stub project-root existence to skip the real .env read; runtime config
    # comes from a fake create_runtime that returns an object exposing
    # `run_outcome` as a coroutine returning a satisfied verdict.
    fake_runtime = SimpleNamespace()

    async def _fake_run_outcome(**_kwargs):
        rr = RunResult(
            session_id="sesn_x",
            cost_usd=0.0,
            tokens_input=10,
            tokens_output=5,
            tokens_cached=0,
            num_turns=1,
            duration_ms=42,
            stop_reason="outcome_satisfied",
            observability={
                "managed_agents": {
                    "outcome": {
                        "result": "satisfied",
                        "explanation": "all criteria met",
                        "iteration": 1,
                    },
                    "outcome_iterations": 1,
                }
            },
        )
        rr.output_text = "ok"
        return rr

    fake_runtime.run_outcome = _fake_run_outcome

    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.create_runtime",
        lambda **_kw: fake_runtime,
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.resolve_project_runtime_config",
        lambda _root: {
            "sdk": "claude_managed",
            "provider": "anthropic_managed",
            "model": "claude-opus-4-7",
        },
    )
    # Skip the project_root.exists() short-circuit by patching Path.exists.
    monkeypatch.setattr(
        "autonomous_agent_builder.orchestrator.orchestrator.Path.exists",
        lambda self: True,
    )

    task = _make_task()
    feature = task.feature  # already populated
    ok, message = await orch._run_feature_verifier_outcome(
        task, feature, "/tmp/some-managed-repo"
    )

    assert ok is True
    assert message == ""

    agent_runs = [o for o in added if isinstance(o, AgentRun)]
    gate_results = [o for o in added if isinstance(o, GateResult)]
    assert len(agent_runs) == 1
    assert agent_runs[0].runtime_sdk == "claude_managed"
    assert agent_runs[0].agent_name == "feature-verifier"
    assert len(gate_results) == 1
    assert gate_results[0].gate_name == "feature-verifier-outcome"
    assert gate_results[0].status == GateStatus.PASS
    assert gate_results[0].evidence["verdict"] == "satisfied"
    assert gate_results[0].evidence["iterations"] == 1
