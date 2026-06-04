"""Unit tests for prompt-timeline reconstruction (observability.timeline_analysis)."""

from __future__ import annotations

from autonomous_agent_builder.observability.timeline_analysis import build_timeline_prompts


def _evt(event_type: str, payload: dict, created_at: str) -> dict:
    return {"event_type": event_type, "payload": payload, "created_at": created_at}


def test_run_status_telemetry_survives_trailing_zero_markers() -> None:
    """IMP-023 Fix B regression: a single prompt emits several run_status events
    (initial running marker, the real model-run total, then deterministic
    continuation / dispatch markers carrying zeros). Last-write-wins let the
    trailing zero marker clobber the real cost/token totals, blanking the
    analyze headline. The additive merge must preserve the real telemetry.
    """
    items = [
        _evt("user_message", {"content": "add a feature"}, "1"),
        _evt(
            "run_status",
            {"running": True, "current_turn": 0, "tokens_used": 0, "cost_usd": 0.0},
            "2",
        ),
        _evt("assistant_message", {"content": "ok"}, "3"),
        _evt(
            "run_status",
            {
                "running": False,
                "current_turn": 1,
                "tokens_used": 946,
                "tokens_input": 3,
                "tokens_output": 943,
                "cost_usd": 0.1041185,
                "duration_ms": 18589,
            },
            "4",
        ),
        _evt(
            "run_status",
            {
                "running": False,
                "current_turn": 0,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "stop_reason": "task_dispatched",
            },
            "5",
        ),
        _evt("assistant_message", {"content": "done"}, "6"),
        _evt(
            "run_status",
            {"running": False, "current_turn": 0, "tokens_used": 0, "cost_usd": 0.0},
            "7",
        ),
    ]

    prompts = build_timeline_prompts(items)

    assert len(prompts) == 1
    telemetry = prompts[0]["telemetry"]
    assert telemetry["cost_usd"] == 0.1041185
    assert telemetry["tokens_used"] == 946
    assert telemetry["tokens_output"] == 943
    # status scalar takes the last non-empty value (the dispatch marker)
    assert telemetry["stop_reason"] == "task_dispatched"


def test_run_status_telemetry_sums_multiple_real_invocations() -> None:
    """A prompt that triggers two real model runs (e.g. a delivery continuation
    that re-invokes the model) accumulates cost/tokens across both.
    """
    items = [
        _evt("user_message", {"content": "do work"}, "1"),
        _evt("run_status", {"running": False, "tokens_used": 100, "cost_usd": 0.01}, "2"),
        _evt("run_status", {"running": False, "tokens_used": 250, "cost_usd": 0.04}, "3"),
    ]

    prompts = build_timeline_prompts(items)

    assert prompts[0]["telemetry"]["tokens_used"] == 350
    assert round(prompts[0]["telemetry"]["cost_usd"], 6) == 0.05


def test_run_status_observability_snapshot_promoted() -> None:
    """An observability snapshot in a run_status payload is promoted onto the
    prompt record (not kept inside telemetry).
    """
    items = [
        _evt("user_message", {"content": "hi"}, "1"),
        _evt(
            "run_status",
            {"running": False, "cost_usd": 0.0, "observability": {"otel": {"enabled": True}}},
            "2",
        ),
    ]

    prompts = build_timeline_prompts(items)

    assert prompts[0]["observability"] == {"otel": {"enabled": True}}
    assert "observability" not in prompts[0]["telemetry"]
