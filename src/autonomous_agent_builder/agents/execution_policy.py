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
    max_thinking_tokens: int | None
    context_strategy: str
    subagents: tuple[str, ...] = ()
    permission_policy: str = "phase_default_permissions"
    hook_policy: str = "workspace_boundary_bash_argv_tool_audit"
    reason_code: str = "role_default"

    def to_payload(self) -> dict[str, Any]:
        """Return the stable agent-facing policy payload stored with run evidence."""
        return {
            "model": self.model,
            "effort": self.effort,
            "max_thinking_tokens": self.max_thinking_tokens,
            "context_strategy": self.context_strategy,
            "selected_subagents": list(self.subagents),
            "permission_policy": self.permission_policy,
            "hook_policy": self.hook_policy,
            "reason_code": self.reason_code,
        }


_AGENT_POLICY: dict[str, tuple[str, int | None, str, tuple[str, ...], str, str, str]] = {
    "chat": (
        "medium",
        4096,
        "interactive_bounded_retrieval",
        (),
        "interactive_read_first",
        "workspace_boundary_bash_argv_tool_audit",
        "interactive_help",
    ),
    "init-project-chat": (
        "medium",
        4096,
        "interactive_project_bootstrap",
        (),
        "interactive_bootstrap",
        "workspace_boundary_bash_argv_tool_audit",
        "day0_bootstrap",
    ),
    "planner": (
        "high",
        8192,
        "compact_plan_artifact",
        ("repo-researcher",),
        "read_only_planning",
        "session_start_context_and_tool_audit",
        "sprint_scope_and_task_routing",
    ),
    "designer": (
        "high",
        12288,
        "compact_design_handoff",
        ("repo-researcher",),
        "read_only_design",
        "session_start_context_and_tool_audit",
        "design_risk_gate",
    ),
    "code-gen": (
        "medium",
        4096,
        "scripted_repeatable_work",
        (),
        "workspace_write_with_argv_shell",
        "workspace_boundary_bash_argv_tool_audit",
        "implementation_efficiency",
    ),
    "integration-resolver": (
        "medium",
        4096,
        "bounded_conflict_resolution",
        ("security-reviewer",),
        "workspace_write_with_review_sidecar",
        "workspace_boundary_bash_argv_tool_audit_subagent_contract",
        "integration_risk_review",
    ),
    "pr-creator": (
        "low",
        2048,
        "evidence_summary_only",
        ("pr-reviewer",),
        "read_only_evidence_summary",
        "tool_audit_subagent_contract",
        "change_evidence_summary",
    ),
    "build-verifier": (
        "low",
        1024,
        "scripted_verification",
        ("build-verifier", "browser-verifier"),
        "deterministic_verification_first",
        "workspace_boundary_bash_argv_tool_audit_stop_evidence",
        "quality_evidence",
    ),
    "feature-verifier": (
        "medium",
        4096,
        "agentic_acceptance_then_durable_playwright",
        ("browser-verifier",),
        "workspace_write_after_acceptance_judgment",
        "workspace_boundary_bash_argv_tool_audit_subagent_contract",
        "feature_acceptance_before_test_generation",
    ),
    "documentation-bridge": (
        "low",
        2048,
        "delegated_doc_refresh",
        ("documentation-agent",),
        "documentation_publish_tools_only",
        "kb_publish_contract_and_subagent_stop",
        "repo_docs_refresh",
    ),
    "optimization-agent": (
        "medium",
        4096,
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
        max_thinking_tokens,
        context_strategy,
        default_subagents,
        permission_policy,
        hook_policy,
        reason_code,
    ) = _AGENT_POLICY.get(
        agent_def.name,
        (
            "medium",
            4096,
            "bounded_default",
            (),
            "phase_default_permissions",
            "workspace_boundary_bash_argv_tool_audit",
            "role_default",
        ),
    )
    subagents = tuple(requested_subagents or default_subagents)
    return AgentRuntimePolicy(
        model=_model_for_agent(agent_def, settings),
        effort=effort,
        max_thinking_tokens=max_thinking_tokens,
        context_strategy=context_strategy,
        subagents=subagents,
        permission_policy=permission_policy,
        hook_policy=hook_policy,
        reason_code=reason_code,
    )


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
