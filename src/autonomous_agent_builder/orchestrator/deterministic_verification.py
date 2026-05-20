"""Deterministic evidence and verification run recording for orchestration."""

from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.runner import capture_workspace_diff
from autonomous_agent_builder.db.models import AgentRun, AgentRunEvent, Feature, Task
from autonomous_agent_builder.services.async_subprocess import run_bounded_subprocess

ORCHESTRATOR_SCRIPT_TIMEOUT_SECONDS = 300.0
BuilderScriptRunner = Callable[
    [str, str, dict[str, Any] | None],
    Awaitable[tuple[bool, dict[str, Any], str, str]],
]
BoardPublisher = Callable[[], Awaitable[None]]


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def run_builder_script(
    script_name: str,
    workspace_path: str,
    extra_args: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = ORCHESTRATOR_SCRIPT_TIMEOUT_SECONDS,
) -> tuple[bool, dict[str, Any], str, str]:
    script_args: dict[str, Any] = {"project_root": workspace_path}
    if extra_args:
        script_args.update(extra_args)
    args = json.dumps(script_args, ensure_ascii=True)
    command = [
        sys.executable,
        "-m",
        "autonomous_agent_builder.cli.main",
        "script",
        "run",
        script_name,
        "--args",
        args,
        "--json",
    ]
    result = await run_bounded_subprocess(
        *command,
        cwd=workspace_path or None,
        timeout_seconds=timeout_seconds,
        label=f"builder script {script_name}",
    )
    stdout_text = result.stdout
    stderr_text = result.stderr
    payload = _json_object(stdout_text)
    return (
        result.returncode == 0 and bool(payload.get("success", False)),
        payload,
        stdout_text,
        stderr_text,
    )


def _changed_files_from_diff(diff_summary: dict[str, Any]) -> list[str]:
    changed_files = [
        str(item.get("path") or item.get("file") or "")
        for item in (diff_summary or {}).get("files", [])
        if str(item.get("path") or item.get("file") or "").strip()
    ]
    if changed_files:
        return changed_files
    return [
        str(item.get("file", ""))
        for item in (diff_summary or {}).get("hunks", [])
        if str(item.get("file", "")).strip()
    ]


