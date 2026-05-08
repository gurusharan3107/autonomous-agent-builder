from __future__ import annotations

from autonomous_agent_builder.services.codex_optimization import (
    codex_run_optimization_summary,
    prompt_budget_breakdown,
    summarize_runs_for_optimization,
)


def test_codex_optimization_summary_calculates_tokens_and_flags() -> None:
    large_output = "x" * 45_000
    summary = codex_run_optimization_summary(
        events=[
            {"method": "item/commandExecution/outputDelta", "params": {"delta": large_output}},
            {"method": "item/tool/completed", "params": {"name": "Grep"}},
        ],
        metrics={
            "input_tokens": 100,
            "cached_input_tokens": 60,
            "output_tokens": 20,
            "reasoning_output_tokens": 5,
            "total_tokens": 120,
        },
        agent_name="pr-creator",
        prompt_text="Implement",
        output_text="Done",
        prompt_budget={"over_budget": True},
    )

    assert summary["token_accounting"]["raw_total_tokens"] == 120
    assert summary["token_accounting"]["noncached_plus_output_tokens"] == 60
    assert summary["token_accounting"]["cache_ratio"] == 0.6
    assert summary["event_accounting"]["largest_command_output_bytes"] > 40_000
    assert "pr_lane_without_explicit_pr_target" in summary["avoidable_cost_flags"]
    assert "large_command_output" in summary["avoidable_cost_flags"]
    assert "prompt_over_phase_budget" in summary["avoidable_cost_flags"]


def test_prompt_budget_breakdown_marks_phase_over_budget() -> None:
    breakdown = prompt_budget_breakdown(
        agent_name="pr-creator",
        prompt="x" * 25_000,
        template_vars={"task_description": "ship feature", "tool_context": "tools"},
        agent_definition="definition",
    )

    assert breakdown["budget_tokens"] == 5_000
    assert breakdown["over_budget"] is True
    assert breakdown["segments"]["task_brief"] > 0


def test_summarize_runs_for_optimization_rolls_up_drivers() -> None:
    runs = [
        {
            "agent_name": "pr-creator",
            "tokens_input": 100,
            "tokens_output": 10,
            "tokens_cached": 50,
            "observability": {
                "optimization_summary": {
                    "token_accounting": {
                        "raw_total_tokens": 110,
                        "noncached_plus_output_tokens": 60,
                        "cached_input_tokens": 50,
                        "output_tokens": 10,
                    },
                    "avoidable_cost_flags": ["pr_lane_without_explicit_pr_target"],
                    "avoidable_token_estimate": 110,
                }
            },
        },
        {
            "agent_name": "code-gen",
            "tokens_input": 80,
            "tokens_output": 20,
            "tokens_cached": 20,
        },
    ]

    summary = summarize_runs_for_optimization(runs)

    assert summary["primary_score"] == "raw_tokens"
    assert summary["raw_token_total"] == 210
    assert summary["noncached_plus_output_tokens"] == 140
    assert summary["phase_ceremony_tokens"] == 110
    assert summary["top_cost_drivers"][0]["agent_name"] == "pr-creator"
    assert summary["recommended_next_change"] == "skip_model_pr_creator_for_low_risk_local_sprints"
