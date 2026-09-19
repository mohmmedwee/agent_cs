"""Track in-flight chat runs so a client disconnect does not cancel the agent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ChatJobBroker"]

logger = logging.getLogger(__name__)


@dataclass
class _Job:
    task: asyncio.Task[Any]
    cancel: asyncio.Event
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue[dict[str, Any] | None]] = field(
        default_factory=list
    )
    done: bool = False


class ChatJobBroker:
    """One background producer task per conversation, with fan-out for reconnect."""

    def __init__(
        self, redis: object | None = None, prefix: str = "agentconsole:"
    ) -> None:
        # redis/prefix accepted for app wiring parity with multi-pod work;
        # this process still keeps jobs in memory.
        self._redis = redis
        self._prefix = prefix
        self._jobs: dict[str, _Job] = {}

    def is_active(self, conversation_id: str) -> bool:
        job = self._jobs.get(conversation_id)
        return job is not None and not job.done

    def publish(self, conversation_id: str, event: dict[str, Any] | None) -> None:
        """Push one event (or None sentinel) to history and every live subscriber."""
        job = self._jobs.get(conversation_id)
        if job is None:
            return
        if event is not None:
            job.events.append(event)
        else:
            job.done = True
        for queue in list(job.subscribers):
            queue.put_nowait(event)

    def subscribe(
        self, conversation_id: str
    ) -> tuple[asyncio.Queue[dict[str, Any] | None], list[dict[str, Any]]] | None:
        """Attach a listener. Returns (live queue, replayed events) or None if idle."""
        job = self._jobs.get(conversation_id)
        if job is None or job.done:
            return None
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        job.subscribers.append(queue)
        return queue, list(job.events)

    def unsubscribe(
        self,
        conversation_id: str,
        queue: asyncio.Queue[dict[str, Any] | None],
    ) -> None:
        job = self._jobs.get(conversation_id)
        if job is None:
            return
        try:
            job.subscribers.remove(queue)
        except ValueError:
            pass

    def register(
        self,
        conversation_id: str,
        *,
        task: asyncio.Task[Any],
        cancel: asyncio.Event,
    ) -> None:
        previous = self._jobs.pop(conversation_id, None)
        if previous is not None:
            previous.cancel.set()
            previous.done = True
            for queue in previous.subscribers:
                queue.put_nowait(None)
            if not previous.task.done():
                previous.task.cancel()
        self._jobs[conversation_id] = _Job(task=task, cancel=cancel)

        def _clear(done: asyncio.Task[Any]) -> None:
            current = self._jobs.get(conversation_id)
            if current and current.task is done:
                current.done = True
                for queue in list(current.subscribers):
                    queue.put_nowait(None)
                # Keep briefly so late watchers can see is_active flip; drop now.
                self._jobs.pop(conversation_id, None)

        task.add_done_callback(_clear)

    def stop(self, conversation_id: str) -> bool:
        """Cancel a run. Returns True if one was active."""
        job = self._jobs.get(conversation_id)
        if job is None:
            return False
        job.cancel.set()
        job.done = True
        if not job.task.done():
            job.task.cancel()
            logger.info("stopped background chat job %s", conversation_id)
        for queue in list(job.subscribers):
            queue.put_nowait(None)
        return True

    def spawn(
        self,
        conversation_id: str,
        coro: Coroutine[Any, Any, None],
        cancel: asyncio.Event,
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=f"chat-job:{conversation_id}")
        self.register(conversation_id, task=task, cancel=cancel)
        return task
