from __future__ import annotations

import pytest

from autonomous_agent_builder.services.token_costing import estimate_run_cost, normalize_model_name


def test_estimate_run_cost_uses_cached_input_rate() -> None:
    estimate = estimate_run_cost(
        model="gpt-5.5",
        input_tokens=10_000,
        cached_input_tokens=8_000,
        output_tokens=500,
        runtime_sdk="codex_sdk",
        provider="codex_subscription",
    )

    assert estimate["estimated_cost_usd"] == pytest.approx(0.029)
    assert estimate["estimated_codex_credits"] == pytest.approx(0.725)
    assert estimate["cost_source"] == "estimated_from_codex_subscription_tokens"
    assert estimate["pricing_available"] is True


def test_estimate_run_cost_preserves_runtime_reported_cost() -> None:
    estimate = estimate_run_cost(
        model="gpt-5.5",
        input_tokens=10_000,
        cached_input_tokens=8_000,
        output_tokens=500,
        actual_cost_usd=0.1234,
    )

    assert estimate["estimated_cost_usd"] == pytest.approx(0.1234)
    assert estimate["cost_source"] == "runtime_reported"


def test_estimate_run_cost_reports_missing_rate_card() -> None:
    estimate = estimate_run_cost(
        model="unknown-model",
        input_tokens=10_000,
        cached_input_tokens=0,
        output_tokens=500,
    )

    assert estimate["estimated_cost_usd"] == 0.0
    assert estimate["cost_source"] == "missing_rate_card"
    assert estimate["pricing_available"] is False


def test_normalize_model_name_handles_common_variants() -> None:
    assert normalize_model_name("OpenAI/GPT_5.4_Mini") == "gpt-5.4-mini"
