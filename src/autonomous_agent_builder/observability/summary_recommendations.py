"""Deterministic recommendation rules extracted from observability summary."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.observability.runtime_optimization import (
    deterministic_script_candidates,
)


def _deterministic_recommendations(
    telemetry_health: dict[str, Any],
    coverage: dict[str, Any],
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for candidate in deterministic_script_candidates(aggregates, optimization):
        candidate_code = str(candidate.get("code") or "")
        candidate_evidence = {
            "estimated_savings_tokens": candidate.get("estimated_savings_tokens", 0),
            "basis": candidate.get("estimated_savings_basis", ""),
        }
        if candidate_code == "output_truncation_artifact":
            candidate_evidence["avoidable_cost_flags"] = [
                item
                for item in optimization.get("avoidable_cost_flags", [])
                if isinstance(item, dict)
                and str(item.get("flag") or "")
                in {"large_command_output", "chunk_pressure_large_event"}
            ]
        if candidate_code == "bounded_retrieval_shortcut":
            candidate_evidence["repeated_retrieval_signal"] = aggregates.get(
                "tool_observability", {}
            ).get("repeated_retrieval_signal", {})
        recommendations.append(
            _deterministic_recommendation(
                code=f"script_candidate_{candidate['code']}",
                severity=candidate["severity"],
                trigger=str(candidate.get("trigger") or ""),
                recommendation=str(candidate.get("recommendation") or ""),
                next_action="promote_or_reuse_builder_script_candidate",
                evidence=candidate_evidence,
                owner_lane=str(candidate.get("owner_lane") or ""),
                next_actor=str(candidate.get("next_actor") or ""),
                handoff=str(candidate.get("handoff") or ""),
                evidence_source=_candidate_evidence_source(candidate_code),
                evidence_command="builder metrics show --json",
                priority_reason=str(candidate.get("trigger") or ""),
            )
        )
    selected = telemetry_health.get("selected_runtime")
    native_key = "codex_native" if selected == "codex_sdk" else "claude_native"
    native = (
        telemetry_health.get(native_key, {})
        if isinstance(telemetry_health.get(native_key), dict)
        else {}
    )
    collector_status = str(
        native.get("collector_status") or native.get("collector", {}).get("status") or ""
    )
    if collector_status in {"missing", "configured_unreachable", "invalid_endpoint"}:
        recommendations.append(
            _deterministic_recommendation(
                code="telemetry_collector_blocked",
                severity="high",
                trigger=f"{native_key}.collector_status={collector_status or 'missing'}",
                recommendation="Block telemetry readiness until the selected runtime has a usable collector path.",
                next_action="start_or_fix_otel_collector_then_recheck_observability",
                evidence={
                    "selected_runtime": selected,
                    "collector_status": collector_status or "missing",
                },
                owner_lane="managed_repo_environment",
                next_actor="optimization_agent",
                handoff=(
                    "Hand to the optimization agent when the selected runtime needs repo-local "
                    "telemetry collector setup or environment repair."
                ),
                evidence_source="telemetry health",
                evidence_command="builder metrics show --json",
                priority_reason="selected runtime collector is not usable",
            )
        )
    if aggregates.get("tool_observability", {}).get("missing_tool_events"):
        recommendations.append(
            _deterministic_recommendation(
                code="tool_event_instrumentation_gap",
                severity="medium",
                trigger="agent_run_events table exists with zero tool events",
                recommendation="Fix tool-event persistence before trusting routing or tool-use recommendations.",
                next_action="inspect_sdk_post_tool_hook_and_agent_run_events_write_path",
                evidence=aggregates.get("tool_observability", {}),
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Fix Builder event persistence before tuning the managed repo.",
                evidence_source="tool event ledger",
                evidence_command="builder metrics show --json --full --limit 10",
                priority_reason="tool-use evidence is missing, so routing recommendations cannot be trusted",
            )
        )
    raw_tokens = int(optimization.get("raw_token_total") or 0)
    cache_ratio = float(optimization.get("cache_ratio") or 0.0)
    benchmark = optimization.get("benchmark") if isinstance(optimization, dict) else {}
    benchmark = benchmark if isinstance(benchmark, dict) else {}
    target_max = int(benchmark.get("target_max_raw_tokens") or 0)
    if raw_tokens > 0 and target_max > 0 and str(benchmark.get("status") or "") == "over_target":
        recommendations.append(
            _deterministic_recommendation(
                code="runtime_token_budget_over_target",
                severity="high",
                trigger=f"raw tokens {raw_tokens} exceed target {target_max}",
                recommendation="Cut the largest runtime token driver before adding new feature work.",
                next_action="inspect_top_cost_driver_and_remove_avoidable_context",
                evidence={"raw_token_total": raw_tokens, "target_max_raw_tokens": target_max},
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Keep global token-budget policy in Builder; only hand repo-local command/setup work to the optimization agent.",
                evidence_source="metrics benchmark",
                evidence_command="builder metrics show --json",
                priority_reason="runtime is over the raw-token target band",
            )
        )
    active_drivers = optimization.get("active_top_cost_drivers")
    if isinstance(active_drivers, list):
        top_driver = _cost_driver(
            optimization,
            "agent-chat",
            driver_key="active_top_cost_drivers",
        )
    else:
        top_driver = _top_cost_driver(optimization)
    top_driver_name = str(top_driver.get("agent_name") or "")
    top_driver_avoidable = int(top_driver.get("avoidable_token_estimate") or 0)
    if top_driver_name == "agent-chat" and top_driver_avoidable > 0:
        recommendations.append(
            _deterministic_recommendation(
                code="agent_chat_readonly_intent_budget",
                severity="high" if top_driver_avoidable >= 25_000 else "medium",
                trigger=f"agent-chat avoidable tokens {top_driver_avoidable}",
                recommendation="Convert repeated read-only operator intents into deterministic Builder answers.",
                next_action="add_or_tighten_dashboard_intent_route_before_model_run",
                evidence={
                    "agent_name": top_driver_name,
                    "avoidable_token_estimate": top_driver_avoidable,
                    "raw_tokens": top_driver.get("raw_tokens", 0),
                },
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Fix Builder Agent/Realtime routing; this is not managed-repo optimization-agent work.",
                evidence_source="metrics top driver",
                evidence_command="builder metrics show --json",
                priority_reason="agent-chat is the largest avoidable token driver",
            )
        )
    code_gen_driver = _cost_driver(optimization, "code-gen")
    code_gen_avoidable = int(code_gen_driver.get("avoidable_token_estimate") or 0)
    if code_gen_avoidable > 0:
        recommendations.append(
            _deterministic_recommendation(
                code="managed_repo_codegen_context_pack",
                severity="medium",
                trigger=f"code-gen avoidable tokens {code_gen_avoidable}",
                recommendation="Have the optimization agent prepare a tighter managed-repo context pack or reusable setup command.",
                next_action="send_repo_context_and_setup_pack_to_optimization_agent",
                evidence={
                    "agent_name": "code-gen",
                    "avoidable_token_estimate": code_gen_avoidable,
                    "raw_tokens": code_gen_driver.get("raw_tokens", 0),
                },
                owner_lane="managed_repo_environment",
                next_actor="optimization_agent",
                handoff="Optimization agent may tune managed-repo setup, context pack, or verification commands; Builder agent policy stays with Codex.",
                evidence_source="metrics top driver",
                evidence_command="builder metrics show --json",
                priority_reason="code-gen has avoidable managed-repo context cost",
            )
        )
    if raw_tokens >= 100_000 and cache_ratio < 0.5:
        recommendations.append(
            _deterministic_recommendation(
                code="context_retrieval_policy_review",
                severity="medium",
                trigger="high raw tokens with low cache reuse",
                recommendation="Review context compaction and retrieval policy before lowering model effort.",
                next_action="tighten_retrieval_policy_and_context_prefix_before_model_change",
                evidence={"raw_token_total": raw_tokens, "cache_ratio": cache_ratio},
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Fix Builder retrieval and context policy before asking the optimization agent to tune a managed repo.",
                evidence_source="metrics cache policy",
                evidence_command="builder metrics show --json --full --limit 10",
                priority_reason="high raw tokens are not being offset by prompt-cache reuse",
            )
        )
    error_summary = aggregates.get("error_summary", {})
    error_count = (
        int(error_summary.get("active_count") or 0) if isinstance(error_summary, dict) else 0
    )
    recent_count = (
        int(error_summary.get("active_recent_count") or 0) if isinstance(error_summary, dict) else 0
    )
    resolved_count = (
        int(error_summary.get("resolved_count") or 0) if isinstance(error_summary, dict) else 0
    )
    if error_count > 0 or resolved_count > 0:
        lifecycle_status = "open" if error_count > 0 else "applied"
        recommendations.append(
            _deterministic_recommendation(
                code="runtime_error_trend",
                severity="high" if error_count > 0 else "info",
                trigger=(
                    f"{error_count} unresolved runtime/tool errors; latest {recent_count} retained for review"
                    if error_count > 0
                    else f"{resolved_count} runtime/tool errors resolved by later successful telemetry"
                ),
                recommendation=(
                    "Fix the recurring runtime error trend before dispatching more autonomous work."
                    if error_count > 0
                    else "Keep the runtime fix completed; latest telemetry has successful replacement evidence."
                ),
                next_action=(
                    "open_latest_error_session_and_fix_owning_runtime_layer"
                    if error_count > 0
                    else "no_operator_action_required"
                ),
                evidence=error_summary,
                owner_lane="builder_source",
                next_actor="builder",
                handoff=(
                    "Use Builder logs and session analysis to fix the owning runtime layer; do not patch generated apps."
                    if error_count > 0
                    else "Telemetry lifecycle resolved this Builder-owned recommendation."
                ),
                evidence_source="builder logs",
                evidence_command="builder logs --error --json --limit 10",
                priority_reason=(
                    "recent failed runs are the clearest operator trust risk"
                    if error_count > 0
                    else "latest telemetry shows replacement successful runs after the failures"
                ),
                validation_status="validated",
                lifecycle_status=lifecycle_status,
            )
        )
    approval_wait = aggregates.get("approval_wait", {})
    unresolved = (
        int(approval_wait.get("active_unresolved") or 0) if isinstance(approval_wait, dict) else 0
    )
    if unresolved > 0:
        recommendations.append(
            _deterministic_recommendation(
                code="approval_action_waiting",
                severity="medium",
                trigger=f"{unresolved} active unresolved approval gate{'s' if unresolved != 1 else ''}",
                recommendation="Resolve the waiting approval before dispatching more autonomous work.",
                next_action="open_approval_and_record_operator_decision",
                evidence=approval_wait,
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Keep approval state in Builder. The optimization agent should not bypass operator decisions.",
                evidence_source="approval gates",
                evidence_command="builder logs --info --compact --json",
                priority_reason="blocked operator decisions should be cleared before new work starts",
            )
        )
    provider_limits = aggregates.get("provider_limits", {})
    provider_count = (
        int(provider_limits.get("count") or 0) if isinstance(provider_limits, dict) else 0
    )
    if provider_count > 0:
        ready = int(provider_limits.get("ready_to_resume") or 0)
        recommendations.append(
            _deterministic_recommendation(
                code="provider_limit_recovery",
                severity="high" if ready > 0 else "medium",
                trigger=f"{provider_count} provider-limit event{'s' if provider_count != 1 else ''}",
                recommendation="Resume provider-limited work when reset is ready; otherwise avoid dispatching new blocked runs.",
                next_action="resume_ready_provider_limited_work_or_wait_for_reset",
                evidence=provider_limits,
                owner_lane="builder_source",
                next_actor="builder",
                handoff="Provider-limit recovery is Builder runtime work unless the managed repo needs environment setup.",
                evidence_source="provider limits",
                evidence_command="builder logs --info --compact --json",
                priority_reason="blocked runtime capacity changes what the operator should do next",
            )
        )
    if "runtime_settings_updated" in set(aggregates.get("event_types", [])):
        recommendations.append(
            _deterministic_recommendation(
                code="runtime_switch_preserve_history",
                severity="info",
                trigger="runtime_settings_updated event exists",
                recommendation="Apply future-runs-only runtime switch semantics and preserve historical attribution.",
                next_action="verify_future_runs_use_selected_runtime_and_history_keeps_attribution",
                evidence={"event_type": "runtime_settings_updated"},
                evidence_source="settings events",
                evidence_command="builder logs --info --compact --json",
                priority_reason="runtime switching changed future-run behavior",
            )
        )
    recovery = aggregates.get("runtime_recovery", {})
    if int(recovery.get("resume_retry_count") or 0) > 0:
        recommendations.append(
            _deterministic_recommendation(
                code="runtime_resume_recovered",
                severity="info",
                trigger="runtime resume retry evidence exists",
                recommendation="Keep the model turn, but retry without stale resume state when the SDK resume handle fails.",
                next_action="monitor_resume_retry_rate_and_clear_stale_session_handles_if_repeated",
                evidence=recovery,
                owner_lane="builder_source",
                next_actor="builder",
                evidence_source="runtime recovery",
                evidence_command="builder metrics show --json --full --limit 10",
                priority_reason="resume fallback happened and should be watched for recurrence",
            )
        )
    if not recommendations:
        recommendations.append(
            _deterministic_recommendation(
                code="deterministic_baseline_ready",
                severity="info",
                trigger="no deterministic recommendation thresholds crossed",
                recommendation="Continue collecting structured run evidence.",
                next_action="continue_collecting_structured_builder_db_events",
                evidence={},
                evidence_source="observability baseline",
                evidence_command="builder metrics show --json",
                priority_reason="no active threshold crossed",
            )
        )
    return _rank_recommendations(recommendations)


def _top_cost_driver(optimization: dict[str, Any]) -> dict[str, Any]:
    drivers = optimization.get("top_cost_drivers") if isinstance(optimization, dict) else []
    if not isinstance(drivers, list):
        return {}
    for item in drivers:
        if isinstance(item, dict):
            return item
    return {}


def _cost_driver(
    optimization: dict[str, Any],
    agent_name: str,
    *,
    driver_key: str = "top_cost_drivers",
) -> dict[str, Any]:
    drivers = optimization.get(driver_key) if isinstance(optimization, dict) else []
    if not isinstance(drivers, list):
        return {}
    for item in drivers:
        if isinstance(item, dict) and str(item.get("agent_name") or "") == agent_name:
            return item
    return {}


def _candidate_evidence_source(code: str) -> str:
    if code == "output_truncation_artifact":
        return "metrics avoidable-cost flags"
    if code == "bounded_retrieval_shortcut":
        return "tool retrieval counts"
    if code == "command_sequence_wrapper":
        return "tool command counts"
    if code in {"build_verify_script", "change_evidence_collector"}:
        return "agent run history"
    return "deterministic script candidates"


def _rank_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        recommendations,
        key=lambda item: (
            _recommendation_priority(item),
            int((item.get("evidence") or {}).get("avoidable_token_estimate") or 0),
        ),
        reverse=True,
    )
    for index, item in enumerate(ranked, start=1):
        item["priority_rank"] = index
        item.setdefault("priority_reason", str(item.get("trigger") or ""))
    return ranked


def _recommendation_priority(item: dict[str, Any]) -> int:
    code = str(item.get("code") or "")
    severity = str(item.get("severity") or "")
    base = {"high": 80, "medium": 50, "low": 30, "info": 10}.get(severity, 20)
    if code in {"runtime_error_trend", "provider_limit_recovery"}:
        base += 20
    elif code in {
        "script_candidate_output_truncation_artifact",
        "runtime_token_budget_over_target",
    }:
        base += 15
    elif code == "agent_chat_readonly_intent_budget":
        base += 12
    elif code in {"approval_action_waiting", "telemetry_collector_blocked"}:
        base += 8
    elif str(item.get("owner_lane") or "") == "managed_repo_environment":
        base -= 5
    return base


def _deterministic_recommendation(
    *,
    code: str,
    severity: str,
    trigger: str,
    recommendation: str,
    next_action: str,
    evidence: dict[str, Any],
    owner_lane: str = "",
    next_actor: str = "",
    handoff: str = "",
    evidence_source: str = "",
    evidence_command: str = "",
    priority_reason: str = "",
    validation_status: str = "validated",
    lifecycle_status: str = "open",
) -> dict[str, Any]:
    item = {
        "code": code,
        "severity": severity,
        "trigger": trigger,
        "recommendation": recommendation,
        "next_action": next_action,
        "evidence": evidence,
        "source": "structured_facts",
        "lifecycle_status": lifecycle_status,
        "validation_status": validation_status,
    }
    if evidence_source:
        item["evidence_source"] = evidence_source
    if evidence_command:
        item["evidence_command"] = evidence_command
    if priority_reason:
        item["priority_reason"] = priority_reason
    if owner_lane:
        item["owner_lane"] = owner_lane
    if next_actor:
        item["next_actor"] = next_actor
    if handoff:
        item["handoff"] = handoff
    return item
