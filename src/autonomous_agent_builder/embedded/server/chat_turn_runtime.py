"""Agent chat-turn runtime execution helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.embedded.server.chat_turn_intent import ChatRunTotals


async def run_chat_runtime_loop(
    *,
    runtime: Any,
    prompt: str,
    agent_name: str,
    project_root: Path,
    run_session: str | None,
    runtime_policy: Any,
    feature_spec_requested: bool,
    active_specialist: Any | None,
    on_stream: Callable[[str], Awaitable[None]],
    can_use_tool: Callable[[str, dict[str, Any], Any], Awaitable[Any]],
    on_tool_event: Callable[..., Awaitable[None]],
    max_requirements_continuations: int,
    requires_autonomous_continuation: Callable[[str], bool],
    continuation_prompt: Callable[..., str],
) -> tuple[RunResult, ChatRunTotals]:
    result: RunResult | None = None
    total_tokens_input = 0
    total_tokens_output = 0
    total_tokens_cached = 0
    total_cost_usd = 0.0
    total_duration_ms = 0
    total_turns = 0

    for continuation_index in range(max_requirements_continuations):
        result = await runtime.run(
            prompt,
            agent=agent_name,
            workspace_path=str(project_root),
            session=run_session,
            effort=runtime_policy.effort,
            approval_policy=(
                "on-request" if feature_spec_requested and runtime.name.startswith("codex") else None
            ),
            subagents=(active_specialist.name,) if active_specialist is not None else None,
            on_chunk=on_stream,
            can_use_tool=can_use_tool,
            on_tool_event=on_tool_event,
        )
        total_tokens_input += result.tokens_input
        total_tokens_output += result.tokens_output
        total_tokens_cached += result.tokens_cached
        total_cost_usd += result.cost_usd
        total_duration_ms += result.duration_ms
        total_turns += result.num_turns
        if result.error or agent_name != "init-project-chat":
            break
        visible_probe = result.output_text or ""
        if not requires_autonomous_continuation(visible_probe):
            break
        if continuation_index == max_requirements_continuations - 1:
            break
        run_session = result.session_id or run_session
        prompt = continuation_prompt(
            project_root,
            previous_response=visible_probe,
            runtime_sdk=runtime.name,
        )

    if result is None:
        raise RuntimeError("Agent run did not start.")

    return result, ChatRunTotals(
        tokens_input=total_tokens_input,
        tokens_output=total_tokens_output,
        tokens_cached=total_tokens_cached,
        cost_usd=total_cost_usd,
        duration_ms=total_duration_ms,
        turns=total_turns,
    )
