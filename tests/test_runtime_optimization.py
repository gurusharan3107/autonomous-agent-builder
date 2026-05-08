from __future__ import annotations

import pytest

from autonomous_agent_builder.observability.runtime_optimization import (
    deterministic_script_candidates,
    normalize_runtime,
    optimization_decision_summary,
    phase_runtime_decisions,
    runtime_capability_matrix,
)


def test_claude_capability_matrix_reports_native_telemetry_and_hooks():
    matrix = runtime_capability_matrix("claude_agent_sdk")

    capabilities = {item["id"]: item for item in matrix["capabilities"]}
    assert matrix["runtime"] == "claude_agent_sdk"
    assert capabilities["telemetry"]["native"] is True
    assert "ResultMessage" in capabilities["telemetry"]["native_signal"]
    assert capabilities["hooks"]["native"] is True
    assert "SubagentStart" in capabilities["hooks"]["native_signal"]


def test_codex_capability_matrix_reports_tool_search_and_config_strengths():
    matrix = runtime_capability_matrix("codex_sdk")

    capabilities = {item["id"]: item for item in matrix["capabilities"]}
    assert matrix["runtime"] == "codex_sdk"
    assert capabilities["tool_routing"]["native"] is True
    assert "tool_search" in capabilities["tool_routing"]["native_signal"]
    assert capabilities["model_effort"]["native"] is True
    assert "model catalog" in capabilities["model_effort"]["native_signal"]
    assert capabilities["hooks"]["native"] is False


def test_unsupported_runtime_is_rejected_not_flattened():
    with pytest.raises(ValueError):
        normalize_runtime("openai_agents")


def test_phase_policy_rejects_subagents_for_questions_and_allows_sidecar_verification():
    decisions = {item["phase"]: item for item in phase_runtime_decisions("claude_agent_sdk")}

    assert decisions["requirements"]["subagent_policy"] == "no_subagents_for_user_questions"
    assert decisions["verification"]["subagent_policy"] == "sidecar_browser_or_eval_only"
    assert decisions["implementation"]["model_effort"] == "lowest_reliable_effort_for_known_files"
    assert decisions["planning"]["selected_subagents"] == ["repo-researcher"]
    assert decisions["verification"]["selected_subagents"] == [
        "build-verifier",
        "browser-verifier",
    ]
    assert decisions["verification"]["permission_policy"] == "deterministic_verification_first"
    assert "subagent_stop" in decisions["verification"]["hook_policy"]


def test_codex_phase_policy_does_not_claim_claude_specialists():
    decisions = {item["phase"]: item for item in phase_runtime_decisions("codex_sdk")}

    assert decisions["planning"]["selected_subagents"] == []
    assert decisions["verification"]["selected_subagents"] == []
    assert decisions["recovery"]["hook_policy"] == "builder_guardrails_and_codex_rules"


def test_optimization_agent_policy_starts_with_focused_preflight():
    from autonomous_agent_builder.agents.definitions import get_agent_definition
    from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
    from autonomous_agent_builder.config import get_settings

    policy = resolve_agent_runtime_policy(get_agent_definition("optimization-agent"), get_settings())

    assert policy.effort == "medium"
    assert policy.context_strategy == "post_ship_structured_observability_review"
    assert policy.subagents == ()
    assert policy.permission_policy == "read_only_preflight_then_exact_candidate_write"
    assert policy.hook_policy == "workspace_boundary_bash_argv_tool_audit_exact_command_validation"
    assert policy.reason_code == "post_ship_delivery_system_optimization"


def test_optimization_agent_prompt_json_example_is_format_safe():
    from autonomous_agent_builder.agents.definitions import get_agent_definition

    prompt = get_agent_definition("optimization-agent").prompt_template.format(
        tool_context="tools",
        sprint_context='{"sprint_id":"S-1"}',
        observability_payload='{"recommendations":[]}',
        workspace_path="/tmp/generated-app",
    )

    assert "Think like a delivery-system optimizer, not a cost cutter" in prompt
    assert "`builder metrics show --json`" in prompt
    assert "Do not load full raw metrics unless" in prompt
    assert "validate the exact recommended command" in prompt
    assert "Never optimize by pushing prompt memorization onto the user" in prompt
    assert (
        '"commands": [{"command": "<command>", "result": "pass|fail|not_run", '
        '"summary": "<evidence observed>"}]'
    ) in prompt


def test_deterministic_script_candidates_detect_repeated_verifier_and_tools():
    aggregates = {
        "by_agent": [
            {"agent_name": "build-verifier", "runs": 2},
            {"agent_name": "pr-creator", "runs": 1},
        ],
        "tool_observability": {
            "tool_counts": [{"tool_name": "Bash", "calls": 5}],
            "repeated_retrieval_signal": {
                "detected": True,
                "tools": [
                    {"tool_name": "Read", "calls": 8},
                    {"tool_name": "Grep", "calls": 5},
                ],
                "summary_tools": [],
                "summary_calls": 0,
            },
        },
    }

    candidates = deterministic_script_candidates(aggregates, {})
    codes = {item["code"] for item in candidates}

    assert "build_verify_script" in codes
    assert "change_evidence_collector" in codes
    assert "command_sequence_wrapper" in codes
    assert "bounded_retrieval_shortcut" in codes
    by_code = {item["code"]: item for item in candidates}
    assert by_code["build_verify_script"]["estimated_savings_tokens"] == 0


