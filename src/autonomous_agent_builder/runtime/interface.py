"""Runtime interface abstractions for modular runtime support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeCapabilities:
    """Stable capability map exposed by runtime adapters."""

    chat: bool = True
    streaming: bool = False
    tools: bool = False
    mcp: bool = False
    subagents: bool = False
    workspace_access: bool = False
    shell: bool = False
    sandboxing: bool = False
    approvals: bool = False
    session_resume: bool = False
    subscription_auth: bool = False
    api_key_auth: bool = False
    model_listing: bool = False
    provider_limit_detection: bool = True
    tracing: bool = False
    native_user_input: bool = False
    mcp_elicitations: bool = False
    request_permissions: bool = False
    app_server_events: bool = False
    token_usage_stream: bool = False


@dataclass
class RuntimeProbeResult:
    """Deterministic activation probe result for a runtime/provider pair."""

    ok: bool
    sdk: str
    provider: str
    model: str
    code: str
    message: str
    next: str = ""
    capabilities: RuntimeCapabilities | None = None
    detail: dict[str, Any] | None = None


@dataclass
class RunResult:
    """Unified result from any runtime."""

    session_id: str | None = None
    output: str = ""
    error: str | None = None
    cost_usd: float = 0.0

    # Usage metrics
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0
    num_turns: int = 0
    duration_ms: int = 0

    # Metadata
    stop_reason: str | None = None
    confidence: float | None = None
    diff_summary: dict[str, Any] | None = None
    observability: dict[str, Any] | None = None
    provider_limit: dict[str, Any] | None = None
    raw_events: list[dict[str, Any]] | None = None

    @property
    def success(self) -> bool:
        """Check if the run was successful."""
        return self.error is None and bool(self.output)

    @property
    def output_text(self) -> str:
        """Alias used by the existing Claude runner and orchestrator code."""
        return self.output

    @output_text.setter
    def output_text(self, value: str) -> None:
        self.output = value

    @property
    def hit_capability_limit(self) -> bool:
        """Return true when the run should pause and preserve the phase target."""
        return self.stop_reason in ("max_turns", "budget_exceeded", "provider_limit")


class AgentRuntime(ABC):
    """Unified runtime interface for all agent SDKs.

    User-facing lanes are Claude Agent SDK (`claude`) and Codex SDK
    (`codex_sdk`). Additional implementations may exist as compatibility
    adapters for lower-level tests and migration support.

    Implementations:
    - ClaudeRuntime: Wraps Claude Agent SDK
    - CodexAppServerRuntime: Wraps Codex app-server/SDK JSON-RPC mode
    - OpenAIAgentsRuntime: Wraps OpenAI Agents SDK
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Runtime implementation identifier."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Current model identifier."""

    @abstractmethod
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
        approval_policy: str | None = None,
        on_chunk: Callable[[str], Any] | None = None,
        subagents: tuple[str, ...] | None = None,
        can_use_tool: Callable[..., Any] | None = None,
        on_tool_event: Callable[..., Any] | None = None,
    ) -> RunResult:
        """Execute an agent run.

        Args:
            input: User input/prompt
            agent: Agent name/key (e.g., 'ask', 'implement')
            workspace_path: Filesystem path for the task workspace. Defaults to cwd.
            tools: Additional tool names to enable beyond agent definition defaults.
            session: Session ID for continuation
            max_turns: Maximum turns (runtime-specific: may be agent-def-controlled)
            max_budget: Maximum budget in USD (runtime-specific: may be agent-def-controlled)
            effort: Reasoning effort for runtimes that expose explicit effort control
            approval_policy: Optional turn-level approval policy override for runtimes that support it
            on_chunk: Streaming callback for real-time output
            subagents: Optional subagent allow-list for runtimes that support handoffs
            can_use_tool: Optional permission callback
            on_tool_event: Optional tool event callback

        Returns:
            RunResult with output and metrics
        """
        pass

    def capabilities(self) -> RuntimeCapabilities:
        """Return adapter capabilities without probing external credentials."""
        return RuntimeCapabilities(chat=True)

    async def probe(self) -> RuntimeProbeResult:
        """Check whether the selected runtime can be activated."""
        ok = await self.health_check()
        return RuntimeProbeResult(
            ok=ok,
            sdk=self.name,
            provider="",
            model=self.model,
            code="runtime_available" if ok else "runtime_unavailable",
            message="Runtime is available." if ok else "Runtime is not available.",
            capabilities=self.capabilities(),
        )

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup resources."""
        pass

    async def health_check(self) -> bool:
        """Check runtime health.

        Default implementation returns True. Override for specific checks.
        """
        return True
