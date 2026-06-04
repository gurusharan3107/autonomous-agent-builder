"""IMP-034b backend: operator-selectable UI prototype preview.

Covers the pure/synchronous backend surface: payload normalization, the
ui_preview approval routing, the should_run_ui_preview predicate, and the
ui-prototyper agent definition. The async orchestrator hold-for-approval flow
is exercised via the routing predicate rather than a full lifecycle run.
"""

from __future__ import annotations

from types import SimpleNamespace

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.db.models import ApprovalDecision, TaskStatus
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    normalize_feature_spec_payload,
)
from autonomous_agent_builder.orchestrator.approval_outcomes import apply_approval_outcome
from autonomous_agent_builder.orchestrator.build_verification import should_run_ui_preview


def _approval_task() -> SimpleNamespace:
    """Minimal task shape for apply_approval_outcome (sets status/phase + blocked_*)."""
    return SimpleNamespace(
        status=TaskStatus.DESIGN_REVIEW,
        phase=None,
        blocked_reason="held for ui preview",
        blocked_at="2026-06-04T00:00:00Z",
        depends_on=None,
    )


def _feature(*, ui_preview_enabled: bool, title: str = "", description: str = ""):
    return SimpleNamespace(
        title=title,
        description=description,
        acceptance_criteria=[],
        ui_preview_enabled=ui_preview_enabled,
    )


def _task_with_feature(feature) -> SimpleNamespace:
    return SimpleNamespace(title="", description="", feature=feature)


# ── Payload normalization ──


def test_normalize_extracts_ui_preview_enabled_true() -> None:
    payload = normalize_feature_spec_payload(
        {"title": "Add dashboard widget", "ui_preview_enabled": True}
    )
    assert payload["ui_preview_enabled"] is True


def test_normalize_defaults_ui_preview_enabled_false() -> None:
    payload = normalize_feature_spec_payload({"title": "Add a CLI flag"})
    assert payload["ui_preview_enabled"] is False


def test_normalize_coerces_truthy_ui_preview_enabled() -> None:
    payload = normalize_feature_spec_payload(
        {"title": "Add panel", "ui_preview_enabled": "yes"}
    )
    assert payload["ui_preview_enabled"] is True


# ── Approval routing ──


def test_ui_preview_approve_routes_to_implementation() -> None:
    task = _approval_task()
    dispatched = apply_approval_outcome(task, "ui_preview", ApprovalDecision.APPROVE)
    assert dispatched is True
    assert task.status == TaskStatus.IMPLEMENTATION
    assert task.blocked_reason is None
    assert task.blocked_at is None


def test_ui_preview_reject_blocks_and_does_not_dispatch() -> None:
    task = _approval_task()
    dispatched = apply_approval_outcome(
        task, "ui_preview", ApprovalDecision.REJECT, reason="wrong layout"
    )
    assert dispatched is False
    assert task.status == TaskStatus.BLOCKED
    assert task.blocked_reason == "wrong layout"


# ── Routing predicate ──


def test_should_run_ui_preview_requires_opt_in_and_ui_task() -> None:
    ui_opted_in = _task_with_feature(
        _feature(ui_preview_enabled=True, title="New dashboard page")
    )
    assert should_run_ui_preview(ui_opted_in) is True


def test_should_run_ui_preview_false_when_not_opted_in() -> None:
    ui_no_opt = _task_with_feature(
        _feature(ui_preview_enabled=False, title="New dashboard page")
    )
    assert should_run_ui_preview(ui_no_opt) is False


def test_should_run_ui_preview_false_for_non_ui_feature() -> None:
    non_ui = _task_with_feature(
        _feature(ui_preview_enabled=True, title="Add a backend retry policy")
    )
    assert should_run_ui_preview(non_ui) is False


# ── Agent definition ──


def test_ui_prototyper_definition() -> None:
    agent = get_agent_definition("ui-prototyper")
    assert agent.model == "sonnet"
    assert "Write" in agent.tools
    assert "{design_directive}" in agent.prompt_template
    assert "UI_PREVIEW_RESULT_JSON" in agent.prompt_template
