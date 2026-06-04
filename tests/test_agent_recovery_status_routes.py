"""Agent recovery status and blocked-evidence route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatEvent,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_recovery_status_check_does_not_auto_dispatch_sprint_task(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Active sprint work",
            description="A dispatchable task exists in the sprint.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        blocked_task = Task(
            feature_id=feature.id,
            title="Verify Deterministic tests and build script for shipping",
            description="Blocked task the operator is asking about.",
            status=TaskStatus.CAPABILITY_LIMIT,
            capability_limit_reason="SDK limit: provider_limit",
        )
        pending_task = Task(
            feature_id=feature.id,
            title="Implement a follow-up notification polish task",
            description="A pending task should not be dispatched by a status check.",
            status=TaskStatus.PENDING,
        )
        db.add(blocked_task)
        db.add(pending_task)
        await db.flush()
        db.add(
            Sprint(
                project_id=project.id,
                label="Sprint 1",
                approved_feature_ids=[feature.id],
                generated_task_ids=[pending_task.id, blocked_task.id],
            )
        )
        await db.commit()

    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, *args, **kwargs):
            runtime_prompts.append(prompt)
            return RunResult(
                session_id="sdk-session-recovery-status",
                cost_usd=0.01,
                tokens_input=5,
                tokens_output=8,
                num_turns=1,
                output_text=(
                    "Board status from Builder source of truth: blocked 1. "
                    "Latest limit: `capability_limit`. SDK limit: provider_limit. "
                    "No approval or prepared action is pending right now. "
                    "I did not create sprint scope, dispatch a task, recover a task, "
                    "or mark work done."
                ),
                stop_reason="end_turn",
            )

    async def fake_run_phase(self, **kwargs):
        runtime_prompts.append(str(kwargs["prompt"]))
        return RunResult(
            session_id="sdk-session-recovery-status",
            cost_usd=0.01,
            tokens_input=5,
            tokens_output=8,
            num_turns=1,
            output_text=(
                "Board status from Builder source of truth: blocked 1. "
                "Latest limit: `capability_limit`. SDK limit: provider_limit. "
                "No approval or prepared action is pending right now. "
                "I did not create sprint scope, dispatch a task, recover a task, "
                "or mark work done."
            ),
            stop_reason="end_turn",
        )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())
    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": (
                    "What is the current status of the blocked task "
                    "Verify Deterministic tests and build script for shipping?"
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Board status from Builder source of truth"
            in item["payload"].get("content", ""),
        )

    async with factory() as db:
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason")
            for event in status_result.scalars().all()
        ]

    content = assistant_item["payload"]["content"]
    assert "blocked 1" in content
    assert "`capability_limit`" in content
    assert "SDK limit: provider_limit" in content
    assert "No approval or prepared action is pending right now." in content
    assert "I did not create sprint scope, dispatch a task, recover a task" in content
    assert dispatched == []
    assert runtime_prompts
    assert "What is the current status of the blocked task" in runtime_prompts[0]
    assert "end_turn" in stop_reasons
    assert "deterministic_status_check" not in stop_reasons
    assert "task_dispatched" not in stop_reasons

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "runtime_output", "expected_content", "prompt_needle"),
    [
        (
            (
                "Investigate the blocked task \"Verify Deterministic tests and build script "
                "for shipping\" using Builder evidence. Tell me the exact failing command "
                "or gate, the likely owner, and the next safe recovery step. Do not modify files."
            ),
            (
                "Failing gate: builder script run build_verify. "
                "Owner: generated app build configuration. "
                "Next safe step: inspect build output without modifying files."
            ),
            "Failing gate: builder script run build_verify",
            "exact failing command or gate",
        ),
        (
            (
                "Using Builder evidence only, are the current deterministic checks and build "
                "for the blocked task \"Verify Deterministic tests and build script for "
                "shipping\" shippable right now? Tell me the exact verifier evidence you used "
                "and answer BLOCKED, NEEDS_RECOVERY, or SHIPPABLE. Do not modify files or mark "
                "anything done."
            ),
            (
                "NEEDS_RECOVERY. Verifier evidence: builder script run build_verify reported "
                "npm run build FAIL, so the blocked verification task is not shippable."
            ),
            "NEEDS_RECOVERY. Verifier evidence",
            "exact verifier evidence",
        ),
        (
            (
                "Give me a bounded recovery plan for the blocked task \"Verify Deterministic "
                "tests and build script for shipping\" using Builder evidence only. Do not "
                "modify files, dispatch work, mark anything done, or create approvals. I want "
                "the smallest safe operator plan: classify the issue, list the exact evidence, "
                "list the proposed steps, and say what approval would be needed before execution."
            ),
            (
                "Recovery plan: inspect the failed verifier evidence, add the missing script "
                "only after approval, then rerun deterministic validation."
            ),
            "Recovery plan: inspect the failed verifier evidence",
            "bounded recovery plan",
        ),
    ],
)
async def test_blocked_task_evidence_requests_use_agent_lane_instead_of_status_shortcut(
    monkeypatch,
    test_db,
    tmp_path,
    message,
    runtime_output,
    expected_content,
    prompt_needle,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Active sprint work",
            description="A blocked verification task exists in the sprint.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        db.add(
            Task(
                feature_id=feature.id,
                title="Verify Deterministic tests and build script for shipping",
                description="Blocked task the operator is asking about.",
                status=TaskStatus.CAPABILITY_LIMIT,
                capability_limit_reason="SDK limit: provider_limit",
            )
        )
        await db.commit()

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, *args, **kwargs):
            runtime_prompts.append(prompt)
            return RunResult(
                session_id="sdk-diagnosis",
                cost_usd=0.01,
                tokens_input=4,
                tokens_output=4,
                num_turns=1,
                output_text=runtime_output,
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": message},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: expected_content in item["payload"].get("content", ""),
        )

    async with factory() as db:
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason")
            for event in status_result.scalars().all()
        ]

    assert runtime_prompts
    assert prompt_needle in runtime_prompts[0]
    assert "Board status from Builder source of truth" not in assistant_item["payload"]["content"]
    assert "end_turn" in stop_reasons
    assert "deterministic_status_check" not in stop_reasons
