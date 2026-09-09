"""Track in-flight chat runs so a client disconnect does not cancel the agent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

__all__ = ["ChatJobBroker"]

logger = logging.getLogger(__name__)


class ChatJobBroker:
    """One background producer task per conversation."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def register(
        self,
        conversation_id: str,
        *,
        task: asyncio.Task[Any],
        cancel: asyncio.Event,
    ) -> None:
        previous = self._jobs.pop(conversation_id, None)
        if previous is not None:
            previous["cancel"].set()
            previous_task: asyncio.Task[Any] = previous["task"]
            if not previous_task.done():
                previous_task.cancel()
        self._jobs[conversation_id] = {"task": task, "cancel": cancel}

        def _clear(done: asyncio.Task[Any]) -> None:
            current = self._jobs.get(conversation_id)
            if current and current["task"] is done:
                self._jobs.pop(conversation_id, None)

        task.add_done_callback(_clear)

    def stop(self, conversation_id: str) -> bool:
        """Cancel a run. Returns True if one was active."""
        job = self._jobs.get(conversation_id)
        if job is None:
            return False
        job["cancel"].set()
        task: asyncio.Task[Any] = job["task"]
        if not task.done():
            task.cancel()
            logger.info("stopped background chat job %s", conversation_id)
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
