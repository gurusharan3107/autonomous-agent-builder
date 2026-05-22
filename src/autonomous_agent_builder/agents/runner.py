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
import shutil
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from autonomous_agent_builder.agents.definitions import (
    AgentDefinition,
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.execution_policy import (
    AgentRuntimePolicy,
    resolve_agent_runtime_policy,
    resolve_subagent_model,
)
from autonomous_agent_builder.agents.tool_registry import ToolRegistry
from autonomous_agent_builder.builder_env import builder_source_env
from autonomous_agent_builder.config import Settings
from autonomous_agent_builder.observability.runtime import resolve_claude_observability
from autonomous_agent_builder.onecli_runtime import scrub_provider_env
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)

log = structlog.get_logger()

# Phases where a valid git HEAD is a precondition for dispatch.
_PHASES_REQUIRE_GIT_HEAD: frozenset[str] = frozenset(
    {
        "code-gen",
        "gate-remediator",
        "integration-resolver",
        "pr-creator",
        "build-verifier",
        "feature-verifier",
        "optimization-agent",
    }
)

# Phases where Python tooling (ruff, pyproject.toml) is expected.
_PYTHON_GATE_PHASES: frozenset[str] = frozenset(
    {"code-gen", "gate-remediator", "feature-verifier"}
)

_SDK_ERROR_OUTPUT_PREFIXES = (
    "API Error:",
    "Claude Code process exited with status",
)


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
        observability: dict[str, Any] | None = None,
        provider_limit: dict[str, Any] | None = None,
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
        self.observability = observability
        self.provider_limit = provider_limit

    @property
    def hit_capability_limit(self) -> bool:
        return self.stop_reason in ("max_turns", "budget_exceeded", "provider_limit")


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
    git_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") or key in {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}
    }
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workspace_path,
            env=git_env,
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
    if not path.exists():
        return None
    is_git_dir = (path / ".git").exists()
    is_worktree = _run_git(workspace_path, "rev-parse", "--is-inside-work-tree")
    if not is_git_dir and not is_worktree:
        # Not a git worktree — nothing to diff.
        return None

    dirty = bool((_run_git(workspace_path, "status", "--porcelain") or "").strip())
    if dirty:
        diff_args = ("HEAD",)
    else:
        # Confirm HEAD~1 exists (a single-commit repo has no previous commit).
        parent = _run_git(workspace_path, "rev-parse", "--verify", "HEAD~1")
        if parent is None:
            return None
        diff_args = ("HEAD~1..HEAD",)

    stat_out = _run_git(workspace_path, "diff", "--numstat", *diff_args)
    if stat_out is None:
        return None

    status_out = _run_git(workspace_path, "diff", "--name-status", *diff_args) or ""
    statuses: dict[str, dict[str, str]] = {}
    for line in status_out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            statuses[parts[2]] = {"status": "R", "old_path": parts[1]}
        else:
            statuses[parts[-1]] = {"status": status[:1] or "M", "old_path": ""}

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

    if dirty:
        untracked = _run_git(workspace_path, "ls-files", "--others", "--exclude-standard") or ""
        for fname in untracked.splitlines():
            if not fname.strip() or fname in per_file:
                continue
            file_path = path / fname
            try:
                added = len(file_path.read_text(errors="ignore").splitlines())
            except OSError:
                added = 0
            per_file[fname] = {"added_lines": added, "removed_lines": 0}
            statuses[fname] = {"status": "A", "old_path": ""}
            insertions += added
            files_changed += 1

    if files_changed == 0:
        return None

    # Collect bounded hunk previews.
    hunks: list[dict[str, Any]] = []
    diff_out = _run_git(workspace_path, "diff", "--unified=3", *diff_args) or ""
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
        "files": [
            {
                "path": path,
                "status": statuses.get(path, {}).get("status", "M"),
                "old_path": statuses.get(path, {}).get("old_path", ""),
                "added_lines": stats["added_lines"],
                "removed_lines": stats["removed_lines"],
            }
            for path, stats in per_file.items()
        ],
        "hunks": hunks,
    }


