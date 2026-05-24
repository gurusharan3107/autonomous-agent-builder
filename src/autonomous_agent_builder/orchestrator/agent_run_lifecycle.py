"""Agent run lifecycle persistence for the deterministic orchestrator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

# P18 (autoresearch INSIGHTS Run #10 / 2026-05-24): SQLite WAL writer contention
# can hold the write lock longer than the engine's busy_timeout=15s during agent
# lifecycle event flushes. The autoflush during merge() raises
# `OperationalError: database is locked`; the lifecycle phase doesn't transition;
# Builder polls forever. Retrying the entire commit on a fresh short-lived
# session usually succeeds because the contending writer has finished. Tuned for
# 5 attempts × exponential backoff (0.5 → 8.0s) = up to ~15.5s extra wait, which
# bounds the worst case but typically resolves on attempt 1–2.
_DB_LOCK_RETRY_ATTEMPTS = 5
_DB_LOCK_RETRY_BASE_SECONDS = 0.5

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult, capture_workspace_diff
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.db.models import AgentRun, AgentRunEvent, Task
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.observability.runtime_optimization import runtime_decision_summary
from autonomous_agent_builder.runtime import resolve_runtime_config
from autonomous_agent_builder.services.codex_optimization import (
    codex_run_optimization_summary,
    prompt_budget_breakdown,
)
from autonomous_agent_builder.services.runtime_settings import resolve_project_runtime_config

_BoardSnapshotPublisher = Callable[[], Awaitable[None]]
_RuntimeFactory = Callable[..., Any]


def _runtime_metadata(runtime: object) -> tuple[str, str]:
    runtime_name_value = getattr(runtime, "name", "")
    runtime_name = runtime_name_value if isinstance(runtime_name_value, str) else "claude_agent_sdk"
    runtime_provider_value = getattr(runtime, "provider", "")
    runtime_provider = runtime_provider_value if isinstance(runtime_provider_value, str) else ""
    return runtime_name, runtime_provider


def _agent_output_event(run_id: int | None, preview: str) -> AgentRunEvent | None:
    if not preview:
        return None
    return AgentRunEvent(
        run_id=run_id,
        event_type="agent_output",
        output_preview=preview[:500],
        timestamp=datetime.now(UTC),
    )


def _runtime_phase_decision(
    *,
    task: Task,
    decision_summary: dict[str, Any],
    runtime_name: str,
    runtime_policy: Any,
) -> dict[str, Any]:
    phase_name = str(getattr(task, "phase", "") or getattr(task, "status", "") or "")
    return next(
        (
            decision
            for decision in decision_summary.get("phase_decisions", [])
            if str(decision.get("phase")) in phase_name.lower()
        ),
        {
            "phase": phase_name.lower() or "unknown",
            "selected_runtime": decision_summary.get("runtime", runtime_name),
            "model_effort": runtime_policy.effort,
            "tool_route": runtime_policy.context_strategy,
            "subagent_policy": "bounded_sidecar_only",
            "context_strategy": runtime_policy.context_strategy,
            "expected_evidence": "agent run result and task state transition",
            "reason_code": "agent_runtime_policy",
        },
    )


def _run_observability(
    *,
    task: Task,
    result: RunResult,
    runtime_name: str,
    runtime_policy: Any,
    agent_name: str,
    prompt: str,
    prompt_budget: dict[str, Any],
) -> dict[str, Any]:
    observability = dict(result.observability or {})
    decision_summary = runtime_decision_summary(
        runtime_name,
        aggregates={},
        optimization=observability.get("optimization_summary") or {},
    )
    observability["runtime_decision_summary"] = decision_summary
    observability["phase_runtime_decision"] = _runtime_phase_decision(
        task=task,
        decision_summary=decision_summary,
        runtime_name=runtime_name,
        runtime_policy=runtime_policy,
    )
    if runtime_name != "codex_sdk":
        return observability

    optimization_summary = observability.get("optimization_summary")
    if not isinstance(optimization_summary, dict):
        optimization_summary = codex_run_optimization_summary(
            events=result.raw_events or [],
            metrics={
                "input_tokens": result.tokens_input,
                "output_tokens": result.tokens_output,
                "cached_input_tokens": result.tokens_cached,
                "reasoning_output_tokens": int(
                    (observability.get("optimization_summary") or {})
                    .get("token_accounting", {})
                    .get("reasoning_output_tokens")
                    or observability.get("reasoning_output_tokens")
                    or 0
                ),
                "total_tokens": result.tokens_input + result.tokens_output,
                "turns": result.num_turns,
            },
            agent_name=agent_name,
            prompt_text=prompt,
            output_text=result.output_text,
            status="failed" if result.error else "completed",
            prompt_budget=prompt_budget,
        )
    observability["optimization_summary"] = optimization_summary
    observability["runtime_decision_summary"] = runtime_decision_summary(
        runtime_name,
        aggregates={},
        optimization=optimization_summary,
    )
    return observability


async def run_agent_lifecycle(
    *,
    task: Task,
    agent_name: str,
    template_vars: dict[str, str],
    settings: Settings,
    db: AsyncSession,
    runner: AgentRunner,
    create_runtime: _RuntimeFactory,
    publish_board_snapshot: _BoardSnapshotPublisher,
    resume_session: str | None = None,
) -> RunResult:
    """Run an agent phase, save run result, and return the runtime result."""
    agent_def = get_agent_definition(agent_name)

    from autonomous_agent_builder.agents.tool_registry import ToolRegistry

    registry = ToolRegistry.build(list(agent_def.tools))
    template_vars["tool_context"] = registry.get_tool_prompt_context()
    template_vars.setdefault(
        "knowledge_requirements",
        (
            "No task-scoped repo-local knowledge requirements were provided. "
            "Use builder KB tools for durable KB work and avoid editing KB files directly."
        ),
    )
    template_vars.setdefault("scope_reminder", "")

    prompt = agent_def.prompt_template.format(**template_vars)
    prompt_budget = prompt_budget_breakdown(
        agent_name=agent_name,
        prompt=prompt,
        template_vars=template_vars,
        agent_definition=agent_def.prompt_template,
    )
    runtime_policy = resolve_agent_runtime_policy(agent_def, settings)
    project_root = Path(str(getattr(task.feature.project, "repo_url", "") or "")).expanduser()
    runtime_config = (
        resolve_project_runtime_config(project_root)
        if project_root.exists()
        else resolve_runtime_config(settings)
    )

    runtime = create_runtime(**runtime_config)
    if hasattr(runtime, "_runner"):
        runtime._runner = runner
    runtime_name, runtime_provider = _runtime_metadata(runtime)
    run = AgentRun(
        task_id=task.id,
        agent_name=agent_name,
        runtime_sdk=runtime_name,
        provider=runtime_provider,
        model=str(runtime_config.get("model") or runtime_policy.model),
        effort=runtime_policy.effort,
        status="running",
    )
    db.add(run)
    await db.flush()
    await db.commit()
    await publish_board_snapshot()

    output_parts: list[str] = []
    pending_output_parts: list[str] = []
    last_publish_at = 0.0
    workspace_path = template_vars.get("workspace_path", "")
    stop_monitor = asyncio.Event()
    last_diff_signature = ""
    db_write_lock = asyncio.Lock()

    _log = structlog.get_logger()

    async def persist_realtime_run_update(*objects: object) -> None:
        # IMP-012: use a short-lived session for each intermediate real-time
        # update so the long-lived dispatch session remains idle (and valid)
        # during the multi-minute runtime.run() call. Holding one session open
        # while doing DB writes every second causes the aiosqlite connection to
        # become invalid ("Can't reconnect until invalid transaction is rolled
        # back") on long runs.
        #
        # P18 (2026-05-24): retry on SQLite `database is locked` with
        # exponential backoff. SQLite's engine-level busy_timeout (15s) covers
        # contention within a single statement, but the autoflush during
        # merge() can race a separately-held write lock; the OperationalError
        # propagates and previously hung the lifecycle. Retrying the entire
        # commit on a fresh session usually wins because the contending writer
        # has finished.
        async with db_write_lock:
            last_exc: Exception | None = None
            for attempt in range(_DB_LOCK_RETRY_ATTEMPTS):
                try:
                    async with get_session_factory()() as update_db:
                        for obj in objects:
                            update_db.add(obj)
                        # Merge the run object so its latest attribute values
                        # (output_text, diff_summary, etc.) are persisted.
                        await update_db.merge(run)
                        await update_db.flush()
                        await update_db.commit()
                    last_exc = None
                    break  # success
                except OperationalError as oe:
                    msg = str(oe).lower()
                    if "database is locked" in msg and attempt + 1 < _DB_LOCK_RETRY_ATTEMPTS:
                        last_exc = oe
                        backoff = _DB_LOCK_RETRY_BASE_SECONDS * (2 ** attempt)
                        _log.warning(
                            "agent_run_lifecycle_db_lock_retry",
                            agent_name=agent_name,
                            task_id=task.id,
                            attempt=attempt + 1,
                            max_attempts=_DB_LOCK_RETRY_ATTEMPTS,
                            backoff_seconds=backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    # Either not a lock error, or out of retries — escalate.
                    last_exc = oe
                    break
                except Exception as flush_exc:
                    last_exc = flush_exc
                    break
            if last_exc is not None:
                _log.error(
                    "agent_run_lifecycle_flush_error",
                    agent_name=agent_name,
                    task_id=task.id,
                    error=str(last_exc),
                )
                raise last_exc
            await publish_board_snapshot()

    async def record_output_chunk(delta: str) -> None:
        nonlocal last_publish_at
        text = str(delta or "")
        if not text.strip():
            return
        output_parts.append(text)
        pending_output_parts.append(text)
        run.output_text = "".join(output_parts)[-12000:]
        now = asyncio.get_running_loop().time()
        if now - last_publish_at >= 1.0:
            last_publish_at = now
            preview = " ".join("".join(pending_output_parts).strip().split())
            pending_output_parts.clear()
            event = _agent_output_event(run.id, preview)
            await persist_realtime_run_update(*([event] if event is not None else []))

    async def record_runtime_event(
        event_payload: dict[str, Any] | None = None,
        *,
        event_type: str | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        output_preview: str = "",
    ) -> None:
        if isinstance(event_payload, dict):
            event_type = event_type or str(event_payload.get("event_type") or "tool_use")
            tool_name = tool_name or str(event_payload.get("tool_name") or "") or None
            raw_tool_input = event_payload.get("tool_input")
            if tool_input is None and isinstance(raw_tool_input, dict):
                tool_input = dict(raw_tool_input)
            tool_use_id = str(event_payload.get("tool_use_id") or "").strip()
            if tool_use_id:
                tool_input = dict(tool_input or {})
                tool_input.setdefault("tool_use_id", tool_use_id)
            if not output_preview:
                output_preview = str(
                    event_payload.get("output_preview")
                    or event_payload.get("tool_response")
                    or event_payload.get("tool_result")
                    or ""
                )
        event_type = event_type or "tool_use"
        event = AgentRunEvent(
            run_id=run.id,
            event_type=event_type,
            tool_name=tool_name,
            tool_input=tool_input,
            output_preview=output_preview[:500],
            timestamp=datetime.now(UTC),
        )
        await persist_realtime_run_update(event)

    async def monitor_workspace_diff() -> None:
        nonlocal last_diff_signature
        while not stop_monitor.is_set():
            await asyncio.sleep(1.0)
            diff_summary = capture_workspace_diff(workspace_path)
            if not diff_summary:
                continue
            signature = json.dumps(diff_summary, sort_keys=True)
            if signature == last_diff_signature:
                continue
            last_diff_signature = signature
            run.diff_summary = diff_summary
            await persist_realtime_run_update()

    monitor_task = asyncio.create_task(monitor_workspace_diff()) if workspace_path else None
    try:
        result = await runtime.run(
            prompt,
            agent=agent_name,
            workspace_path=workspace_path,
            session=resume_session,
            effort=runtime_policy.effort,
            on_chunk=record_output_chunk,
            on_tool_event=record_runtime_event,
        )
    finally:
        # IMP-010: always stop the monitor task regardless of whether runtime.run()
        # raised. Without this, the monitor keeps writing to the (possibly
        # rolled-back) session after the exception propagates upward.
        stop_monitor.set()
        if monitor_task is not None:
            monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await monitor_task

    diff_summary = result.diff_summary or capture_workspace_diff(workspace_path)
    observability = _run_observability(
        task=task,
        result=result,
        runtime_name=runtime_name,
        runtime_policy=runtime_policy,
        agent_name=agent_name,
        prompt=prompt,
        prompt_budget=prompt_budget,
    )
    run.session_id = result.session_id
    run.runtime_sdk = runtime_name
    run.provider = runtime_provider
    run.model = str(runtime_config.get("model") or runtime_policy.model)
    run.effort = runtime_policy.effort
    run.cost_usd = result.cost_usd
    run.tokens_input = result.tokens_input
    run.tokens_output = result.tokens_output
    run.tokens_cached = result.tokens_cached
    run.num_turns = result.num_turns
    run.duration_ms = result.duration_ms
    run.stop_reason = result.stop_reason
    run.status = "completed" if not result.error else "failed"
    run.error = result.error
    run.output_text = result.output_text or "".join(output_parts)
    preview = " ".join("".join(pending_output_parts).strip().split())
    final_event = _agent_output_event(run.id, preview)
    run.confidence = result.confidence
    run.diff_summary = diff_summary
    run.observability = observability or result.observability
    run.completed_at = datetime.now(UTC)
    await persist_realtime_run_update(*([final_event] if final_event is not None else []))

    return result
