"""Modular runtime support - multiple LLM providers and SDKs.

User-facing runtime lanes:
- claude: Claude Agent SDK through Claude Code auth/runtime.
- codex_sdk: Codex app-server/SDK JSON-RPC mode.

Compatibility adapters such as codex_cli and openai_agents can remain
implemented for migration and lower-level tests, but are not valid dashboard or
`builder agent runtime set` selections.
"""

from autonomous_agent_builder.runtime.factory import (
    create_runtime,
    get_available_runtimes,
    get_current_runtime_name,
    get_implemented_runtimes,
    normalize_sdk,
    resolve_runtime_config,
    validate_runtime_config,
)
from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)

__all__ = [
    # Interfaces
    "AgentRuntime",
    "RunResult",
    "RuntimeCapabilities",
    "RuntimeProbeResult",
    # Factory
    "create_runtime",
    "get_available_runtimes",
    "get_implemented_runtimes",
    "get_current_runtime_name",
    "normalize_sdk",
    "resolve_runtime_config",
    "validate_runtime_config",
]
