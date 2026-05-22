"""Helpers for assembling ClaudeAgentOptions, SDK hook matchers, and RunResult
construction from SDK message stream events.

Extracted from ``agents/runner.py::AgentRunner._execute_query`` to keep the
runtime entry point at a readable size. These helpers are pure builders — no
SDK calls, no I/O. They take Builder-side state (AgentDefinition, runtime
policy, allowed tools) and return SDK-shaped values or RunResult instances.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from autonomous_agent_builder.agents.definitions import (
    AgentDefinition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.execution_policy import (
    AgentRuntimePolicy,
    resolve_subagent_model,
)
from autonomous_agent_builder.observability import ClaudeObservabilityConfig
from autonomous_agent_builder.onecli_runtime import scrub_provider_env


def resolve_allowed_tools(
    agent_def: AgentDefinition,
    can_use_tool: Any | None,
    subagents: tuple[str, ...] | None,
) -> list[str]:
    """Pick the visible tool list per the agent definition + interactive lane."""
    selected = (
        agent_def.tools
        if can_use_tool is not None
        else (agent_def.auto_approve_tools or agent_def.tools)
    )
    allowed = list(selected)
    if subagents and "Agent" not in allowed:
        allowed.append("Agent")
    return allowed


def resolve_sdk_subagents(
    subagents: tuple[str, ...] | None,
    sdk_subagent_cls: Any,
) -> dict[str, Any] | None:
    """Build the SDK ``agents`` mapping for delegated specialist lanes."""
    if not subagents:
        return None
    result: dict[str, Any] = {}
    for name in subagents:
        sub_def = get_subagent_definition(name)
        kwargs: dict[str, Any] = {
            "description": sub_def.description,
            "prompt": sub_def.prompt,
            "tools": list(sub_def.tools),
            "model": resolve_subagent_model(sub_def),
        }
        if sub_def.max_turns is not None:
            kwargs["maxTurns"] = sub_def.max_turns
        result[name] = sdk_subagent_cls(**kwargs)
    return result


def build_options_kwargs(
    *,
    agent_def: AgentDefinition,
    runtime_policy: AgentRuntimePolicy,
    allowed_tools: list[str],
    workspace_path: str,
    mcp_servers: dict[str, Any],
    permission_mode: str,
    sdk_subagents: dict[str, Any] | None,
    effective_can_use_tool: Any,
) -> dict[str, Any]:
    """Assemble the ClaudeAgentOptions kwargs dict (no SDK type construction)."""
    return {
        "allowed_tools": allowed_tools,
        "system_prompt": {
            "type": "preset",
            "preset": "claude_code",
            "exclude_dynamic_sections": True,  # G2
        },
        "setting_sources": ["project"],
        "settings": '{"autoCompactEnabled": true}'
        if runtime_policy.autocompact_enabled
        else None,
        "mcp_servers": mcp_servers,
        "permission_mode": permission_mode,
        "model": runtime_policy.model,
        "cwd": workspace_path or None,
        "max_turns": agent_def.max_turns,
        "max_budget_usd": agent_def.max_budget_usd,
        "can_use_tool": effective_can_use_tool,
        "agents": sdk_subagents,
        "effort": runtime_policy.effort,
        "thinking": runtime_policy.thinking,
        "include_partial_messages": True,  # G1
        "strict_mcp_config": True,  # G7
        "extra_args": {"disable-slash-commands": None},
    }


def merge_child_env(
    options: Any,
    observability: ClaudeObservabilityConfig,
    source_env: dict[str, str],
) -> None:
    """Attach observability + scrubbed provider env to ``options.env`` in place."""
    child_env: dict[str, str] = {**observability.env}
    if source_env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        child_env["CLAUDE_CODE_OAUTH_TOKEN"] = source_env["CLAUDE_CODE_OAUTH_TOKEN"]
    merged = scrub_provider_env(child_env)
    if merged:
        options.env = {**getattr(options, "env", {}), **merged}


def build_run_result_from_result_message(
    *,
    run_result_cls: Any,
    message: Any,
    output_parts: list[str],
    session_id: str | None,
    workspace_path: str,
    observability: Any,
    runtime_policy: Any,
    rate_limit_info_captured: Any,
    parse_confidence: Any,
    capture_diff: Any,
) -> Any:
    """Build a RunResult from a SDK ResultMessage, applying provider-limit
    supersession when a RateLimitEvent fired earlier in the same session."""
    usage = message.usage or {}
    output_text = "\n".join(output_parts)
    stop_reason = getattr(message, "stop_reason", None)
    confidence: float | None = None
    if stop_reason not in ("max_turns", "budget_exceeded"):
        confidence = parse_confidence(output_text)
    base_kwargs: dict[str, Any] = dict(
        session_id=getattr(message, "session_id", None) or session_id,
        cost_usd=getattr(message, "total_cost_usd", 0.0),
        tokens_input=usage.get("input_tokens", 0),
        tokens_output=usage.get("output_tokens", 0),
        tokens_cached=usage.get("cache_read_input_tokens", 0),
        num_turns=getattr(message, "num_turns", 0),
        duration_ms=getattr(message, "duration_ms", 0),
        output_text=output_text,
        confidence=confidence,
        diff_summary=capture_diff(workspace_path),
        observability={**observability.summary, "runtime_policy": runtime_policy.to_payload()},
    )
    if rate_limit_info_captured is not None:
        info = rate_limit_info_captured
        resets_at_iso = (
            datetime.fromtimestamp(info.resets_at / 1000, UTC).isoformat()
            if info.resets_at
            else None
        )
        return run_result_cls(
            **base_kwargs,
            stop_reason="provider_limit",
            provider_limit={
                "code": "provider_limit",
                "reason": "rate_limit_event",
                "reset_at": resets_at_iso,
                "rate_limit_type": info.rate_limit_type,
                "utilization": info.utilization,
                "source": "claude_agent_sdk",
            },
        )
    return run_result_cls(**base_kwargs, stop_reason=stop_reason)


def map_sdk_exception_to_result(
    *,
    run_result_cls: Any,
    exc: Exception,
    observability: Any,
    runtime_policy: Any,
    configuration_error_cls: type[Exception],
    transient_error_cls: type[Exception],
    is_provider_limit: Any,
    parse_reset: Any,
) -> Any:
    """Translate an SDK exception into either a RunResult (provider limit /
    connection / process errors) or raise a Builder-typed error to the caller."""
    error_type = type(exc).__name__
    if error_type == "CLINotFoundError":
        raise configuration_error_cls("Claude Code CLI not installed") from exc
    if error_type == "CLIConnectionError":
        return run_result_cls(error=f"{exc} (cause: {exc.__cause__})")
    if error_type == "ProcessError":
        exit_code = getattr(exc, "exit_code", -1)
        if is_provider_limit(str(exc)):
            reset_at, reset_hint = parse_reset(str(exc))
            return run_result_cls(
                output_text=str(exc),
                stop_reason="provider_limit",
                provider_limit={
                    "code": "provider_limit",
                    "reason": "process_error",
                    "reset_at": reset_at.isoformat() if reset_at else None,
                    "reset_hint": reset_hint,
                    "source": "claude_agent_sdk",
                },
                observability={**observability.summary, "runtime_policy": runtime_policy.to_payload()},
            )
        if exit_code in (1, 2):
            raise transient_error_cls(f"Process error (exit {exit_code}): {exc}") from exc
        return run_result_cls(error=str(exc), stop_reason="process_error")
    if error_type == "CLIJSONDecodeError":
        raise transient_error_cls(f"Malformed SDK output: {exc}") from exc
    raise exc


def build_hooks_dict(
    *,
    agent_name: str,
    hook_matcher_cls: Any,
    post_tool_audit: Any,
) -> dict[str, list[Any]]:
    """Return the SDK ``options.hooks`` dict wiring all PreToolUse / PostToolUse /
    SessionStart / SubagentStop / Stop matchers Builder relies on."""
    from autonomous_agent_builder.agents.hooks import (
        audit_subagent_stop,
        enforce_completion_evidence,
        enforce_workspace_boundary,
        keep_tool_stream_open,
        make_enforce_claude_md_block_ownership,
        session_start_context_policy,
        validate_bash_argv,
    )
    from autonomous_agent_builder.agents.hooks_trim import trim_tool_output_for_context

    claude_md_block_hook = make_enforce_claude_md_block_ownership(agent_name)
    return {
        "SessionStart": [
            hook_matcher_cls(matcher=".*", hooks=[session_start_context_policy], timeout=30.0),
        ],
        "PreToolUse": [
            hook_matcher_cls(matcher=".*", hooks=[keep_tool_stream_open], timeout=30.0),
            hook_matcher_cls(
                matcher="Read|Edit|Write|Glob|Grep",
                hooks=[enforce_workspace_boundary],
                timeout=30.0,
            ),
            hook_matcher_cls(matcher="Edit|Write", hooks=[claude_md_block_hook], timeout=30.0),
            hook_matcher_cls(matcher="Bash", hooks=[validate_bash_argv], timeout=30.0),
        ],
        "PostToolUse": [
            hook_matcher_cls(matcher=".*", hooks=[post_tool_audit], timeout=30.0),
            hook_matcher_cls(
                matcher="Bash|Read|mcp__workspace__run_tests|mcp__workspace__run_linter",
                hooks=[trim_tool_output_for_context],
                timeout=30.0,
            ),
        ],
        "SubagentStop": [
            hook_matcher_cls(matcher=".*", hooks=[audit_subagent_stop], timeout=30.0),
        ],
        "Stop": [
            hook_matcher_cls(matcher=".*", hooks=[enforce_completion_evidence], timeout=30.0),
        ],
    }
