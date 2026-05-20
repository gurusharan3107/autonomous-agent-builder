from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from autonomous_agent_builder.runtime.openai_runtime import OpenAIAgentsRuntime


@pytest.mark.asyncio
async def test_openai_agents_uses_provider_key_not_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "provider-key")

    captured: dict[str, object] = {}
    agents_module = ModuleType("agents")
    openai_module = ModuleType("openai")

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

    class FakeRunner:
        @staticmethod
        async def run(agent, input, *, max_turns):
            captured["run_agent"] = agent
            captured["run_input"] = input
            captured["run_max_turns"] = max_turns
            return SimpleNamespace(final_output="completed")

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            captured["model"] = model
            captured["openai_client"] = openai_client

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    def fake_set_tracing_disabled(value):
        captured["tracing_disabled"] = value

    agents_module.Agent = FakeAgent
    agents_module.Runner = FakeRunner
    agents_module.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    agents_module.function_tool = lambda func: func
    agents_module.set_tracing_disabled = fake_set_tracing_disabled
    openai_module.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "agents", agents_module)
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    runtime = OpenAIAgentsRuntime(model="kimi-k2.6", tracing="off")
    result = await runtime.run(
        "do work",
        agent="planner",
        workspace_path="/tmp/workspace",
        max_turns=7,
    )

    assert result.success is True
    assert result.output == "completed"
    assert captured["api_key"] == "provider-key"
    assert captured["base_url"] == "https://opencode.ai/zen/go/v1"
    assert captured["model"] == "kimi-k2.6"
    assert captured["run_input"] == "do work"
    assert captured["run_max_turns"] == 7
    assert captured["tracing_disabled"] is True
    assert captured["agent_kwargs"]["tools"] == []


@pytest.mark.asyncio
async def test_openai_agents_runtime_registers_request_user_input_tool(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "provider-key")

    captured: dict[str, object] = {}
    agents_module = ModuleType("agents")
    openai_module = ModuleType("openai")

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["agent_kwargs"] = kwargs

    class FakeRunner:
        @staticmethod
        async def run(agent, input, *, max_turns):
            tool = agent.kwargs["tools"][0]
            tool_result = await tool(
                [
                    {
                        "header": "Fairness",
                        "question": "Which chore rule should ChoreFlow use?",
                        "options": [
                            {
                                "label": "Lowest load (Recommended)",
                                "description": "Assign to the lowest current effort load.",
                            },
                            {
                                "label": "Round robin",
                                "description": "Rotate roommates in order.",
                            },
                        ],
                    }
                ]
            )
            captured["tool_result"] = tool_result
            return SimpleNamespace(final_output="completed")

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            pass

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            pass

    def fake_function_tool(func):
        captured["tool_name"] = func.__name__
        return func

    async def can_use_tool(tool_name, input_data, context):
        captured["bridge_tool_name"] = tool_name
        captured["bridge_input"] = input_data
        return SimpleNamespace(
            updated_input={
                "questions": input_data["questions"],
                "answers": {
                    "Which chore rule should ChoreFlow use?": "Lowest load (Recommended)",
                },
            }
        )

    agents_module.Agent = FakeAgent
    agents_module.Runner = FakeRunner
    agents_module.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    agents_module.function_tool = fake_function_tool
    agents_module.set_tracing_disabled = lambda value: None
    openai_module.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "agents", agents_module)
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    runtime = OpenAIAgentsRuntime()
    result = await runtime.run(
        "start requirements",
        agent="init-project-chat",
        can_use_tool=can_use_tool,
    )

    assert result.success is True
    assert captured["tool_name"] == "request_user_input"
    assert captured["bridge_tool_name"] == "request_user_input"
    assert captured["bridge_input"]["runtime_sdk"] == "openai_agents"
    assert captured["bridge_input"]["native_tool"] == "function_tool"
    assert captured["tool_result"]["answers"] == {
        "Which chore rule should ChoreFlow use?": "Lowest load (Recommended)"
    }


@pytest.mark.asyncio
async def test_openai_agents_maps_provider_limit(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "provider-key")

    agents_module = ModuleType("agents")
    openai_module = ModuleType("openai")

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

    class FakeRunner:
        @staticmethod
        async def run(agent, input, *, max_turns):
            raise RuntimeError("rate limit reached, reset in 1 hour")

    class FakeOpenAIChatCompletionsModel:
        def __init__(self, *, model, openai_client):
            pass

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key, base_url):
            pass

    agents_module.Agent = FakeAgent
    agents_module.Runner = FakeRunner
    agents_module.OpenAIChatCompletionsModel = FakeOpenAIChatCompletionsModel
    agents_module.function_tool = lambda func: func
    agents_module.set_tracing_disabled = lambda value: None
    openai_module.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "agents", agents_module)
    monkeypatch.setitem(sys.modules, "openai", openai_module)

    runtime = OpenAIAgentsRuntime()
    result = await runtime.run("do work", agent="planner")

    assert result.error is None
    assert result.stop_reason == "provider_limit"
    assert result.hit_capability_limit is True
    assert result.provider_limit is not None
    assert result.provider_limit["source"] == "opencode_go"
