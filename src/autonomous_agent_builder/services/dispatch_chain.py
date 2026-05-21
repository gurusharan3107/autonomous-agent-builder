"""Shared dispatch follow-up chain state for API and embedded route adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from autonomous_agent_builder.db.models import Task, TaskStatus, set_task_status, utcnow

MAX_DISPATCH_FOLLOWUP_STEPS = 100


@dataclass
class DispatchChainState:
    seen_states: set[tuple[str, str, int]] = field(default_factory=set)


DispatchStep = Callable[[str, DispatchChainState], Awaitable[str | None]]
DispatchBlocker = Callable[[str, str], Awaitable[None]]


async def run_dispatch_followup_chain(
    task_id: str,
    *,
    run_step: DispatchStep,
    block_chain: DispatchBlocker,
) -> None:
    state = DispatchChainState()
    followup_task_id: str | None = task_id
    steps = 0
    while followup_task_id:
        if steps >= MAX_DISPATCH_FOLLOWUP_STEPS:
            await block_chain(
                followup_task_id,
                (
                    "Dispatch follow-up chain exceeded "
                    f"{MAX_DISPATCH_FOLLOWUP_STEPS} steps without reaching idle."
                ),
            )
            return
        steps += 1
        followup_task_id = await run_step(followup_task_id, state)


def mark_repeated_dispatch_state(task: Task, state: DispatchChainState) -> str | None:
    # Include retry_count in the state key so gate-failure retries (which
    # legitimately revisit IMPLEMENTATION) are not flagged as cycles.
    retry = int(getattr(task, "retry_count", 0) or 0)
    current_state = (task.id, _status_value(task.status), retry)
    if current_state not in state.seen_states:
        state.seen_states.add(current_state)
        return None

    reason = (
        "Dispatch follow-up cycle detected for task "
        f"{task.id} at status {current_state[1]} (retry {current_state[2]})."
    )
    set_task_status(task, TaskStatus.BLOCKED)
    task.blocked_reason = reason
    task.blocked_at = utcnow()
    return reason


def _status_value(status: object) -> str:
    return status.value if hasattr(status, "value") else str(status)
