from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from autonomous_agent_builder import claude_runtime
from autonomous_agent_builder.onecli_runtime import OneCLIRuntimeEnv


@pytest.mark.asyncio
async def test_check_claude_availability_uses_minimal_prompt(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return "OK"

    monkeypatch.setattr(claude_runtime, "run_claude_prompt", fake_run)
    monkeypatch.setattr(claude_runtime, "resolve_claude_backend", lambda: "sdk")

    availability = await claude_runtime.check_claude_availability(
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=["Bash"],
        permission_mode="acceptEdits",
    )

    assert availability.available is True
    assert availability.backend == "sdk"
    assert captured == {
        "prompt": "Reply with exactly OK.",
        "workspace_path": Path("/tmp/workspace"),
        "model": "haiku",
        "allowed_tools": None,
        "permission_mode": "acceptEdits",
    }


def test_resolve_claude_backend_auto_prefers_sdk(monkeypatch):
    monkeypatch.setattr(
        claude_runtime,
        "get_settings",
        lambda: SimpleNamespace(agent=SimpleNamespace(auth_backend="auto")),
    )
    monkeypatch.setattr(claude_runtime.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")

    assert claude_runtime.resolve_claude_backend() == "sdk"


def test_resolve_claude_backend_auto_falls_back_to_cli(monkeypatch):
    monkeypatch.setattr(
        claude_runtime,
        "get_settings",
        lambda: SimpleNamespace(agent=SimpleNamespace(auth_backend="auto")),
    )
    monkeypatch.setattr(claude_runtime.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")

    assert claude_runtime.resolve_claude_backend() == "cli"


@pytest.mark.asyncio
async def test_run_claude_cli_prompt_places_prompt_before_tool_flags(monkeypatch):
    calls: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"OK", b"")

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        claude_runtime.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await claude_runtime._run_claude_cli_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=["Bash"],
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    assert calls["kwargs"]["cwd"] == "/tmp/workspace"

    args = calls["args"]
    assert args[:4] == ("claude", "-p", "Reply with exactly OK.", "--output-format")
    assert "--tools" in args
    assert "--allowed-tools" in args
    assert args.index("Reply with exactly OK.") < args.index("--tools")


@pytest.mark.asyncio
async def test_run_claude_cli_prompt_applies_onecli_env(monkeypatch):
    calls: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"OK", b"")

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    async def fake_prepare_onecli_runtime_env():
        return OneCLIRuntimeEnv(
            active=True,
            env={
                "CLAUDE_CODE_OAUTH_TOKEN": "placeholder",
                "ANTHROPIC_API_KEY": "placeholder",
                "HTTPS_PROXY": "http://x:aoc_token@localhost:10255",
            },
        )

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-token-from-env")
    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        claude_runtime.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        claude_runtime,
        "prepare_onecli_runtime_env",
        fake_prepare_onecli_runtime_env,
    )

    result = await claude_runtime._run_claude_cli_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    process_env = calls["kwargs"]["env"]
    assert process_env["CLAUDE_CODE_OAUTH_TOKEN"] == "placeholder"
    assert process_env["ANTHROPIC_API_KEY"] == "placeholder"
    assert process_env["HTTPS_PROXY"] == "http://x:aoc_token@localhost:10255"


@pytest.mark.asyncio
async def test_run_claude_cli_prompt_kills_process_on_cancellation(monkeypatch):
    events: list[str] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            events.append("communicate")
            raise asyncio.CancelledError

        def kill(self):
            events.append("kill")

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(
        claude_runtime.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with pytest.raises(asyncio.CancelledError):
        await claude_runtime._run_claude_cli_prompt(
            "Reply with exactly OK.",
            workspace_path=Path("/tmp/workspace"),
            model="haiku",
            allowed_tools=None,
            permission_mode="acceptEdits",
        )

    assert events == ["communicate", "kill", "communicate"]


@pytest.mark.asyncio
async def test_run_claude_sdk_prompt_applies_onecli_env(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClaudeAgentOptions:
        def __init__(self, **kwargs):
            captured["options_kwargs"] = kwargs

    class FakeAssistantMessage:
        def __init__(self):
            self.content = [SimpleNamespace(text="OK")]

    class FakeResultMessage:
        is_error = False
        result = ""

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        yield FakeAssistantMessage()
        yield FakeResultMessage()

    async def fake_prepare_onecli_runtime_env():
        return OneCLIRuntimeEnv(
            active=True,
            env={
                "CLAUDE_CODE_OAUTH_TOKEN": "placeholder",
                "HTTPS_PROXY": "http://x:aoc_token@localhost:10255",
            },
        )

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.query = fake_query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setattr(
        claude_runtime,
        "prepare_onecli_runtime_env",
        fake_prepare_onecli_runtime_env,
    )

    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    assert captured["options_kwargs"]["env"] == {
        "CLAUDE_CODE_OAUTH_TOKEN": "placeholder",
        "HTTPS_PROXY": "http://x:aoc_token@localhost:10255",
    }


@pytest.mark.asyncio
async def test_run_claude_prompt_times_out_with_backend_context(monkeypatch):
    async def never_returns(_prompt, **_kwargs):
        await asyncio.sleep(10)
        return "unreachable"

    monkeypatch.setattr(claude_runtime, "resolve_claude_backend", lambda: "cli")
    monkeypatch.setattr(claude_runtime, "_run_claude_cli_prompt", never_returns)

    with pytest.raises(RuntimeError, match=r"Claude cli prompt timed out after 0.01s\."):
        await claude_runtime.run_claude_prompt(
            "Reply with exactly OK.",
            workspace_path=Path("/tmp/workspace"),
            model="haiku",
            timeout_seconds=0.01,
        )
