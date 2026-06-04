from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import get_settings


def _write_builder_source_env(monkeypatch, tmp_path: Path, text: str) -> Path:
    path = tmp_path / "builder-source.env"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("AAB_BUILDER_SOURCE_ENV", str(path))
    return path


def test_sdk_api_error_output_is_not_successful_agent_work():
    runner = AgentRunner(get_settings())
    result = RunResult(
        output_text="API Error: 400 This model does not support user-configurable task budgets.",
        stop_reason="stop_sequence",
        num_turns=1,
    )

    assert runner._sdk_output_error(result) == result.output_text


def test_sdk_api_error_output_with_real_usage_is_left_as_agent_text():
    runner = AgentRunner(get_settings())
    result = RunResult(
        output_text="API Error: this is literal app copy in a generated UI",
        tokens_input=10,
        tokens_output=5,
        cost_usd=0.01,
    )

    assert runner._sdk_output_error(result) is None


@pytest.mark.asyncio
async def test_execute_query_uses_sdk_client_receive_response(monkeypatch, tmp_path: Path):
    captured: dict[str, Any] = {}
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://collector.example.com:4318")
    _write_builder_source_env(monkeypatch, tmp_path, "CLAUDE_CODE_OAUTH_TOKEN=builder-token\n")

    class FakeHookMatcher:
        def __init__(self, matcher, hooks, timeout=None):
            self.matcher = matcher
            self.hooks = hooks
            self.timeout = timeout

    class FakeClaudeAgentOptions:
        def __init__(
            self,
            *,
            allowed_tools,
            mcp_servers,
            permission_mode,
            model,
            cwd,
            max_turns,
            max_budget_usd,
            can_use_tool=None,
            system_prompt=None,
            setting_sources=None,
            continue_conversation=False,
            resume=None,
            agents=None,
            effort=None,
            thinking=None,
            settings=None,
            extra_args=None,
            include_partial_messages=None,
            strict_mcp_config=None,
            **kwargs,
        ):
            self.allowed_tools = allowed_tools
            self.mcp_servers = mcp_servers
            self.permission_mode = permission_mode
            self.model = model
            self.cwd = cwd
            self.max_turns = max_turns
            self.max_budget_usd = max_budget_usd
            self.can_use_tool = can_use_tool
            self.system_prompt = system_prompt
            self.setting_sources = setting_sources
            self.continue_conversation = continue_conversation
            self.resume = resume
            self.agents = agents
            self.effort = effort
            self.thinking = thinking
            self.settings = settings
            self.has_task_budget = "task_budget" in kwargs
            self.extra_args = extra_args
            self.include_partial_messages = include_partial_messages
            self.strict_mcp_config = strict_mcp_config
            self.hooks = None

    class FakeSystemMessage:
        def __init__(self, session_id: str):
            self.subtype = "init"
            self.data = {"session_id": session_id}

    class FakeAssistantMessage:
        def __init__(self, text: str):
            self.content = [SimpleNamespace(text=text)]

    class FakeResultMessage:
        def __init__(self):
            self.session_id = "sdk-session-123"
            self.usage = {
                "input_tokens": 11,
                "output_tokens": 7,
                "cache_read_input_tokens": 3,
            }
            self.total_cost_usd = 0.12
            self.num_turns = 2
            self.duration_ms = 321
            self.stop_reason = "stop_sequence"

    class FakeClaudeSDKClient:
        def __init__(self, options):
            captured["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def query(self, prompt, session_id="default"):
            captured["prompt"] = []
            async for item in prompt:
                captured["prompt"].append(item)
            captured["session_id"] = session_id

        async def receive_response(self):
            yield FakeSystemMessage("sdk-session-123")
            yield FakeAssistantMessage("hello from assistant")
            yield FakeResultMessage()

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            func._sdk_tool_description = description
            func._sdk_tool_schema = input_schema
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {
            "name": name,
            "version": version,
            "tools": tools or [],
        }

    class FakeSdkAgentDefinition:
        def __init__(self, description, prompt, tools=None, model=None, **kwargs):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model
            self.max_turns = kwargs.get("maxTurns")

    class FakeRateLimitEvent:
        pass

    class FakeStreamEvent:
        pass

    fake_sdk: Any = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.RateLimitEvent = FakeRateLimitEvent
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.StreamEvent = FakeStreamEvent
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    runner = AgentRunner(get_settings())
    result = await runner.run_phase(
        agent_name="chat",
        prompt="hello",
        workspace_path=".",
        resume_session="resume-abc",
    )

    assert captured["prompt"][0]["message"]["content"] == "hello"
    assert captured["session_id"] == "default"
    assert "Read" in captured["options"].allowed_tools
    assert "Bash" not in captured["options"].allowed_tools
    assert set(captured["options"].mcp_servers.keys()) == {"builder", "workspace"}
    builder_tool_names = {
        tool._sdk_tool_name for tool in captured["options"].mcp_servers["builder"]["tools"]
    }
    workspace_tool_names = {
        tool._sdk_tool_name for tool in captured["options"].mcp_servers["workspace"]["tools"]
    }
    assert builder_tool_names.issubset(
        {
            name.removeprefix("mcp__builder__")
            for name in captured["options"].allowed_tools
            if name.startswith("mcp__builder__")
        }
    )
    assert workspace_tool_names == set()
    assert captured["options"].can_use_tool is not None
    assert captured["options"].system_prompt == {
        "type": "preset",
        "preset": "claude_code",
        "exclude_dynamic_sections": True,
    }
    assert captured["options"].setting_sources == ["project"]
    assert captured["options"].effort == "medium"
    # chat resolves to implementation_model (sonnet) → adaptive thinking (builder-owned policy)
    assert captured["options"].thinking == {"type": "adaptive"}
    # chat is the interactive operator lane: must run under "default" so the
    # can_use_tool callback is invoked and AskUserQuestion stays enabled (IMP-018).
    assert captured["options"].permission_mode == "default"
    assert captured["options"].settings is None  # chat agent not in autocompact strategies
    assert captured["options"].has_task_budget is False
    assert captured["options"].extra_args == {"disable-slash-commands": None}
    assert captured["options"].include_partial_messages is True  # G1
    assert captured["options"].strict_mcp_config is True  # G7
    assert captured["options"].continue_conversation is False
    assert captured["options"].resume == "resume-abc"
    assert captured["options"].env["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert captured["options"].env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert (
        captured["options"].env["OTEL_EXPORTER_OTLP_ENDPOINT"]
        == "http://collector.example.com:4318"
    )
    assert result.observability is not None
    assert result.observability["enabled"] is True
    assert result.observability["service_name"] == "autonomous-agent-builder"
    assert result.session_id == "sdk-session-123"
    assert result.output_text == "hello from assistant"
    assert result.cost_usd == 0.12
    assert result.tokens_input == 11
    assert result.tokens_output == 7
    assert result.tokens_cached == 3
    assert result.num_turns == 2
    assert result.duration_ms == 321

    captured.clear()
    await runner.run_phase(
        agent_name="code-gen",
        prompt="implement the feature",
        workspace_path=".",
    )

    assert captured["options"].has_task_budget is False


@pytest.mark.asyncio
async def test_execute_query_exposes_full_tool_set_when_can_use_tool_is_present(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeHookMatcher:
        def __init__(self, matcher, hooks, timeout=None):
            self.matcher = matcher
            self.hooks = hooks
            self.timeout = timeout

    class FakeClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.allowed_tools = kwargs["allowed_tools"]
            self.mcp_servers = kwargs["mcp_servers"]
            self.permission_mode = kwargs["permission_mode"]
            self.model = kwargs["model"]
            self.cwd = kwargs["cwd"]
            self.max_turns = kwargs["max_turns"]
            self.max_budget_usd = kwargs["max_budget_usd"]
            self.can_use_tool = kwargs.get("can_use_tool")
            self.resume = kwargs.get("resume")
            self.agents = kwargs.get("agents")
            self.hooks = None

    class FakeSystemMessage:
        def __init__(self, session_id: str):
            self.subtype = "init"
            self.data = {"session_id": session_id}

    class FakeAssistantMessage:
        def __init__(self, text: str):
            self.content = [SimpleNamespace(text=text)]

    class FakeResultMessage:
        def __init__(self):
            self.session_id = "sdk-session-approval"
            self.usage = {}
            self.total_cost_usd = 0.01
            self.num_turns = 1
            self.duration_ms = 50
            self.stop_reason = "stop_sequence"

    class FakeClaudeSDKClient:
        def __init__(self, options):
            captured["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def query(self, prompt, session_id="default"):
            captured["prompt"] = prompt

        async def receive_response(self):
            yield FakeSystemMessage("sdk-session-approval")
            yield FakeAssistantMessage("approval path ready")
            yield FakeResultMessage()

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            func._sdk_tool_description = description
            func._sdk_tool_schema = input_schema
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "version": version, "tools": tools or []}

    class FakeSdkAgentDefinition:
        def __init__(self, description, prompt, tools=None, model=None, **kwargs):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model
            self.max_turns = kwargs.get("maxTurns")

    fake_sdk: Any = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.RateLimitEvent = type("FakeRateLimitEvent", (), {})
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.StreamEvent = type("FakeStreamEvent", (), {})
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    runner = AgentRunner(get_settings())
    result = await runner.run_phase(
        agent_name="chat",
        prompt="hello",
        workspace_path=".",
        can_use_tool=lambda *_args, **_kwargs: None,
    )

    assert result.session_id == "sdk-session-approval"
    # full tool set includes mutation tools not in auto_approve_tools
    assert "AskUserQuestion" in captured["options"].allowed_tools
    assert "mcp__builder__kb_add" in captured["options"].allowed_tools
    assert "mcp__builder__kb_update" in captured["options"].allowed_tools
    assert result.stop_reason == "stop_sequence"


@pytest.mark.asyncio
async def test_execute_query_registers_documentation_subagent(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeHookMatcher:
        def __init__(self, matcher, hooks, timeout=None):
            self.matcher = matcher
            self.hooks = hooks
            self.timeout = timeout

    class FakeClaudeAgentOptions:
        def __init__(self, **kwargs):
            self.allowed_tools = kwargs["allowed_tools"]
            self.mcp_servers = kwargs["mcp_servers"]
            self.permission_mode = kwargs["permission_mode"]
            self.model = kwargs["model"]
            self.cwd = kwargs["cwd"]
            self.max_turns = kwargs["max_turns"]
            self.max_budget_usd = kwargs["max_budget_usd"]
            self.can_use_tool = kwargs.get("can_use_tool")
            self.resume = kwargs.get("resume")
            self.agents = kwargs.get("agents")
            self.hooks = None

    class FakeSystemMessage:
        def __init__(self, session_id: str):
            self.subtype = "init"
            self.data = {"session_id": session_id}

    class FakeAssistantMessage:
        def __init__(self, text: str):
            self.content = [SimpleNamespace(text=text)]

    class FakeResultMessage:
        def __init__(self):
            self.session_id = "sdk-session-docs"
            self.usage = {}
            self.total_cost_usd = 0.01
            self.num_turns = 1
            self.duration_ms = 50
            self.stop_reason = "stop_sequence"

    class FakeClaudeSDKClient:
        def __init__(self, options):
            captured["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def query(self, prompt, session_id="default"):
            captured["prompt"] = []
            async for item in prompt:
                captured["prompt"].append(item)
            captured["session_id"] = session_id

        async def receive_response(self):
            yield FakeSystemMessage("sdk-session-docs")
            yield FakeAssistantMessage("documentation path")
            yield FakeResultMessage()

    class FakeSdkAgentDefinition:
        def __init__(self, description, prompt, tools=None, model=None, **kwargs):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model
            self.max_turns = kwargs.get("maxTurns")

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            func._sdk_tool_description = description
            func._sdk_tool_schema = input_schema
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "version": version, "tools": tools or []}

    fake_sdk: Any = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.RateLimitEvent = type("FakeRateLimitEvent", (), {})
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.StreamEvent = type("FakeStreamEvent", (), {})
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)

    runner = AgentRunner(get_settings())
    result = await runner.run_phase(
        agent_name="chat",
        prompt="check docs",
        workspace_path=".",
        subagents=("documentation-agent",),
    )

    assert result.session_id == "sdk-session-docs"
    assert "Agent" in captured["options"].allowed_tools
    assert captured["options"].agents is not None
    doc_agent = captured["options"].agents["documentation-agent"]
    assert "mcp__builder__kb_extract" in doc_agent.tools
    assert "mcp__builder__kb_validate" in doc_agent.tools


def test_preflight_fails_for_git_required_phase_with_unborn_head(tmp_path):
    import subprocess

    # Init a git repo but make NO commit — HEAD is unborn
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    runner = AgentRunner(get_settings())
    result = runner._preflight_workspace("code-gen", str(tmp_path))
    assert result is not None
    assert result.stop_reason == "preflight_failed"
    assert "preflight" in (result.error or "")
    assert "unborn HEAD" in (result.error or "")


def test_preflight_passes_for_git_required_phase_with_valid_head(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    runner = AgentRunner(get_settings())
    result = runner._preflight_workspace("code-gen", str(tmp_path))
    assert result is None


def test_preflight_warns_not_fails_for_non_git_workspace(tmp_path):
    runner = AgentRunner(get_settings())
    # No .git directory — not a git repo yet. Should warn, not fail.
    result = runner._preflight_workspace("code-gen", str(tmp_path))
    assert result is None


def test_preflight_skips_git_check_for_non_git_required_phase(tmp_path):
    runner = AgentRunner(get_settings())
    # scaffold is not in _PHASES_REQUIRE_GIT_HEAD — no git check at all
    result = runner._preflight_workspace("scaffold", str(tmp_path))
    assert result is None


def test_preflight_skips_git_check_for_chat_phase(tmp_path):
    runner = AgentRunner(get_settings())
    result = runner._preflight_workspace("chat", str(tmp_path))
    assert result is None


# ---------------------------------------------------------------------------
# Tier B (M2.3 P0) — G1 / G2 / G7 / G12 / StopFailure
# ---------------------------------------------------------------------------


def test_trim_tool_output_hook_constants():
    """G12 + G7: curated trim-tool set and threshold match plan decisions."""
    from autonomous_agent_builder.agents.hooks_trim import _OUTPUT_TRIM_CHARS, _OUTPUT_TRIM_TOOLS

    assert "Bash" in _OUTPUT_TRIM_TOOLS
    assert "Read" in _OUTPUT_TRIM_TOOLS
    assert "mcp__workspace__run_tests" in _OUTPUT_TRIM_TOOLS
    assert "mcp__workspace__run_linter" in _OUTPUT_TRIM_TOOLS
    assert _OUTPUT_TRIM_CHARS == 8_000


@pytest.mark.asyncio
async def test_post_tool_hook_truncates_large_bash_stdout():
    """G12: trim_tool_output_for_context truncates large Bash stdout."""
    from autonomous_agent_builder.agents.hooks_trim import trim_tool_output_for_context

    large_stdout = "x" * 20_000
    tool_input = {
        "tool_name": "Bash",
        "tool_response": {"stdout": large_stdout, "stderr": "", "interrupted": False},
    }
    result = await trim_tool_output_for_context(tool_input, None, {})

    hook_out = result.get("hookSpecificOutput", {})
    assert hook_out.get("hookEventName") == "PostToolUse"
    updated = hook_out.get("updatedToolOutput", {})
    assert isinstance(updated, dict)
    assert len(updated["stdout"]) < len(large_stdout)
    assert "trimmed" in updated["stdout"].lower() or "..." in updated["stdout"]
    assert updated["interrupted"] is False


@pytest.mark.asyncio
async def test_post_tool_hook_passes_through_small_bash_stdout():
    """G12: trim_tool_output_for_context is a no-op when output is small."""
    from autonomous_agent_builder.agents.hooks_trim import trim_tool_output_for_context

    tool_input = {
        "tool_name": "Bash",
        "tool_response": {"stdout": "ok", "stderr": "", "interrupted": False},
    }
    result = await trim_tool_output_for_context(tool_input, None, {})
    assert result == {}


@pytest.mark.asyncio
async def test_post_tool_hook_truncates_mcp_run_tests():
    """G12: trim_tool_output_for_context truncates MCP run_tests output."""
    from autonomous_agent_builder.agents.hooks_trim import trim_tool_output_for_context

    large_text = "FAILED " * 3000
    tool_input = {
        "tool_name": "mcp__workspace__run_tests",
        "tool_response": {"content": [{"type": "text", "text": large_text}]},
    }
    result = await trim_tool_output_for_context(tool_input, None, {})

    hook_out = result.get("hookSpecificOutput", {})
    assert hook_out.get("hookEventName") == "PostToolUse"
    updated = hook_out.get("updatedMCPToolOutput", {})
    text_items = [i for i in updated.get("content", []) if i.get("type") == "text"]
    assert text_items
    assert len(text_items[0]["text"]) < len(large_text)


@pytest.mark.asyncio
async def test_rate_limit_event_sets_provider_limit_stop_reason(monkeypatch):
    """StopFailure: RateLimitEvent(rejected) → RunResult.stop_reason=provider_limit
    with SDK-sourced reset_at / rate_limit_type / utilization."""
    import sys
    from types import ModuleType

    # ---- fake types that the runner isinstance-checks against ----

    class FakeRateLimitInfo:
        status = "rejected"
        resets_at = 1_700_000_000_000  # unix-ms
        rate_limit_type = "five_hour"
        utilization = 0.99

    class FakeRateLimitEvent:
        rate_limit_info = FakeRateLimitInfo()
        session_id = "rl-session"
        uuid = "u1"

    class FakeResultMessage:
        session_id = "rl-session"
        usage: dict = {}
        total_cost_usd = 0.0
        num_turns = 1
        duration_ms = 0
        stop_reason = "end_turn"

    class FakeSystemMessage:
        def __init__(self, sid: str):
            self.subtype = "init"
            self.data = {"session_id": sid}

    class FakeAssistantMessage:
        content: list = []

    class FakeStreamEvent:
        pass

    class _Opts:
        def __init__(self, **kw):
            pass

        def __setattr__(self, k, v):
            object.__setattr__(self, k, v)

    class _Client:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def query(self, *_a, **_kw):
            pass

        async def receive_response(self):
            yield FakeSystemMessage("rl-session")
            yield FakeRateLimitEvent()
            yield FakeResultMessage()

    fake = ModuleType("claude_agent_sdk")
    fake.ClaudeAgentOptions = _Opts  # type: ignore[attr-defined]
    fake.ClaudeSDKClient = _Client  # type: ignore[attr-defined]
    fake.HookMatcher = type("HM", (), {"__init__": lambda s, **kw: None})  # type: ignore[attr-defined]
    fake.RateLimitEvent = FakeRateLimitEvent  # type: ignore[attr-defined]
    fake.ResultMessage = FakeResultMessage  # type: ignore[attr-defined]
    fake.StreamEvent = FakeStreamEvent  # type: ignore[attr-defined]
    fake.SystemMessage = FakeSystemMessage  # type: ignore[attr-defined]
    fake.AssistantMessage = FakeAssistantMessage  # type: ignore[attr-defined]
    fake.AgentDefinition = type("AD", (), {})  # type: ignore[attr-defined]

    def _tool(n, d, s, annotations=None):
        def dec(f):
            f._sdk_tool_name = n
            return f

        return dec

    fake.tool = _tool  # type: ignore[attr-defined]
    fake.create_sdk_mcp_server = lambda name, version="1.0.0", tools=None: {  # type: ignore[attr-defined]
        "name": name,
        "tools": tools or [],
    }

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    runner = AgentRunner(get_settings())
    result = await runner.run_phase(agent_name="chat", prompt="hi", workspace_path=".")

    assert result.stop_reason == "provider_limit", f"got {result.stop_reason}"
    assert result.provider_limit is not None
    assert result.provider_limit["reason"] == "rate_limit_event"
    assert result.provider_limit["rate_limit_type"] == "five_hour"
    assert result.provider_limit["utilization"] == 0.99
    assert result.provider_limit["reset_at"] is not None


@pytest.mark.asyncio
async def test_stream_event_invokes_on_stream_usage_callback(monkeypatch):
    """G1: StreamEvent message_start + message_delta accumulate and invoke on_stream_usage."""
    import sys
    from types import ModuleType

    class FakeSystemMessage:
        def __init__(self, sid: str):
            self.subtype = "init"
            self.data = {"session_id": sid}

    class FakeAssistantMessage:
        def __init__(self):
            self.content = [SimpleNamespace(text="done")]

    class FakeResultMessage:
        session_id = "usage-session"
        usage: dict = {}
        total_cost_usd = 0.0
        num_turns = 1
        duration_ms = 0
        stop_reason = "end_turn"

    class FakeStreamEvent:
        def __init__(self, event_dict: dict):
            self.event = event_dict

    class _Opts:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class _Client:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def query(self, *_a, **_kw):
            pass

        async def receive_response(self):
            yield FakeSystemMessage("usage-session")
            yield FakeStreamEvent(
                {
                    "type": "message_start",
                    "message": {
                        "usage": {
                            "input_tokens": 100,
                            "cache_read_input_tokens": 80,
                            "cache_creation_input_tokens": 10,
                        }
                    },
                }
            )
            yield FakeStreamEvent({"type": "message_delta", "usage": {"output_tokens": 25}})
            yield FakeAssistantMessage()
            yield FakeResultMessage()

    fake = ModuleType("claude_agent_sdk")
    fake.ClaudeAgentOptions = _Opts  # type: ignore[attr-defined]
    fake.ClaudeSDKClient = _Client  # type: ignore[attr-defined]
    fake.HookMatcher = type("HM", (), {"__init__": lambda s, **kw: None})  # type: ignore[attr-defined]
    fake.RateLimitEvent = type("RLE", (), {})  # type: ignore[attr-defined]
    fake.ResultMessage = FakeResultMessage  # type: ignore[attr-defined]
    fake.StreamEvent = FakeStreamEvent  # type: ignore[attr-defined]
    fake.SystemMessage = FakeSystemMessage  # type: ignore[attr-defined]
    fake.AssistantMessage = FakeAssistantMessage  # type: ignore[attr-defined]
    fake.AgentDefinition = type("AD", (), {})  # type: ignore[attr-defined]
    fake.tool = lambda n, d, s, annotations=None: lambda f: f  # type: ignore[attr-defined]
    fake.create_sdk_mcp_server = lambda name, version="1.0.0", tools=None: {  # type: ignore[attr-defined]
        "name": name,
        "tools": tools or [],
    }

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    usage_calls: list[tuple[int, int, int]] = []

    async def on_stream_usage(inp: int, cached: int, out: int) -> None:
        usage_calls.append((inp, cached, out))

    runner = AgentRunner(get_settings())
    await runner.run_phase(
        agent_name="chat",
        prompt="hi",
        workspace_path=".",
        on_stream_usage=on_stream_usage,
    )

    assert len(usage_calls) == 1
    inp, cached, out = usage_calls[0]
    assert inp == 100
    assert cached == 90  # cache_read(80) + cache_creation(10)
    assert out == 25
