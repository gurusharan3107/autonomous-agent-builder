"""Unit tests for recommendation_outcome: compute_outcome + metric_for_code."""

from autonomous_agent_builder.observability.recommendation_outcome import (
    compute_outcome,
    metric_for_code,
)

# ---------------------------------------------------------------------------
# metric_for_code
# ---------------------------------------------------------------------------


class TestMetricForCode:
    def test_static_trim_prompt(self):
        assert metric_for_code("trim_prompt_segments_over_phase_budget") == "noncached_plus_output_tokens"

    def test_static_truncate_tool_output(self):
        assert metric_for_code("truncate_tool_output_before_reinjection") == "noncached_plus_output_tokens"

    def test_static_reduce_rework(self):
        assert metric_for_code("reduce_rework_before_token_band") == "noncached_plus_output_tokens"

    def test_dynamic_reduce_raw_tokens(self):
        assert metric_for_code("reduce_code-gen_raw_tokens") == "noncached_plus_output_tokens"

    def test_dynamic_reduce_another_agent_raw_tokens(self):
        assert metric_for_code("reduce_planner_raw_tokens") == "noncached_plus_output_tokens"

    def test_unmapped_maintain_current_flow(self):
        assert metric_for_code("maintain_current_flow") is None

    def test_unmapped_skip_code(self):
        assert metric_for_code("skip_model_pr_creator_for_low_risk_local_sprints") is None

    def test_unmapped_script_candidate(self):
        assert metric_for_code("script_candidate_build_verify_script") is None

    def test_dynamic_prefix_only_no_match(self):
        # "reduce__raw_tokens" has empty middle segment
        assert metric_for_code("reduce__raw_tokens") is None

    def test_empty_string(self):
        assert metric_for_code("") is None

    def test_none_input(self):
        assert metric_for_code(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_outcome — verdicts
# ---------------------------------------------------------------------------


class TestComputeOutcome:
    def test_improved(self):
        result = compute_outcome(1000, 800, 5, 5)
        assert result["verdict"] == "improved"
        assert result["delta"] == -200
        assert result["before"] == 1000
        assert result["after"] == 800
        assert result["metric"] == "noncached_plus_output_tokens"

    def test_regressed(self):
        result = compute_outcome(800, 1100, 5, 5)
        assert result["verdict"] == "regressed"
        assert result["delta"] == 300

    def test_flat_exact_positive_band_edge(self):
        # delta_pct = 0.04999... < 0.05 → flat
        before = 1000
        after = 1049  # delta_pct ≈ 0.049 < 0.05
        result = compute_outcome(before, after, 5, 5)
        assert result["verdict"] == "flat"

    def test_flat_exact_negative_band_edge(self):
        before = 1000
        after = 951   # delta_pct ≈ -0.049 → abs < 0.05 → flat
        result = compute_outcome(before, after, 5, 5)
        assert result["verdict"] == "flat"

    def test_just_over_band_regressed(self):
        # delta_pct = 0.06 → regressed (not flat)
        before = 1000
        after = 1060
        result = compute_outcome(before, after, 5, 5)
        assert result["verdict"] == "regressed"

    def test_just_over_band_improved(self):
        before = 1000
        after = 940  # delta_pct = -0.06 → improved
        result = compute_outcome(before, after, 5, 5)
        assert result["verdict"] == "improved"

    def test_insufficient_data_before_runs_too_low(self):
        result = compute_outcome(1000, 800, 2, 5, min_n=3)
        assert result["verdict"] == "insufficient_data"

    def test_insufficient_data_after_runs_too_low(self):
        result = compute_outcome(1000, 800, 5, 2, min_n=3)
        assert result["verdict"] == "insufficient_data"

    def test_exactly_min_n_is_measured(self):
        result = compute_outcome(1000, 800, 3, 3, min_n=3)
        assert result["verdict"] == "improved"

    def test_before_zero_after_positive_regressed(self):
        result = compute_outcome(0, 500, 5, 5)
        assert result["verdict"] == "regressed"
        assert result["delta_pct"] == 1.0

    def test_both_zero_insufficient_data(self):
        result = compute_outcome(0, 0, 5, 5)
        assert result["verdict"] == "insufficient_data"

    def test_result_has_all_keys(self):
        result = compute_outcome(100, 90, 5, 5)
        assert set(result.keys()) == {"metric", "before", "after", "delta", "delta_pct", "verdict"}
