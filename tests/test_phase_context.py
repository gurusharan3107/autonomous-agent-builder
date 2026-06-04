from __future__ import annotations

from types import SimpleNamespace

from autonomous_agent_builder.orchestrator.phase_context import (
    compact_phase_output,
    phase_context,
    store_phase_context,
)


def test_phase_context_returns_trimmed_stored_value() -> None:
    task = SimpleNamespace(depends_on={"phase_context": {"design_context": " keep this \n"}})

    assert phase_context(task, "design_context") == "keep this"


def test_phase_context_ignores_missing_or_malformed_context() -> None:
    assert phase_context(SimpleNamespace(depends_on=None), "design_context") == ""
    assert phase_context(SimpleNamespace(depends_on={"phase_context": "bad"}), "design_context") == ""


def test_store_phase_context_preserves_existing_dependency_data() -> None:
    task = SimpleNamespace(depends_on={"existing": True, "phase_context": {"planning": "done"}})

    store_phase_context(task, "design_context", "ADR summary")

    assert task.depends_on == {
        "existing": True,
        "phase_context": {
            "planning": "done",
            "design_context": "ADR summary",
        },
    }


def test_store_phase_context_skips_empty_values() -> None:
    task = SimpleNamespace(depends_on={"existing": True})

    store_phase_context(task, "design_context", "")

    assert task.depends_on == {"existing": True}


def test_compact_phase_output_normalizes_and_truncates() -> None:
    assert compact_phase_output("  one\n\n two\tthree  ") == "one two three"
    assert compact_phase_output("abcdef", max_chars=6) == "abcdef"
    assert compact_phase_output("abcdef", max_chars=5) == "ab..."