class AgentRunner:
    """Runs SDLC agents using the Claude Agent SDK."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _preflight_workspace(self, agent_name: str, workspace_path: str) -> RunResult | None:
        """Check critical workspace preconditions before dispatching.

        Returns a failed RunResult if a hard precondition is not met, else None.
        Logs informational warnings for soft preconditions (missing ruff, pyproject.toml).

        Git HEAD check is only a hard failure when the workspace IS a git repo but
        HEAD is invalid (unborn HEAD, like IMP-008 class). A workspace that isn't
        git-initialized yet is only warned, not failed — the workspace manager
        owns git initialization before this phase runs.
        """
        if agent_name in _PHASES_REQUIRE_GIT_HEAD:
            workspace = Path(workspace_path)
            is_git_dir = (workspace / ".git").exists()
            is_worktree = _run_git(workspace_path, "rev-parse", "--is-inside-work-tree")
            if is_git_dir or is_worktree:
                head = _run_git(workspace_path, "rev-parse", "HEAD")
                if head is None:
                    return RunResult(
                        error=(
                            f"preflight: git HEAD is invalid in {workspace_path} — "
                            "workspace has unborn HEAD (workspace manager must create "
                            "an initial commit before dispatching this phase)"
                        ),
                        stop_reason="preflight_failed",
                    )
            else:
                log.info(
                    "preflight_no_git_repo",
                    agent=agent_name,
                    workspace=workspace_path,
                )
        if agent_name in _PYTHON_GATE_PHASES:
            workspace = Path(workspace_path)
            if not (workspace / "pyproject.toml").exists():
                log.info(
                    "preflight_missing_pyproject",
                    agent=agent_name,
                    workspace=workspace_path,
                )
            if shutil.which("ruff") is None:
                log.info(
                    "preflight_ruff_not_found",
                    agent=agent_name,
                    workspace=workspace_path,
                )
        return None

    async def run_phase(
        self,
        agent_name: str,
        prompt: str,
        workspace_path: str,
        resume_session: str | None = None,
        subagents: tuple[str, ...] | None = None,
        custom_tools: dict[str, Any] | None = None,
        on_stream: Any | None = None,
        on_stream_usage: Any | None = None,
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
            on_stream_usage: Async callback(input, cached, output) for live token telemetry.

        Returns:
            RunResult with cost, session_id, and output.
        """
        agent_def = get_agent_definition(agent_name)
        runtime_policy = resolve_agent_runtime_policy(agent_def, self.settings, subagents)
        subagents = runtime_policy.subagents

        # Build ToolRegistry — schema discovery at phase start
        allowed_tool_names = list(agent_def.tools)
        if subagents and "Agent" not in allowed_tool_names:
            allowed_tool_names.append("Agent")

        registry = ToolRegistry.build(
            allowed_tool_names=allowed_tool_names,
            custom_tools=custom_tools,
        )

        preflight_error = self._preflight_workspace(agent_name, workspace_path)
        if preflight_error is not None:
            log.warning(
                "agent_preflight_failed",
                agent=agent_name,
                error=preflight_error.error,
            )
            return preflight_error

        log.info(
            "agent_phase_start",
            agent=agent_name,
            model=runtime_policy.model,
            effort=runtime_policy.effort,
            context_strategy=runtime_policy.context_strategy,
            selected_subagents=list(runtime_policy.subagents),
            permission_policy=runtime_policy.permission_policy,
            hook_policy=runtime_policy.hook_policy,
            reason_code=runtime_policy.reason_code,
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
                runtime_policy=runtime_policy,
                subagents=subagents,
                on_stream=on_stream,
                on_stream_usage=on_stream_usage,
                can_use_tool=can_use_tool,
                on_tool_event=on_tool_event,
            )
            if self._is_empty_sdk_result(result):
                if agent_def.model != "sonnet" and resume_session is None:
                    log.warning(
                        "agent_empty_result_model_fallback",
                        agent=agent_name,
                        from_model=agent_def.model,
                        to_model="sonnet",
                    )
                    result = await self._execute_query(
                        agent_def=replace(agent_def, model="sonnet"),
                        prompt=prompt,
                        workspace_path=workspace_path,
                        registry=registry,
                        resume_session=None,
                        runtime_policy=replace(
                            runtime_policy,
                            model="sonnet",
                            effort="medium",
                            thinking={"type": "adaptive"},
                        ),
                        subagents=subagents,
                        on_stream=on_stream,
                        on_stream_usage=on_stream_usage,
                        can_use_tool=can_use_tool,
                        on_tool_event=on_tool_event,
                    )
                if self._is_empty_sdk_result(result):
                    return RunResult(
                        session_id=result.session_id,
                        error=(
                            "Empty SDK result: no assistant text, token usage, or cost was returned"
                        ),
                        stop_reason=result.stop_reason,
                        observability=result.observability,
                    )
            if self._is_provider_limit_result(result):
                # Prefer SDK-sourced provider_limit already set by _execute_query
                # (e.g. from RateLimitEvent); fall back to text-parsed metadata.
                provider_limit = result.provider_limit or self._provider_limit_metadata(result)
                return RunResult(
                    session_id=result.session_id,
                    output_text=result.output_text,
                    stop_reason="provider_limit",
                    observability=result.observability,
                    provider_limit=provider_limit,
                )
            if sdk_error := self._sdk_output_error(result):
                return RunResult(
                    session_id=result.session_id,
                    output_text=result.output_text,
                    error=sdk_error,
                    stop_reason="sdk_output_error",
                    observability=result.observability,
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

    def _is_empty_sdk_result(self, result: RunResult) -> bool:
        if result.error:
            return False
        if result.stop_reason == "provider_limit":
            return False
        return (
            not str(result.output_text or "").strip()
            and result.tokens_input == 0
            and result.tokens_output == 0
            and result.tokens_cached == 0
            and float(result.cost_usd or 0.0) == 0.0
        )

    def _is_provider_limit_result(self, result: RunResult) -> bool:
        if result.error:
            return False
        text = str(result.output_text or "").lower()
        return result.stop_reason == "provider_limit" or (
            is_provider_limit_text(text)
            and result.tokens_input == 0
            and result.tokens_output == 0
            and float(result.cost_usd or 0.0) == 0.0
        )

    def _sdk_output_error(self, result: RunResult) -> str | None:
        if result.error:
            return None
        text = str(result.output_text or "").strip()
        if not text:
            return None
        has_usage = (
            result.tokens_input > 0
            or result.tokens_output > 0
            or result.tokens_cached > 0
            or float(result.cost_usd or 0.0) > 0.0
        )
        if has_usage:
            return None
        if any(text.startswith(prefix) for prefix in _SDK_ERROR_OUTPUT_PREFIXES):
            return text
        return None

    def _provider_limit_metadata(self, result: RunResult) -> dict[str, Any]:
        reset_at, reset_hint = parse_reset_hint(result.output_text)
        return {
            "code": "provider_limit",
            "reason": result.stop_reason or "provider_limit",
            "reset_at": reset_at.isoformat() if reset_at else None,
            "reset_hint": reset_hint,
            "source": "claude_agent_sdk",
        }

    async def _execute_query(
        self,
        agent_def: AgentDefinition,
        prompt: str,
        workspace_path: str,
        registry: ToolRegistry,
        resume_session: str | None,
        runtime_policy: AgentRuntimePolicy,
        subagents: tuple[str, ...] | None,
        on_stream: Any | None,
        on_stream_usage: Any | None,
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
                RateLimitEvent,
                ResultMessage,
                StreamEvent,
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
                sdk_subagent_kwargs: dict[str, Any] = {
                    "description": subagent_def.description,
                    "prompt": subagent_def.prompt,
                    "tools": list(subagent_def.tools),
                    "model": resolve_subagent_model(subagent_def),
                }
                if subagent_def.max_turns is not None:
                    sdk_subagent_kwargs["maxTurns"] = subagent_def.max_turns
                sdk_subagents[subagent_name] = SDKSubagentDefinition(**sdk_subagent_kwargs)

        source_env = builder_source_env()
        observability = resolve_claude_observability(source_env)

        # Always wire can_use_tool — omitting it leaves the subprocess permission
        # callback channel closed, causing the SDK to hang after SystemMessage init.
        # For non-interactive runs, auto-approve within the already-restricted
        # allowed_tools surface is safe.
        try:
            from claude_agent_sdk.types import PermissionResultAllow
        except ImportError:

            class PermissionResultAllow:  # type: ignore[no-redef]
                def __init__(self, updated_input: object | None = None):
                    self.updated_input = updated_input

        async def _auto_approve(
            tool_name: str, input_data: object, context: object
        ) -> PermissionResultAllow:
            return PermissionResultAllow(updated_input=input_data)  # type: ignore[arg-type]

        effective_can_use_tool = can_use_tool if can_use_tool is not None else _auto_approve

        options_kwargs: dict[str, Any] = {
            "allowed_tools": allowed_tools,
            "system_prompt": {
                "type": "preset",
                "preset": "claude_code",
                "exclude_dynamic_sections": True,  # G2: skip cwd/memory/git sections to maximise cache ratio
            },
            "setting_sources": ["project"],
            "settings": '{"autoCompactEnabled": true}'
            if runtime_policy.autocompact_enabled
            else None,
            "mcp_servers": self._build_mcp_servers(workspace_path, allowed_tools),
            "permission_mode": self.settings.agent.permission_mode,
            "model": runtime_policy.model,
            "cwd": workspace_path or None,
            "max_turns": agent_def.max_turns,
            "max_budget_usd": agent_def.max_budget_usd,
            "can_use_tool": effective_can_use_tool,
            "agents": sdk_subagents,
            "effort": runtime_policy.effort,
            "thinking": runtime_policy.thinking,
            "include_partial_messages": True,  # G1: enables per-turn StreamEvent usage telemetry
            "strict_mcp_config": True,  # G7: only explicitly registered MCP tools are visible
            "extra_args": {
                "disable-slash-commands": None,
            },
        }
        options = ClaudeAgentOptions(**options_kwargs)
        child_env = {**observability.env}
        if source_env.get("CLAUDE_CODE_OAUTH_TOKEN"):
            child_env["CLAUDE_CODE_OAUTH_TOKEN"] = source_env["CLAUDE_CODE_OAUTH_TOKEN"]
        merged_child_env = scrub_provider_env(child_env)
        if merged_child_env:
            options.env = {**getattr(options, "env", {}), **merged_child_env}

        if resume_session:
            # For an HTTP chat lane that needs a specific past conversation,
            # follow the SDK contract directly: persist the SDK session id and
            # pass it back via `resume` on the next call.
            options.resume = resume_session

        # Wire safety and audit hooks with SDK signatures
        from autonomous_agent_builder.agents.hooks import (
            audit_log_tool_use,
            audit_subagent_stop,
            enforce_completion_evidence,
            enforce_workspace_boundary,
            keep_tool_stream_open,
            make_enforce_claude_md_block_ownership,
            session_start_context_policy,
            trim_tool_output_for_context,
            validate_bash_argv,
        )

        claude_md_block_hook = make_enforce_claude_md_block_ownership(agent_def.name)

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
            "SessionStart": [
                HookMatcher(
                    matcher=".*",
                    hooks=[session_start_context_policy],
                    timeout=30.0,
                ),
            ],
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
                    matcher="Edit|Write",
                    hooks=[claude_md_block_hook],
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
                HookMatcher(
                    matcher="Bash|Read|mcp__workspace__run_tests|mcp__workspace__run_linter",
                    hooks=[trim_tool_output_for_context],
                    timeout=30.0,
                ),
            ],
            "SubagentStop": [
                HookMatcher(
                    matcher=".*",
                    hooks=[audit_subagent_stop],
                    timeout=30.0,
                ),
            ],
            "Stop": [
                HookMatcher(
                    matcher=".*",
                    hooks=[enforce_completion_evidence],
                    timeout=30.0,
                ),
            ],
        }

        async def _prompt_stream():
            yield {
                "type": "user",
                "session_id": resume_session or "",
                "message": {"role": "user", "content": prompt},
                "parent_tool_use_id": None,
            }

        rate_limit_info_captured = None
        # Running totals for G1 per-turn StreamEvent usage (reset per _execute_query call)
        _live_input = 0
        _live_cached = 0
        _live_output = 0

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(_prompt_stream())
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage) and message.subtype == "init":
                        session_id = message.data.get("session_id")

                    elif isinstance(message, RateLimitEvent):
                        if message.rate_limit_info.status == "rejected":
                            rate_limit_info_captured = message.rate_limit_info
                            log.warning(
                                "sdk_rate_limit_rejected",
                                rate_limit_type=message.rate_limit_info.rate_limit_type,
                                resets_at=message.rate_limit_info.resets_at,
                                utilization=message.rate_limit_info.utilization,
                            )

                    elif isinstance(message, StreamEvent):
                        ev = message.event or {}
                        ev_type = ev.get("type", "")
                        if ev_type == "message_start":
                            u = ev.get("message", {}).get("usage", {})
                            _live_input += u.get("input_tokens", 0)
                            _live_cached += u.get("cache_read_input_tokens", 0) + u.get(
                                "cache_creation_input_tokens", 0
                            )
                        elif ev_type == "message_delta":
                            u = ev.get("usage", {})
                            _live_output += u.get("output_tokens", 0)
                            if on_stream_usage:
                                await on_stream_usage(_live_input, _live_cached, _live_output)

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
                        base_result_kwargs: dict[str, Any] = dict(
                            session_id=getattr(message, "session_id", None) or session_id,
                            cost_usd=getattr(message, "total_cost_usd", 0.0),
                            tokens_input=usage.get("input_tokens", 0),
                            tokens_output=usage.get("output_tokens", 0),
                            tokens_cached=usage.get("cache_read_input_tokens", 0),
                            num_turns=getattr(message, "num_turns", 0),
                            duration_ms=getattr(message, "duration_ms", 0),
                            output_text=output_text,
                            confidence=confidence,
                            diff_summary=diff_summary,
                            observability={
                                **observability.summary,
                                "runtime_policy": runtime_policy.to_payload(),
                            },
                        )
                        if rate_limit_info_captured is not None:
                            # SDK-sourced rate limit data supersedes text-parsed metadata
                            info = rate_limit_info_captured
                            resets_at_iso = (
                                datetime.fromtimestamp(info.resets_at / 1000, UTC).isoformat()
                                if info.resets_at
                                else None
                            )
                            return RunResult(
                                **base_result_kwargs,
                                stop_reason="provider_limit",
                                provider_limit={
                                    "code": "provider_limit",
                                    "reason": "rate_limit_event",
                                    "reset_at": resets_at_iso,
                                    "rate_limit_type": info.rate_limit_type,
                                    "utilization": info.utilization,
                                    "source": "claude_agent_sdk",
                                },
                            )
                        return RunResult(**base_result_kwargs, stop_reason=stop_reason)

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
                if is_provider_limit_text(str(e)):
                    reset_at, reset_hint = parse_reset_hint(str(e))
                    return RunResult(
                        output_text=str(e),
                        stop_reason="provider_limit",
                        provider_limit={
                            "code": "provider_limit",
                            "reason": "process_error",
                            "reset_at": reset_at.isoformat() if reset_at else None,
                            "reset_hint": reset_hint,
                            "source": "claude_agent_sdk",
                        },
                        observability={
                            **observability.summary,
                            "runtime_policy": runtime_policy.to_payload(),
                        },
                    )
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
            observability={
                **observability.summary,
                "runtime_policy": runtime_policy.to_payload(),
            },
        )

    def _build_mcp_servers(
        self,
        workspace_path: str,
        allowed_tool_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create default in-process SDK MCP servers for builder and workspace tools."""
        from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

        return build_default_mcp_servers(
            workspace_path=workspace_path,
            project_root=os.environ.get("AAB_PROJECT_ROOT"),
            allowed_tool_names=allowed_tool_names,
        )


class ConfigurationError(Exception):
    """Non-retryable configuration error."""


class TransientError(Exception):
    """Retryable transient error."""