def test_deterministic_script_candidates_skip_weak_retrieval_signal():
    aggregates = {
        "tool_observability": {
            "tool_counts": [{"tool_name": "Read", "calls": 13}, {"tool_name": "Glob", "calls": 1}],
            "repeated_retrieval_signal": {
                "detected": False,
                "tools": [{"tool_name": "Read", "calls": 13}],
                "summary_tools": [],
                "summary_calls": 0,
            },
        }
    }

    candidates = deterministic_script_candidates(aggregates, {})

    assert "bounded_retrieval_shortcut" not in {item["code"] for item in candidates}


def test_optimization_decision_defaults_to_reducers_and_points_to_raw_cli():
    aggregates = {
        "by_agent": [
            {
                "agent_name": "build-verifier",
                "runs": 3,
                "input_tokens": 3000,
                "output_tokens": 300,
                "cached_tokens": 1500,
            }
        ],
        "tool_observability": {"tool_counts": []},
    }
    optimization = {
        "top_cost_drivers": [
            {"agent_name": "build-verifier", "raw_tokens": 3300}
        ],
    }

    decision = optimization_decision_summary(
        "codex_sdk",
        aggregates=aggregates,
        optimization=optimization,
    )

    assert decision["next_action"] == "convert_repeated_operations_to_deterministic_scripts"
    assert decision["target_area"] == "build_verify_script"
    assert decision["estimated_script_savings_tokens"] > 0
    assert decision["cli_surface"] == "builder metrics show --json --full"


def test_available_build_verify_script_changes_decision_to_use_script():
    aggregates = {
        "available_scripts": ["build_verify", "change_evidence"],
        "by_agent": [
            {
                "agent_name": "build-verifier",
                "runs": 3,
                "input_tokens": 3000,
                "output_tokens": 300,
                "cached_tokens": 1500,
            },
            {
                "agent_name": "pr-creator",
                "runs": 1,
                "input_tokens": 1000,
                "output_tokens": 100,
                "cached_tokens": 200,
            }
        ],
        "tool_observability": {"tool_counts": []},
    }
    optimization = {
        "top_cost_drivers": [
            {"agent_name": "build-verifier", "raw_tokens": 3300}
        ],
    }

    decision = optimization_decision_summary(
        "claude_agent_sdk",
        aggregates=aggregates,
        optimization=optimization,
    )
    candidate = decision["deterministic_script_candidates"][0]

    assert decision["next_action"] == "use_available_deterministic_script"
    assert candidate["status"] == "available"
    assert candidate["command"].startswith("builder script run build_verify")
    evidence_candidate = {
        item["code"]: item for item in decision["deterministic_script_candidates"]
    }["change_evidence_collector"]
    assert evidence_candidate["status"] == "available"
    assert evidence_candidate["command"] == "builder script run change_evidence --args '{}' --json"


def test_optimization_decision_prioritizes_provider_limit_over_zero_token_driver():
    aggregates = {
        "provider_limits": {"count": 1},
        "available_scripts": [],
        "by_agent": [
            {
                "agent_name": "agent-chat",
                "runs": 2,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
            }
        ],
        "tool_observability": {"tool_counts": []},
    }
    optimization = {
        "top_cost_drivers": [
            {
                "agent_name": "agent-chat",
                "raw_tokens": 0,
                "noncached_plus_output_tokens": 0,
                "cached_tokens": 0,
            }
        ],
    }

    decision = optimization_decision_summary(
        "claude_agent_sdk",
        aggregates=aggregates,
        optimization=optimization,
    )

    assert decision["next_action"] == "resume_after_provider_limit_reset"
    assert decision["target_area"] == "runtime_recovery"
    assert decision["reason"] == "provider limit blocked run evidence"


def test_optimization_decision_prioritizes_higher_savings_pr_evidence_lane():
    aggregates = {
        "available_scripts": ["build_verify", "change_evidence"],
        "by_agent": [
            {
                "agent_name": "build-verifier",
                "runs": 3,
                "input_tokens": 90000,
                "output_tokens": 900,
                "cached_tokens": 87000,
                "noncached_plus_output_tokens": 3900,
            },
            {
                "agent_name": "pr-creator",
                "runs": 3,
                "input_tokens": 120000,
                "output_tokens": 3000,
                "cached_tokens": 111000,
                "noncached_plus_output_tokens": 12000,
            },
        ],
        "tool_observability": {"tool_counts": []},
    }
    optimization = {
        "avoidable_cost_flags": [
            {"flag": "pr_lane_without_explicit_pr_target", "count": 3}
        ],
        "top_cost_drivers": [
            {
                "agent_name": "pr-creator",
                "raw_tokens": 123000,
                "avoidable_token_estimate": 12000,
            }
        ],
    }

    decision = optimization_decision_summary(
        "codex_sdk",
        aggregates=aggregates,
        optimization=optimization,
    )

    assert decision["next_action"] == "use_available_deterministic_script"
    assert decision["target_area"] == "change_evidence_collector"
    assert decision["reason"] == "model-backed PR/evidence lane used"
    assert decision["deterministic_script_candidates"][0]["command"] == (
        "builder script run change_evidence --args '{}' --json"
    )
