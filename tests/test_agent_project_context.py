"""Tests for Agent project-context handoff helpers."""

from __future__ import annotations

from autonomous_agent_builder.embedded.server.agent_project_context import (
    append_target_claude_constraints,
    extract_technical_constraints,
    inject_feature_list_constraints,
    map_chat_answers_to_project_context,
)


def test_map_chat_answers_to_project_context_infers_vanilla_web_stack():
    fields = map_chat_answers_to_project_context(
        {
            "What are we building?": "Single HTML file",
            "How should data persist?": "Browser localStorage",
        }
    )

    assert fields == {
        "language": "javascript",
        "framework": None,
        "app_type": "web (single-file SPA)",
        "persistence": "browser localStorage",
        "package_manager": "none",
    }


def test_map_chat_answers_to_project_context_infers_framework_language():
    fields = map_chat_answers_to_project_context(
        {
            "Backend?": "FastAPI python backend",
            "Storage?": "PostgreSQL",
        }
    )

    assert fields["language"] == "python"
    assert fields["framework"] == "fastapi"
    assert fields["persistence"] == "postgresql"
    assert fields["package_manager"] == "pip"


def test_extract_technical_constraints_deduplicates_stack_mentions():
    constraints = extract_technical_constraints(
        "Use FastAPI with sqlite. fastapi should remain the backend framework."
    )

    assert constraints == [
        "Use FastAPI as the Python web framework",
        "Use SQLite for persistence",
    ]


def test_inject_feature_list_constraints_preserves_existing_metadata():
    payload = {
        "features": [{"title": "Ship trace view"}],
        "metadata": {"technical_constraints": ["Use SQLite for persistence"]},
    }

    updated = inject_feature_list_constraints(
        payload,
        [
            "Use SQLite for persistence",
            "Use React for the frontend",
        ],
    )

    assert updated is not payload
    assert updated["metadata"]["technical_constraints"] == [
        "Use SQLite for persistence",
        "Use React for the frontend",
    ]


def test_append_target_claude_constraints_appends_missing_lines_once(tmp_path):
    claude_path = tmp_path / "CLAUDE.md"
    claude_path.write_text(
        "# Runtime contract\n\n## Project Constraints\n- Use SQLite for persistence\n",
        encoding="utf-8",
    )

    append_target_claude_constraints(
        tmp_path,
        [
            "Use SQLite for persistence",
            "Use React for the frontend",
        ],
    )
    append_target_claude_constraints(tmp_path, ["Use React for the frontend"])

    assert claude_path.read_text(encoding="utf-8").splitlines() == [
        "# Runtime contract",
        "",
        "## Project Constraints",
        "- Use SQLite for persistence",
        "- Use React for the frontend",
    ]
