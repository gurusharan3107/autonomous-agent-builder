"""Shared chat session runtime state for interactive embedded agent sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

StreamQueue = asyncio.Queue[dict[str, Any]]


class ChatSessionHub:
    """Coordinate per-session SSE subscribers, active runs, and pending answers."""

    def __init__(self) -> None:
        self._session_clients: dict[str, set[StreamQueue]] = {}
        self._pending_answers: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
        self._run_tasks: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()

    async def register_session(self, session_id: str) -> StreamQueue:
        queue: StreamQueue = asyncio.Queue(maxsize=50)
        async with self._lock:
            self._session_clients.setdefault(session_id, set()).add(queue)
        return queue

    async def unregister_session(self, session_id: str, queue: StreamQueue) -> None:
        async with self._lock:
            clients = self._session_clients.get(session_id)
            if not clients:
                return
            clients.discard(queue)
            if not clients:
                self._session_clients.pop(session_id, None)

    async def publish(self, session_id: str, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            clients = set(self._session_clients.get(session_id, set()))
        event = {"event": "event", "data": dict(payload)}
        for queue in clients:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue

    async def create_pending_answer(
        self,
        session_id: str,
        event_id: str,
    ) -> asyncio.Future[dict[str, Any]]:
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        async with self._lock:
            self._pending_answers[event_id] = (session_id, future)
        return future

    async def resolve_pending_answer(self, event_id: str, payload: dict[str, Any]) -> bool:
        async with self._lock:
            entry = self._pending_answers.pop(event_id, None)
        if entry is None:
            return False
        _, future = entry
        if not future.done():
            future.set_result(payload)
        return True

    async def has_pending_answer(self, event_id: str) -> bool:
        async with self._lock:
            return event_id in self._pending_answers

    async def attach_run(self, session_id: str, task: asyncio.Task[Any]) -> bool:
        async with self._lock:
            current = self._run_tasks.get(session_id)
            if current is not None and not current.done():
                return False
            self._run_tasks[session_id] = task

        def _cleanup(completed: asyncio.Task[Any]) -> None:
            async def _drop() -> None:
                async with self._lock:
                    if self._run_tasks.get(session_id) is completed:
                        self._run_tasks.pop(session_id, None)

            asyncio.create_task(_drop())

        task.add_done_callback(_cleanup)
        return True

    async def has_active_run(self, session_id: str) -> bool:
        async with self._lock:
            task = self._run_tasks.get(session_id)
            return task is not None and not task.done()

    async def snapshot_active_session_ids(self) -> list[str]:
        async with self._lock:
            return [
                session_id
                for session_id, task in self._run_tasks.items()
                if task is not None and not task.done()
            ]

    async def pending_answer_count(self) -> int:
        async with self._lock:
            return sum(1 for _event_id, (_session_id, future) in self._pending_answers.items() if not future.done())

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._run_tasks.values())
            pending = list(self._pending_answers.values())
            self._run_tasks.clear()
            self._pending_answers.clear()
            self._session_clients.clear()

        for task in tasks:
            task.cancel()
        for _session_id, future in pending:
            if not future.done():
                future.cancel()
