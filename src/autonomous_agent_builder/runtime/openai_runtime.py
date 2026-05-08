"""OpenAI Agents SDK runtime adapter."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)


class OpenAIAgentsRuntime(AgentRuntime):
    """API-backed OpenAI Agents SDK adapter.

    This path is for provider API keys such as OpenCode Go. It is not the
    ChatGPT/Codex subscription path; subscription auth is owned by Codex CLI.
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        provider: str | None = None,
        api_base_url: str | None = None,
        api_key_env: str | None = None,
        tracing: str = "builder",
    ):
        self._model = model or "minimax-m2.7"
        self._provider = provider or "opencode_go"
        self._api_base_url = (api_base_url or "https://opencode.ai/zen/go/v1").rstrip("/")
        self._api_key_env = api_key_env or "OPENCODE_GO_API_KEY"
        self._tracing = tracing

    @property
    def name(self) -> str:
        return "openai_agents"

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def api_base_url(self) -> str:
        return self._api_base_url

    @property
    def api_key_env(self) -> str:
        return self._api_key_env

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            chat=True,
            streaming=False,
            tools=True,
            mcp=False,
            subagents=True,
            workspace_access=False,
            shell=False,
            sandboxing=False,
            approvals=False,
            session_resume=False,
            subscription_auth=False,
            api_key_auth=True,
            model_listing=True,
            provider_limit_detection=True,
            tracing=self._tracing != "off",
            native_user_input=True,
        )

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
        """Execute an OpenAI Agents SDK run through an API-compatible provider."""
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            return RunResult(
                error=f"Missing API key environment variable: {self._api_key_env}",
                stop_reason="configuration_error",
            )

        try:
            from agents import (
                Agent,
                OpenAIChatCompletionsModel,
                Runner,
                function_tool,
                set_tracing_disabled,
            )
            from openai import AsyncOpenAI
        except ImportError:
            return RunResult(
                error=(
                    "OpenAI Agents SDK is not installed. Install optional dependency "
                    "`openai-agents` to use sdk=openai_agents."
                ),
                stop_reason="configuration_error",
            )

        try:
            set_tracing_disabled(self._tracing == "off")
            client = AsyncOpenAI(api_key=api_key, base_url=self._api_base_url)
            model = OpenAIChatCompletionsModel(model=self._model, openai_client=client)
            agent_tools: list[Any] = []
            if can_use_tool is not None:

                async def request_user_input(questions: list[dict[str, Any]]) -> dict[str, Any]:
                    """Ask the operator one or more bounded multiple-choice questions."""

                    permission = await can_use_tool(
                        "request_user_input",
                        {
                            "questions": questions,
                            "runtime_sdk": self.name,
                            "native_tool": "function_tool",
                        },
                        {},
                    )
                    updated_input = getattr(permission, "updated_input", None) or getattr(
                        permission,
                        "updatedInput",
                        None,
                    )
                    if isinstance(updated_input, dict):
                        return updated_input
                    return {"questions": questions, "answers": {}}

                agent_tools.append(function_tool(request_user_input))
            sdk_agent = Agent(
                name=agent,
                instructions=_instructions_for_agent(agent, workspace_path=workspace_path),
                model=model,
                tools=agent_tools,
            )
            result = await Runner.run(sdk_agent, input, max_turns=max_turns)
            output = str(getattr(result, "final_output", "") or "").strip()
            if on_chunk and output:
                emitted = on_chunk(output)
                if hasattr(emitted, "__await__"):
                    await emitted
            return RunResult(
                output=output,
                stop_reason="completed",
                observability={"model": self._model, "effort": effort},
            )
        except Exception as exc:
            text = str(exc)
            if is_provider_limit_text(text):
                reset_at, reset_hint = parse_reset_hint(text)
                return RunResult(
                    output=text,
                    stop_reason="provider_limit",
                    provider_limit={
                        "code": "provider_limit",
                        "reason": "openai_agents_limit",
                        "reset_at": reset_at.isoformat() if reset_at else None,
                        "reset_hint": reset_hint,
                        "source": self._provider,
                    },
                )
            return RunResult(error=text, stop_reason="runtime_error")

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> bool:
        return (await self.probe()).ok

    async def probe(self) -> RuntimeProbeResult:
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            return RuntimeProbeResult(
                ok=False,
                sdk=self.name,
                provider=self._provider,
                model=self._model,
                code="missing_api_key_env",
                message=f"Environment variable {self._api_key_env} is not set.",
                next=f"export {self._api_key_env}=...; builder agent runtime probe --json",
                capabilities=self.capabilities(),
                detail={"api_base_url": self._api_base_url, "api_key_env": self._api_key_env},
            )

        models = await self.list_models(api_key=api_key)
        ok = models["ok"]
        return RuntimeProbeResult(
            ok=ok,
            sdk=self.name,
            provider=self._provider,
            model=self._model,
            code="provider_models_available" if ok else str(models.get("code") or "probe_failed"),
            message=(
                "Provider models endpoint is reachable."
                if ok
                else str(models.get("message") or "Provider probe failed.")
            ),
            next="" if ok else f"Check {self._api_key_env} and {self._api_base_url}/models.",
            capabilities=self.capabilities(),
            detail={
                "api_base_url": self._api_base_url,
                "api_key_env": self._api_key_env,
                "models": models.get("models", []),
            },
        )

    async def list_models(self, *, api_key: str | None = None) -> dict[str, Any]:
        key = api_key or os.environ.get(self._api_key_env, "")
        if not key:
            return {
                "ok": False,
                "code": "missing_api_key_env",
                "message": f"Environment variable {self._api_key_env} is not set.",
                "models": [],
            }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self._api_base_url}/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "code": "models_fetch_failed",
                "message": str(exc),
                "models": [],
            }

        raw_models = payload.get("data", payload if isinstance(payload, list) else [])
        models: list[dict[str, Any]] = []
        if isinstance(raw_models, list):
            for item in raw_models:
                if isinstance(item, dict):
                    model_id = str(item.get("id") or item.get("name") or "").strip()
                    if model_id:
                        models.append({"id": model_id, **item})
                elif isinstance(item, str):
                    models.append({"id": item})
        return {"ok": True, "code": "ok", "message": "models fetched", "models": models}


def _instructions_for_agent(agent: str, *, workspace_path: str | None) -> str:
    workspace_note = f"Workspace path: {workspace_path}" if workspace_path else "No workspace path."
    return (
        f"You are the Autonomous Agent Builder {agent} agent. "
        "Use only the capabilities available through this API-backed harness. "
        f"{workspace_note}"
    )


# Backward-compatible import name for older tests and callers.
OpenAIRuntime = OpenAIAgentsRuntime
