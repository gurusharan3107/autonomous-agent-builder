from __future__ import annotations

from types import SimpleNamespace

from autonomous_agent_builder.orchestrator.failure_diagnosis import (
    diagnose_task_failure,
    is_codex_chunk_limit_error,
    workspace_contains_builder_internals,
)


def test_codex_chunk_error_names_polluted_workspace_issue(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".agent-builder" / "dashboard").mkdir(parents=True)
    result = SimpleNamespace(
        observability={
            "runtime_sdk": "codex_sdk",
            "raw_event_count": 196,
            "duration_ms": 50645,
        }
    )

    reason = diagnose_task_failure(
        "Separator is not found, and chunk exceed the limit",
        workspace_path=str(workspace),
        result=result,
    )

    assert reason.startswith("workspace_pollution_codex_chunk_limit:")
    assert "Task workspace contains builder internals" in reason
    assert "runtime=codex_sdk" in reason
    assert "events=196" in reason
    assert "duration_ms=50645" in reason


def test_codex_chunk_error_names_transport_issue_without_workspace_pollution(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = SimpleNamespace(observability={"runtime_sdk": "codex_sdk"})

    reason = diagnose_task_failure(
        "Separator is not found, and chunk exceed the limit",
        workspace_path=str(workspace),
        result=result,
    )

    assert reason.startswith("codex_transport_chunk_limit:")
    assert "runtime=codex_sdk" in reason


def test_workspace_contains_builder_internals_detects_pollution(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".codex").mkdir(parents=True)

    assert workspace_contains_builder_internals(str(workspace)) is True
    assert workspace_contains_builder_internals("") is False


def test_is_codex_chunk_limit_error_requires_both_fragments() -> None:
    assert is_codex_chunk_limit_error("Separator is not found and chunk exceed") is True
    assert is_codex_chunk_limit_error("Separator is not found") is False
