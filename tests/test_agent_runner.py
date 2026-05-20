from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
    captured: dict[str, object] = {}
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
        def __init__(self, description, prompt, tools=None, model=None):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.ResultMessage = FakeResultMessage
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
    assert captured["options"].system_prompt == {"type": "preset", "preset": "claude_code"}
    assert captured["options"].setting_sources == ["project"]
    assert captured["options"].effort == "medium"
    assert captured["options"].thinking is None  # chat agent uses haiku → no adaptive thinking
    assert captured["options"].settings is None  # chat agent not in autocompact strategies
    assert captured["options"].has_task_budget is False
    assert captured["options"].extra_args == {
        "disable-slash-commands": None,
        "strict-mcp-config": None,
    }
    assert captured["options"].continue_conversation is False
    assert captured["options"].resume == "resume-abc"
    assert captured["options"].env["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert captured["options"].env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert captured["options"].env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://collector.example.com:4318"
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
    captured: dict[str, object] = {}

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
        def __init__(self, description, prompt, tools=None, model=None):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.ResultMessage = FakeResultMessage
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
    assert "Bash" in captured["options"].allowed_tools
    assert "mcp__builder__kb_add" in captured["options"].allowed_tools
    assert "mcp__builder__kb_update" in captured["options"].allowed_tools
    assert result.stop_reason == "stop_sequence"


@pytest.mark.asyncio
async def test_execute_query_registers_documentation_subagent(monkeypatch):
    captured: dict[str, object] = {}

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
        def __init__(self, description, prompt, tools=None, model=None):
            self.description = description
            self.prompt = prompt
            self.tools = tools or []
            self.model = model

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            func._sdk_tool_description = description
            func._sdk_tool_schema = input_schema
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "version": version, "tools": tools or []}

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AgentDefinition = FakeSdkAgentDefinition
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ClaudeSDKClient = FakeClaudeSDKClient
    fake_sdk.HookMatcher = FakeHookMatcher
    fake_sdk.ResultMessage = FakeResultMessage
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
