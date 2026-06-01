"""Tests for builder backlog item and query CLI surfaces."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import approval as approval_module
from autonomous_agent_builder.cli.commands import item as item_module
from autonomous_agent_builder.cli.commands import project as project_module
from autonomous_agent_builder.cli.commands import run as run_module
from autonomous_agent_builder.cli.commands import task as task_module
from autonomous_agent_builder.cli.main import app
from tests.builder_cli_surface_helpers import PathClient as _PathClient

runner = CliRunner()


def test_backlog_item_create_incident_requires_evidence():
    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "create",
            "--project",
            "proj-1",
            "--type",
            "incident",
            "--title",
            "Backlog render mismatch",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["code"] == "incident_evidence_required"


def test_backlog_item_create_improvement_posts_stable_payload(monkeypatch):
    captured: dict[str, object] = {}

    def _create(path: str, data=None):
        captured["path"] = path
        captured["data"] = data
        return {
            "id": "item-1",
            "project_id": "proj-1",
            "title": data["title"],
            "description": data["description"],
            "status": "backlog",
            "priority": data["priority"],
            "item_type": data["type"],
            "type": data["type"],
            "tags": data["tags"],
            "severity": data["severity"] or "",
            "source": data["source"],
            "evidence": data["evidence"],
        }

    monkeypatch.setattr(
        item_module,
        "get_client",
        lambda **_: _PathClient({"POST:/projects/proj-1/backlog/items": _create}),
    )

    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "create",
            "--project",
            "proj-1",
            "--type",
            "improvement",
            "--title",
            "Persist validation anecdotes",
            "--tags",
            "reverse-engineering",
            "--source",
            "validation",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured["path"] == "/projects/proj-1/backlog/items"
    assert captured["data"]["type"] == "improvement"
    assert captured["data"]["tags"] == ["reverse-engineering"]
    payload = json.loads(result.stdout)
    assert payload["item_type"] == "improvement"


def test_backlog_item_cancel_requires_confirmation():
    result = runner.invoke(
        app,
        ["backlog", "item", "cancel", "item-1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "cancel"
    assert payload["confirmed"] is False


def test_backlog_item_cancel_posts_to_cancel_route(monkeypatch):
    captured: dict[str, object] = {}

    def _cancel(path: str, data=None):
        captured["path"] = path
        return {
            "id": "item-1",
            "title": "Retire me",
            "item_type": "improvement",
            "type": "improvement",
            "status": "cancelled",
        }

    monkeypatch.setattr(
        item_module,
        "get_client",
        lambda **_: _PathClient({"POST:/backlog/items/item-1/cancel": _cancel}),
    )

    result = runner.invoke(
        app,
        ["backlog", "item", "cancel", "item-1", "--yes", "--json"],
    )

    assert result.exit_code == 0
    assert captured["path"] == "/backlog/items/item-1/cancel"
    payload = json.loads(result.stdout)
    assert payload["status"] == "cancelled"


def test_backlog_item_list_filters_by_type_and_tag(monkeypatch):
    def _list(path: str, **params):
        assert path == "/projects/proj-1/backlog/items"
        assert params == {"type": "incident", "tag": "reverse-engineering"}
        return [
            {
                "id": "item-2",
                "title": "Inbox approval mismatch",
                "status": "backlog",
                "item_type": "incident",
                "tags": ["reverse-engineering"],
                "severity": "high",
            }
        ]

    monkeypatch.setattr(
        item_module,
        "get_client",
        lambda **_: _PathClient({"/projects/proj-1/backlog/items": _list}),
    )

    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "list",
            "--project",
            "proj-1",
            "--type",
            "incident",
            "--tag",
            "reverse-engineering",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"][0]["item_type"] == "incident"


def test_project_summary_resolves_natural_query(monkeypatch):
    client = _PathClient(
        {
            "/projects/": [
                {
                    "id": "proj-1",
                    "name": "Builder",
                    "description": "Autonomous agent builder project",
                    "repo_url": "https://example.com/repo",
                    "language": "python",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ],
            "/projects/proj-1": {
                "id": "proj-1",
                "name": "Builder",
                "description": "Autonomous agent builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
                "created_at": "2026-01-01T00:00:00Z",
            },
        }
    )
    monkeypatch.setattr(project_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "project", "summary", "builder", "project", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "proj-1"
    assert payload["next_step"] == "builder backlog project show proj-1 --json"


def test_task_search_json_is_compact(monkeypatch):
    client = _PathClient(
        {
            "/tasks": [
                {
                    "id": "task-1",
                    "feature_id": "feat-1",
                    "title": "Implement retrieval hints",
                    "description": "Add fuzzy retrieval support.",
                    "status": "planning",
                    "complexity": 2,
                    "retry_count": 0,
                    "blocked_reason": "",
                    "capability_limit_reason": "",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
    )
    monkeypatch.setattr(task_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "task", "search", "retrieval", "hints", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "task-1"
    assert "description" not in payload["results"][0]


def test_task_show_full_includes_gate_results(monkeypatch):
    task = {
        "id": "task-1",
        "title": "Implement verification surface",
        "description": "Expose task-scoped verification evidence.",
        "status": "quality_gates",
    }
    gates = [
        {
            "id": "gate-1",
            "task_id": "task-1",
            "gate_name": "quality-gates",
            "status": "pass",
        }
    ]
    runs = [
        {
            "id": "run-1",
            "task_id": "task-1",
            "agent_name": "designer",
            "status": "success",
        }
    ]
    client = _PathClient(
        {
            "/tasks": [task],
            "/tasks/task-1": dict(task),
            "/tasks/task-1/gates": gates,
            "/tasks/task-1/runs": runs,
        }
    )
    monkeypatch.setattr(task_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "task", "show", "verification", "surface", "--full", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "task-1"
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["gate_results"] == gates
    assert payload["agent_runs"] == runs


def test_run_summary_resolves_natural_query(monkeypatch):
    run = {
        "id": "run-1",
        "task_id": "task-1",
        "agent_name": "designer",
        "session_id": "sess-1",
        "cost_usd": 0.42,
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_cached": 0,
        "num_turns": 3,
        "duration_ms": 1500,
        "stop_reason": "completed",
        "status": "success",
        "error": "",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
    }
    client = _PathClient({"/runs": [run], "/runs/run-1": run})
    monkeypatch.setattr(run_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "run", "summary", "designer", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "run-1"
    assert payload["matched_on"] in {"search", "name", "prefix"}


def test_run_list_falls_back_to_metrics_runs_when_run_index_is_empty(monkeypatch):
    run = {
        "id": "run-1",
        "task_id": "task-1",
        "agent_name": "agent-chat",
        "session_id": "sess-1",
        "cost_usd": 0.42,
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_cached": 0,
        "num_turns": 3,
        "duration_ms": 1500,
        "stop_reason": "completed",
        "status": "success",
        "error": "",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
    }
    client = _PathClient({"/runs": [], "/dashboard/metrics": {"runs": [run]}})
    monkeypatch.setattr(run_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "run", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "run-1"


def test_run_show_falls_back_to_metrics_payload_when_run_show_route_is_missing(monkeypatch):
    run = {
        "id": "run-1",
        "task_id": "task-1",
        "agent_name": "agent-chat",
        "session_id": "sess-1",
        "cost_usd": 0.42,
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_cached": 0,
        "num_turns": 3,
        "duration_ms": 1500,
        "stop_reason": "completed",
        "status": "success",
        "error": "",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
    }
    client = _PathClient({"/runs": [], "/dashboard/metrics": {"runs": [run]}})
    monkeypatch.setattr(run_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "run", "show", "run-1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "run-1"
    assert payload["agent_name"] == "agent-chat"


def test_approval_search_json_is_compact(monkeypatch):
    gate = {
        "id": "approval-1",
        "task_id": "task-1",
        "gate_type": "design",
        "status": "pending",
        "created_at": "2026-01-01T00:00:00Z",
    }
    client = _PathClient({"/approval-gates": [gate]})
    monkeypatch.setattr(approval_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "approval", "search", "design", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "approval-1"
    assert "created_at" not in payload["results"][0]


def test_backlog_item_update_puts_payload(monkeypatch):
    recorded: list[tuple[str, object]] = []

    class _ItemClient:
        def put(self, path: str, data=None):
            recorded.append((path, data))
            return {
                "id": "item-123",
                "item_type": "incident",
                "type": "incident",
                "title": "Updated title",
                "status": "backlog",
                "tags": ["dispatch"],
            }

        def close(self):
            return None

    monkeypatch.setattr(item_module, "get_client", lambda **_: _ItemClient())

    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "update",
            "item-123",
            "--title",
            "Updated title",
            "--status",
            "done",
            "--tags",
            "dispatch",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert recorded == [
        (
            "/backlog/items/item-123",
            {"title": "Updated title", "status": "done", "tags": ["dispatch"]},
        )
    ]
    assert payload["title"] == "Updated title"
    assert payload["tags"] == ["dispatch"]


def test_backlog_item_update_rejects_invalid_status():
    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "update",
            "item-123",
            "--status",
            "closed",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["code"] == "invalid_backlog_item_status"


def test_backlog_item_create_rejects_multiple_tags():
    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "create",
            "--project",
            "proj-1",
            "--title",
            "Bad tags",
            "--tags",
            "dispatch,approval",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["code"] == "invalid_backlog_item_tags"


def test_backlog_item_update_rejects_multiple_tags():
    result = runner.invoke(
        app,
        [
            "backlog",
            "item",
            "update",
            "item-123",
            "--tags",
            "dispatch,approval",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["code"] == "invalid_backlog_item_tags"
