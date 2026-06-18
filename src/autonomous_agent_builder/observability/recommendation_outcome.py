"""Read-time outcome attribution for applied optimization recommendations.

Design A: pure read-time computation over agent_runs; no new DB table, no FK,
no migration, no write to Sprint.verification_evidence.

Public surface:
- ``metric_for_code(code)`` — maps a recommendation code to its metric name, or None.
- ``compute_outcome(...)`` — compute a verdict dict given before/after token windows.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Code → metric map
# ---------------------------------------------------------------------------

# Static codes that map to the noncached_plus_output_tokens metric.
_STATIC_TOKEN_CODES: frozenset[str] = frozenset(
    {
        "trim_prompt_segments_over_phase_budget",
        "truncate_tool_output_before_reinjection",
        "reduce_rework_before_token_band",
    }
)

# Dynamic pattern: reduce_<anything>_raw_tokens  (e.g. reduce_code-gen_raw_tokens)
_DYNAMIC_REDUCE_PREFIX = "reduce_"
_DYNAMIC_REDUCE_SUFFIX = "_raw_tokens"

_TOKEN_METRIC = "noncached_plus_output_tokens"


def metric_for_code(code: str | None) -> str | None:
    """Return the metric name for a recommendation code, or None if not measurable.

    Static codes: trim_prompt_segments_over_phase_budget,
                  truncate_tool_output_before_reinjection,
                  reduce_rework_before_token_band.
    Dynamic codes: any code matching reduce_*_raw_tokens.
    Everything else (maintain_current_flow, skip_*, script_candidate_*) → None.
    """
    if not isinstance(code, str):
        return None
    code = code.strip()
    if code in _STATIC_TOKEN_CODES:
        return _TOKEN_METRIC
    if (
        code.startswith(_DYNAMIC_REDUCE_PREFIX)
        and code.endswith(_DYNAMIC_REDUCE_SUFFIX)
        and len(code) > len(_DYNAMIC_REDUCE_PREFIX) + len(_DYNAMIC_REDUCE_SUFFIX)
    ):
        return _TOKEN_METRIC
    return None


# ---------------------------------------------------------------------------
# Outcome computation
# ---------------------------------------------------------------------------


def compute_outcome(
    before_tokens: int,
    after_tokens: int,
    before_runs: int,
    after_runs: int,
    *,
    min_n: int = 3,
    flat_band: float = 0.05,
) -> dict[str, Any]:
    """Compute an outcome verdict given before/after token window totals.

    Args:
        before_tokens: total noncached+output tokens in the before window.
        after_tokens:  total noncached+output tokens in the after window.
        before_runs:   delivery run count in the before window.
        after_runs:    delivery run count in the after window.
        min_n:         minimum runs in each window to produce a measured verdict.
        flat_band:     |delta_pct| < flat_band → "flat".

    Returns a dict with keys: metric, before, after, delta, delta_pct, verdict.
    """
    before_tokens = int(before_tokens or 0)
    after_tokens = int(after_tokens or 0)
    before_runs = int(before_runs or 0)
    after_runs = int(after_runs or 0)

    if before_runs < min_n or after_runs < min_n:
        return {
            "metric": _TOKEN_METRIC,
            "before": before_tokens,
            "after": after_tokens,
            "delta": after_tokens - before_tokens,
            "delta_pct": 0.0,
            "verdict": "insufficient_data",
        }

    delta = after_tokens - before_tokens

    if before_tokens == 0 and after_tokens == 0:
        return {
            "metric": _TOKEN_METRIC,
            "before": 0,
            "after": 0,
            "delta": 0,
            "delta_pct": 0.0,
            "verdict": "insufficient_data",
        }

    if before_tokens == 0:
        # Tokens appeared from nowhere → regressed
        return {
            "metric": _TOKEN_METRIC,
            "before": 0,
            "after": after_tokens,
            "delta": after_tokens,
            "delta_pct": 1.0,
            "verdict": "regressed",
        }

    delta_pct = delta / before_tokens

    if abs(delta_pct) < flat_band:
        verdict = "flat"
    elif delta < 0:
        verdict = "improved"
    else:
        verdict = "regressed"

    return {
        "metric": _TOKEN_METRIC,
        "before": before_tokens,
        "after": after_tokens,
        "delta": delta,
        "delta_pct": round(delta_pct, 6),
        "verdict": verdict,
    }
