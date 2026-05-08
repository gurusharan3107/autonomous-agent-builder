"""Token-based model cost estimates for dashboard optimization views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenRate:
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    codex_input_credits_per_million: float | None = None
    codex_cached_input_credits_per_million: float | None = None
    codex_output_credits_per_million: float | None = None


# Source: OpenAI API pricing and Codex token-based rate card, checked 2026-05-03.
MODEL_RATES: dict[str, TokenRate] = {
    "gpt-5.5": TokenRate(5.00, 0.50, 30.00, 125.0, 12.50, 750.0),
    "gpt-5.4": TokenRate(2.50, 0.25, 15.00, 62.50, 6.250, 375.0),
    "gpt-5.4-mini": TokenRate(0.75, 0.075, 4.50, 18.75, 1.875, 113.0),
    "gpt-5.3-codex": TokenRate(1.75, 0.175, 14.00, 43.75, 4.375, 350.0),
    "gpt-5.2": TokenRate(1.75, 0.175, 14.00, 43.75, 4.375, 350.0),
    "gpt-5.2-codex": TokenRate(1.75, 0.175, 14.00, 43.75, 4.375, 350.0),
}


def normalize_model_name(model: str | None) -> str:
    normalized = (model or "").strip().lower().replace("_", "-")
    normalized = normalized.removeprefix("openai/")
    if normalized in {"gpt-5.4-mini", "gpt-5-4-mini"}:
        return "gpt-5.4-mini"
    return normalized


def estimate_run_cost(
    *,
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    actual_cost_usd: float = 0.0,
    runtime_sdk: str = "",
    provider: str = "",
) -> dict[str, Any]:
    """Estimate USD and Codex credits from token fields.

    `input_tokens` is treated as total input tokens. Cached input is charged at
    the cached rate and the remainder at the normal input rate.
    """

    actual_cost = max(float(actual_cost_usd or 0.0), 0.0)
    normalized_model = normalize_model_name(model)
    rate = MODEL_RATES.get(normalized_model)
    if actual_cost > 0:
        return {
            "estimated_cost_usd": actual_cost,
            "estimated_codex_credits": None,
            "cost_source": "runtime_reported",
            "pricing_model": normalized_model,
            "pricing_available": bool(rate),
            "pricing_note": "runtime reported billable cost",
        }
    if rate is None:
        return {
            "estimated_cost_usd": 0.0,
            "estimated_codex_credits": None,
            "cost_source": "missing_rate_card",
            "pricing_model": normalized_model or "",
            "pricing_available": False,
            "pricing_note": "no local rate card for model",
        }

    input_total = max(int(input_tokens or 0), 0)
    cached = min(max(int(cached_input_tokens or 0), 0), input_total)
    uncached = max(input_total - cached, 0)
    output = max(int(output_tokens or 0), 0)

    usd = (
        (uncached * rate.input_usd_per_million)
        + (cached * rate.cached_input_usd_per_million)
        + (output * rate.output_usd_per_million)
    ) / 1_000_000
    credits = None
    if (
        rate.codex_input_credits_per_million is not None
        and rate.codex_cached_input_credits_per_million is not None
        and rate.codex_output_credits_per_million is not None
    ):
        credits = (
            (uncached * rate.codex_input_credits_per_million)
            + (cached * rate.codex_cached_input_credits_per_million)
            + (output * rate.codex_output_credits_per_million)
        ) / 1_000_000

    source = "estimated_from_openai_rate_card"
    if provider == "codex_subscription" or str(runtime_sdk).startswith("codex"):
        source = "estimated_from_codex_subscription_tokens"
    return {
        "estimated_cost_usd": round(usd, 6),
        "estimated_codex_credits": round(credits, 6) if credits is not None else None,
        "cost_source": source,
        "pricing_model": normalized_model,
        "pricing_available": True,
        "pricing_note": "estimated from input, cached input, and output tokens",
    }
