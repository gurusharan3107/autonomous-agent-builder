"""Agent runner — query() dispatch + ResultMessage cost + SDK error handling.

This is the core execution engine. It:
1. Builds a ToolRegistry for the agent
2. Dispatches via SDK query() with proper options
3. Captures session_id for phase chaining
4. Extracts cost/usage from ResultMessage
5. Handles SDK-specific errors (CLINotFoundError, ProcessError, CLIJSONDecodeError)
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.agents.definitions import (
    AgentDefinition,
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.tool_registry import ToolRegistry
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.onecli_runtime import prepare_onecli_runtime_env

log = structlog.get_logger()


class RunResult:
    """Result of an agent run — wraps SDK ResultMessage data."""

    def __init__(
        self,
        session_id: str | None = None,
        cost_usd: float = 0.0,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_cached: int = 0,
        num_turns: int = 0,
        duration_ms: int = 0,
        stop_reason: str | None = None,
        output_text: str = "",
        error: str | None = None,
        confidence: float | None = None,
        diff_summary: dict[str, Any] | None = None,
    ):
        self.session_id = session_id
        self.cost_usd = cost_usd
        self.tokens_input = tokens_input
        self.tokens_output = tokens_output
        self.tokens_cached = tokens_cached
        self.num_turns = num_turns
        self.duration_ms = duration_ms
        self.stop_reason = stop_reason
        self.output_text = output_text
        self.error = error
        self.confidence = confidence
        self.diff_summary = diff_summary

    @property
    def hit_capability_limit(self) -> bool:
        return self.stop_reason in ("max_turns", "budget_exceeded")


# Matches either `confidence: 0.82`, `confidence = 0.82`, or `**confidence**: 0.82`
# on any line of the final assistant message. Percent form `confidence: 82%` is
# normalized to the [0, 1] range.
_CONFIDENCE_RE = re.compile(
    r"(?im)^\s*[*_`]*\s*confidence\s*[*_`]*\s*[:=]\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<pct>%)?"
)


def parse_confidence_from_text(text: str) -> float | None:
    """Extract a confidence score from the final assistant message.

    Per SDK-verifier guidance: agent-emitted confidence is soft signal — always
    null-safe. Returns None when no marker is found, value is out of range,
    or parsing fails. Percent form (e.g., `confidence: 82%`) is normalized.
    """
    if not text:
        return None
    match = _CONFIDENCE_RE.search(text)
    if not match:
        return None
    try:
        raw = float(match.group("value"))
    except (TypeError, ValueError):
        return None
    if match.group("pct"):
        raw = raw / 100.0
    if raw < 0.0 or raw > 1.0:
        return None
    return raw


_DIFF_HUNK_PREVIEW_CHARS = 400
_DIFF_MAX_HUNKS = 20


def _run_git(workspace_path: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        log.debug("git_command_failed", args=args, error=str(exc))
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def capture_workspace_diff(workspace_path: str | None) -> dict[str, Any] | None:
    """Capture a structured diff summary of the last commit in the worktree.

    Per SDK-verifier guidance: shells `git diff HEAD~1..HEAD` post-run in the
    worktree. Empty diff (no commits, or worktree not a git repo) returns
    None — a valid signal, not an error. Never blocks the run.
    """
    if not workspace_path:
        return None
    path = Path(workspace_path)
    if not path.exists() or not (path / ".git").exists() and not _run_git(workspace_path, "rev-parse", "--is-inside-work-tree"):
        # Not a git worktree — nothing to diff.
        return None

    # Confirm HEAD~1 exists (a single-commit repo has no previous commit).
    parent = _run_git(workspace_path, "rev-parse", "--verify", "HEAD~1")
    if parent is None:
        return None

    stat_out = _run_git(workspace_path, "diff", "--numstat", "HEAD~1..HEAD")
    if stat_out is None:
        return None

    files_changed = 0
    insertions = 0
    deletions = 0
    per_file: dict[str, dict[str, int]] = {}
    for line in stat_out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, removed_s, fname = parts
        try:
            added = int(added_s) if added_s != "-" else 0
            removed = int(removed_s) if removed_s != "-" else 0
        except ValueError:
            continue
        per_file[fname] = {"added_lines": added, "removed_lines": removed}
        insertions += added
        deletions += removed
        files_changed += 1

    if files_changed == 0:
        return None

    # Collect bounded hunk previews.
    hunks: list[dict[str, Any]] = []
    diff_out = _run_git(workspace_path, "diff", "--unified=3", "HEAD~1..HEAD") or ""
    current_file: str | None = None
    current_preview: list[str] = []

    def flush_current() -> None:
        nonlocal current_file, current_preview
        if current_file is None:
            return
        stats = per_file.get(current_file, {"added_lines": 0, "removed_lines": 0})
        preview = "\n".join(current_preview)[:_DIFF_HUNK_PREVIEW_CHARS]
        hunks.append(
            {
                "file": current_file,
                "added_lines": stats["added_lines"],
                "removed_lines": stats["removed_lines"],
                "preview": preview,
            }
        )
        current_file = None
        current_preview = []

    for line in diff_out.splitlines():
        if len(hunks) >= _DIFF_MAX_HUNKS:
            break
        if line.startswith("diff --git"):
            flush_current()
            # `diff --git a/path b/path` — pick the b/ side as canonical.
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) == 2 else None
            current_preview = []
        elif current_file is not None:
            current_preview.append(line)
    flush_current()

    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "hunks": hunks,
    }


class AgentRunner:
    """Runs SDLC agents using the Claude Agent SDK."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run_phase(
        self,
        agent_name: str,
        prompt: str,
        workspace_path: str,
        resume_session: str | None = None,
        subagents: tuple[str, ...] | None = None,
        custom_tools: dict[str, Any] | None = None,
        on_stream: Any | None = None,
        can_use_tool: Any | None = None,
        on_tool_event: Any | None = None,
    ) -> RunResult:
        """Execute an agent phase.

        Args:
            agent_name: Key in AGENT_DEFINITIONS.
            prompt: Formatted prompt with template vars filled.
            workspace_path: Path to the task workspace.
            resume_session: session_id from a prior phase for context chaining.
            custom_tools: Dict of custom tool name -> callable.
            on_stream: Async callback for streaming output to dashboard.

        Returns:
            RunResult with cost, session_id, and output.
        """
        agent_def = get_agent_definition(agent_name)

        # Build ToolRegistry — schema discovery at phase start
        allowed_tool_names = list(agent_def.tools)
        if subagents and "Agent" not in allowed_tool_names:
            allowed_tool_names.append("Agent")

        registry = ToolRegistry.build(
            allowed_tool_names=allowed_tool_names,
            custom_tools=custom_tools,
        )

        log.info(
            "agent_phase_start",
            agent=agent_name,
            model=agent_def.model,
            tools=registry.list_tools(),
            workspace=workspace_path,
            resume=resume_session is not None,
        )

        try:
            result = await self._execute_query(
                agent_def=agent_def,
                prompt=prompt,
                workspace_path=workspace_path,
                registry=registry,
                resume_session=resume_session,
                subagents=subagents,
                on_stream=on_stream,
                can_use_tool=can_use_tool,
                on_tool_event=on_tool_event,
            )
        except ConfigurationError:
            raise
        except TransientError as e:
            log.warning("agent_transient_error", agent=agent_name, error=str(e))
            raise
        except Exception as e:
            log.error("agent_unexpected_error", agent=agent_name, error=str(e))
            return RunResult(error=str(e))

        log.info(
            "agent_phase_complete",
            agent=agent_name,
            cost_usd=result.cost_usd,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            num_turns=result.num_turns,
            stop_reason=result.stop_reason,
        )

        return result

    async def _execute_query(
        self,
        agent_def: AgentDefinition,
        prompt: str,
        workspace_path: str,
        registry: ToolRegistry,
        resume_session: str | None,
        subagents: tuple[str, ...] | None,
        on_stream: Any | None,
        can_use_tool: Any | None,
        on_tool_event: Any | None,
    ) -> RunResult:
        """Execute the SDK query() call.

        This is separated to allow mocking in tests. In production,
        this calls the actual Claude Agent SDK.
        """
        # Import SDK at call time — allows graceful degradation if not installed
        try:
            from claude_agent_sdk import (
                AgentDefinition as SDKSubagentDefinition,
            )
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ClaudeSDKClient,
                HookMatcher,
                ResultMessage,
                SystemMessage,
            )
        except ImportError as exc:
            raise ConfigurationError(
                "Claude Agent SDK not installed. Run: pip install claude-agent-sdk"
            ) from exc

        session_id = None
        output_parts: list[str] = []
        selected_tools = (
            agent_def.tools
            if can_use_tool is not None
            else (agent_def.auto_approve_tools or agent_def.tools)
        )
        allowed_tools = list(selected_tools)
        if subagents and "Agent" not in allowed_tools:
            allowed_tools.append("Agent")
        sdk_subagents = None
        if subagents:
            sdk_subagents = {}
            for subagent_name in subagents:
                subagent_def = get_subagent_definition(subagent_name)
                sdk_subagents[subagent_name] = SDKSubagentDefinition(
                    description=subagent_def.description,
                    prompt=subagent_def.prompt,
                    tools=list(subagent_def.tools),
                    model=subagent_def.model,
                )

        onecli_env = await prepare_onecli_runtime_env()

        options = ClaudeAgentOptions(
            allowed_tools=allowed_tools,
            mcp_servers=self._build_mcp_servers(workspace_path),
            permission_mode=self.settings.agent.permission_mode,
            model=agent_def.model,
            cwd=workspace_path or None,
            max_turns=agent_def.max_turns,
            max_budget_usd=agent_def.max_budget_usd,
            can_use_tool=can_use_tool,
            agents=sdk_subagents,
        )
        if onecli_env.active:
            options.env = {**getattr(options, "env", {}), **onecli_env.env}

        if resume_session:
            # For an HTTP chat lane that needs a specific past conversation,
            # follow the SDK contract directly: persist the SDK session id and
            # pass it back via `resume` on the next call.
            options.resume = resume_session

        # Wire safety and audit hooks with SDK signatures
        from autonomous_agent_builder.agents.hooks import (
            audit_log_tool_use,
            enforce_workspace_boundary,
            keep_tool_stream_open,
            validate_bash_argv,
        )

        async def _post_tool_audit(
            input: dict[str, Any],
            tool_use_id: str | None,
            context: dict[str, Any],
        ) -> dict[str, Any]:
            await audit_log_tool_use(input, tool_use_id, context)
            if on_tool_event is not None:
                await on_tool_event(
                    {
                        "tool_name": input.get("tool_name", ""),
                        "tool_input": input.get("tool_input", {}),
                        "tool_response": input.get("tool_response", ""),
                        "tool_use_id": tool_use_id,
                    }
                )
            return {}

        options.hooks = {
            "PreToolUse": [
                HookMatcher(
                    matcher=".*",
                    hooks=[keep_tool_stream_open],
                    timeout=30.0,
                ),
                HookMatcher(
                    matcher="Read|Edit|Write|Glob|Grep",
                    hooks=[enforce_workspace_boundary],
                    timeout=30.0,
                ),
                HookMatcher(
                    matcher="Bash",
                    hooks=[validate_bash_argv],
                    timeout=30.0,
                ),
            ],
            "PostToolUse": [
                HookMatcher(
                    matcher=".*",
                    hooks=[_post_tool_audit],
                    timeout=30.0,
                ),
            ],
        }

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        session_id = message.data.get("session_id")

                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if hasattr(block, "text"):
                                output_parts.append(block.text)
                                if on_stream:
                                    await on_stream(block.text)

                    elif isinstance(message, ResultMessage):
                        usage = message.usage or {}
                        output_text = "\n".join(output_parts)
                        stop_reason = getattr(message, "stop_reason", None)
                        # Per SDK-verifier: only trust confidence on clean runs.
                        # Capability-limited runs get null confidence regardless
                        # of what the final message claims.
                        confidence: float | None = None
                        if stop_reason not in ("max_turns", "budget_exceeded"):
                            confidence = parse_confidence_from_text(output_text)
                        diff_summary = capture_workspace_diff(workspace_path)
                        return RunResult(
                            session_id=getattr(message, "session_id", None) or session_id,
                            cost_usd=getattr(message, "total_cost_usd", 0.0),
                            tokens_input=usage.get("input_tokens", 0),
                            tokens_output=usage.get("output_tokens", 0),
                            tokens_cached=usage.get("cache_read_input_tokens", 0),
                            num_turns=getattr(message, "num_turns", 0),
                            duration_ms=getattr(message, "duration_ms", 0),
                            stop_reason=stop_reason,
                            output_text=output_text,
                            confidence=confidence,
                            diff_summary=diff_summary,
                        )

        except Exception as e:
            # Map SDK errors to our error types
            error_type = type(e).__name__
            log.error(
                "sdk_query_error",
                error_type=error_type,
                error=str(e),
                cause=str(e.__cause__) if e.__cause__ else None,
            )
            if error_type == "CLINotFoundError":
                raise ConfigurationError("Claude Code CLI not installed") from e
            elif error_type == "CLIConnectionError":
                return RunResult(error=f"{e} (cause: {e.__cause__})")
            elif error_type == "ProcessError":
                exit_code = getattr(e, "exit_code", -1)
                if exit_code in (1, 2):
                    raise TransientError(f"Process error (exit {exit_code}): {e}") from e
                else:
                    return RunResult(error=str(e), stop_reason="process_error")
            elif error_type == "CLIJSONDecodeError":
                raise TransientError(f"Malformed SDK output: {e}") from e
            raise

        # If we get here without a ResultMessage, something went wrong
        return RunResult(
            session_id=session_id,
            output_text="\n".join(output_parts),
            error="No ResultMessage received",
        )

    def _build_mcp_servers(self, workspace_path: str) -> dict[str, Any]:
        """Create default in-process SDK MCP servers for builder and workspace tools."""
        from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

        return build_default_mcp_servers(
            workspace_path=workspace_path,
            project_root=os.environ.get("AAB_PROJECT_ROOT"),
        )


class ConfigurationError(Exception):
    """Non-retryable configuration error."""


class TransientError(Exception):
    """Retryable transient error."""