async def record_deterministic_evidence(
    db: AsyncSession,
    task: Task,
    workspace_path: str,
    script_runner: BuilderScriptRunner,
    publish_board_snapshot: BoardPublisher,
) -> None:
    success, payload, _stdout, stderr = await script_runner(
        "change_evidence",
        workspace_path,
        None,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    diff_summary = data if success and data else capture_workspace_diff(workspace_path)
    changed_files = _changed_files_from_diff(diff_summary)
    output = (
        "Deterministic evidence collector completed without model-backed PR creation.\n"
        f"Changed files: {', '.join(changed_files) if changed_files else 'none detected'}.\n"
        "Next: sprint-level build verification."
    )
    run = AgentRun(
        task_id=task.id,
        agent_name="evidence-collector",
        runtime_sdk="deterministic",
        provider="builder",
        model="none",
        effort="none",
        cost_usd=0.0,
        tokens_input=0,
        tokens_output=0,
        tokens_cached=0,
        num_turns=0,
        duration_ms=0,
        stop_reason="deterministic_evidence",
        status="completed",
        output_text=output,
        diff_summary=diff_summary,
        observability={
            "command": "builder script run change_evidence --json",
            "success": success,
            "error": ""
            if success
            else str(payload.get("error") or stderr or "change_evidence failed"),
            "optimization_summary": {
                "schema_version": "1",
                "primary_score": "raw_tokens",
                "token_accounting": {
                    "raw_total_tokens": 0,
                    "noncached_plus_output_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "cache_ratio": 0.0,
                },
                "avoidable_cost_flags": [],
                "avoidable_token_estimate": 0,
                "deterministic_evidence": True,
            },
        },
        completed_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    db.add(
        AgentRunEvent(
            run_id=run.id,
            event_type="tool_use",
            tool_name="builder_script",
            tool_input={
                "command": "builder script run change_evidence --json",
                "workspace_path": workspace_path,
                "result": "pass" if success else "fail",
            },
            output_preview=output[:500],
            timestamp=datetime.now(UTC),
        )
    )
    await publish_board_snapshot()


def build_verification_output(
    payload: dict[str, Any],
    stderr: str,
    *,
    success: bool,
) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    checks = data.get("checks") if isinstance(data, dict) else []
    lines: list[str] = []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            command = check.get("command")
            command_text = (
                " ".join(str(part) for part in command)
                if isinstance(command, list)
                else str(command or check.get("name") or "")
            ).strip()
            status = "PASS" if check.get("status") == "passed" else "FAIL"
            line = f"{command_text or 'check'} {status}"
            if status == "FAIL":
                stderr_tail = str(check.get("stderr_tail") or "").strip()
                stdout_tail = str(check.get("stdout_tail") or "").strip()
                detail = stderr_tail or stdout_tail
                if detail:
                    line = f"{line}: {detail[:1800]}"
            lines.append(line)
    return "\n".join(lines) or (
        "builder script run build_verify --json PASS"
        if success
        else str(payload.get("error") or stderr or "build_verify failed")
    )


async def record_deterministic_build_verification(
    db: AsyncSession,
    task: Task,
    workspace_path: str,
    publish_board_snapshot: BoardPublisher,
) -> tuple[bool, str]:
    started_at = datetime.now(UTC)
    from autonomous_agent_builder.embedded.scripts.build_verify import BuildVerifyScript

    payload = BuildVerifyScript().run(project_root=workspace_path)
    success = bool(payload.get("success", False))
    stderr = ""
    completed_at = datetime.now(UTC)
    output = build_verification_output(payload, stderr, success=success)
    run = AgentRun(
        task_id=task.id,
        agent_name="build-verifier",
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
        stop_reason="deterministic_build_verify",
        status="completed" if success else "failed",
        error=None if success else str(payload.get("error") or stderr or "build_verify failed"),
        output_text=output,
        observability={
            "command": "builder script run build_verify --json",
            "success": success,
            "optimization_summary": {
                "schema_version": "1",
                "primary_score": "raw_tokens",
                "token_accounting": {
                    "raw_total_tokens": 0,
                    "noncached_plus_output_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "cache_ratio": 0.0,
                },
            },
        },
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(run)
    await db.flush()
    db.add(
        AgentRunEvent(
            run_id=run.id,
            event_type="tool_use",
            tool_name="builder_script",
            tool_input={
                "command": "builder script run build_verify --json",
                "workspace_path": workspace_path,
                "result": "pass" if success else "fail",
            },
            output_preview=output[:500],
            timestamp=completed_at,
        )
    )
    await publish_board_snapshot()
    return success, output


def feature_acceptance_output(
    data: dict[str, Any],
    payload: dict[str, Any],
    stderr: str,
    *,
    success: bool,
) -> str:
    status = str(data.get("status") or ("passed" if success else "failed"))
    command = data.get("command")
    command_text = (
        " ".join(str(part) for part in command)
        if isinstance(command, list)
        else str(command or "")
    ).strip()
    coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
    matched_files = coverage.get("matched_files") if isinstance(coverage, dict) else []
    criteria = (
        data.get("acceptance_criteria")
        if isinstance(data.get("acceptance_criteria"), list)
        else []
    )
    lines = [
        f"Feature acceptance tests {'PASS' if success else 'FAIL'} ({status}).",
    ]
    if command_text:
        lines.append(f"Command: `{command_text}`.")
    if criteria:
        lines.append("Acceptance criteria: " + "; ".join(str(item) for item in criteria[:5]))
    if isinstance(matched_files, list) and matched_files:
        lines.append("Matched test files: " + ", ".join(str(item) for item in matched_files[:5]))
    if not success:
        lines.append(str(payload.get("error") or stderr or "feature_acceptance failed"))
    return "\n".join(lines)


async def record_feature_acceptance_tests(
    db: AsyncSession,
    task: Task,
    workspace_path: str,
    feature: Feature,
    publish_board_snapshot: BoardPublisher,
) -> tuple[bool, str]:
    started_at = datetime.now(UTC)
    from autonomous_agent_builder.embedded.scripts.feature_acceptance import (
        FeatureAcceptanceScript,
    )

    payload = FeatureAcceptanceScript().run(
        project_root=workspace_path,
        feature_title=feature.title,
        feature_description=feature.description or "",
        acceptance_criteria=feature.acceptance_criteria or [],
    )
    success = bool(payload.get("success", False))
    stderr = ""
    completed_at = datetime.now(UTC)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    output = feature_acceptance_output(data, payload, stderr, success=success)
    run = AgentRun(
        task_id=task.id,
        agent_name="feature-acceptance-tests",
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
        stop_reason="deterministic_feature_acceptance",
        status="completed" if success else "failed",
        error=None
        if success
        else str(payload.get("error") or stderr or "feature_acceptance failed"),
        output_text=output,
        observability={
            "command": "builder script run feature_acceptance --json",
            "success": success,
            "data": data,
        },
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(run)
    await db.flush()
    db.add(
        AgentRunEvent(
            run_id=run.id,
            event_type="tool_use",
            tool_name="builder_script",
            tool_input={
                "command": "builder script run feature_acceptance --json",
                "workspace_path": workspace_path,
                "feature_id": feature.id,
                "result": "pass" if success else "fail",
            },
            output_preview=output[:500],
            timestamp=completed_at,
        )
    )
    await publish_board_snapshot()
    return success, output
