"""Shared chat session runtime state for interactive embedded agent sessions."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Mapping
from typing import Any, ClassVar

StreamQueue = asyncio.Queue[dict[str, Any]]


class ChatSessionHub:
    """Coordinate per-session SSE subscribers, active runs, and pending answers."""

    _instances: ClassVar[weakref.WeakSet[ChatSessionHub]] = weakref.WeakSet()

    def __init__(self) -> None:
        self._session_clients: dict[str, set[StreamQueue]] = {}
        self._pending_answers: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
        self._run_tasks: dict[str, asyncio.Task[Any] | None] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._instances.add(self)

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
            if self._closed:
                return False
            current = self._run_tasks.get(session_id)
            if current is None and session_id in self._run_tasks:
                return False
            if current is not None and not current.done():
                return False
            self._run_tasks[session_id] = task

        def _cleanup(completed: asyncio.Task[Any]) -> None:
            if self._closed:
                return

            async def _drop() -> None:
                async with self._lock:
                    if self._run_tasks.get(session_id) is completed:
                        self._run_tasks.pop(session_id, None)

            asyncio.create_task(_drop())

        task.add_done_callback(_cleanup)
        return True

    async def reserve_run(self, session_id: str) -> bool:
        async with self._lock:
            if self._closed:
                return False
            current = self._run_tasks.get(session_id)
            if current is None and session_id in self._run_tasks:
                return False
            if current is not None and not current.done():
                return False
            self._run_tasks[session_id] = None
            return True

    async def attach_reserved_run(self, session_id: str, task: asyncio.Task[Any]) -> bool:
        async with self._lock:
            if self._closed or session_id not in self._run_tasks:
                return False
            current = self._run_tasks.get(session_id)
            if current is not None and not current.done():
                return False
            self._run_tasks[session_id] = task

        def _cleanup(completed: asyncio.Task[Any]) -> None:
            if self._closed:
                return

            async def _drop() -> None:
                async with self._lock:
                    if self._run_tasks.get(session_id) is completed:
                        self._run_tasks.pop(session_id, None)

            asyncio.create_task(_drop())

        task.add_done_callback(_cleanup)
        return True

    async def release_run(self, session_id: str) -> None:
        async with self._lock:
            self._run_tasks.pop(session_id, None)

    async def has_active_run(self, session_id: str) -> bool:
        async with self._lock:
            task = self._run_tasks.get(session_id)
            return (task is None and session_id in self._run_tasks) or (
                task is not None and not task.done()
            )

    async def snapshot_active_session_ids(self) -> list[str]:
        async with self._lock:
            return [
                session_id
                for session_id, task in self._run_tasks.items()
                if task is None or not task.done()
            ]

    def has_active_subscribers(self, session_id: str) -> bool:
        """Return True if at least one SSE queue is still registered for session_id.

        Synchronous (no lock) — safe to call from an asyncio ``finally`` block
        after ``unregister_session`` has already run under the lock; by the time
        this is called the state is stable for this coroutine step.
        """
        clients = self._session_clients.get(session_id)
        return bool(clients)

    async def cancel_session_pending_answers(self, session_id: str) -> int:
        """Cancel every pending-answer future belonging to session_id.

        Called when the last SSE subscriber for a session disconnects (IMP-040)
        so that awaited ``create_pending_answer`` futures (AskUserQuestion /
        approval cards) unblock with CancelledError instead of pinning the
        runtime session forever.

        Returns the number of futures cancelled.
        """
        to_cancel: list[asyncio.Future[dict[str, Any]]] = []
        async with self._lock:
            stale_keys = [
                eid for eid, (sid, _) in self._pending_answers.items() if sid == session_id
            ]
            for eid in stale_keys:
                _, future = self._pending_answers.pop(eid)
                to_cancel.append(future)
        for future in to_cancel:
            if not future.done():
                future.cancel()
        return len(to_cancel)

    async def pending_answer_count(self) -> int:
        async with self._lock:
            return sum(
                1
                for _event_id, (_session_id, future) in self._pending_answers.items()
                if not future.done()
            )

    async def shutdown(self) -> None:
        async with self._lock:
            self._closed = True
            tasks = [task for task in self._run_tasks.values() if task is not None]
            pending = list(self._pending_answers.values())
            self._run_tasks.clear()
            self._pending_answers.clear()
            self._session_clients.clear()

        for task in tasks:
            task.cancel()
        for _session_id, future in pending:
            if not future.done():
                future.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def shutdown_all(cls) -> None:
        """Cancel active chat runs across app instances in this process."""

        hubs = list(cls._instances)
        if hubs:
            await asyncio.gather(*(hub.shutdown() for hub in hubs), return_exceptions=True)
