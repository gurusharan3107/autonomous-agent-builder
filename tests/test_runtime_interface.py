"""Tests for the modular runtime interface (Phase 1).

Covers:
- RunResult dataclass contract
- AgentRuntime ABC contract
- Factory: create_runtime, get_available_runtimes, get_implemented_runtimes
- ClaudeRuntime construction and run() delegation
- Placeholder runtimes return an error RunResult (not exceptions)
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.runtime import (
    AgentRuntime,
    RunResult,
    create_runtime,
    get_available_runtimes,
    get_current_runtime_name,
    get_implemented_runtimes,
)
from autonomous_agent_builder.runtime.claude_runtime import ClaudeRuntime
from autonomous_agent_builder.runtime.codex_app_server_runtime import CodexAppServerRuntime
from autonomous_agent_builder.runtime.codex_cli_runtime import CodexCliRuntime
from autonomous_agent_builder.runtime.openai_runtime import OpenAIAgentsRuntime, OpenAIRuntime
from autonomous_agent_builder.runtime.opencode_runtime import OpenCodeRuntime

# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------


class TestRunResult:
    def test_success_true_when_no_error_and_output(self):
        r = RunResult(output="hello", error=None)
        assert r.success is True

    def test_success_false_when_error_set(self):
        r = RunResult(output="hello", error="boom")
        assert r.success is False

    def test_success_false_when_output_empty(self):
        r = RunResult(output="", error=None)
        assert r.success is False

    def test_default_numeric_fields_are_zero(self):
        r = RunResult()
        assert r.cost_usd == 0.0
        assert r.tokens_input == 0
        assert r.tokens_output == 0
        assert r.tokens_cached == 0
        assert r.num_turns == 0
        assert r.duration_ms == 0

    def test_session_id_defaults_none(self):
        r = RunResult()
        assert r.session_id is None
        assert r.stop_reason is None
        assert r.error is None


# ---------------------------------------------------------------------------
# AgentRuntime interface contract
# ---------------------------------------------------------------------------


class TestAgentRuntimeInterface:
    def test_run_signature_has_workspace_path(self):
        sig = inspect.signature(AgentRuntime.run)
        assert "workspace_path" in sig.parameters

    def test_run_signature_has_on_chunk(self):
        sig = inspect.signature(AgentRuntime.run)
        assert "on_chunk" in sig.parameters

    def test_all_implementations_match_interface(self):
        base_params = set(inspect.signature(AgentRuntime.run).parameters)
        for cls in (
            ClaudeRuntime,
            CodexCliRuntime,
            CodexAppServerRuntime,
            OpenAIAgentsRuntime,
            OpenCodeRuntime,
        ):
            impl_params = set(inspect.signature(cls.run).parameters)
            missing = base_params - impl_params
            assert not missing, f"{cls.__name__}.run() is missing params: {missing}"

    def test_abstract_methods_required(self):
        """Cannot instantiate AgentRuntime directly."""
        with pytest.raises(TypeError):
            AgentRuntime()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_available_runtimes_contains_only_user_facing_lanes(self):
        available = get_available_runtimes()
        assert available == ["claude", "claude_managed", "codex_sdk"]

    def test_get_implemented_runtimes_may_include_compatibility_adapters(self):
        implemented = set(get_implemented_runtimes())
        available = set(get_available_runtimes())
        assert available <= implemented

    def test_get_implemented_runtimes_contains_claude(self):
        assert "claude" in get_implemented_runtimes()

    def test_compatibility_adapters_are_not_user_facing(self):
        implemented = get_implemented_runtimes()
        available = get_available_runtimes()
        assert "openai" not in implemented
        assert "opencode" not in implemented
        assert "codex_cli" not in available
        assert "openai_agents" not in available
        assert "codex_cli" in implemented
        assert "codex_sdk" in implemented
        assert "openai_agents" in implemented

    def test_create_runtime_default_returns_claude(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="claude", model="anthropic/claude-sonnet-4-6")
            ),
        ):
            runtime = create_runtime()
        assert runtime.name == "claude"

    def test_create_runtime_openai_alias_returns_openai_agents(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="openai", model="openai/gpt-5")
            ),
        ):
            runtime = create_runtime()
        assert runtime.name == "openai_agents"

    def test_create_runtime_opencode_alias_returns_openai_agents(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="opencode", model="opencode/big-pickle")
            ),
        ):
            runtime = create_runtime()
        assert runtime.name == "openai_agents"

    def test_create_runtime_codex_cli_sdk_returns_codex_cli(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="codex_cli", model="gpt-5.5")
            ),
        ):
            runtime = create_runtime()
        assert runtime.name == "codex_cli"

    def test_create_runtime_codex_sdk_selector_returns_codex_app_server_runtime(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="codex_sdk", model="gpt-5.5")
            ),
        ):
            runtime = create_runtime()
        assert isinstance(runtime, CodexAppServerRuntime)
        assert runtime.name == "codex_sdk"

    def test_create_runtime_kwargs_override_config(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(
                runtime=SimpleNamespace(sdk="claude", model="anthropic/claude-sonnet-4-6")
            ),
        ):
            runtime = create_runtime(sdk="codex_cli", model="gpt-5.5")
        assert runtime.name == "codex_cli"

    def test_get_current_runtime_name_reads_config(self):
        with patch(
            "autonomous_agent_builder.runtime.factory.get_settings",
            return_value=SimpleNamespace(runtime=SimpleNamespace(sdk="claude")),
        ):
            assert get_current_runtime_name() == "claude"


# ---------------------------------------------------------------------------
# ClaudeRuntime
# ---------------------------------------------------------------------------


class TestClaudeRuntime:
    def _make_fake_runner_result(self) -> Any:
        return SimpleNamespace(
            session_id="sess-1",
            output_text="done",
            error=None,
            cost_usd=0.01,
            tokens_input=100,
            tokens_output=50,
            num_turns=3,
            duration_ms=1200,
            stop_reason="end_turn",
        )

    def test_name_is_claude(self):
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            r = ClaudeRuntime()
        assert r.name == "claude"

    def test_model_reads_from_config(self):
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-opus-4")
            )
            r = ClaudeRuntime()
        assert r.model == "anthropic/claude-opus-4"

    def test_model_kwarg_overrides_config(self):
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            r = ClaudeRuntime(model="anthropic/claude-haiku-3-5")
        assert r.model == "anthropic/claude-haiku-3-5"

    async def test_run_passes_workspace_path_to_runner(self):
        fake_result = self._make_fake_runner_result()
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            runtime = ClaudeRuntime()

        runtime._runner = MagicMock()
        runtime._runner.run_phase = AsyncMock(return_value=fake_result)

        result = await runtime.run(
            "hello",
            agent="ask",
            workspace_path="/tmp/myworkspace",
        )

        call_kwargs = runtime._runner.run_phase.call_args
        assert call_kwargs.kwargs["workspace_path"] == "/tmp/myworkspace"
        assert result.success is True
        assert result.output == "done"
        assert result.session_id == "sess-1"

    async def test_run_defaults_workspace_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fake_result = self._make_fake_runner_result()
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            runtime = ClaudeRuntime()

        runtime._runner = MagicMock()
        runtime._runner.run_phase = AsyncMock(return_value=fake_result)

        await runtime.run("hello", agent="ask")

        call_kwargs = runtime._runner.run_phase.call_args
        assert call_kwargs.kwargs["workspace_path"] == str(tmp_path)

    async def test_run_maps_result_fields(self):
        fake_result = self._make_fake_runner_result()
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            runtime = ClaudeRuntime()

        runtime._runner = MagicMock()
        runtime._runner.run_phase = AsyncMock(return_value=fake_result)

        result = await runtime.run("hello", agent="ask")

        assert result.cost_usd == 0.01
        assert result.tokens_input == 100
        assert result.tokens_output == 50
        assert result.num_turns == 3
        assert result.duration_ms == 1200
        assert result.stop_reason == "end_turn"

    async def test_run_returns_error_result_on_exception(self):
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            runtime = ClaudeRuntime()

        runtime._runner = MagicMock()
        runtime._runner.run_phase = AsyncMock(side_effect=RuntimeError("network down"))

        result = await runtime.run("hello", agent="ask")

        assert result.success is False
        assert "network down" in (result.error or "")

    async def test_run_retries_without_resume_after_resume_process_error(self):
        first_error = RuntimeError("Process error (exit 1): stale resume session")
        fake_result = self._make_fake_runner_result()
        fake_result.session_id = "fresh-session"
        fake_result.observability = {"runtime_policy": {"model": "haiku"}}
        with patch("autonomous_agent_builder.runtime.claude_runtime.get_settings") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(
                runtime=SimpleNamespace(model="anthropic/claude-sonnet-4-6")
            )
            runtime = ClaudeRuntime()

        runtime._runner = MagicMock()
        runtime._runner.run_phase = AsyncMock(side_effect=[first_error, fake_result])

        result = await runtime.run("which project am I working on?", agent="chat", session="old-session")

        assert result.success is True
        assert result.session_id == "fresh-session"
        assert runtime._runner.run_phase.call_args_list[0].kwargs["resume_session"] == "old-session"
        assert runtime._runner.run_phase.call_args_list[1].kwargs["resume_session"] is None
        assert result.observability is not None
        assert result.observability["resume_retry"]["fallback"] == "fresh_model_turn"


# ---------------------------------------------------------------------------
# Non-Claude runtimes
# ---------------------------------------------------------------------------


class TestNonClaudeRuntimes:
    async def test_openai_agents_runtime_requires_provider_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        runtime = OpenAIRuntime()
        result = await runtime.run("hello", agent="ask")
        assert result.success is False
        assert result.error is not None
        assert "OPENCODE_GO_API_KEY" in (result.error or "")

    async def test_opencode_wrapper_requires_provider_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        runtime = OpenCodeRuntime()
        result = await runtime.run("hello", agent="ask")
        assert result.success is False
        assert result.error is not None
        assert "OPENCODE_GO_API_KEY" in (result.error or "")

    async def test_openai_agents_health_check_returns_false_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        runtime = OpenAIRuntime()
        assert await runtime.health_check() is False

    async def test_opencode_health_check_returns_false_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
        runtime = OpenCodeRuntime()
        assert await runtime.health_check() is False

    def test_openai_agents_default_model(self):
        runtime = OpenAIRuntime()
        assert runtime.name == "openai_agents"
        assert runtime.provider == "opencode_go"
        assert runtime.model == "minimax-m2.7"

    def test_opencode_wrapper_uses_opencode_go_provider(self):
        runtime = OpenCodeRuntime()
        assert runtime.name == "openai_agents"
        assert runtime.provider == "opencode_go"
        assert runtime.model == "minimax-m2.7"

    def test_codex_cli_default_model_and_provider(self):
        runtime = CodexCliRuntime()
        assert runtime.name == "codex_cli"
        assert runtime.provider == "codex_subscription"
        assert runtime.model == "gpt-5.5"

    def test_codex_sdk_default_uses_app_server_capabilities(self):
        runtime = CodexAppServerRuntime()
        assert runtime.name == "codex_sdk"
        assert runtime.provider == "codex_subscription"
        assert runtime.model == "gpt-5.5"
        capabilities = runtime.capabilities()
        assert capabilities.app_server_events is True
        assert capabilities.native_user_input is True

    async def test_codex_cli_probe_reports_missing_binary(self, monkeypatch):
        monkeypatch.setattr(
            "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
            lambda name: None,
        )
        runtime = CodexCliRuntime()
        result = await runtime.probe()
        assert result.ok is False
        assert result.code == "codex_cli_missing"
