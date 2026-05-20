"""Runtime status payload helpers for embedded Agent chat routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_turn_intent import ChatRunTotals
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.runtime_settings import resolve_project_runtime_config


def runtime_metadata_for_agent(
    agent_name: str, project_root: Path | None = None
) -> dict[str, Any]:
    settings = get_settings()
    agent_def = get_agent_definition(agent_name)
    policy = resolve_agent_runtime_policy(agent_def, settings)
    runtime_config = (
        resolve_project_runtime_config(project_root)
        if project_root is not None
        else resolve_runtime_config(settings)
    )
    return {
        "model": str(runtime_config.get("model") or policy.model),
        "effort": policy.effort,
        "runtime_sdk": str(runtime_config.get("sdk") or ""),
        "provider": str(runtime_config.get("provider") or ""),
    }


def chat_runtime_metadata(project_root: Path) -> dict[str, Any]:
    return runtime_metadata_for_agent("chat", project_root)


def chat_model_name(project_root: Path) -> str:
    return str(chat_runtime_metadata(project_root)["model"])


def initial_status(agent_name: str, project_root: Path | None = None) -> dict[str, Any]:
    agent_def = get_agent_definition(agent_name)
    return {
        **runtime_metadata_for_agent(agent_name, project_root),
        "running": True,
        "current_turn": 0,
        "max_turns": agent_def.max_turns,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }


def chat_run_status_payload(
    *,
    agent_name: str,
    project_root: Path,
    result: RunResult,
    totals: ChatRunTotals,
    max_turns: int,
    stop_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **runtime_metadata_for_agent(agent_name, project_root),
        "running": False,
        "current_turn": totals.turns,
        "max_turns": max_turns,
        **agent_chat_transcript.token_usage_status_payload(
            tokens_input=totals.tokens_input,
            tokens_output=totals.tokens_output,
            tokens_cached=totals.tokens_cached,
        ),
        "cost_usd": totals.cost_usd,
        "sdk_session_id": result.session_id,
        "duration_ms": totals.duration_ms,
        "stop_reason": stop_reason if stop_reason is not None else result.stop_reason,
        "observability": result.observability or {},
        **(extra or {}),
    }
