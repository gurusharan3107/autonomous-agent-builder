"""Tests for documentation refresh gate support helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.db.models import Task
from autonomous_agent_builder.orchestrator.documentation_refresh_gate import (
    documentation_gate_message,
    record_documentation_bridge_run,
    resolve_documentation_project_root,
)


def test_resolve_documentation_project_root_prefers_existing_project_repo(tmp_path) -> None:
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project_root.mkdir()
    workspace.mkdir()
    task = SimpleNamespace(feature=SimpleNamespace(project=SimpleNamespace(repo_url=str(project_root))))

    assert resolve_documentation_project_root(task, str(workspace)) == project_root.resolve()


def test_documentation_gate_message_prefers_remaining_gap() -> None:
    message = documentation_gate_message(
        {
            "remaining_gap": "maintained docs still stale",
            "summary": "fallback summary",
        }
    )

    assert message == "documentation refresh gate blocked: maintained docs still stale"


@pytest.mark.asyncio
async def test_record_documentation_bridge_run_persists_bridge_run() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    task = Task(id="task-1", title="Task", description="Do work")

    await record_documentation_bridge_run(
        db,
        task,
        {
            "bridge_invoked": True,
            "status": "updated_and_verified",
            "summary": "docs updated",
            "run": {
                "session_id": "sess-docs",
                "runtime_sdk": "claude_agent_sdk",
                "provider": "anthropic",
                "model": "claude",
                "tokens_input": 11,
                "tokens_output": 7,
            },
        },
    )

    db.add.assert_called_once()
    run = db.add.call_args.args[0]
    assert run.task_id == "task-1"
    assert run.agent_name == "documentation-bridge"
    assert run.session_id == "sess-docs"
    assert run.status == "completed"
    assert run.output_text == "docs updated"
    db.flush.assert_awaited_once()
