"""Deprecated OpenCode runtime compatibility wrapper."""

from __future__ import annotations

from autonomous_agent_builder.runtime.openai_runtime import OpenAIAgentsRuntime


class OpenCodeRuntime(OpenAIAgentsRuntime):
    """Compatibility wrapper for the old sdk=opencode vocabulary.

    This adapter is not a user-facing dashboard or `builder agent runtime set`
    lane; new lifecycle validation should use `claude` or `codex_sdk`.
    """

    def __init__(self, model: str | None = None):
        super().__init__(
            model=model or "minimax-m2.7",
            provider="opencode_go",
            api_base_url="https://opencode.ai/zen/go/v1",
            api_key_env="OPENCODE_GO_API_KEY",
        )
