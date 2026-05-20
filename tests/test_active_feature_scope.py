"""Tests for active feature scope reminder rendering."""

from __future__ import annotations

import json
from types import SimpleNamespace

from autonomous_agent_builder.orchestrator.active_feature_scope import (
    build_active_feature_scope_reminder,
    sibling_task_ownership_hints,
)


def test_active_feature_scope_reminder_renders_feature_and_ownership() -> None:
    task = SimpleNamespace(
        feature=SimpleNamespace(
            title="Calendar sync",
            description="Ship visible calendar sync.",
            acceptance_criteria=["Shows synced events", "Persists refresh tokens"],
        ),
        depends_on={
            "phase_context": {
                "design_context": json.dumps(
                    {
                        "task_file_ownership_hints": [
                            {
                                "task_key": "current",
                                "title": "Current task",
                                "ownership": "src/current.py",
                            },
                            {
                                "task_key": "settings",
                                "title": "Settings UI",
                                "ownership": "src/settings.py",
                            },
                        ]
                    }
                )
            }
        },
    )

    reminder = build_active_feature_scope_reminder(
        task,
        {
            "task_key": "current",
            "file_ownership_hint": "src/current.py and tests",
        },
    )

    assert "Feature: Calendar sync" in reminder
    assert "- Shows synced events" in reminder
    assert "You OWN: src/current.py and tests" in reminder
    assert "- Settings UI → src/settings.py" in reminder
    assert "Current task → src/current.py" not in reminder


def test_active_feature_scope_reminder_collapses_without_scope() -> None:
    task = SimpleNamespace(
        feature=SimpleNamespace(title="", description="", acceptance_criteria=[]),
        depends_on={},
    )

    assert build_active_feature_scope_reminder(task, {}) == ""


def test_sibling_task_ownership_hints_ignore_invalid_design_context() -> None:
    task = SimpleNamespace(depends_on={"phase_context": {"design_context": "not json"}})

    assert sibling_task_ownership_hints(task, "current") == []
