"""Model, thinking, subagent, and context policy for builder-owned agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autonomous_agent_builder.agents.definitions import AgentDefinition, SubagentDefinition
from autonomous_agent_builder.config import Settings


@dataclass(frozen=True)
class AgentRuntimePolicy:
    """Resolved execution policy for one SDK run."""

    model: str
    effort: str
    thinking: dict | None
    context_strategy: str
    autocompact_enabled: bool = False
    task_budget_tokens: int | None = None
    subagents: tuple[str, ...] = ()
    permission_policy: str = "phase_default_permissions"
    hook_policy: str = "workspace_boundary_bash_argv_tool_audit"
    reason_code: str = "role_default"

    def to_payload(self) -> dict[str, Any]:
        """Return the stable agent-facing policy payload stored with run evidence."""
        return {
            "model": self.model,
            "effort": self.effort,
            "thinking": self.thinking,
            "context_strategy": self.context_strategy,
            "autocompact_enabled": self.autocompact_enabled,
            "task_budget_tokens": self.task_budget_tokens,
            "selected_subagents": list(self.subagents),
            "permission_policy": self.permission_policy,
            "hook_policy": self.hook_policy,
            "reason_code": self.reason_code,
        }


# Per-agent token budgets retained as builder-owned policy evidence. Do not pass
# them as Claude Agent SDK `task_budget` request options: current Claude runtime
# models can reject user-configurable task budgets even when the SDK constructor
# accepts the option.
_TASK_BUDGET_TOKENS: dict[str, int] = {
    "planner": 120_000,  # 20 turns, opus reasoning-heavy
    "designer": 120_000,  # 20 turns, opus architecture work
    "scaffold": 60_000,  # 12 turns, sonnet stack-decision + minimum config
    "code-gen": 150_000,  # 30 turns, sonnet implementation
    "integration-resolver": 100_000,  # 20 turns, conflict resolution
    "feature-verifier": 120_000,  # 24 turns, acceptance + test generation
}

# Context strategies where autocompact should be enabled.
# These are the long-running phases (≥ 20 turns) where context accumulation
# will hit the limit and degrade output quality without auto-summarisation.
_AUTOCOMPACT_STRATEGIES: frozenset[str] = frozenset(
    {
        "compact_plan_artifact",  # planner — 20 turns
        "compact_design_handoff",  # designer — 20 turns
        "scripted_repeatable_work",  # code-gen — 30 turns
        "bounded_conflict_resolution",  # integration-resolver — 20 turns
        "agentic_acceptance_then_durable_playwright",  # feature-verifier — 24 turns
    }
)

_AGENT_POLICY: dict[str, tuple[str, str, tuple[str, ...], str, str, str]] = {
    "chat": (
        "medium",
        "interactive_bounded_retrieval",
        (),
        "interactive_read_first",
        "workspace_boundary_bash_argv_tool_audit",
        "interactive_help",
    ),
    "init-project-chat": (
        "medium",
        "interactive_project_bootstrap",
        (),
        "interactive_bootstrap",
        "workspace_boundary_bash_argv_tool_audit",
        "day0_bootstrap",
    ),
    "planner": (
        "high",
        "compact_plan_artifact",
        ("repo-researcher",),
        "read_only_planning",
        "session_start_context_and_tool_audit",
        "sprint_scope_and_task_routing",
    ),
    "designer": (
        "high",
        "compact_design_handoff",
        ("repo-researcher",),
        "read_only_design",
        "session_start_context_and_tool_audit",
        "design_risk_gate",
    ),
    "scaffold": (
        "medium",
        "scripted_repeatable_work",
        (),
        "workspace_write_with_argv_shell",
        "workspace_boundary_bash_argv_tool_audit",
        "scaffold_efficiency",
    ),
    "code-gen": (
        "high",
        "scripted_repeatable_work",
        (),
        "workspace_write_with_argv_shell",
        "workspace_boundary_bash_argv_tool_audit",
        "implementation_efficiency",
    ),
    "integration-resolver": (
        "medium",
        "bounded_conflict_resolution",
        ("security-reviewer",),
        "workspace_write_with_review_sidecar",
        "workspace_boundary_bash_argv_tool_audit_subagent_contract",
        "integration_risk_review",
    ),
    "pr-creator": (
        "low",
        "evidence_summary_only",
        ("pr-reviewer",),
        "read_only_evidence_summary",
        "tool_audit_subagent_contract",
        "change_evidence_summary",
    ),
    "build-verifier": (
        "low",
        "scripted_verification",
        ("build-verifier", "browser-verifier"),
        "deterministic_verification_first",
        "workspace_boundary_bash_argv_tool_audit_stop_evidence",
        "quality_evidence",
    ),
    "feature-verifier": (
        "medium",
        "agentic_acceptance_then_durable_playwright",
        ("browser-verifier",),
        "workspace_write_after_acceptance_judgment",
        "workspace_boundary_bash_argv_tool_audit_subagent_contract",
        "feature_acceptance_before_test_generation",
    ),
    "documentation-bridge": (
        "low",
        "delegated_doc_refresh",
        ("documentation-agent",),
        "documentation_publish_tools_only",
        "kb_publish_contract_and_subagent_stop",
        "repo_docs_refresh",
    ),
    "optimization-agent": (
        "medium",
        "post_ship_structured_observability_review",
        (),
        "read_only_preflight_then_exact_candidate_write",
        "workspace_boundary_bash_argv_tool_audit_exact_command_validation",
        "post_ship_delivery_system_optimization",
    ),
}


def resolve_agent_runtime_policy(
    agent_def: AgentDefinition,
    settings: Settings,
    requested_subagents: tuple[str, ...] | None = None,
) -> AgentRuntimePolicy:
    """Resolve the runtime policy from stable product settings and agent role."""
    (
        effort,
        context_strategy,
        default_subagents,
        permission_policy,
        hook_policy,
        reason_code,
    ) = _AGENT_POLICY.get(
        agent_def.name,
        (
            "medium",
            "bounded_default",
            (),
            "phase_default_permissions",
            "workspace_boundary_bash_argv_tool_audit",
            "role_default",
        ),
    )
    subagents = tuple(requested_subagents or default_subagents)
    model = _model_for_agent(agent_def, settings)
    return AgentRuntimePolicy(
        model=model,
        effort=effort,
        thinking=_thinking_for_model(model),
        context_strategy=context_strategy,
        autocompact_enabled=context_strategy in _AUTOCOMPACT_STRATEGIES,
        task_budget_tokens=_TASK_BUDGET_TOKENS.get(agent_def.name),
        subagents=subagents,
        permission_policy=permission_policy,
        hook_policy=hook_policy,
        reason_code=reason_code,
    )


def _thinking_for_model(model: str) -> dict | None:
    """Return adaptive thinking config for Claude models that support it.

    Haiku and non-Claude models (e.g. Codex gpt-*) get None — thinking is
    either unsupported or handled by the foreign runtime. Sonnet and Opus
    use adaptive thinking; the effort parameter controls depth.
    """
    if not model or model == "haiku" or "haiku" in model or model.startswith("gpt"):
        return None
    return {"type": "adaptive"}


def resolve_subagent_model(subagent_def: SubagentDefinition) -> str:
    """Return the cheapest configured model for a bounded subagent role."""
    if subagent_def.name in {
        "documentation-agent",
        "repo-researcher",
        "browser-verifier",
        "build-verifier",
        "pr-reviewer",
    }:
        return "haiku"
    if subagent_def.name == "security-reviewer":
        return "sonnet"
    return subagent_def.model


def _model_for_agent(agent_def: AgentDefinition, settings: Settings) -> str:
    runtime_model = _non_claude_runtime_model(settings)
    if runtime_model:
        return runtime_model
    if agent_def.name == "planner":
        return settings.agent.planning_model
    if agent_def.name == "designer":
        return settings.agent.design_model
    if agent_def.name in {
        "code-gen",
        "init-project-chat",
        "documentation-bridge",
        "integration-resolver",
        "optimization-agent",
        "feature-verifier",
    }:
        return settings.agent.implementation_model
    if agent_def.name in {"pr-creator", "build-verifier"}:
        return settings.agent.pr_model
    return agent_def.model


def _non_claude_runtime_model(settings: Settings) -> str | None:
    """Return the selected non-Claude runtime model when the active SDK owns model choice."""
    try:
        from autonomous_agent_builder.runtime.factory import resolve_runtime_config

        runtime_config = resolve_runtime_config(settings)
    except Exception:
        return None

    if runtime_config.get("sdk") == "claude":
        return None
    model = runtime_config.get("model")
    return str(model) if model else None
