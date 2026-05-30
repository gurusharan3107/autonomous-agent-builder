"""Modular runtime support - multiple LLM providers and SDKs.

User-facing runtime lanes:
- claude: Claude Agent SDK with local Claude OAuth token auth.
- codex_sdk: Codex app-server/SDK JSON-RPC mode.

These are the only implemented lanes; there are no hidden compatibility adapters.
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
