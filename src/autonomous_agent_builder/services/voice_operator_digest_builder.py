"""Voice digest string builder extracted from AgentOperatorService.voice_digest."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.embedded.server.board_scope import board_status_projection_lines
from autonomous_agent_builder.services.voice_operator_interaction import (
    provider_limit_reason_is_current as _provider_limit_reason_is_current,
)


def build_voice_digest(
    *,
    active_run: bool,
    pending_count: int,
    board_status: dict[str, Any] | None = None,
    prefer_latest_summary: bool = False,
    latest_voice_summary: str = "",
    status_prompt: str = "",
) -> str:
    board_status = board_status or {}
    blocked_count = int(board_status.get("blocked_count") or 0)
    queued_count = int(board_status.get("queued_count") or 0)
    active_count = int(board_status.get("active_count") or 0)
    review_count = int(board_status.get("review_count") or 0)
    done_count = int(board_status.get("done_count") or 0)
    scope = str(board_status.get("scope") or "")
    current_sprint_label = str(board_status.get("current_sprint_label") or "").strip()
    current_sprint_phase = str(board_status.get("current_sprint_phase") or "").strip()
    backlog_status = dict(board_status.get("backlog_status") or {})
    backlog_open_count = int(backlog_status.get("open_count") or 0)
    backlog_feature_count = int(backlog_status.get("feature_count") or 0)
    backlog_done_count = int(backlog_status.get("done_count") or 0)
    blocked_tasks = list(board_status.get("blocked_tasks") or [])
    provider_limit_runs = list(board_status.get("provider_limit_runs") or [])
    scoped_label = (
        f"Current sprint `{current_sprint_label}` "
        if scope == "current_sprint" and current_sprint_label
        else "Builder "
    )
    status_prompt = str(status_prompt or "").strip()
    detailed_status_lines = board_status_projection_lines(
        scope=scope,
        current_sprint_label=current_sprint_label,
        current_sprint_phase=current_sprint_phase,
        queued_count=queued_count,
        active_count=active_count,
        review_count=review_count,
        done_count=done_count,
        blocked_count=blocked_count,
        backlog_feature_count=backlog_feature_count,
        backlog_done_count=backlog_done_count,
        backlog_open_count=backlog_open_count,
    )

    def detailed_status(message: str = "") -> str:
        prefix = " ".join(detailed_status_lines).strip()
        if message:
            prefix = f"{prefix} {message}".strip()
        if pending_count:
            return f"{prefix} Builder needs {pending_count} operator decision or answer."
        return f"{prefix} No operator decision is pending."

    if blocked_count:
        first = blocked_tasks[0] if blocked_tasks else {}
        title = str(first.get("title") or "a board task")
        status = str(first.get("status") or "blocked").replace("_", " ")
        reason = str(first.get("reason") or "").strip()
        all_reasons = " ".join(
            str(first.get(key) or "")
            for key in ("reason", "blocked_reason", "capability_limit_reason")
        )
        detail = f": {reason}" if reason else "."
        if "provider_limit" in all_reasons or "provider limit" in all_reasons.lower():
            if not _provider_limit_reason_is_current(all_reasons):
                if status_prompt:
                    return detailed_status(
                        f"`{title}` has stale provider-limit evidence and is still {status}{detail} "
                        "Treat this as recovery or retry work, not a current Claude rate limit."
                    )
                return (
                    f"{scoped_label}still has a stale provider-limit Board block. `{title}` "
                    f"is {status}{detail} The reset time has passed, so this is a "
                    "recovery or retry state, not evidence of a current Claude rate limit."
                )
            if status_prompt:
                return detailed_status(
                    f"`{title}` hit a provider limit and is currently {status}{detail}"
                )
            return f"{scoped_label}hit a provider limit. `{title}` is {status}{detail}"
        if status_prompt:
            return detailed_status(f"`{title}` is {status}{detail}")
        return (
            f"{scoped_label}has {blocked_count} blocked board task(s). "
            f"`{title}` is {status}{detail}"
        )
    if provider_limit_runs:
        latest = provider_limit_runs[0]
        title = str(latest.get("task_title") or "a Board task")
        task_status = str(latest.get("task_status") or "unknown").replace("_", " ")
        agent_name = str(latest.get("agent_name") or "the SDK runner")
        model = str(latest.get("model") or "").strip()
        model_text = f" on {model}" if model else ""
        backlog_prefix = ""
        if backlog_feature_count and backlog_open_count == 0:
            backlog_prefix = f"Backlog features are complete ({backlog_done_count}/{backlog_feature_count} done). "
        queued_text = (
            f"{scoped_label}still has {queued_count} queued board task(s), including `{title}`. "
            if queued_count
            else ""
        )
        if not bool(latest.get("provider_limit_current")):
            if status_prompt:
                return detailed_status(
                    f"{queued_text}`{title}` has prior provider-limit evidence, but it is not current. "
                    f"The Board task is still {task_status}; treat this as recovery or retry work, not a live Claude rate limit."
                )
            return (
                f"{backlog_prefix}{queued_text}"
                f"{scoped_label}has prior provider-limit evidence for `{title}`, but it is not "
                f"current. The Board task is still {task_status}; treat this as recovery or retry work, not a live "
                "Claude rate limit."
            )
        if status_prompt:
            return detailed_status(
                f"{queued_text}`{title}` hit a provider limit recently. "
                f"The latest `{agent_name}` run{model_text} stopped with provider_limit; "
                f"the Board task is currently {task_status}."
            )
        return (
            f"{backlog_prefix}{queued_text}"
            f"{scoped_label}hit a provider limit recently for `{title}`. "
            f"The latest `{agent_name}` run{model_text} stopped with provider_limit; "
            f"the Board task is currently {task_status}."
        )
    if pending_count:
        if status_prompt:
            return detailed_status()
        return f"Builder needs {pending_count} operator decision or answer."
    if active_run:
        if status_prompt:
            return detailed_status("Builder is actively working.")
        return "Builder is actively working. No operator decision is pending."
    if active_count:
        if status_prompt:
            return detailed_status(f"{scoped_label}has {active_count} active board task(s).")
        return (
            f"{scoped_label}has {active_count} active board task(s). "
            "No operator decision is pending."
        )
    if queued_count:
        if status_prompt:
            return detailed_status(
                f"{scoped_label}still has {queued_count} queued board task(s)."
            )
        if backlog_feature_count and backlog_open_count == 0:
            return (
                f"Backlog features are complete ({backlog_done_count}/{backlog_feature_count} done). "
                f"{scoped_label}still has {queued_count} queued board task(s). "
                "No operator decision is pending."
            )
        return (
            f"{scoped_label}has {queued_count} queued board task(s). "
            "No operator decision is pending."
        )
    if status_prompt:
        return detailed_status()
    if scope == "current_sprint" and current_sprint_label and current_sprint_phase == "shipped":
        return f"Current sprint `{current_sprint_label}` is shipped. No operator decision is pending."
    if prefer_latest_summary and latest_voice_summary:
        return f"Builder finished: {latest_voice_summary}"
    if latest_voice_summary:
        return f"Builder is idle. Last Agent result: {latest_voice_summary}"
    return "Builder is idle. No operator decision is pending."
