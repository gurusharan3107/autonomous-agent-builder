from __future__ import annotations

from types import SimpleNamespace

import pytest

from autonomous_agent_builder.agents.definitions import (
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.execution_policy import (
    resolve_agent_runtime_policy,
    resolve_subagent_model,
)
from autonomous_agent_builder.config import get_settings


CANONICAL_PHASE_AGENTS = (
    "planner",
    "designer",
    "code-gen",
    "integration-resolver",
    "pr-creator",
    "build-verifier",
    "feature-verifier",
    "documentation-bridge",
)


EXPECTED_ROLE_POLICIES = {
    "planner": ("high", 8192, "compact_plan_artifact"),
    "designer": ("high", 12288, "compact_design_handoff"),
    "code-gen": ("medium", 4096, "scripted_repeatable_work"),
    "integration-resolver": ("medium", 4096, "bounded_conflict_resolution"),
    "pr-creator": ("low", 2048, "evidence_summary_only"),
    "build-verifier": ("low", 1024, "scripted_verification"),
    "feature-verifier": ("medium", 4096, "agentic_acceptance_then_durable_playwright"),
    "documentation-bridge": ("low", 2048, "delegated_doc_refresh"),
}


def _settings_for_runtime(sdk: str) -> SimpleNamespace:
    return SimpleNamespace(
        runtime=SimpleNamespace(
            sdk=sdk,
            provider="codex_subscription" if sdk.startswith("codex") else "claude_code",
            model="gpt-5.5" if sdk.startswith("codex") else "",
            subscription=None,
            api_base_url=None,
            api_key_env=None,
            codex_profile=None,
            sandbox_mode="workspace-write",
            approval_policy="never",
            tracing="builder",
        ),
        agent=SimpleNamespace(
            planning_model="opus",
            design_model="opus",
            implementation_model="sonnet",
            pr_model="haiku",
        ),
    )


def test_planner_policy_uses_expensive_reasoning_only_for_planning() -> None:
    settings = get_settings()
    policy = resolve_agent_runtime_policy(get_agent_definition("planner"), settings)

    assert policy.model == settings.agent.planning_model
    assert policy.effort == "high"
    assert policy.max_thinking_tokens == 8192
    assert policy.context_strategy == "compact_plan_artifact"


def test_code_gen_policy_uses_sonnet_and_scripted_context_strategy() -> None:
    settings = get_settings()
    policy = resolve_agent_runtime_policy(get_agent_definition("code-gen"), settings)

    assert policy.model == settings.agent.implementation_model
    assert policy.effort == "medium"
    assert policy.context_strategy == "scripted_repeatable_work"


def test_codex_cli_policy_uses_runtime_model_and_role_effort() -> None:
    settings = SimpleNamespace(
        runtime=SimpleNamespace(
            sdk="codex_cli",
            provider="codex_subscription",
            model="gpt-5.5",
            subscription=None,
            api_base_url=None,
            api_key_env=None,
            codex_profile=None,
            sandbox_mode="workspace-write",
            approval_policy="never",
            tracing="builder",
        ),
        agent=SimpleNamespace(
            planning_model="opus",
            design_model="opus",
            implementation_model="opus",
            pr_model="sonnet",
        ),
    )

    policy = resolve_agent_runtime_policy(get_agent_definition("init-project-chat"), settings)

    assert policy.model == "gpt-5.5"
    assert policy.effort == "medium"


def test_codex_sdk_policy_uses_runtime_model_and_role_effort() -> None:
    settings = SimpleNamespace(
        runtime=SimpleNamespace(
            sdk="codex_sdk",
            provider="codex_subscription",
            model="gpt-5.5",
            subscription=None,
            api_base_url=None,
            api_key_env=None,
            codex_profile=None,
            sandbox_mode="workspace-write",
            approval_policy="never",
            tracing="builder",
        ),
        agent=SimpleNamespace(
            planning_model="opus",
            design_model="opus",
            implementation_model="opus",
            pr_model="sonnet",
        ),
    )

    policy = resolve_agent_runtime_policy(get_agent_definition("planner"), settings)

    assert policy.model == "gpt-5.5"
    assert policy.effort == "high"


@pytest.mark.parametrize("agent_name", CANONICAL_PHASE_AGENTS)
def test_canonical_phase_agents_have_builder_owned_role_policy(agent_name: str) -> None:
    policy = resolve_agent_runtime_policy(
        get_agent_definition(agent_name),
        _settings_for_runtime("claude"),
    )
    expected_effort, expected_thinking, expected_context = EXPECTED_ROLE_POLICIES[agent_name]

    assert policy.effort == expected_effort
    assert policy.max_thinking_tokens == expected_thinking
    assert policy.context_strategy == expected_context
    assert policy.reason_code
    assert policy.permission_policy
    assert policy.hook_policy


@pytest.mark.parametrize("runtime_sdk", ("claude", "codex_sdk"))
@pytest.mark.parametrize("agent_name", CANONICAL_PHASE_AGENTS)
def test_runtime_switch_preserves_phase_agent_policy_shape(
    runtime_sdk: str,
    agent_name: str,
) -> None:
    policy = resolve_agent_runtime_policy(
        get_agent_definition(agent_name),
        _settings_for_runtime(runtime_sdk),
    )
    expected_effort, expected_thinking, expected_context = EXPECTED_ROLE_POLICIES[agent_name]

    assert policy.effort == expected_effort
    assert policy.max_thinking_tokens == expected_thinking
    assert policy.context_strategy == expected_context
    if runtime_sdk.startswith("codex"):
        assert policy.model == "gpt-5.5"
    else:
        assert policy.model in {"opus", "sonnet", "haiku"}


def test_documentation_subagent_defaults_to_haiku() -> None:
    assert resolve_subagent_model(get_subagent_definition("documentation-agent")) == "haiku"


def test_claude_phase_policy_selects_bounded_specialists() -> None:
    settings = _settings_for_runtime("claude")

    planner = resolve_agent_runtime_policy(get_agent_definition("planner"), settings)
    verifier = resolve_agent_runtime_policy(get_agent_definition("build-verifier"), settings)
    integration = resolve_agent_runtime_policy(
        get_agent_definition("integration-resolver"),
        settings,
    )

    assert planner.subagents == ("repo-researcher",)
    assert verifier.subagents == ("build-verifier", "browser-verifier")
    assert integration.subagents == ("security-reviewer",)
    assert verifier.reason_code == "quality_evidence"
    assert "stop_evidence" in verifier.hook_policy


@pytest.mark.parametrize(
    "subagent_name",
    (
        "repo-researcher",
        "browser-verifier",
        "build-verifier",
        "security-reviewer",
        "pr-reviewer",
        "documentation-agent",
    ),
)
def test_claude_specialist_subagents_have_structured_evidence_contract(
    subagent_name: str,
) -> None:
    subagent = get_subagent_definition(subagent_name)

    assert "JSON object" in subagent.prompt
    assert subagent.tools
    assert resolve_subagent_model(subagent) in {"haiku", "sonnet"}


def test_runtime_policy_payload_is_agent_friendly() -> None:
    policy = resolve_agent_runtime_policy(
        get_agent_definition("build-verifier"),
        _settings_for_runtime("claude"),
    )

    payload = policy.to_payload()

    assert payload["selected_subagents"] == ["build-verifier", "browser-verifier"]
    assert payload["permission_policy"] == "deterministic_verification_first"
    assert payload["reason_code"] == "quality_evidence"
