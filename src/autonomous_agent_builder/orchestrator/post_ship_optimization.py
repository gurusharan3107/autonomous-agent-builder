"""Post-ship optimization cluster.

Module-level functions extracted from Orchestrator for the post-ship
optimization phase: observability payload collection, deterministic
preflight, guidance refresh, and the model-backed optimization agent run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import (
    Sprint,
    Task,
)
from autonomous_agent_builder.orchestrator.workspace_policy import is_builder_source_repo


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_object_from_text(text: str) -> dict[str, Any]:
    value = _json_object(text)
    if value:
        return value
    raw = str(text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    return _json_object(raw[start : end + 1])


def _sqlite_path_from_sync_url(sync_url: str) -> Path | None:
    from urllib.parse import unquote, urlparse

    value = str(sync_url or "")
    parsed = urlparse(value)
    if parsed.scheme != "sqlite" or not value.startswith("sqlite:///"):
        return None
    return Path(unquote(value.removeprefix("sqlite:///"))).expanduser()


async def _run_post_ship_optimization_agent(
    orchestrator: Any,
    task: Task,
    sprint: Sprint,
    sprint_context: dict[str, Any],
) -> None:
    """Run a bounded optimization review after a sprint ships."""
    evidence = dict(sprint.verification_evidence or {})
    previous = evidence.get("optimization_agent")
    if isinstance(previous, dict) and previous.get("status") in {
        "completed",
        "implemented",
        "failed",
        "skipped",
        "blocked",
    }:
        return

    from autonomous_agent_builder.orchestrator.post_ship_runtime_guidance import (  # noqa: PLC0415
        _compact_optimization_payload,
        _post_ship_observability_payload,
        _run_app_runtime_guidance_optimization,
        _run_deterministic_post_ship_optimization,
    )

    project_root = Path(str(getattr(task.feature.project, "repo_url", "") or "")).expanduser()
    observability_payload = _post_ship_observability_payload(orchestrator)
    recommendations = observability_payload.get("observability_coverage", {}).get(
        "deterministic_recommendations", []
    )
    if not recommendations:
        guidance_result = await _run_app_runtime_guidance_optimization(
            orchestrator,
            task,
            project_root,
            observability_payload,
            reason="no_structured_recommendations",
        )
        if guidance_result is not None:
            evidence["optimization_agent"] = guidance_result
            sprint.verification_evidence = evidence
            return
        evidence["optimization_agent"] = {
            "status": "skipped",
            "reason": "no_structured_recommendations",
            "completed_at": datetime.now(UTC).isoformat(),
        }
        sprint.verification_evidence = evidence
        return

    deterministic_preflight = await _run_deterministic_post_ship_optimization(
        orchestrator,
        task,
        project_root,
        recommendations,
        observability_payload,
    )
    if deterministic_preflight is not None:
        post_preflight_decision = _post_ship_post_preflight_decision(
            orchestrator,
            project_root,
            deterministic_preflight,
            recommendations,
        )
        deterministic_preflight["post_preflight_decision"] = post_preflight_decision
        if not post_preflight_decision["model_backed_review_required"]:
            evidence["optimization_agent"] = deterministic_preflight
            sprint.verification_evidence = evidence
            return

    if deterministic_preflight is None and not is_builder_source_repo(project_root):
        guidance_result = await _run_app_runtime_guidance_optimization(
            orchestrator,
            task,
            project_root,
            observability_payload,
            reason="unsupported_deterministic_recommendation",
        )
        if guidance_result is not None:
            deterministic_preflight = guidance_result
            post_preflight_decision = _post_ship_post_preflight_decision(
                orchestrator,
                project_root,
                deterministic_preflight,
                recommendations,
            )
            deterministic_preflight["post_preflight_decision"] = post_preflight_decision
            if not post_preflight_decision["model_backed_review_required"]:
                evidence["optimization_agent"] = deterministic_preflight
                sprint.verification_evidence = evidence
                return

    workspace_path = str(project_root)
    model_payload = dict(_compact_optimization_payload(orchestrator, observability_payload))
    if deterministic_preflight is not None:
        model_payload["deterministic_preflight"] = deterministic_preflight
    result = await orchestrator._run_agent(
        task,
        "optimization-agent",
        {
            "sprint_context": json.dumps(sprint_context, ensure_ascii=True, sort_keys=True),
            "observability_payload": json.dumps(
                model_payload,
                ensure_ascii=True,
                sort_keys=True,
            ),
            "workspace_path": workspace_path,
        },
    )
    output_payload = _json_object_from_text(result.output_text or "")
    command_timeline = []
    if isinstance(deterministic_preflight, dict):
        command_timeline.extend(deterministic_preflight.get("commands", []))
    if isinstance(output_payload.get("commands"), list):
        command_timeline.extend(output_payload["commands"])
    recommendation_decisions = _validated_optimization_recommendation_decisions(
        orchestrator,
        output_payload.get("recommendation_decisions"),
        command_timeline,
    )
    evidence["optimization_agent"] = {
        "status": (
            "failed" if result.error else str(output_payload.get("status") or "completed")
        ),
        "agent_name": "optimization-agent",
        "runtime_sdk": "model_backed",
        "session_id": result.session_id,
        "error": result.error or "",
        "summary": str(
            output_payload.get("summary")
            or output_payload.get("why_selected")
            or result.output_text
            or ""
        )[:1000],
        "selected_recommendation": str(output_payload.get("selected_recommendation") or ""),
        "selected_recommendations": (
            output_payload.get("selected_recommendations")
            if isinstance(output_payload.get("selected_recommendations"), list)
            else []
        ),
        "recommendation_decisions": (recommendation_decisions),
        "why_selected": str(output_payload.get("why_selected") or ""),
        "benefit": str(output_payload.get("benefit") or ""),
        "files_changed": (
            output_payload.get("files_changed")
            if isinstance(output_payload.get("files_changed"), list)
            else []
        ),
        "commands": command_timeline,
        "deterministic_preflight": deterministic_preflight or {},
        "post_preflight_decision": (
            deterministic_preflight.get("post_preflight_decision")
            if isinstance(deterministic_preflight, dict)
            else {}
        ),
        "observability": {
            "metrics_source": "builder metrics show --json --full",
            "logs_source": "builder logs --info --compact --json",
            "analysis_source": "builder logs analyze --session <latest-session> --json",
            "optimization_decision": observability_payload.get("optimization_decision", {}),
            "app_scope": str(project_root),
        },
        "completed_at": datetime.now(UTC).isoformat(),
    }
    sprint.verification_evidence = evidence


def _validated_optimization_recommendation_decisions(
    orchestrator: Any,
    decisions: Any,
    command_timeline: list[Any],
) -> list[dict[str, Any]]:
    """Prevent unsupported optimization claims from being persisted as applied."""

    if not isinstance(decisions, list):
        return []
    exact_command_requirements = {
        "script_candidate_build_verify_script": "builder script run build_verify",
        "build_verify_script": "builder script run build_verify",
        "script_candidate_change_evidence_collector": "builder script run change_evidence",
        "change_evidence_collector": "builder script run change_evidence",
    }
    passed_commands = []
    for item in command_timeline:
        if not isinstance(item, dict):
            continue
        result = str(item.get("result") or "").lower()
        command = str(item.get("command") or "")
        if result == "pass" and command:
            passed_commands.append(command)

    validated: list[dict[str, Any]] = []
    for raw_decision in decisions:
        if not isinstance(raw_decision, dict):
            continue
        decision = dict(raw_decision)
        code = str(decision.get("code") or "")
        lifecycle = str(decision.get("lifecycle_status") or "").lower()
        required_command = exact_command_requirements.get(code)
        if (
            required_command
            and lifecycle == "applied"
            and not any(required_command in command for command in passed_commands)
        ):
            decision["lifecycle_status"] = "deferred"
            decision["reason"] = (
                f"Exact command `{required_command}` was not recorded as pass in this "
                "optimization run, so the builder cannot persist this recommendation as applied."
            )
        validated.append(decision)
    return validated


def _post_ship_post_preflight_decision(
    orchestrator: Any,
    project_root: Path,
    deterministic_preflight: dict[str, Any],
    recommendations: list[Any],
) -> dict[str, Any]:
    """Decide whether deterministic preflight fully resolved optimization work."""

    def recommendation_codes(raw: Any) -> set[str]:
        if isinstance(raw, str):
            return {raw} if raw.strip() else set()
        if isinstance(raw, dict):
            code = str(raw.get("code") or "").strip()
            return {code} if code else set()
        if not isinstance(raw, list):
            return set()
        codes: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                codes.add(item.strip())
            elif isinstance(item, dict) and str(item.get("code") or "").strip():
                codes.add(str(item.get("code")).strip())
        return codes

    selected = str(deterministic_preflight.get("selected_recommendation") or "")
    implemented_codes = recommendation_codes(selected)
    implemented_codes.update(
        recommendation_codes(deterministic_preflight.get("selected_recommendations"))
    )
    observability = deterministic_preflight.get("observability")
    guidance = (
        observability.get("app_runtime_guidance") if isinstance(observability, dict) else {}
    )
    if isinstance(guidance, dict) and guidance.get("status") in {"updated", "unchanged"}:
        implemented_codes.add("app_runtime_guidance_refresh")
    guidance_current = (
        selected == "app_runtime_guidance_refresh"
        and isinstance(guidance, dict)
        and guidance.get("status") in {"updated", "unchanged"}
    )

    residual_recommendations = [
        item
        for item in recommendations
        if isinstance(item, dict) and str(item.get("code") or "") not in implemented_codes
    ]
    recommendation_decisions: list[dict[str, Any]] = [
        {
            "code": code,
            "lifecycle_status": "applied",
            "reason": "deterministic preflight applied this recommendation",
        }
        for code in sorted(implemented_codes)
    ]
    if "script_candidate_build_verify_script" in implemented_codes:
        for item in residual_recommendations:
            if str(item.get("code") or "") != "script_candidate_command_sequence_wrapper":
                continue
            recommendation_decisions.append(
                {
                    "code": "script_candidate_command_sequence_wrapper",
                    "lifecycle_status": "applied",
                    "reason": (
                        "covered by builder script run build_verify for repeated setup, "
                        "lint, test, build, and app-smoke evidence"
                    ),
                }
            )
    target_scope = (
        "builder_source" if is_builder_source_repo(project_root) else "generated_app"
    )
    deterministic_status = str(deterministic_preflight.get("status") or "")
    auto_resolved_codes = {
        str(item.get("code") or "")
        for item in recommendation_decisions
        if item.get("lifecycle_status") in {"applied", "observed", "not_applicable", "rejected"}
    }
    for item in residual_recommendations:
        code = str(item.get("code") or "")
        if code in {"runtime_switch_preserve_history", "runtime_resume_recovered"}:
            recommendation_decisions.append(
                {
                    "code": code,
                    "lifecycle_status": "observed",
                    "reason": "historical runtime signal; no current optimization action required",
                }
            )
            auto_resolved_codes.add(code)
    builder_source_residual_codes = {
        "agent_chat_readonly_intent_budget",
        "context_retrieval_policy_review",
        "runtime_error_trend",
        "runtime_token_budget_over_target",
        "telemetry_collector_blocked",
        "tool_event_instrumentation_gap",
    }
    deferred_builder_source_codes: set[str] = set()
    for item in residual_recommendations:
        if target_scope != "generated_app":
            continue
        code = str(item.get("code") or "")
        owner_lane = str(item.get("owner_lane") or "")
        next_actor = str(item.get("next_actor") or "")
        if (
            owner_lane == "builder_source"
            or next_actor == "builder"
            or code in builder_source_residual_codes
        ):
            recommendation_decisions.append(
                {
                    "code": code,
                    "lifecycle_status": "deferred",
                    "reason": (
                        "Builder-owned optimization surfaced during a generated-app "
                        "shipment; keep the generated-app post-ship lane deterministic "
                        "and route this follow-up to the Builder source backlog."
                    ),
                }
            )
            deferred_builder_source_codes.add(code)
    actionable_residual_recommendations = [
        item
        for item in residual_recommendations
        if str(item.get("code") or "") not in auto_resolved_codes
        and str(item.get("code") or "") not in deferred_builder_source_codes
        and str(item.get("code") or "") != "deterministic_baseline_ready"
    ]
    if deterministic_status not in {"implemented", "completed"} and not guidance_current:
        model_required = False
        reason = (
            "deterministic preflight did not complete; preserve the blocker before "
            "spending model tokens"
        )
    elif target_scope == "generated_app" and actionable_residual_recommendations:
        model_required = True
        reason = (
            "generated-app optimization has residual recommendations after deterministic "
            "preflight; route a compact model-backed review to apply, reject, or defer each "
            "remaining code from app-local evidence"
        )
    elif target_scope == "generated_app":
        model_required = False
        reason = (
            "generated-app optimization is resolved through app-local SDK guidance, "
            "deterministic scripts, and persisted recommendation decisions"
        )
    elif actionable_residual_recommendations:
        model_required = True
        reason = (
            "builder-source optimization has residual prompt, tool, model, or "
            "workflow recommendations after deterministic preflight"
        )
    else:
        model_required = False
        reason = "deterministic preflight fully resolved the structured recommendations"

    return {
        "target_scope": target_scope,
        "deterministic_status": deterministic_status,
        "deterministic_actions_applied": sorted(implemented_codes),
        "residual_recommendations": [
            {
                "code": str(item.get("code") or ""),
                "severity": str(item.get("severity") or ""),
                "recommendation": str(item.get("recommendation") or ""),
            }
            for item in actionable_residual_recommendations
        ],
        "recommendation_decisions": recommendation_decisions,
        "model_backed_review_required": model_required,
        "reason": reason,
        "sdk_alignment": {
            "claude_agent_sdk": (
                "use compact preflight evidence with explicit tool permissions, "
                "subagent boundaries, and CLAUDE.md runtime guidance"
            ),
            "codex_sdk": (
                "use compact preflight evidence with AGENTS.md project guidance, "
                "sandbox/approval-aware commands, and Codex-native token/cost signals"
            ),
        },
    }

