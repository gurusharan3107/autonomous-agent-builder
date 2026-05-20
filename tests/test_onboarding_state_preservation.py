from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from autonomous_agent_builder import onboarding
from autonomous_agent_builder.db.models import Project, Sprint
from autonomous_agent_builder.services.readiness import READY_STATE


def _write_completed_onboarding_state(project_root):
    state = onboarding.default_onboarding_state(project_root)
    state["onboarding_mode"] = "forward_engineering"
    state["current_phase"] = "ready"
    state["ready"] = False
    for phase in state["phases"]:
        if phase["id"] == "ready":
            phase["status"] = "passed"
            phase["result"] = {"ready": True, "readiness_state": READY_STATE}
    onboarding.save_onboarding_state(project_root, state)
    return state


def _write_operational_sqlite_db(project_root):
    builder_dir = project_root / ".agent-builder"
    builder_dir.mkdir(parents=True, exist_ok=True)
    db_path = builder_dir / "agent_builder.db"
    with sqlite3.connect(db_path) as con:
        con.execute("create table projects (id text primary key)")
        con.execute("insert into projects (id) values ('existing-project')")
    return db_path


@pytest.mark.asyncio
async def test_completed_onboarding_runtime_guidance_repair_does_not_rerun_pipeline(
    monkeypatch,
    tmp_path,
):
    _write_completed_onboarding_state(tmp_path)
    _write_operational_sqlite_db(tmp_path)

    async def fail_preflight(*_args, **_kwargs):
        pytest.fail("completed onboarding repair must not run onboarding preflight")

    async def fail_pipeline(*_args, **_kwargs):
        pytest.fail("completed onboarding repair must not rerun the onboarding pipeline")

    async def noop_publish(*_args, **_kwargs):
        return None

    def fail_create_task(coro):
        coro.close()
        pytest.fail("completed onboarding repair must not schedule the pipeline")

    def fake_assess(*_args, **_kwargs):
        return {"state": READY_STATE, "blocking_reasons": [], "next": []}

    monkeypatch.setattr(onboarding, "_ensure_project_runtime_guidance", lambda *_args: None)
    monkeypatch.setattr(onboarding, "_preflight_onboarding_claude", fail_preflight)
    monkeypatch.setattr(onboarding, "_run_pipeline", fail_pipeline)
    monkeypatch.setattr(onboarding, "publish_onboarding_snapshot", noop_publish)
    monkeypatch.setattr(onboarding, "assess_readiness", fake_assess)
    monkeypatch.setattr(onboarding.asyncio, "create_task", fail_create_task)

    result = await onboarding.start_onboarding(tmp_path, session_factory=object())

    assert result["ready"] is True
    assert result["current_phase"] == "ready"
    assert result["errors"] == []
    persisted = onboarding.load_onboarding_state(tmp_path)
    assert persisted["ready"] is True


@pytest.mark.asyncio
async def test_clear_operational_state_removes_sprints(test_db):
    _, session_factory = test_db
    async with session_factory() as db:
        project = Project(name="existing-project", language="python")
        db.add(project)
        await db.flush()
        db.add(Sprint(project_id=project.id, label="Sprint 1"))
        await db.commit()

        await onboarding._clear_operational_state(db)
        await db.commit()

        projects = list((await db.execute(select(Project))).scalars().all())
        sprints = list((await db.execute(select(Sprint))).scalars().all())

    assert projects == []
    assert sprints == []
