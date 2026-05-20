from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from autonomous_agent_builder import claude_runtime


def _write_builder_source_env(monkeypatch, tmp_path: Path, text: str) -> Path:
    path = tmp_path / "builder-source.env"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("AAB_BUILDER_SOURCE_ENV", str(path))
    return path


@pytest.fixture(autouse=True)
def empty_builder_source_env(monkeypatch, tmp_path: Path) -> Path:
    return _write_builder_source_env(monkeypatch, tmp_path, "")


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
        "timeout_seconds": 60.0,
    }


@pytest.mark.asyncio
async def test_check_claude_availability_captures_sdk_stderr(monkeypatch, capsys):
    async def fake_run(prompt: str, **kwargs):
        print("Fatal error in message reader: Not logged in", file=sys.stderr)
        raise RuntimeError("Check stderr output for details")

    monkeypatch.setattr(claude_runtime, "run_claude_prompt", fake_run)
    monkeypatch.setattr(claude_runtime, "resolve_claude_backend", lambda: "sdk")

    availability = await claude_runtime.check_claude_availability(
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=["Bash"],
        permission_mode="acceptEdits",
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    assert availability.available is False
    assert availability.message == "Fatal error in message reader: Not logged in"


def test_resolve_claude_backend_auto_prefers_sdk(monkeypatch):
    monkeypatch.setattr(
        claude_runtime,
        "get_settings",
        lambda: SimpleNamespace(agent=SimpleNamespace(auth_backend="auto")),
    )
    monkeypatch.setattr(claude_runtime.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")

    assert claude_runtime.resolve_claude_backend() == "sdk"


def test_resolve_claude_backend_auto_stays_on_sdk_lane(monkeypatch):
    monkeypatch.setattr(
        claude_runtime,
        "get_settings",
        lambda: SimpleNamespace(agent=SimpleNamespace(auth_backend="auto")),
    )
    monkeypatch.setattr(claude_runtime.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(claude_runtime.shutil, "which", lambda name: "/usr/local/bin/claude")

    assert claude_runtime.resolve_claude_backend() == "sdk"


def test_resolve_claude_observability_marks_placeholder_endpoint(monkeypatch):
    for key in (
        "CLAUDE_CODE_ENABLE_TELEMETRY",
        "OTEL_TRACES_EXPORTER",
        "OTEL_METRICS_EXPORTER",
        "OTEL_LOGS_EXPORTER",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://your-collector:4318")

    config = claude_runtime.resolve_claude_observability()

    assert config.env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://your-collector:4318"
    assert config.summary["endpoint_configured"] is False
    assert config.summary["endpoint_placeholder"] is True


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
async def test_run_claude_cli_prompt_uses_builder_source_env_not_onecli(
    monkeypatch,
    tmp_path: Path,
):
    calls: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"OK", b"")

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-token-from-env")
    _write_builder_source_env(
        monkeypatch,
        tmp_path,
        "CLAUDE_CODE_OAUTH_TOKEN=builder-token\nANTHROPIC_API_KEY=must-not-be-used\n",
    )
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
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    process_env = calls["kwargs"]["env"]
    assert process_env["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert "ANTHROPIC_API_KEY" not in process_env


@pytest.mark.asyncio
async def test_run_claude_cli_prompt_ignores_process_oauth(
    monkeypatch,
    tmp_path: Path,
):
    calls: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"OK", b"")

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-token-from-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    _write_builder_source_env(monkeypatch, tmp_path, "CLAUDE_CODE_OAUTH_TOKEN=builder-token\n")
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
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    process_env = calls["kwargs"]["env"]
    assert process_env["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert "ANTHROPIC_API_KEY" not in process_env


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
async def test_run_claude_sdk_prompt_uses_builder_source_env_not_onecli(
    monkeypatch,
    tmp_path: Path,
):
    captured: dict[str, object] = {}
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENABLED", "1")
    monkeypatch.setenv("AAB_CLAUDE_OTEL_ENDPOINT", "http://collector.example.com:4318")
    _write_builder_source_env(
        monkeypatch,
        tmp_path,
        "CLAUDE_CODE_OAUTH_TOKEN=builder-token\n",
    )

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

    class FakeSystemMessage:
        pass

    class FakePermissionResultAllow:
        def __init__(self, updated_input=None):
            self.updated_input = updated_input

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.query = fake_query
    fake_sdk_types = ModuleType("claude_agent_sdk.types")
    fake_sdk_types.PermissionResultAllow = FakePermissionResultAllow
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_sdk_types)
    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    assert captured["options_kwargs"]["system_prompt"] == {
        "type": "preset",
        "preset": "claude_code",
    }
    assert captured["options_kwargs"]["setting_sources"] == ["project"]
    assert captured["options_kwargs"]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert captured["options_kwargs"]["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert captured["options_kwargs"]["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://collector.example.com:4318"
    assert captured["options_kwargs"]["env"]["OTEL_SERVICE_NAME"] == "autonomous-agent-builder"


@pytest.mark.asyncio
async def test_run_claude_sdk_prompt_uses_empty_env_mapping(monkeypatch):
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

    class FakeSystemMessage:
        pass

    class FakePermissionResultAllow:
        def __init__(self, updated_input):
            self.updated_input = updated_input

    async def fake_query(*, prompt, options):
        yield FakeAssistantMessage()
        yield FakeResultMessage()

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.query = fake_query
    fake_sdk_types = ModuleType("claude_agent_sdk.types")
    fake_sdk_types.PermissionResultAllow = FakePermissionResultAllow
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_sdk_types)
    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    assert captured["options_kwargs"]["env"] == {}
    assert "permission_prompt_tool_name" not in captured["options_kwargs"]


@pytest.mark.asyncio
async def test_run_claude_sdk_prompt_uses_builder_source_oauth_and_suppresses_api_key(
    monkeypatch,
    tmp_path: Path,
):
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

    class FakeSystemMessage:
        pass

    class FakePermissionResultAllow:
        def __init__(self, updated_input):
            self.updated_input = updated_input

    async def fake_query(*, prompt, options):
        yield FakeAssistantMessage()
        yield FakeResultMessage()

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.query = fake_query
    fake_sdk_types = ModuleType("claude_agent_sdk.types")
    fake_sdk_types.PermissionResultAllow = FakePermissionResultAllow
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_sdk_types)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-token-from-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    _write_builder_source_env(
        monkeypatch,
        tmp_path,
        "CLAUDE_CODE_OAUTH_TOKEN=builder-token\nANTHROPIC_API_KEY=must-not-be-used\n",
    )

    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    env = captured["options_kwargs"]["env"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "builder-token"
    assert "ANTHROPIC_API_KEY" not in env


@pytest.mark.asyncio
async def test_run_claude_sdk_prompt_drains_error_result_before_raising(monkeypatch):
    events: list[str] = []

    class FakeClaudeAgentOptions:
        def __init__(self, **_kwargs):
            pass

    class FakeAssistantMessage:
        content: list[object] = []

    class FakeResultMessage:
        is_error = True
        result = "Not logged in · Please run /login"

    class FakeSystemMessage:
        pass

    class FakePermissionResultAllow:
        def __init__(self, updated_input):
            self.updated_input = updated_input

    async def fake_query(*, prompt, options):
        events.append("start")
        yield FakeResultMessage()
        events.append("drained")

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ClaudeAgentOptions = FakeClaudeAgentOptions
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.query = fake_query
    fake_sdk_types = ModuleType("claude_agent_sdk.types")
    fake_sdk_types.PermissionResultAllow = FakePermissionResultAllow
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_sdk_types)
    with pytest.raises(RuntimeError, match="/login"):
        await claude_runtime._run_claude_sdk_prompt(
            "Reply with exactly OK.",
            workspace_path=Path("/tmp/workspace"),
            model="haiku",
            allowed_tools=None,
            permission_mode="acceptEdits",
        )

    assert events == ["start", "drained"]


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
