"""Post-ship runtime guidance and deterministic optimization helpers."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import AgentRun, AgentRunEvent, Task
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.orchestrator.post_ship_cli_probe import (
    _post_ship_optimization_cli_probe as _cli_probe,
)
from autonomous_agent_builder.orchestrator.post_ship_optimization import (
    _json_object,
    _sqlite_path_from_sync_url,
)
from autonomous_agent_builder.services.runtime_guidance import refresh_project_runtime_guidance


def _refresh_app_runtime_guidance_payload(
    orchestrator: Any,
    task: Task,
    project_root: Path,
) -> dict[str, Any]:
    project = task.feature.project
    raw_language = str(getattr(project, "language", "") or "").strip()
    language = raw_language if raw_language and raw_language != "unknown" else None
    try:
        return refresh_project_runtime_guidance(
            project_root,
            project_name=str(getattr(project, "name", "") or project_root.name),
            language=language,
        )
    except Exception as exc:
        return {
            "status": "failed",
            "project_root": str(project_root),
            "updated_files": [],
            "unchanged_files": [],
            "skipped_files": [],
            "missing_files": [],
            "commands": {},
            "error": str(exc),
        }


async def _run_app_runtime_guidance_optimization(
    orchestrator: Any,
    task: Task,
    project_root: Path,
    observability_payload: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any] | None:
    started_at = datetime.now(UTC)
    telemetry_commands = (
        await _cli_probe(orchestrator, project_root)
        if project_root.exists()
        else []
    )
    guidance = _refresh_app_runtime_guidance_payload(orchestrator, task, project_root)
    completed_at = datetime.now(UTC)
    updated_files = [
        str(path) for path in guidance.get("updated_files", []) if str(path).strip()
    ]
    guidance_failed = guidance.get("status") == "failed"
    guidance_command = {
        "command": "builder runtime guidance refresh",
        "result": "fail" if guidance_failed else "pass",
        "summary": (
            str(guidance.get("error") or "failed to refresh app-local runtime guidance")
            if guidance_failed
            else (
                "updated " + ", ".join(updated_files)
                if updated_files
                else "checked app-local runtime guidance"
            )
        ),
    }
    commands: list[dict[str, str]] = [*telemetry_commands, guidance_command]
    status = "blocked" if guidance_failed else "implemented" if updated_files else "skipped"
    summary = (
        "Refreshed the generated app's SDK guidance with discovered setup, run, test, "
        "lint, and build commands from the app workspace."
        if updated_files
        else (
            str(guidance.get("error") or "App-local runtime guidance refresh failed.")
            if guidance_failed
            else "Checked app-local SDK guidance; no builder-generated guidance needed changes."
        )
    )
    optimization = {
        "status": status,
        "agent_name": "optimization-agent",
        "runtime_sdk": "deterministic",
        "selected_recommendation": "app_runtime_guidance_refresh",
        "why_selected": (
            f"{reason}; generated-app optimization should update app-local SDK handoff "
            "surfaces before spending model tokens."
        ),
        "summary": summary,
        "benefit": (
            "Next sprint agents load concrete app commands and validation paths from "
            "CLAUDE.md/AGENTS.md, reducing discovery turns, stale-command drift, and "
            "unnecessary model-backed validation work."
        ),
        "files_changed": updated_files,
        "commands": commands,
        "command_timeline_source": "builder_cli_telemetry_then_runtime_guidance_refresh",
        "observability": {
            "metrics_source": "builder metrics show --json --full",
            "logs_source": "builder logs --info --compact --json",
            "analysis_source": "builder logs analyze --session <latest-session> --json",
            "optimization_decision": observability_payload.get("optimization_decision", {}),
            "app_runtime_guidance": guidance,
            "app_scope": str(project_root),
        },
        "completed_at": completed_at.isoformat(),
    }
    run = AgentRun(
        task_id=task.id,
        agent_name="optimization-agent",
        runtime_sdk="deterministic",
        provider="builder",
        model="none",
        effort="none",
        cost_usd=0.0,
        tokens_input=0,
        tokens_output=0,
        tokens_cached=0,
        num_turns=0,
        duration_ms=int((completed_at - started_at).total_seconds() * 1000),
        stop_reason=f"deterministic_{reason}",
        status="failed" if guidance_failed else "completed",
        error=str(guidance.get("error") or "") if guidance_failed else None,
        output_text=json.dumps(optimization, ensure_ascii=True, sort_keys=True),
        observability=optimization["observability"],
        started_at=started_at,
        completed_at=completed_at,
    )
    orchestrator.db.add(run)
    await orchestrator.db.flush()
    for item in commands:
        orchestrator.db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="tool_use",
                tool_name=(
                    "builder_runtime_guidance"
                    if item["command"] == "builder runtime guidance refresh"
                    else "builder_cli"
                ),
                tool_input={"command": item["command"], "result": item["result"]},
                output_preview=f"{item['result']}: {item['command']}",
                timestamp=completed_at,
            )
        )
    return optimization


async def _run_deterministic_post_ship_optimization(
    orchestrator: Any,
    task: Task,
    project_root: Path,
    recommendations: list[Any],
    observability_payload: dict[str, Any],
) -> dict[str, Any] | None:
    by_code = {
        str(item.get("code") or ""): item for item in recommendations if isinstance(item, dict)
    }
    supported_scripts = {
        "script_candidate_build_verify_script": {
            "script": "build_verify",
            "command": "builder script run build_verify --json",
            "target_area": "build_verify_script",
            "summary": (
                "Checked builder CLI metrics, compact logs, and observability analysis, then "
                "replaced the post-ship model verification recommendation with builder script "
                "run build_verify from the project root."
            ),
            "fallback_benefit": "Expected saving: avoids another model-backed build-verifier pass.",
            "savings_label": "model verification work",
        },
        "script_candidate_change_evidence_collector": {
            "script": "change_evidence",
            "command": "builder script run change_evidence --json",
            "target_area": "change_evidence_collector",
            "summary": (
                "Checked builder CLI metrics, compact logs, and observability analysis, then "
                "replaced model-backed PR evidence collection with builder script run "
                "change_evidence from the project root."
            ),
            "fallback_benefit": "Expected saving: avoids another model-backed PR/evidence pass.",
            "savings_label": "model PR/evidence work",
        },
    }
    selected_codes = [code for code in by_code if code in supported_scripts]
    if not selected_codes:
        return None

    telemetry_commands = await _cli_probe(orchestrator, project_root)
    started_at = datetime.now(UTC)
    commands: list[dict[str, str]] = [*telemetry_commands]
    script_results: list[dict[str, Any]] = []
    summary_parts: list[str] = []
    failure_parts: list[str] = []
    total_estimated_savings = 0
    success = True

    for recommendation_code in selected_codes:
        recommendation = by_code[recommendation_code]
        script = supported_scripts[recommendation_code]
        args = json.dumps({"project_root": str(project_root)}, ensure_ascii=True)
        command = [
            sys.executable,
            "-m",
            "autonomous_agent_builder.cli.main",
            "script",
            "run",
            str(script["script"]),
            "--args",
            args,
            "--json",
        ]
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")
        payload = _json_object(stdout_text)
        script_success = proc.returncode == 0 and bool(payload.get("success", False))
        success = success and script_success
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        checks = data.get("checks") if isinstance(data, dict) else []
        estimated_savings = int(recommendation.get("estimated_savings_tokens") or 0)
        total_estimated_savings += estimated_savings
        commands.append(
            {
                "command": str(script["command"]),
                "result": "pass" if script_success else "fail",
            }
        )
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                raw_command = check.get("command")
                command_text = (
                    " ".join(str(part) for part in raw_command)
                    if isinstance(raw_command, list)
                    else str(raw_command or "")
                ).strip()
                if command_text:
                    commands.append(
                        {
                            "command": command_text,
                            "result": "pass" if check.get("status") == "passed" else "fail",
                        }
                    )
        result_summary = (
            str(script["summary"])
            if script_success
            else (payload.get("error") or stderr_text or f"{script['script']} command failed")
        )
        if script_success:
            summary_parts.append(result_summary)
        else:
            failure_parts.append(str(result_summary))
        script_results.append(
            {
                "code": recommendation_code,
                "script": str(script["script"]),
                "status": "implemented" if script_success else "blocked",
                "estimated_savings_tokens": estimated_savings,
                "summary": str(result_summary)[:1000],
            }
        )

    guidance = _refresh_app_runtime_guidance_payload(orchestrator, task, project_root)
    guidance_failed = guidance.get("status") == "failed"
    success = success and not guidance_failed
    updated_guidance_files = [
        str(path) for path in guidance.get("updated_files", []) if str(path).strip()
    ]
    commands.append(
        {
            "command": "builder runtime guidance refresh",
            "result": "fail" if guidance_failed else "pass",
            "summary": (
                str(guidance.get("error") or "failed to refresh app-local runtime guidance")
                if guidance_failed
                else (
                    "updated " + ", ".join(updated_guidance_files)
                    if updated_guidance_files
                    else "checked app-local runtime guidance"
                )
            ),
        }
    )
    completed_at = datetime.now(UTC)
    guidance_suffix = (
        " Refreshed app-local SDK guidance so the next sprint can load discovered "
        "setup, run, test, lint, and build commands without rediscovery."
        if updated_guidance_files
        else ""
    )
    optimization = {
        "status": "implemented" if success else "blocked",
        "agent_name": "optimization-agent",
        "runtime_sdk": "deterministic",
        "selected_recommendation": selected_codes[0],
        "selected_recommendations": selected_codes,
        "why_selected": "; ".join(
            str(
                by_code[code].get("trigger")
                or f"{supported_scripts[code]['target_area']} detected from builder CLI telemetry and logs"
            )
            for code in selected_codes
        ),
        "summary": (
            " ".join(summary_parts) + guidance_suffix
            if success
            else "; ".join(
                failure_parts or summary_parts or ["deterministic script optimization failed"]
            )
        ),
        "benefit": (
            f"Expected saving: about {total_estimated_savings:,} tokens by replacing repeatable "
            f"model-backed work with deterministic script evidence across "
            f"{len(selected_codes)} recommendation(s). "
            "App-local guidance also reduces command rediscovery during the next SDK run."
            if total_estimated_savings
            else (
                "Expected saving: replaces repeatable model-backed checks with deterministic "
                "script evidence. App-local guidance refresh reduces command rediscovery "
                "during the next SDK run."
            )
        ),
        "files_changed": updated_guidance_files,
        "commands": commands,
        "script_results": script_results,
        "command_timeline_source": "builder_cli_telemetry_then_script_run",
        "observability": {
            "metrics_source": "builder metrics show --json --full",
            "logs_source": "builder logs --info --compact --json",
            "analysis_source": "builder logs analyze --session <latest-session> --json",
            "raw_token_total": (
                observability_payload.get("optimization_summary", {})
                if isinstance(observability_payload.get("optimization_summary"), dict)
                else {}
            ).get("raw_token_total"),
            "optimization_decision": observability_payload.get("optimization_decision", {}),
            "app_runtime_guidance": guidance,
        },
        "completed_at": completed_at.isoformat(),
    }
    run = AgentRun(
        task_id=task.id,
        agent_name="optimization-agent",
        runtime_sdk="deterministic",
        provider="builder",
        model="none",
        effort="none",
        cost_usd=0.0,
        tokens_input=0,
        tokens_output=0,
        tokens_cached=0,
        num_turns=0,
        duration_ms=int((completed_at - started_at).total_seconds() * 1000),
        stop_reason="deterministic_post_ship_optimization",
        status="completed" if success else "failed",
        error=None
        if success
        else "; ".join(
            failure_parts or [str(guidance.get("error") or "script optimization failed")]
        ),
        output_text=json.dumps(optimization, ensure_ascii=True, sort_keys=True),
        observability=optimization["observability"],
        started_at=started_at,
        completed_at=completed_at,
    )
    orchestrator.db.add(run)
    await orchestrator.db.flush()
    for item in commands:
        orchestrator.db.add(
            AgentRunEvent(
                run_id=run.id,
                event_type="tool_use",
                tool_name=(
                    "builder_script"
                    if item["command"].startswith("builder script run")
                    else "builder_runtime_guidance"
                    if item["command"] == "builder runtime guidance refresh"
                    else "builder_cli"
                ),
                tool_input={"command": item["command"], "result": item["result"]},
                output_preview=f"{item['result']}: {item['command']}",
                timestamp=completed_at,
            )
        )
    return optimization


def _post_ship_observability_payload(orchestrator: Any) -> dict[str, Any]:
    db_path = _sqlite_path_from_sync_url(orchestrator.settings.db.sync_url)
    if db_path is None:
        return {
            "ok": False,
            "status": "unavailable",
            "reason": "non_sqlite_db_path",
            "observability_coverage": {"deterministic_recommendations": []},
        }
    return dashboard_observability_summary(db_path)


def _compact_optimization_payload(
    orchestrator: Any, payload: dict[str, Any]
) -> dict[str, Any]:
    coverage = payload.get("observability_coverage", {})
    aggregates = payload.get("runtime_aggregates", {})
    return {
        "runtime": payload.get("runtime", {}),
        "recommendations": coverage.get("deterministic_recommendations", []),
        "resolved_recommendations": coverage.get("resolved_recommendations", []),
        "recommendation_lifecycle": coverage.get("recommendation_lifecycle", {}),
        "telemetry_health": coverage.get("telemetry_health", {}),
        "optimization_decision": payload.get("optimization_decision", {}),
        "runtime_recovery": aggregates.get("runtime_recovery", {}),
        "tool_observability": aggregates.get("tool_observability", {}),
        "totals": aggregates.get("totals", {}),
    }
