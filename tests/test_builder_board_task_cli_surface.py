"""Tests for builder Board and task CLI surfaces."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli import local_fallback as local_fallback_module
from autonomous_agent_builder.cli.client import BuilderConnectivityError
from autonomous_agent_builder.cli.commands import board as board_module
from autonomous_agent_builder.cli.commands import task as task_module
from autonomous_agent_builder.cli.main import app
from tests.builder_cli_surface_helpers import PathClient as _PathClient

runner = CliRunner()


def test_board_show_json_includes_counts_and_next_step(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: {
            "pending": [{"id": "task-1", "title": "Plan task", "status": "pending"}],
            "active": [{"id": "task-2", "title": "Build task", "status": "active"}],
            "review": [],
            "done": [],
            "blocked": [],
        },
    )

    result = runner.invoke(app, ["board", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["counts"]["pending"] == 1
    assert payload["counts"]["active"] == 1
    assert payload["next_step"] == "builder backlog task status <task-id> --json"


def test_board_show_json_compacts_raw_task_and_sprint_fields(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    noisy_task = {
        "id": "task-1",
        "title": "Plan task",
        "description": "raw task description " * 200,
        "status": "pending",
        "phase": "planning",
        "feature_id": "feature-1",
        "feature_title": "Feature",
        "feature_description": "raw feature description " * 200,
        "feature_item_type": "feature",
        "acceptance_criteria": ["criteria " * 200],
        "dependencies": ["dep-1"],
        "sprint_execution": {"raw": "execution evidence " * 300},
        "observability": {"raw": "observability evidence " * 300},
        "agent_runs": [{"raw": "run evidence " * 300}],
        "activity_timeline": [{"raw": "timeline evidence " * 300}],
        "agent_name": "implementation",
        "runtime_sdk": "claude",
        "model": "sonnet",
        "effort": "high",
        "cost_usd": 1.25,
        "tokens_input": 1000,
        "tokens_output": 250,
        "blocked_reason": "blocked reason " * 60,
    }
    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: {
            "pending": [noisy_task],
            "active": [],
            "review": [],
            "done": [],
            "blocked": [],
            "counts": {"pending": 1, "active": 0, "review": 0, "done": 0, "blocked": 0},
            "current_sprint": {
                "sprint_id": "sprint-1",
                "label": "Sprint 1",
                "active_phase": "planning",
                "included_items": [
                    {
                        "id": "item-1",
                        "title": "Item",
                        "status": "planned",
                        "description": "raw item description " * 200,
                        "sprint_execution": {"raw": "execution evidence " * 300},
                    }
                ],
            },
        },
    )

    result = runner.invoke(app, ["board", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["pending"][0]["id"] == "task-1"
    assert "description" not in payload["pending"][0]
    assert "acceptance_criteria" not in payload["pending"][0]
    assert "sprint_execution" not in payload["pending"][0]
    assert "observability" not in payload["pending"][0]
    assert "agent_runs" not in payload["pending"][0]
    assert "activity_timeline" not in payload["pending"][0]
    assert "description" not in payload["current_sprint"]["included_items"][0]
    assert (
        payload["raw_evidence"]["full_payload_command"]
        == "builder board show --json --full --limit 5"
    )
    assert payload["token_estimate"] < 1000


def test_board_show_json_full_preserves_raw_task_fields(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: {
            "pending": [
                {
                    "id": "task-1",
                    "title": "Plan task",
                    "description": "raw task description",
                    "status": "pending",
                    "acceptance_criteria": ["raw criterion"],
                }
            ],
            "active": [],
            "review": [],
            "done": [],
            "blocked": [],
        },
    )

    result = runner.invoke(app, ["board", "show", "--json", "--full", "--limit", "1"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["pending"][0]["description"] == "raw task description"
    assert payload["pending"][0]["acceptance_criteria"] == ["raw criterion"]
    assert payload["counts"]["pending"] == 1


def test_local_board_counts_survive_section_limit(monkeypatch):
    async def _fake_load_board_response(_session):
        class _Response:
            def model_dump(self, **_kwargs):
                return {
                    "pending": [],
                    "active": [],
                    "review": [],
                    "done": [{"id": f"task-{index}"} for index in range(17)],
                    "blocked": [{"id": "blocked-1"}],
                }

        return _Response()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _Factory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(local_fallback_module, "_local_session_factory", lambda: _Factory())
    monkeypatch.setattr(local_fallback_module, "load_board_response", _fake_load_board_response)

    payload = local_fallback_module.load_local_board(5)

    assert payload["counts"]["done"] == 17
    assert len(payload["done"]) == 5


def test_local_task_status_resolves_from_unsliced_board(monkeypatch):
    async def _fake_load_board_response(_session):
        class _Response:
            def model_dump(self, **_kwargs):
                return {
                    "pending": [],
                    "active": [],
                    "review": [],
                    "done": [{"id": f"task-{index}", "status": "done"} for index in range(12)],
                    "blocked": [
                        {
                            "id": "blocked-123",
                            "status": "capability_limit",
                            "blocked_reason": "provider limit",
                        }
                    ],
                }

        return _Response()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _Factory:
        def __call__(self):
            return _Session()

    monkeypatch.setattr(local_fallback_module, "_local_session_factory", lambda: _Factory())
    monkeypatch.setattr(local_fallback_module, "load_board_response", _fake_load_board_response)

    payload = local_fallback_module.load_local_task_status("blocked-123")

    assert payload is not None
    assert payload["status"] == "capability_limit"
    assert payload["blocked_reason"] == "provider limit"
    assert payload["degraded"] is True


def test_board_show_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            BuilderConnectivityError("http://127.0.0.1:9876")
        ),
    )
    monkeypatch.setattr(
        board_module,
        "load_local_board",
        lambda limit: {
            "pending": [{"id": "task-local", "title": "Plan task", "status": "pending"}],
            "active": [],
            "review": [],
            "done": [],
            "blocked": [],
            "counts": {"pending": 1, "active": 0, "review": 0, "done": 0, "blocked": 0},
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder backlog task status <task-id> --json",
        },
    )

    result = runner.invoke(app, ["board", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["counts"]["pending"] == 1


def test_task_status_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(task_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        task_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            BuilderConnectivityError("http://127.0.0.1:9876")
        ),
    )
    monkeypatch.setattr(
        task_module,
        "load_local_task_status",
        lambda task_id: {
            "id": task_id,
            "status": "capability_limit",
            "retry_count": 2,
            "blocked_reason": "provider limit",
            "capability_limit_reason": "reset_at=2026-05-09T01:00:00Z",
            "degraded": True,
            "source": "local_db_fallback",
        },
    )

    result = runner.invoke(app, ["backlog", "task", "status", "task-local", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "task-local"
    assert payload["status"] == "capability_limit"
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["next_step"] == "builder backlog task show task-local --json"


def test_task_show_points_failed_tasks_to_recover(monkeypatch):
    monkeypatch.setattr(
        task_module,
        "get_client",
        lambda **_: _PathClient(
            {
                "/tasks": [
                    {
                        "id": "task-123",
                        "title": "Recover planner failure",
                        "description": "Planner crashed",
                        "status": "failed",
                        "complexity": 2,
                        "retry_count": 0,
                        "blocked_reason": "planner failed",
                    }
                ],
                "/tasks/task-123": {
                    "id": "task-123",
                    "title": "Recover planner failure",
                    "description": "Planner crashed",
                    "status": "failed",
                    "complexity": 2,
                    "retry_count": 0,
                    "blocked_reason": "planner failed",
                },
            }
        ),
    )

    result = runner.invoke(app, ["backlog", "task", "show", "task-123", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder backlog task recover task-123 --yes --json"


def test_task_recover_posts_recovery_request(monkeypatch):
    recorded: list[tuple[str, object]] = []

    class _RecoverClient:
        def post(self, path: str, data=None):
            recorded.append((path, data))
            return {
                "status": "ok",
                "task_id": "task-123",
                "previous_status": "failed",
                "current_status": "pending",
                "next_step": "builder backlog task dispatch task-123 --yes --json",
            }

        def close(self):
            return None

    monkeypatch.setattr(task_module, "get_client", lambda **_: _RecoverClient())

    result = runner.invoke(app, ["backlog", "task", "recover", "task-123", "--yes", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert recorded == [("/tasks/task-123/recover", None)]
    assert payload["current_status"] == "pending"
    assert payload["next_step"] == "builder backlog task dispatch task-123 --yes --json"
