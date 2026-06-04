"""Runtime capability and phase-decision policy for optimization surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_RUNTIMES = {"claude_agent_sdk", "codex_sdk"}


@dataclass(frozen=True)
class RuntimeCapability:
    id: str
    label: str
    native: bool
    native_signal: str
    fallback: str
    diagnostic_gap: str
    recommendation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "native": self.native,
            "native_signal": self.native_signal,
            "fallback": self.fallback,
            "diagnostic_gap": self.diagnostic_gap,
            "recommendation": self.recommendation,
        }


def normalize_runtime(runtime: str) -> str:
    """Return the builder runtime kind or reject unsupported values."""

    value = str(runtime or "").strip()
    if value in {"claude", "claude_agent_sdk"}:
        return "claude_agent_sdk"
    if value in {"codex", "codex_cli", "codex_sdk"} or value.startswith("codex"):
        return "codex_sdk"
    raise ValueError(f"Unsupported runtime SDK: {value or '(empty)'}")


def runtime_capability_matrix(runtime: str) -> dict[str, Any]:
    """Return native capabilities and fallbacks for the selected runtime."""

    runtime_kind = normalize_runtime(runtime)
    capabilities = (
        _claude_capabilities() if runtime_kind == "claude_agent_sdk" else _codex_capabilities()
    )
    gaps = [item.diagnostic_gap for item in capabilities if item.diagnostic_gap]
    return {
        "runtime": runtime_kind,
        "supported_runtimes": sorted(SUPPORTED_RUNTIMES),
        "capabilities": [item.as_dict() for item in capabilities],
        "native_count": sum(1 for item in capabilities if item.native),
        "fallback_count": sum(1 for item in capabilities if not item.native),
        "diagnostic_gaps": gaps,
        "principle": "same builder UX, runtime-specific execution intelligence",
    }


def phase_runtime_decisions(
    runtime: str,
    *,
    aggregates: dict[str, Any] | None = None,
    optimization: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return phase-level runtime decisions for dashboard and run observability."""

    runtime_kind = normalize_runtime(runtime)
    aggregates = aggregates or {}
    optimization = optimization or {}
    candidates = deterministic_script_candidates(aggregates, optimization)
    deterministic_policy = (
        "reuse_or_create_script_candidates"
        if candidates
        else "prefer_script_when_operation_repeats"
    )
    subagent_policy = "bounded_sidecar_only"
    if runtime_kind == "claude_agent_sdk":
        question_route = "ask_user_question_top_level"
        approval_route = "claude_permission_or_hook_review"
        telemetry_route = "native_result_message_plus_otel"
        hook_route = "claude_hooks_for_deterministic_enforcement"
        context_route = "project_memory_plus_compaction"
        planning_subagents = ("repo-researcher",)
        design_subagents = ("repo-researcher",)
        implementation_subagents: tuple[str, ...] = ()
        verification_subagents = ("build-verifier", "browser-verifier")
        recovery_subagents = ("repo-researcher",)
        integration_subagents = ("security-reviewer", "pr-reviewer")
        hook_policy = "session_start_tool_audit_subagent_stop_evidence"
    else:
        question_route = "request_user_input_top_level"
        approval_route = "codex_granular_approval_policy"
        telemetry_route = "codex_app_server_events_plus_rate_card"
        hook_route = "codex_rules_or_builder_guardrails"
        context_route = "stable_prefix_dynamic_tail_tool_search"
        planning_subagents = ()
        design_subagents = ()
        implementation_subagents = ()
        verification_subagents = ()
        recovery_subagents = ()
        integration_subagents = ()
        hook_policy = "builder_guardrails_and_codex_rules"

    return [
        _phase_decision(
            "requirements",
            runtime_kind,
            "interactive_default",
            question_route,
            "no_subagents_for_user_questions",
            "requirements_questions",
            "locked requirements and explicit approvals",
            permission_policy="interactive_user_questions_only",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "planning",
            runtime_kind,
            "risk_based_model_effort",
            "capability_matrix_plus_sprint_plan",
            subagent_policy,
            "sprint_scope_and_task_routing",
            "model/effort, tool route, script candidates, verification route",
            selected_subagents=planning_subagents,
            permission_policy="read_only_planning",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "design",
            runtime_kind,
            "stronger_reasoning_only_on_architecture_risk",
            context_route,
            subagent_policy,
            "design_risk_gate",
            "flow, state model, module boundaries, test strategy",
            selected_subagents=design_subagents,
            permission_policy="read_only_design",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "implementation",
            runtime_kind,
            "lowest_reliable_effort_for_known_files",
            deterministic_policy,
            "disjoint_write_sets_only",
            "implementation_efficiency",
            "changed files, command evidence, compact task briefs",
            selected_subagents=implementation_subagents,
            permission_policy="workspace_write_with_argv_shell",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "integration",
            runtime_kind,
            "cheap_evidence_summary_with_risk_review",
            "changed_files_pr_evidence_and_security_review",
            "sidecar_review_only",
            "change_evidence_summary",
            "changed files, validation commands, residual risk, PR evidence",
            selected_subagents=integration_subagents,
            permission_policy="read_only_evidence_summary",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "verification",
            runtime_kind,
            "cheap_deterministic_first",
            "tests_build_browser_evidence",
            "sidecar_browser_or_eval_only",
            "quality_evidence",
            "test/build/browser proof and acceptance check",
            selected_subagents=verification_subagents,
            permission_policy="deterministic_verification_first",
            hook_policy=hook_policy,
        ),
        _phase_decision(
            "recovery",
            runtime_kind,
            "diagnose_before_rerun",
            f"{telemetry_route}; {approval_route}; {hook_route}",
            "only_if_parallel_diagnosis_needed",
            "preserved_state_recovery",
            "logs, telemetry, workspace state, provider limits, blocked handoff",
            selected_subagents=recovery_subagents,
            permission_policy="read_only_recovery_then_resume",
            hook_policy=hook_policy,
        ),
    ]


