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


def test_codex_optimization_counts_generic_app_server_tool_output() -> None:
    large_output = "x" * 45_000
    summary = codex_run_optimization_summary(
        events=[
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "toolCall",
                        "name": "Bash",
                        "input": {"cmd": "builder metrics show --json"},
                        "output": large_output,
                    }
                },
            }
        ],
        metrics={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        agent_name="chat",
    )

    assert summary["event_accounting"]["largest_command_output_bytes"] == len(large_output)
    assert "large_command_output" in summary["avoidable_cost_flags"]


def test_codex_optimization_flags_live_chunk_failure_sized_output() -> None:
    output = "x" * 26_468
    summary = codex_run_optimization_summary(
        events=[
            {"method": "item/commandExecution/outputDelta", "params": {"delta": output}},
        ],
        metrics={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        agent_name="chat",
        status="failed",
    )

    accounting = summary["event_accounting"]
    assert accounting["largest_command_output_bytes"] >= len(output)
    assert accounting["chunk_pressure_risk"] is True
    assert "large_command_output" in summary["avoidable_cost_flags"]


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
                    "event_accounting": {
                        "raw_event_count": 4,
                        "largest_event_bytes": 125_000,
                        "largest_command_output_bytes": 45_000,
                        "chunk_pressure_risk": True,
                    },
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
    assert summary["chunk_pressure"]["available"] is True
    assert summary["chunk_pressure"]["runs_with_signal"] == 1
    assert summary["chunk_pressure"]["risky_runs"] == 1
    assert summary["chunk_pressure"]["large_output_runs"] == 1
    assert summary["chunk_pressure"]["large_event_runs"] == 1
    assert summary["chunk_pressure"]["largest_command_output_bytes"] == 45_000
    assert summary["recommended_next_change"] == "skip_model_pr_creator_for_low_risk_local_sprints"


def test_summarize_runs_keeps_historical_large_output_from_driving_next_change() -> None:
    recent_clean_run = {
        "agent_name": "agent-chat",
        "tokens_input": 220_000,
        "tokens_output": 1_000,
        "tokens_cached": 216_000,
        "observability": {
            "optimization_summary": {
                "token_accounting": {
                    "raw_total_tokens": 221_000,
                    "noncached_plus_output_tokens": 5_000,
                    "cached_input_tokens": 216_000,
                    "output_tokens": 1_000,
                },
                "avoidable_cost_flags": [],
                "avoidable_token_estimate": 0,
                "event_accounting": {
                    "raw_event_count": 12,
                    "largest_event_bytes": 8_000,
                    "largest_command_output_bytes": 9_000,
                    "chunk_pressure_risk": False,
                },
            }
        },
    }
    historical_large_output_run = {
        "agent_name": "agent-chat",
        "tokens_input": 100,
        "tokens_output": 10,
        "tokens_cached": 0,
        "observability": {
            "optimization_summary": {
                "token_accounting": {
                    "raw_total_tokens": 110,
                    "noncached_plus_output_tokens": 110,
                    "cached_input_tokens": 0,
                    "output_tokens": 10,
                },
                "avoidable_cost_flags": ["large_command_output"],
                "avoidable_token_estimate": 110,
                "event_accounting": {
                    "raw_event_count": 4,
                    "largest_event_bytes": 45_000,
                    "largest_command_output_bytes": 45_000,
                    "chunk_pressure_risk": False,
                },
            }
        },
    }
    runs = [
        {
            "agent_name": "agent-chat",
            **recent_clean_run,
        }
        for _ in range(5)
    ] + [historical_large_output_run]

    summary = summarize_runs_for_optimization(runs)

    assert summary["avoidable_cost_flags"] == [{"flag": "large_command_output", "count": 1}]
    assert summary["active_avoidable_cost_flags"] == []
    assert summary["active_top_cost_drivers"][0]["agent_name"] == "agent-chat"
    assert summary["active_top_cost_drivers"][0]["avoidable_token_estimate"] == 0
    assert summary["chunk_pressure"]["large_output_runs"] == 1
    assert summary["chunk_pressure"]["recent_large_output_runs"] == 0
    assert summary["recommended_next_change"] == "maintain_current_flow"


def test_summarize_runs_uses_active_driver_when_recent_tokens_are_avoidable() -> None:
    recent_wasteful_run = {
        "agent_name": "agent-chat",
        "tokens_input": 120_000,
        "tokens_output": 12_000,
        "tokens_cached": 20_000,
        "observability": {
            "optimization_summary": {
                "token_accounting": {
                    "raw_total_tokens": 132_000,
                    "noncached_plus_output_tokens": 112_000,
                    "cached_input_tokens": 20_000,
                    "output_tokens": 12_000,
                },
                "avoidable_cost_flags": [],
                "avoidable_token_estimate": 0,
                "event_accounting": {
                    "raw_event_count": 4,
                    "largest_event_bytes": 8_000,
                    "largest_command_output_bytes": 0,
                    "chunk_pressure_risk": False,
                },
            }
        },
    }
    historical_code_gen_run = {
        "agent_name": "code-gen",
        "tokens_input": 500_000,
        "tokens_output": 10_000,
        "tokens_cached": 450_000,
    }

    summary = summarize_runs_for_optimization(
        [
            {
                "agent_name": "agent-chat",
                **recent_wasteful_run,
            }
            for _ in range(5)
        ]
        + [
            historical_code_gen_run,
        ]
    )

    assert summary["active_top_cost_drivers"][0]["agent_name"] == "agent-chat"
    assert summary["recommended_next_change"] == "reduce_agent-chat_raw_tokens"
