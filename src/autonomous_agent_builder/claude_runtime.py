"""Claude runtime helpers for SDK-backed helper lanes."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from autonomous_agent_builder.builder_env import builder_source_env
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.runtime import resolve_claude_observability
from autonomous_agent_builder.onecli_runtime import scrub_provider_env


@dataclass(frozen=True)
class ClaudeAvailability:
    available: bool
    backend: str
    message: str = ""


def _normalized_backend() -> str:
    backend = get_settings().agent.auth_backend.strip().lower()
    if backend not in {"auto", "cli", "sdk"}:
        return "auto"
    return backend


def resolve_claude_backend() -> str:
    """Resolve the Claude execution backend for the current environment."""
    backend = _normalized_backend()
    if backend != "auto":
        return backend
    if importlib.util.find_spec("claude_agent_sdk") is not None:
        return "sdk"
    return "sdk"


async def check_claude_availability(
    workspace_path: Path,
    model: str,
    *,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> ClaudeAvailability:
    """Probe the configured Claude backend with a minimal prompt."""
    backend = resolve_claude_backend()
    probe_timeout = float(get_settings().agent.availability_probe_timeout_seconds)
    stderr_capture = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr_capture):
            await asyncio.wait_for(
                run_claude_prompt(
                    "Reply with exactly OK.",
                    workspace_path=workspace_path,
                    model=model,
                    # Keep the availability probe tool-free so the CLI prompt cannot
                    # be misparsed by variadic tool flags.
                    allowed_tools=None,
                    permission_mode=permission_mode,
                    timeout_seconds=probe_timeout,
                ),
                timeout=probe_timeout,
            )
    except TimeoutError:
        return ClaudeAvailability(
            available=False,
            backend=backend,
            message=f"Claude availability probe timed out after {probe_timeout:g}s.",
        )
    except Exception as exc:
        captured = stderr_capture.getvalue().strip()
        message = str(exc).strip()
        if captured and (not message or "stderr" in message.lower()):
            message = captured
        return ClaudeAvailability(available=False, backend=backend, message=message or captured)
    return ClaudeAvailability(available=True, backend=backend)


def require_claude_available(
    workspace_path: Path,
    model: str,
    *,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> ClaudeAvailability:
    """Synchronous wrapper for availability probing."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        availability = asyncio.run(
            check_claude_availability(
                workspace_path=workspace_path,
                model=model,
                allowed_tools=allowed_tools,
                permission_mode=permission_mode,
            )
        )
        if not availability.available:
            raise RuntimeError(availability.message or "Claude is unavailable.") from None
        return availability
    raise RuntimeError(
        "require_claude_available() cannot run inside an active event loop; "
        "use `await check_claude_availability(...)` instead."
    )


async def run_claude_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Execute a one-shot Claude prompt using the configured backend."""
    backend = resolve_claude_backend()
    timeout = timeout_seconds or float(get_settings().agent.query_timeout_seconds)
    runner = _run_claude_cli_prompt if backend == "cli" else _run_claude_sdk_prompt
    try:
        return await asyncio.wait_for(
            runner(
                prompt,
                workspace_path=workspace_path,
                model=model,
                allowed_tools=allowed_tools,
                permission_mode=permission_mode,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise RuntimeError(f"Claude {backend} prompt timed out after {timeout:g}s.") from exc


async def _run_claude_cli_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> str:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude CLI is not installed or not on PATH.")

    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--model",
        model,
        "--permission-mode",
        permission_mode or get_settings().agent.permission_mode,
        "--permission-prompt-tool",
        "reject",
    ]

    if allowed_tools is not None:
        if allowed_tools:
            command.extend(["--tools", *allowed_tools])
        else:
            command.extend(["--tools", ""])
        if allowed_tools:
            command.extend(["--allowed-tools", *allowed_tools])

    builder_env = builder_source_env()
    base_env = {**os.environ}
    base_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    base_env.pop("ANTHROPIC_API_KEY", None)
    if builder_env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        base_env["CLAUDE_CODE_OAUTH_TOKEN"] = builder_env["CLAUDE_CODE_OAUTH_TOKEN"]
    # Preserve only the local Claude OAuth token from the Builder source `.env`.
    process_env = scrub_provider_env(base_env)

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(workspace_path),
        env=process_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise RuntimeError(stderr_text or stdout_text or "Claude CLI prompt failed.")
    if not stdout_text:
        raise RuntimeError("Claude CLI returned no output.")
    return stdout_text


async def _run_claude_sdk_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> str:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        SystemMessage,
    )
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

    from autonomous_agent_builder.embedded.server.agent_tool_policy import (
        chat_mutating_builtin_denial,
    )

    source_env = builder_source_env()
    observability = resolve_claude_observability(source_env)

    # Phase/context value the deny policy needs: the tools this helper lane was
    # explicitly granted for the current phase. Anything in this set is allowed;
    # ungranted mutating built-ins are denied by the shared phase-boundary policy.
    granted_tools = frozenset(allowed_tools or [])

    async def _prompt_stream():
        yield {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None,
        }

    async def _auto_approve(
        tool_name: str, input_data: object, context: object
    ) -> PermissionResultAllow | PermissionResultDeny:
        # M2.6: enforce phase boundaries one layer above dispatch_lock. A tool
        # granted for this phase executes; an ungranted mutating built-in is
        # denied via the shared chat-lane deny policy (single owner) so this
        # helper lane cannot edit the workspace directly outside the visible
        # backlog -> task -> approval -> execution lifecycle.
        if tool_name not in granted_tools:
            deny, reason = chat_mutating_builtin_denial(tool_name)
            if deny:
                return PermissionResultDeny(message=reason)
        return PermissionResultAllow(updated_input=input_data)  # type: ignore[arg-type]

    merged_env = {**observability.env}
    if source_env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        merged_env["CLAUDE_CODE_OAUTH_TOKEN"] = source_env["CLAUDE_CODE_OAUTH_TOKEN"]
    merged_env = scrub_provider_env(merged_env)
    options = ClaudeAgentOptions(
        model=model,
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "exclude_dynamic_sections": True,
        },
        setting_sources=["project"],
        cwd=workspace_path,
        max_turns=5,
        allowed_tools=allowed_tools or [],
        permission_mode=permission_mode or get_settings().agent.permission_mode,
        env=merged_env,
        can_use_tool=_auto_approve,
        include_partial_messages=True,
    )

    output_parts: list[str] = []
    error_result: str | None = None

    # M1.5: run under the ClaudeSDKClient context manager (mirrors runner.py:691)
    # so __aexit__ deterministically cancels the monitor/streaming tasks on exit,
    # rather than relying on bare query() generator finalization.
    async with ClaudeSDKClient(options=options) as client:
        await client.query(_prompt_stream())
        async for message in client.receive_response():
            if isinstance(message, SystemMessage):
                continue
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    text = getattr(block, "text", None)
                    if text:
                        output_parts.append(text)
                continue
            if isinstance(message, ResultMessage):
                if getattr(message, "is_error", False):
                    error_result = (
                        message.result
                        or "\n".join(output_parts).strip()
                        or "Claude SDK query failed."
                    )
                continue

    if error_result:
        raise RuntimeError(error_result)

    response = "\n".join(output_parts).strip()
    if not response:
        raise RuntimeError("Claude SDK returned no output.")
    return response
