"""Claude Agent SDK wrapper - implements AgentRuntime interface."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.runner import AgentRunner
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)


def _runner_result_to_runtime_result(result: Any) -> RunResult:
    return RunResult(
        session_id=result.session_id,
        output=result.output_text,
        error=result.error,
        cost_usd=result.cost_usd,
        tokens_input=result.tokens_input,
        tokens_output=result.tokens_output,
        tokens_cached=getattr(result, "tokens_cached", 0),
        num_turns=result.num_turns,
        duration_ms=result.duration_ms,
        stop_reason=result.stop_reason,
        confidence=getattr(result, "confidence", None),
        diff_summary=getattr(result, "diff_summary", None),
        observability=getattr(result, "observability", None),
        provider_limit=getattr(result, "provider_limit", None),
    )


def _should_retry_without_resume(error: Exception, session: str | None) -> bool:
    if not session:
        return False
    text = str(error)
    return "Process error (exit 1)" in text or "Process error (exit 2)" in text


class ClaudeRuntime(AgentRuntime):
    """Claude Agent SDK wrapper.

    Wraps the existing AgentRunner in the AgentRuntime interface.
    """

    def __init__(self, model: str | None = None, provider: str | None = None):
        self._settings = get_settings()
        self._model = model or self._settings.runtime.model
        self._provider = provider or "claude_code"
        self._runner = AgentRunner(self._settings)

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    async def run(
        self,
        input: str,
        *,
        agent: str,
        workspace_path: str | None = None,
        tools: list[str] | None = None,
        session: str | None = None,
        max_turns: int = 30,
        max_budget: float = 5.0,
        effort: str | None = None,
        on_chunk: Callable[[str], Any] | None = None,
        subagents: tuple[str, ...] | None = None,
        can_use_tool: Callable[..., Any] | None = None,
        on_tool_event: Callable[..., Any] | None = None,
    ) -> RunResult:
        """Execute using existing AgentRunner.

        Note: max_turns and max_budget are controlled by the agent definition
        in AgentRunner, not by these parameters. Pass them for interface
        compatibility; they are not forwarded. `effort` is resolved inside
        AgentRunner for Claude SDK options.

        Note: tools names are not forwarded — the agent definition controls
        the base tool set. Custom callable tools are not yet supported through
        this interface.
        """
        resolved_workspace = workspace_path or str(Path.cwd())
        try:
            result = await self._runner.run_phase(
                agent_name=agent,
                prompt=input,
                workspace_path=resolved_workspace,
                resume_session=session,
                subagents=subagents,
                on_stream=on_chunk,
                can_use_tool=can_use_tool,
                on_tool_event=on_tool_event,
            )
            return _runner_result_to_runtime_result(result)
        except Exception as e:
            if _should_retry_without_resume(e, session):
                try:
                    result = await self._runner.run_phase(
                        agent_name=agent,
                        prompt=input,
                        workspace_path=resolved_workspace,
                        resume_session=None,
                        subagents=subagents,
                        on_stream=on_chunk,
                        can_use_tool=can_use_tool,
                        on_tool_event=on_tool_event,
                    )
                    runtime_result = _runner_result_to_runtime_result(result)
                    observability = dict(runtime_result.observability or {})
                    observability["resume_retry"] = {
                        "attempted": True,
                        "reason": str(e),
                        "fallback": "fresh_model_turn",
                    }
                    runtime_result.observability = observability
                    return runtime_result
                except Exception as retry_error:
                    return RunResult(
                        error=f"{retry_error} (resume retry after: {e})",
                    )
            return RunResult(
                error=str(e),
            )

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            chat=True,
            streaming=True,
            tools=True,
            mcp=True,
            subagents=True,
            workspace_access=True,
            shell=True,
            sandboxing=True,
            approvals=True,
            session_resume=True,
            subscription_auth=True,
            api_key_auth=False,
            model_listing=False,
            provider_limit_detection=True,
            tracing=True,
        )

    async def probe(self) -> RuntimeProbeResult:
        from pathlib import Path

        from autonomous_agent_builder.claude_runtime import check_claude_availability

        result = await check_claude_availability(
            workspace_path=Path.cwd(),
            model=self._model,
        )
        return RuntimeProbeResult(
            ok=result.available,
            sdk=self.name,
            provider=self._provider,
            model=self._model,
            code="claude_available" if result.available else "claude_unavailable",
            message=result.message,
            next=(
                ""
                if result.available
                else "Run `claude login` and retry `builder agent runtime probe --json`."
            ),
            capabilities=self.capabilities(),
            detail={"backend": result.backend},
        )

    async def shutdown(self) -> None:
        """Cleanup - currently no-op for Claude SDK."""
        pass

    async def health_check(self) -> bool:
        """Check Claude availability."""
        return (await self.probe()).ok
