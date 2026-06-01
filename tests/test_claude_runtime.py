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


def _make_fake_client_cls(messages: list, events: list[str], holder: dict):
    """Build a fake ClaudeSDKClient that mirrors the SDK 0.2.85 API.

    Records context-manager entry/exit and the query payload so tests can assert
    that the chat path runs under `async with ClaudeSDKClient(...)` and that
    `__aexit__` runs deterministically (the M1.5 cleanup guarantee).
    """

    class FakeClaudeSDKClient:
        def __init__(self, *, options):
            holder["options"] = options
            holder["client"] = self

        async def __aenter__(self):
            events.append("enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append("exit")
            return False

        async def query(self, prompt):
            events.append("query")
            holder["prompt"] = prompt

        async def receive_response(self):
            for message in messages:
                yield message

    return FakeClaudeSDKClient


def _install_fake_sdk(
    monkeypatch,
    options_cls,
    assistant_cls,
    result_cls,
    messages: list,
    *,
    events: list[str] | None = None,
    holder: dict | None = None,
):
    events = events if events is not None else []
    holder = holder if holder is not None else {}
    holder.setdefault("events", events)

    class FakeSystemMessage:
        pass

    class FakePermissionResultAllow:
        def __init__(self, updated_input=None):
            self.updated_input = updated_input

    class FakePermissionResultDeny:
        def __init__(self, message: str = "", interrupt: bool = False):
            self.message = message
            self.interrupt = interrupt

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = assistant_cls
    fake_sdk.ClaudeAgentOptions = options_cls
    fake_sdk.ResultMessage = result_cls
    fake_sdk.SystemMessage = FakeSystemMessage
    fake_sdk.ClaudeSDKClient = _make_fake_client_cls(messages, events, holder)
    fake_sdk_types = ModuleType("claude_agent_sdk.types")
    fake_sdk_types.PermissionResultAllow = FakePermissionResultAllow
    fake_sdk_types.PermissionResultDeny = FakePermissionResultDeny
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", fake_sdk_types)
    return holder


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

    client_holder = _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
    )
    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    captured["options"] = client_holder["options"]
    assert result == "OK"
    assert captured["options_kwargs"]["system_prompt"] == {
        "type": "preset",
        "preset": "claude_code",
        "exclude_dynamic_sections": True,
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

    _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
    )
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

    _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
    )
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

    holder = _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeResultMessage()],
        events=events,
    )
    with pytest.raises(RuntimeError, match="/login"):
        await claude_runtime._run_claude_sdk_prompt(
            "Reply with exactly OK.",
            workspace_path=Path("/tmp/workspace"),
            model="haiku",
            allowed_tools=None,
            permission_mode="acceptEdits",
        )

    # M1.5: the error result is drained inside the context manager and __aexit__
    # still runs deterministically before the RuntimeError surfaces.
    assert holder["events"] == ["enter", "query", "exit"]


@pytest.mark.asyncio
async def test_run_claude_sdk_prompt_runs_under_client_context_manager(monkeypatch):
    """M1.5: chat path executes inside `async with ClaudeSDKClient(...)` and
    __aexit__ fires after a successful response (deterministic cleanup)."""
    events: list[str] = []

    class FakeClaudeAgentOptions:
        def __init__(self, **_kwargs):
            pass

    class FakeAssistantMessage:
        def __init__(self):
            self.content = [SimpleNamespace(text="OK")]

    class FakeResultMessage:
        is_error = False
        result = ""

    holder = _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
        events=events,
    )
    result = await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=None,
        permission_mode="acceptEdits",
    )

    assert result == "OK"
    assert holder["events"] == ["enter", "query", "exit"]
    # query() received the streamed prompt payload, not a bare string.
    assert holder["prompt"] is not None


@pytest.mark.asyncio
async def test_auto_approve_denies_ungranted_mutating_builtin(monkeypatch):
    """M2.6: the permission callback denies an ungranted mutating built-in via
    the shared phase-boundary deny policy, with a routing reason."""
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

    _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
    )
    await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=["Read"],
        permission_mode="acceptEdits",
    )

    can_use_tool = captured["options_kwargs"]["can_use_tool"]
    # Write is a mutating built-in and was NOT granted -> deny with a reason.
    decision = await can_use_tool("Write", {"file_path": "x"}, None)
    assert type(decision).__name__ == "FakePermissionResultDeny"
    assert "chat lane" in decision.message
    assert "task_dispatch" in decision.message


@pytest.mark.asyncio
async def test_auto_approve_allows_granted_and_readonly_tools(monkeypatch):
    """M2.6: a tool granted for this phase is allowed even when it is a mutating
    built-in; a non-mutating tool is always allowed."""
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

    _install_fake_sdk(
        monkeypatch,
        FakeClaudeAgentOptions,
        FakeAssistantMessage,
        FakeResultMessage,
        [FakeAssistantMessage(), FakeResultMessage()],
    )
    await claude_runtime._run_claude_sdk_prompt(
        "Reply with exactly OK.",
        workspace_path=Path("/tmp/workspace"),
        model="haiku",
        allowed_tools=["Bash"],
        permission_mode="acceptEdits",
    )

    can_use_tool = captured["options_kwargs"]["can_use_tool"]
    # Bash is mutating but explicitly granted for this phase -> allow.
    granted = await can_use_tool("Bash", {"command": "ls"}, None)
    assert type(granted).__name__ == "FakePermissionResultAllow"
    assert granted.updated_input == {"command": "ls"}
    # Read is non-mutating and not in the deny set -> allow.
    readonly = await can_use_tool("Read", {"file_path": "x"}, None)
    assert type(readonly).__name__ == "FakePermissionResultAllow"


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