def deterministic_script_candidates(
    aggregates: dict[str, Any] | None,
    optimization: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Detect repeatable operations that should become deterministic scripts."""

    aggregates = aggregates or {}
    optimization = optimization or {}
    override = aggregates.get("deterministic_script_candidates_override")
    if isinstance(override, list):
        return [dict(item) for item in override if isinstance(item, dict)]
    by_agent = {str(row.get("agent_name") or ""): row for row in aggregates.get("by_agent", [])}
    available_scripts = {str(item) for item in aggregates.get("available_scripts", [])}
    tool_state = aggregates.get("tool_observability", {})
    tool_counts = {
        str(row.get("tool_name") or ""): int(row.get("calls") or 0)
        for row in tool_state.get("tool_counts", [])
    }
    candidates: list[dict[str, Any]] = []
    build_verifier = by_agent.get("build-verifier", {})
    build_verifier_runs = int(build_verifier.get("runs") or 0)
    if build_verifier_runs >= 2:
        build_verify_available = "build_verify" in available_scripts
        candidates.append(
            _script_candidate(
                "build_verify_script",
                "build-verifier reruns detected",
                (
                    "Use builder script run build_verify for deterministic lint/build/test/app-smoke proof."
                    if build_verify_available
                    else "Create or reuse one deterministic test/build/browser proof command."
                ),
                "high",
                estimated_savings_tokens=(
                    _agent_noncached_plus_output(build_verifier) // max(build_verifier_runs, 1)
                )
                * max(build_verifier_runs - 1, 0),
                estimated_savings_basis="repeated build-verifier non-cached plus output tokens",
                status="available" if build_verify_available else "candidate",
                command=(
                    "builder script run build_verify --args "
                    '\'{"app_url":"http://127.0.0.1:<port>","paths":["/"]}\' --json'
                    if build_verify_available
                    else ""
                ),
                owner_lane="builder_source",
                next_actor="builder",
                handoff=(
                    "Keep script promotion in Builder. The optimization agent may only run the "
                    "resulting command for App work."
                ),
            )
        )
    pr_creator = by_agent.get("pr-creator", {})
    if int(pr_creator.get("runs") or 0) > 0:
        change_evidence_available = "change_evidence" in available_scripts
        candidates.append(
            _script_candidate(
                "change_evidence_collector",
                "model-backed PR/evidence lane used",
                (
                    "Use builder script run change_evidence for deterministic changed-file evidence unless a real PR target exists."
                    if change_evidence_available
                    else "Use deterministic changed-file and command-evidence collection unless a real PR target exists."
                ),
                "medium",
                estimated_savings_tokens=_agent_noncached_plus_output(pr_creator),
                estimated_savings_basis="replace model-backed evidence lane with deterministic file evidence",
                status="available" if change_evidence_available else "candidate",
                command=(
                    "builder script run change_evidence --args '{}' --json"
                    if change_evidence_available
                    else ""
                ),
                owner_lane="builder_source",
                next_actor="builder",
                handoff=(
                    "Change the Builder evidence lane unless the managed repo only needs to run "
                    "an already available evidence command."
                ),
            )
        )
    if tool_counts.get("Bash", 0) >= 5 or tool_counts.get("command", 0) >= 5:
        candidates.append(
            _script_candidate(
                "command_sequence_wrapper",
                "repeated shell commands detected",
                "Wrap repeated setup, server, lint, test, or environment checks in a builder command.",
                "medium",
                owner_lane="managed_repo_environment",
                next_actor="optimization_agent",
                handoff=(
                    "Hand to the optimization agent when the repeated commands are repo-local "
                    "setup, test, build, or browser-smoke steps."
                ),
            )
        )
    repeated_retrieval = tool_state.get("repeated_retrieval_signal", {})
    if isinstance(repeated_retrieval, dict) and repeated_retrieval.get("detected"):
        candidates.append(
            _script_candidate(
                "bounded_retrieval_shortcut",
                "repeated broad retrieval detected",
                "Use knowledge or memory summary retrieval before file walking.",
                "medium",
                owner_lane="builder_source",
                next_actor="builder",
                handoff=(
                    "Fix Builder retrieval policy, memory, or knowledge routing before asking the "
                    "optimization agent to tune a specific managed repo."
                ),
            )
        )
    flags = optimization.get("active_avoidable_cost_flags")
    if not isinstance(flags, list):
        flags = optimization.get("avoidable_cost_flags") or []
    flag_names = {str(item.get("flag") if isinstance(item, dict) else item) for item in flags}
    if flag_names.intersection({"large_command_output", "chunk_pressure_large_event"}):
        candidates.append(
            _script_candidate(
                "output_truncation_artifact",
                "large output or chunk pressure detected",
                "Store full output as evidence and reinject only compact JSON summaries.",
                "high",
                owner_lane="builder_source",
                next_actor="builder",
                handoff=(
                    "Fix Builder agent/runtime output reinjection. Do not hand this to the "
                    "generated-app optimization agent."
                ),
            )
        )
    return sorted(candidates, key=_candidate_priority, reverse=True)


def runtime_decision_summary(
    runtime: str,
    *,
    aggregates: dict[str, Any] | None = None,
    optimization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact decision payload shared by metrics, logs, and runs."""

    matrix = runtime_capability_matrix(runtime)
    decisions = phase_runtime_decisions(runtime, aggregates=aggregates, optimization=optimization)
    scripts = deterministic_script_candidates(aggregates, optimization)
    return {
        "runtime": matrix["runtime"],
        "capability_gaps": matrix["diagnostic_gaps"],
        "native_capability_count": matrix["native_count"],
        "fallback_capability_count": matrix["fallback_count"],
        "phase_decisions": decisions,
        "deterministic_script_candidates": scripts,
        "next": _next_decision_action(matrix, scripts),
    }


def optimization_decision_summary(
    runtime: str,
    *,
    aggregates: dict[str, Any] | None = None,
    optimization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the compact optimization decision an agent should act on."""

    runtime_kind = normalize_runtime(runtime)
    aggregates = aggregates or {}
    optimization = optimization or {}
    scripts = deterministic_script_candidates(aggregates, optimization)
    recommended = str(optimization.get("recommended_next_change") or "")
    active_drivers = optimization.get("active_top_cost_drivers")
    driver_source = (
        active_drivers
        if isinstance(active_drivers, list) and any(
            int(item.get("raw_tokens") or 0) > 0
            for item in active_drivers
            if isinstance(item, dict)
        )
        else optimization.get("top_cost_drivers")
    )
    top_driver = (driver_source or [{}])[0]
    top_driver_name = (
        str(top_driver.get("agent_name") or "") if isinstance(top_driver, dict) else ""
    )
    top_driver_tokens = (
        int(top_driver.get("raw_tokens") or 0)
        + int(top_driver.get("noncached_plus_output_tokens") or 0)
        if isinstance(top_driver, dict)
        else 0
    )
    provider_limit_count = int(aggregates.get("provider_limits", {}).get("count") or 0)
    if scripts:
        next_action = (
            "use_available_deterministic_script"
            if scripts[0].get("status") == "available"
            else "convert_repeated_operations_to_deterministic_scripts"
        )
        target_area = scripts[0]["code"]
        reason = scripts[0]["trigger"]
    elif provider_limit_count > 0 and top_driver_tokens == 0:
        next_action = "resume_after_provider_limit_reset"
        target_area = "runtime_recovery"
        reason = "provider limit blocked run evidence"
    elif recommended == "maintain_current_flow":
        next_action = "maintain_current_flow"
        target_area = "observability"
        reason = "no active avoidable optimization driver"
    elif recommended:
        next_action = recommended
        target_area = _target_area_from_recommendation(recommended, top_driver_name)
        reason = "metrics recommended next change"
    elif top_driver_name and top_driver_tokens > 0:
        next_action = f"reduce_{top_driver_name}_raw_tokens"
        target_area = top_driver_name
        reason = "highest raw-token driver"
    elif optimization.get("avoidable_cost_flags"):
        next_action = "remove_avoidable_runtime_flags"
        target_area = "runtime_policy"
        reason = "avoidable-cost flags detected"
    else:
        next_action = "collect_more_run_evidence"
        target_area = "observability"
        reason = "no clear optimization driver yet"
    return {
        "runtime": runtime_kind,
        "primary_score_surface": "metrics",
        "diagnostic_surface": "observability",
        "cli_surface": "builder metrics show --json --full",
        "next_action": next_action,
        "target_area": target_area,
        "reason": reason,
        "top_driver": top_driver if isinstance(top_driver, dict) else {},
        "deterministic_script_candidates": scripts,
        "estimated_script_savings_tokens": sum(
            int(item.get("estimated_savings_tokens") or 0) for item in scripts
        ),
        "model_effort_action": _model_effort_action(top_driver_name),
        "subagent_action": "keep_subagents_for_bounded_sidecar_work_only",
        "ui_placement": {
            "metrics": "scores, trends, costs, model/effort distribution, and top drivers",
            "observability": "diagnostic gaps, recommendations, capability matrix, and next tuning action",
        },
    }


def _target_area_from_recommendation(recommendation: str, fallback: str) -> str:
    if recommendation.startswith("reduce_") and recommendation.endswith("_raw_tokens"):
        return recommendation.removeprefix("reduce_").removesuffix("_raw_tokens")
    if recommendation == "truncate_tool_output_before_reinjection":
        return "tool_output_reinjection"
    if recommendation == "trim_prompt_segments_over_phase_budget":
        return "prompt_budget"
    if recommendation == "skip_model_pr_creator_for_low_risk_local_sprints":
        return "pr_creator"
    return fallback or "runtime_policy"


def _phase_decision(
    phase: str,
    runtime: str,
    model_effort: str,
    tool_route: str,
    subagent_policy: str,
    reason_code: str,
    expected_evidence: str,
    *,
    selected_subagents: tuple[str, ...] = (),
    permission_policy: str = "phase_default_permissions",
    hook_policy: str = "runtime_default_hooks",
) -> dict[str, Any]:
    return {
        "phase": phase,
        "selected_runtime": runtime,
        "model_effort": model_effort,
        "tool_route": tool_route,
        "subagent_policy": subagent_policy,
        "context_strategy": "phase_compact_dynamic_context",
        "selected_subagents": list(selected_subagents),
        "permission_policy": permission_policy,
        "hook_policy": hook_policy,
        "expected_evidence": expected_evidence,
        "reason_code": reason_code,
    }


def _script_candidate(
    code: str,
    trigger: str,
    recommendation: str,
    severity: str,
    *,
    estimated_savings_tokens: int = 0,
    estimated_savings_basis: str = "",
    status: str = "candidate",
    command: str = "",
    owner_lane: str = "builder_source",
    next_actor: str = "builder",
    handoff: str = "Change Builder runtime policy or agent prompt/tool contracts.",
) -> dict[str, Any]:
    return {
        "code": code,
        "trigger": trigger,
        "recommendation": recommendation,
        "severity": severity,
        "status": status,
        "command": command,
        "owner_lane": owner_lane,
        "next_actor": next_actor,
        "handoff": handoff,
        "estimated_savings_tokens": max(int(estimated_savings_tokens or 0), 0),
        "estimated_savings_basis": estimated_savings_basis,
    }


def _agent_noncached_plus_output(row: dict[str, Any]) -> int:
    if "noncached_plus_output_tokens" in row:
        return max(int(row.get("noncached_plus_output_tokens") or 0), 0)
    input_tokens = int(row.get("input_tokens") or 0)
    output_tokens = int(row.get("output_tokens") or 0)
    cached_tokens = int(row.get("cached_tokens") or 0)
    return max(input_tokens - cached_tokens, 0) + output_tokens


def _candidate_priority(candidate: dict[str, Any]) -> tuple[int, int, int]:
    status_rank = 1 if candidate.get("status") == "available" else 0
    severity_rank = {"high": 3, "medium": 2, "low": 1}.get(str(candidate.get("severity")), 0)
    savings = int(candidate.get("estimated_savings_tokens") or 0)
    return (status_rank, savings, severity_rank)


def _model_effort_action(top_driver_name: str) -> str:
    if top_driver_name == "code-gen":
        return "tighten_task_briefs_before_lowering_implementation_effort"
    if top_driver_name in {"build-verifier", "pr-creator"}:
        return "replace_repeatable_model_work_with_deterministic_evidence"
    return "keep_phase_risk_based_model_effort"


def _next_decision_action(matrix: dict[str, Any], scripts: list[dict[str, Any]]) -> str:
    if matrix["diagnostic_gaps"]:
        return "close_runtime_capability_gaps"
    if scripts:
        return "convert_repeated_operations_to_scripts"
    return "collect_phase_decision_evidence"


def _claude_capabilities() -> tuple[RuntimeCapability, ...]:
    return (
        RuntimeCapability(
            "user_questions",
            "User questions",
            True,
            "AskUserQuestion top-level",
            "None",
            "",
            "Keep operator questions out of subagents.",
        ),
        RuntimeCapability(
            "approvals",
            "Approvals",
            True,
            "permission callbacks and human review",
            "approval gates",
            "",
            "Persist approval state and resume the same run.",
        ),
        RuntimeCapability(
            "model_effort",
            "Model and thinking",
            True,
            "model plus ThinkingConfig",
            "agent runtime policy",
            "",
            "Route thinking by phase risk.",
        ),
        RuntimeCapability(
            "subagents",
            "Subagents",
            True,
            "SDK agents and .claude/agents",
            "main-lane execution",
            "",
            "Use isolated specialists only when context or policy changes.",
        ),
        RuntimeCapability(
            "hooks",
            "Hooks and guardrails",
            True,
            "PreToolUse/PostToolUse/SubagentStart/SubagentStop",
            "builder guardrails",
            "",
            "Use hooks for deterministic enforcement and telemetry.",
        ),
        RuntimeCapability(
            "telemetry",
            "Telemetry and cost",
            True,
            "ResultMessage plus OTEL",
            "builder estimates",
            "",
            "Prefer native cost, usage, model_usage, turns, and stop reason.",
        ),
        RuntimeCapability(
            "tool_routing",
            "Tool routing",
            True,
            "tool permissions and MCP",
            "builder tool allowlist",
            "",
            "Keep safe discovery auto-approved.",
        ),
        RuntimeCapability(
            "context",
            "Context management",
            True,
            "Claude compaction plus project memory",
            "builder compact briefs",
            "",
            "Use memory and compact handoffs before broad rereads.",
        ),
        RuntimeCapability(
            "deterministic_work",
            "Deterministic work",
            False,
            "No single native script planner",
            "builder scripts and quality gates",
            "deterministic_script_candidates",
            "Promote repeated operations into scripts.",
        ),
        RuntimeCapability(
            "workspace_recovery",
            "Workspace and recovery",
            True,
            "stable cwd and resume state",
            "builder workspaces",
            "",
            "Recover from persisted state before rerunning.",
        ),
    )


def _codex_capabilities() -> tuple[RuntimeCapability, ...]:
    return (
        RuntimeCapability(
            "user_questions",
            "User questions",
            True,
            "request_user_input top-level",
            "approval cards",
            "",
            "Keep operator questions out of subagents.",
        ),
        RuntimeCapability(
            "approvals",
            "Approvals",
            True,
            "granular approval policy and rules",
            "builder approval gates",
            "",
            "Use SDK policy for risky actions.",
        ),
        RuntimeCapability(
            "model_effort",
            "Model and effort",
            True,
            "model, review_model, effort, model catalog",
            "agent runtime policy",
            "",
            "Route model and effort by phase risk.",
        ),
        RuntimeCapability(
            "subagents",
            "Subagents",
            True,
            "Codex subagents with max threads/depth",
            "main-lane execution",
            "",
            "Use only for bounded sidecar work.",
        ),
        RuntimeCapability(
            "hooks",
            "Hooks and guardrails",
            False,
            "No Claude-style subagent hook parity in current path",
            "Codex rules plus builder guardrails",
            "codex_hook_parity",
            "Expose the fallback instead of pretending parity.",
        ),
        RuntimeCapability(
            "telemetry",
            "Telemetry and cost",
            True,
            "app-server events, token usage, rate-card credits",
            "builder estimates",
            "",
            "Track raw tokens, noncached+output, credits, and chunk pressure.",
        ),
        RuntimeCapability(
            "tool_routing",
            "Tool routing",
            True,
            "tool_search and deferred tool loading",
            "builder tool allowlist",
            "",
            "Defer large tool schemas where possible.",
        ),
        RuntimeCapability(
            "context",
            "Context management",
            True,
            "prompt caching, context window, auto-compaction",
            "builder compact briefs",
            "",
            "Keep stable prefixes and dynamic context late.",
        ),
        RuntimeCapability(
            "deterministic_work",
            "Deterministic work",
            False,
            "No single native script planner",
            "builder scripts and quality gates",
            "deterministic_script_candidates",
            "Promote repeated operations into scripts.",
        ),
        RuntimeCapability(
            "workspace_recovery",
            "Workspace and recovery",
            True,
            "workspace cwd and app-server run evidence",
            "builder workspaces",
            "",
            "Diagnose from events and state before rerun.",
        ),
    )
