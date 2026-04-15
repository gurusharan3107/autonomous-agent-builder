"""Agent runner — query() dispatch + ResultMessage cost + SDK error handling.

This is the core execution engine. It:
1. Builds a ToolRegistry for the agent
2. Dispatches via SDK query() with proper options
3. Captures session_id for phase chaining
4. Extracts cost/usage from ResultMessage
5. Handles SDK-specific errors (CLINotFoundError, ProcessError, CLIJSONDecodeError)
"""

from __future__ import annotations

from typing import Any

import structlog

from autonomous_agent_builder.agents.definitions import AgentDefinition, get_agent_definition
from autonomous_agent_builder.agents.tool_registry import ToolRegistry
from autonomous_agent_builder.config import Settings

log = structlog.get_logger()


class RunResult:
    """Result of an agent run — wraps SDK ResultMessage data."""

    def __init__(
        self,
        session_id: str | None = None,
        cost_usd: float = 0.0,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_cached: int = 0,
        num_turns: int = 0,
        duration_ms: int = 0,
        stop_reason: str | None = None,
        output_text: str = "",
        error: str | None = None,
    ):
        self.session_id = session_id
        self.cost_usd = cost_usd
        self.tokens_input = tokens_input
        self.tokens_output = tokens_output
        self.tokens_cached = tokens_cached
        self.num_turns = num_turns
        self.duration_ms = duration_ms
        self.stop_reason = stop_reason
        self.output_text = output_text
        self.error = error

    @property
    def hit_capability_limit(self) -> bool:
        return self.stop_reason in ("max_turns", "budget_exceeded")


class AgentRunner:
    """Runs SDLC agents using the Claude Agent SDK."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run_phase(
        self,
        agent_name: str,
        prompt: str,
        workspace_path: str,
        resume_session: str | None = None,
        custom_tools: dict[str, Any] | None = None,
        on_stream: Any | None = None,
    ) -> RunResult:
        """Execute an agent phase.

        Args:
            agent_name: Key in AGENT_DEFINITIONS.
            prompt: Formatted prompt with template vars filled.
            workspace_path: Path to the task workspace.
            resume_session: session_id from a prior phase for context chaining.
            custom_tools: Dict of custom tool name -> callable.
            on_stream: Async callback for streaming output to dashboard.

        Returns:
            RunResult with cost, session_id, and output.
        """
        agent_def = get_agent_definition(agent_name)

        # Build ToolRegistry — schema discovery at phase start
        registry = ToolRegistry.build(
            allowed_tool_names=list(agent_def.tools),
            custom_tools=custom_tools,
        )

        log.info(
            "agent_phase_start",
            agent=agent_name,
            model=agent_def.model,
            tools=registry.list_tools(),
            workspace=workspace_path,
            resume=resume_session is not None,
        )

        try:
            result = await self._execute_query(
                agent_def=agent_def,
                prompt=prompt,
                workspace_path=workspace_path,
                registry=registry,
                resume_session=resume_session,
                on_stream=on_stream,
            )
        except ConfigurationError:
            raise
        except TransientError as e:
            log.warning("agent_transient_error", agent=agent_name, error=str(e))
            raise
        except Exception as e:
            log.error("agent_unexpected_error", agent=agent_name, error=str(e))
            return RunResult(error=str(e))

        log.info(
            "agent_phase_complete",
            agent=agent_name,
            cost_usd=result.cost_usd,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            num_turns=result.num_turns,
            stop_reason=result.stop_reason,
        )

        return result

    async def _execute_query(
        self,
        agent_def: AgentDefinition,
        prompt: str,
        workspace_path: str,
        registry: ToolRegistry,
        resume_session: str | None,
        on_stream: Any | None,
    ) -> RunResult:
        """Execute the SDK query() call.

        This is separated to allow mocking in tests. In production,
        this calls the actual Claude Agent SDK.
        """
        # Import SDK at call time — allows graceful degradation if not installed
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                HookMatcher,
                ResultMessage,
                SystemMessage,
                query,
            )
        except ImportError as exc:
            raise ConfigurationError(
                "Claude Agent SDK not installed. Run: pip install claude-agent-sdk"
            ) from exc

        session_id = None
        output_parts: list[str] = []

        options = ClaudeAgentOptions(
            allowed_tools=list(agent_def.tools),
            permission_mode=self.settings.agent.permission_mode,
            model=agent_def.model,
            cwd=workspace_path or None,
            max_turns=agent_def.max_turns,
            max_budget_usd=agent_def.max_budget_usd,
        )

        if resume_session:
            options.resume = resume_session

        # Wire safety and audit hooks with SDK signatures
        from autonomous_agent_builder.agents.hooks import (
            audit_log_tool_use,
            enforce_workspace_boundary,
            validate_bash_argv,
        )

        options.hooks = {
            "PreToolUse": [
                HookMatcher(
                    matcher="Read|Edit|Write|Glob|Grep",
                    hooks=[enforce_workspace_boundary],
                    timeout=30.0,
                ),
                HookMatcher(
                    matcher="Bash",
                    hooks=[validate_bash_argv],
                    timeout=30.0,
                ),
            ],
            "PostToolUse": [
                HookMatcher(
                    matcher=".*",
                    hooks=[audit_log_tool_use],
                    timeout=30.0,
                ),
            ],
        }

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    session_id = message.data.get("session_id")

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text"):
                            output_parts.append(block.text)
                            if on_stream:
                                await on_stream(block.text)

                elif isinstance(message, ResultMessage):
                    usage = message.usage or {}
                    return RunResult(
                        session_id=session_id,
                        cost_usd=getattr(message, "total_cost_usd", 0.0),
                        tokens_input=usage.get("input_tokens", 0),
                        tokens_output=usage.get("output_tokens", 0),
                        tokens_cached=usage.get("cache_read_input_tokens", 0),
                        num_turns=getattr(message, "num_turns", 0),
                        duration_ms=getattr(message, "duration_ms", 0),
                        stop_reason=getattr(message, "stop_reason", None),
                        output_text="\n".join(output_parts),
                    )

        except Exception as e:
            # Map SDK errors to our error types
            error_type = type(e).__name__
            log.error(
                "sdk_query_error",
                error_type=error_type,
                error=str(e),
                cause=str(e.__cause__) if e.__cause__ else None,
            )
            if error_type == "CLINotFoundError":
                raise ConfigurationError("Claude Code CLI not installed") from e
            elif error_type == "CLIConnectionError":
                return RunResult(error=f"{e} (cause: {e.__cause__})")
            elif error_type == "ProcessError":
                exit_code = getattr(e, "exit_code", -1)
                if exit_code in (1, 2):
                    raise TransientError(f"Process error (exit {exit_code}): {e}") from e
                else:
                    return RunResult(error=str(e), stop_reason="process_error")
            elif error_type == "CLIJSONDecodeError":
                raise TransientError(f"Malformed SDK output: {e}") from e
            raise

        # If we get here without a ResultMessage, something went wrong
        return RunResult(
            session_id=session_id,
            output_text="\n".join(output_parts),
            error="No ResultMessage received",
        )


class ConfigurationError(Exception):
    """Non-retryable configuration error."""


class TransientError(Exception):
    """Retryable transient error."""
