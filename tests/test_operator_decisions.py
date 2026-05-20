"""Tests for orchestrator operator-decision handoff helpers."""

from __future__ import annotations

from autonomous_agent_builder.db.models import Task, TaskStatus
from autonomous_agent_builder.orchestrator.operator_decisions import (
    apply_operator_decision_handoff,
    clear_operator_decision_handoff,
    extract_operator_decision,
)


def test_extract_operator_decision_normalizes_embedded_payload() -> None:
    payload = extract_operator_decision(
        'Need a choice.\nOPERATOR_DECISION_JSON: {"phase": " design ", '
        '"summary": "Need decision", "question": "Pick layout?", '
        '"options": [" Drawer ", 42], "recommended_option": " Drawer "}\nThanks'
    )

    assert payload == {
        "phase": "design",
        "summary": "Need decision",
        "question": "Pick layout?",
        "options": ["Drawer", "42"],
        "recommended_option": "Drawer",
    }


def test_apply_operator_decision_handoff_blocks_task() -> None:
    task = Task(id="task-1", title="Task", description="Do work", status=TaskStatus.DESIGN)

    handled = apply_operator_decision_handoff(
        task,
        'OPERATOR_DECISION_JSON: {"phase": "design", "summary": "Need decision"}',
    )

    assert handled is True
    assert task.status == TaskStatus.BLOCKED
    assert task.blocked_reason == "design blocked: Need decision"
    assert task.depends_on["operator_decision"]["summary"] == "Need decision"


def test_clear_operator_decision_handoff_preserves_other_dependencies() -> None:
    task = Task(
        id="task-1",
        title="Task",
        description="Do work",
        depends_on={"operator_decision": {"phase": "design"}, "other": True},
    )

    clear_operator_decision_handoff(task)

    assert task.depends_on == {"other": True}
