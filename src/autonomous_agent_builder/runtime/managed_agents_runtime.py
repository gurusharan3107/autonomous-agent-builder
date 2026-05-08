"""Anthropic Managed Agents wrapper — implements AgentRuntime interface.

Third runtime lane (`RUNTIME_SDK=claude_managed`). Translates one builder
agent invocation into:

    sessions.create(agent=<pre-created>, environment_id=<pre-created>, ...)
    -> SSE stream consumption (stream-first per MA docs Pattern 7)
    -> RunResult mapped from agent.message + span.model_request_end events

Builder DB stays canonical: cost, tokens, session_id, runtime attribution
flow back into agent_runs / agent_run_events via the existing AgentRuntime
contract. No new DB tables.

Memory: agents in MA sessions access builder memory via the
`builder_memory_search` custom tool (host-side; see
managed_agents_custom_tools.py). The filesystem-based `.memory/` contract
is preserved; no Memory Stores projection.

Pre-conditions:
- ANTHROPIC_API_KEY set in env
- `.agent-builder/managed_agents.json` exists with at least the agent_id
  for the requested role (run `builder agent runtime managed-agents setup`
  to provision)
- Project has a GitHub remote (Phase C will attach github_repository
  resources; Phase A runs without a workspace mount)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)
from autonomous_agent_builder.runtime.managed_agents_custom_tools import (
    CustomToolRegistry,
    default_custom_tool_registry,
)
from autonomous_agent_builder.runtime.managed_agents_workspace import (
    WORKSPACE_REQUIRED_ROLES,
    build_github_resource,
)

log = structlog.get_logger()

_MA_CONFIG_PATH = Path(".agent-builder/managed_agents.json")


class ManagedAgentsConfigError(RuntimeError):
    """Raised when MA configuration (agent IDs, environment IDs) is missing."""


def _load_managed_agents_config(project_root: Path | None = None) -> dict[str, Any]:
    """Read `.agent-builder/managed_agents.json` for agent + environment IDs.

    Returns the parsed JSON or raises ManagedAgentsConfigError if missing.
    Setup: `builder agent runtime managed-agents setup`.
    """
    root = project_root or Path.cwd()
    path = root / _MA_CONFIG_PATH
    if not path.exists():
        raise ManagedAgentsConfigError(
            f"Managed Agents config not found at {path}. "
            "Run `builder agent runtime managed-agents setup` first."
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ManagedAgentsConfigError(
            f"Managed Agents config at {path} is invalid JSON: {exc}"
        ) from exc


def _agent_id_for_role(config: dict[str, Any], role: str) -> str:
    agents = config.get("agents") or {}
    agent_id = agents.get(role)
    if not agent_id:
        raise ManagedAgentsConfigError(
            f"No managed agent provisioned for role '{role}'. "
            f"Available roles: {sorted(agents.keys()) or 'none'}. "
            "Run `builder agent runtime managed-agents setup` to provision."
        )
    return str(agent_id)


def _environment_id(config: dict[str, Any]) -> str:
    env_id = config.get("environment_id")
    if not env_id:
        raise ManagedAgentsConfigError(
            "No managed-agents environment provisioned. "
            "Run `builder agent runtime managed-agents setup` to provision."
        )
    return str(env_id)


def _vault_ids(config: dict[str, Any]) -> list[str]:
    """Return the list of vault IDs to attach at session create.

    Phase C+: vaults hold OAuth credentials for MCP servers (e.g. GitHub
    Copilot MCP for PR creation). Sessions on roles that use MCP tools
    (pr-creator, integration-resolver) need the vault attached so
    Anthropic-side proxies can inject credentials post-sandbox.
    """
    vaults = config.get("vaults") or {}
    if not isinstance(vaults, dict):
        return []
    return [str(v) for v in vaults.values() if v]


class ManagedAgentsRuntime(AgentRuntime):
    """Anthropic Managed Agents adapter — third user-facing runtime lane.

    Implements the AgentRuntime ABC by wrapping `client.beta.sessions.*`.
    Stream-first SSE consumption per `shared/managed-agents-client-patterns.md`
    Pattern 7; idle-break gate per Pattern 5; reconnect-with-dedupe per
    Pattern 1 (deferred to a later phase — Phase A breaks on disconnect).
    """

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        custom_tool_registry: CustomToolRegistry | None = None,
        config_loader: Callable[[], dict[str, Any]] | None = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        self._settings = get_settings()
        self._model = model or "claude-opus-4-7"
        self._provider = provider or "anthropic_managed"
        self._custom_tools = custom_tool_registry or default_custom_tool_registry()
        self._config_loader = config_loader or _load_managed_agents_config
        self._client_factory = client_factory or self._default_client_factory

    @staticmethod
    def _default_client_factory() -> Any:
        import anthropic  # local import — only when MA lane is active

        return anthropic.AsyncAnthropic()

    @property
    def name(self) -> str:
        return "claude_managed"

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

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
            approvals=True,  # via user.tool_confirmation
            session_resume=False,  # MA sessions are per-run; resume not in scope for Phase A
            subscription_auth=False,
            api_key_auth=True,
            model_listing=False,
            provider_limit_detection=True,
            tracing=True,
            native_user_input=True,
            request_permissions=True,
            app_server_events=True,
            token_usage_stream=True,
        )

    async def probe(self) -> RuntimeProbeResult:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return RuntimeProbeResult(
                ok=False,
                sdk=self.name,
                provider=self._provider,
                model=self._model,
                code="missing_api_key",
                message="ANTHROPIC_API_KEY is not set.",
                next="export ANTHROPIC_API_KEY=...; builder agent runtime probe --json",
                capabilities=self.capabilities(),
            )
        try:
            self._config_loader()
        except ManagedAgentsConfigError as exc:
            return RuntimeProbeResult(
                ok=False,
                sdk=self.name,
                provider=self._provider,
                model=self._model,
                code="missing_setup",
                message=str(exc),
                next="builder agent runtime managed-agents setup --json",
                capabilities=self.capabilities(),
            )
        try:
            client = self._client_factory()
            # Lightweight beta-access check
            await client.beta.agents.list(limit=1)
            ok = True
            code = "managed_agents_available"
            message = "Managed Agents API reachable; agents + environment provisioned."
            next_cmd = ""
        except Exception as exc:
            ok = False
            code = "managed_agents_unreachable"
            message = f"Managed Agents API check failed: {exc}"
            next_cmd = "Verify ANTHROPIC_API_KEY has Managed Agents beta access."
        return RuntimeProbeResult(
            ok=ok,
            sdk=self.name,
            provider=self._provider,
            model=self._model,
            code=code,
            message=message,
            next=next_cmd,
            capabilities=self.capabilities(),
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
        """Execute one builder agent invocation through Managed Agents.

        Resolves the pre-created agent_id for ``agent`` (role) from
        `.agent-builder/managed_agents.json`, opens an SSE stream BEFORE
        sending the kickoff `user.message` (per MA client patterns Pattern 7),
        consumes events until terminated/idle-with-terminal-stop_reason,
        and returns RunResult with cost/tokens/session_id mapped.

        Custom tools (e.g. `builder_memory_search`) are handled inline:
        when `agent.custom_tool_use` arrives, the registered handler runs
        host-side and `user.custom_tool_result` is sent back.
        """
        try:
            config = self._config_loader()
            agent_id = _agent_id_for_role(config, agent)
            environment_id = _environment_id(config)
        except ManagedAgentsConfigError as exc:
            return RunResult(error=str(exc))

        vault_ids = _vault_ids(config)
        repo_resource = build_github_resource(workspace_path=workspace_path)
        if repo_resource is None and agent in WORKSPACE_REQUIRED_ROLES:
            log.warning(
                "managed_agents_workspace_unavailable",
                role=agent,
                workspace_path=workspace_path,
                hint="Set GITHUB_TOKEN and ensure workspace has a GitHub origin remote.",
            )

        client = self._client_factory()
        start_t = time.monotonic()
        try:
            return await self._run_session(
                client=client,
                agent_id=agent_id,
                environment_id=environment_id,
                user_input=input,
                role=agent,
                on_chunk=on_chunk,
                start_t=start_t,
                resources=[repo_resource] if repo_resource else None,
                vault_ids=vault_ids or None,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_t) * 1000)
            log.error("managed_agents_run_failed", role=agent, error=str(exc))
            return RunResult(
                error=f"managed_agents run failed: {exc}",
                duration_ms=duration_ms,
            )
        finally:
            # AsyncAnthropic owns its httpx client; close to release sockets.
            with contextlib.suppress(Exception):
                await client.close()

    async def _run_session(
        self,
        *,
        client: Any,
        agent_id: str,
        environment_id: str,
        user_input: str,
        role: str,
        on_chunk: Callable[[str], Any] | None,
        start_t: float,
        resources: list[dict[str, Any]] | None = None,
        vault_ids: list[str] | None = None,
    ) -> RunResult:
        sessions = client.beta.sessions

        # 1. Create session referencing pre-created agent + environment
        create_kwargs: dict[str, Any] = {
            "agent": agent_id,
            "environment_id": environment_id,
            "title": f"builder/{role}",
        }
        if resources:
            create_kwargs["resources"] = resources
        if vault_ids:
            create_kwargs["vault_ids"] = vault_ids
        session = await sessions.create(**create_kwargs)
        session_id = session.id

        # Accumulators
        output_chunks: list[str] = []
        cost_usd = 0.0
        tokens_input = 0
        tokens_output = 0
        tokens_cached = 0
        num_turns = 0
        stop_reason: str | None = None
        provider_limit_detail: dict[str, Any] | None = None
        observability: dict[str, Any] = {
            "managed_agents": {
                "session_id": session_id,
                "agent_id": agent_id,
                "environment_id": environment_id,
                "role": role,
                "compactions": 0,
                "outcome_iterations": 0,
                "thread_spawns": 0,
                "resources": [r.get("type") for r in (resources or [])],
                "vault_count": len(vault_ids or []),
            }
        }

        # 2. Stream-first: open SSE BEFORE sending the kickoff user.message
        # Per MA Pattern 7 — sending first risks missing early events.
        async with sessions.events.stream(session_id=session_id) as stream:
            await sessions.events.send(
                session_id=session_id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": user_input}],
                    }
                ],
            )

            async for event in stream:
                event_type = getattr(event, "type", None)

                if event_type == "agent.message":
                    for block in getattr(event, "content", []) or []:
                        if getattr(block, "type", None) == "text":
                            text = getattr(block, "text", "") or ""
                            if text:
                                output_chunks.append(text)
                                if on_chunk is not None:
                                    try:
                                        result = on_chunk(text)
                                        if asyncio.iscoroutine(result):
                                            await result
                                    except Exception:  # pragma: no cover
                                        pass
                    num_turns += 1

                elif event_type == "span.model_request_end":
                    usage = getattr(event, "model_usage", None) or {}
                    tokens_input += int(_usage_get(usage, "input_tokens"))
                    tokens_output += int(_usage_get(usage, "output_tokens"))
                    tokens_cached += int(_usage_get(usage, "cache_read_input_tokens"))

                elif event_type == "agent.thread_context_compacted":
                    observability["managed_agents"]["compactions"] += 1

                elif event_type == "session.thread_created":
                    observability["managed_agents"]["thread_spawns"] += 1

                elif event_type == "span.outcome_evaluation_end":
                    observability["managed_agents"]["outcome_iterations"] += 1

                elif event_type == "agent.custom_tool_use":
                    await self._handle_custom_tool(
                        client=client,
                        session_id=session_id,
                        event=event,
                    )

                elif event_type == "session.error":
                    err_obj = getattr(event, "error", None)
                    err_msg = (
                        getattr(err_obj, "message", None) if err_obj is not None else None
                    ) or "session.error event"
                    log.warning(
                        "managed_agents_session_error",
                        session_id=session_id,
                        error=err_msg,
                    )

                elif event_type == "session.status_terminated":
                    stop_reason = "terminated"
                    break

                elif event_type == "session.status_idle":
                    sr = getattr(event, "stop_reason", None)
                    sr_type = getattr(sr, "type", None) if sr is not None else None
                    # Idle-break gate per MA Pattern 5: keep streaming if
                    # idle is transient (requires_action means the session is
                    # waiting for a client-side response we already handled
                    # via custom_tool_result above).
                    if sr_type == "requires_action":
                        continue
                    if sr_type == "retries_exhausted":
                        stop_reason = "retries_exhausted"
                        provider_limit_detail = {
                            "code": "retries_exhausted",
                            "source": "managed_agents",
                        }
                        break
                    # end_turn or any other terminal idle reason — done.
                    stop_reason = sr_type or "end_turn"
                    break

        duration_ms = int((time.monotonic() - start_t) * 1000)
        cost_usd = _estimate_cost(self._model, tokens_input, tokens_output, tokens_cached)

        return RunResult(
            session_id=session_id,
            output="".join(output_chunks),
            cost_usd=cost_usd,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cached=tokens_cached,
            num_turns=num_turns,
            duration_ms=duration_ms,
            stop_reason=stop_reason,
            observability=observability,
            provider_limit=provider_limit_detail,
        )

    async def _handle_custom_tool(
        self,
        *,
        client: Any,
        session_id: str,
        event: Any,
    ) -> None:
        """Run a host-side custom tool and reply with `user.custom_tool_result`."""
        tool_use_id = getattr(event, "id", "") or ""
        tool_name = getattr(event, "name", "") or ""
        tool_input = getattr(event, "input", {}) or {}

        handler = self._custom_tools.get(tool_name)
        if handler is None:
            log.warning(
                "managed_agents_unknown_custom_tool",
                tool=tool_name,
                tool_use_id=tool_use_id,
            )
            await client.beta.sessions.events.send(
                session_id=session_id,
                events=[
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": tool_use_id,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Unknown tool: {tool_name}",
                            }
                        ],
                        "is_error": True,
                    }
                ],
            )
            return

        try:
            result_text = await handler(tool_input)
            await client.beta.sessions.events.send(
                session_id=session_id,
                events=[
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": result_text}],
                    }
                ],
            )
        except Exception as exc:  # pragma: no cover — defensive boundary
            log.error(
                "managed_agents_custom_tool_failed",
                tool=tool_name,
                error=str(exc),
            )
            await client.beta.sessions.events.send(
                session_id=session_id,
                events=[
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                        "is_error": True,
                    }
                ],
            )

    async def shutdown(self) -> None:
        """No persistent client state in the adapter — clients are per-run."""
        return None

    async def health_check(self) -> bool:
        return (await self.probe()).ok


def _usage_get(usage: Any, key: str) -> int:
    """Pull a token-usage field from an SDK object or dict."""
    if isinstance(usage, dict):
        return int(usage.get(key, 0) or 0)
    return int(getattr(usage, key, 0) or 0)


# Per-1M-token pricing for cost estimation (Phase A — pricing table mirrors
# what's in shared/models.md as of cache date 2026-04-29). Update via the
# Models API when refreshing pricing.
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def _estimate_cost(
    model: str, tokens_input: int, tokens_output: int, tokens_cached: int
) -> float:
    """Estimate run cost from token counts. Cached tokens billed at 0.1×."""
    rates = _PRICING_PER_M_TOKENS.get(model)
    if rates is None:
        return 0.0
    in_rate, out_rate = rates
    uncached = max(tokens_input - tokens_cached, 0)
    cost = (
        (uncached / 1_000_000) * in_rate
        + (tokens_cached / 1_000_000) * (in_rate * 0.1)
        + (tokens_output / 1_000_000) * out_rate
    )
    return round(cost, 6)
