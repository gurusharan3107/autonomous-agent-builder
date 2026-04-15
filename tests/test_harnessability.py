"""Tests for harnessability scorer."""

from __future__ import annotations

from autonomous_agent_builder.db.models import HarnessAction
from autonomous_agent_builder.harness.harnessability import score_project


class TestHarnessabilityScorer:
    def test_well_structured_python_project(self, sample_workspace):
        result = score_project(str(sample_workspace), language="python")
        # Has pyproject.toml (ruff config), has tests dir, has src-like structure
        assert result.score >= 3
        assert result.routing_action in (HarnessAction.ARCHITECT_REVIEW, HarnessAction.PROCEED)

    def test_empty_project_gets_rejected(self, tmp_path):
        result = score_project(str(tmp_path), language="python")
        assert result.score < 3
        assert result.routing_action == HarnessAction.REJECT

    def test_score_never_exceeds_max(self, sample_workspace):
        result = score_project(str(sample_workspace), language="python")
        assert 0 <= result.score <= 8

    def test_checks_all_present(self, sample_workspace):
        result = score_project(str(sample_workspace), language="python")
        expected_checks = {
            "has_type_annotations",
            "has_linting_config",
            "has_test_suite",
            "has_module_boundaries",
            "has_api_contracts",
        }
        assert set(result.checks.keys()) == expected_checks

    def test_recommendations_for_low_score(self, tmp_path):
        result = score_project(str(tmp_path), language="python")
        assert len(result.recommendations) > 0

    def test_java_gets_type_annotations_free(self, tmp_path):
        # Java is inherently typed
        (tmp_path / "pom.xml").write_text("<project></project>")
        result = score_project(str(tmp_path), language="java")
        assert result.checks["has_type_annotations"]["score"] == 2

    def test_routing_thresholds(self, tmp_path):
        # Score 0 -> REJECT
        result = score_project(str(tmp_path), language="python")
        assert result.routing_action == HarnessAction.REJECT

    def test_typescript_with_tsconfig(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        (tmp_path / "src").mkdir()
        result = score_project(str(tmp_path), language="typescript")
        assert result.checks["has_type_annotations"]["score"] == 2
