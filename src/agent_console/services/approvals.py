"""In-process broker that pauses the agent loop until a human approves a tool.

Keyed by conversation + tool-call id so concurrent chats do not collide. Lives
on app.state for the process lifetime — fine for a single-node deploy; a
multi-worker setup would need Redis futures instead.
"""

from __future__ import annotations

import asyncio

__all__ = ["ApprovalBroker"]


class ApprovalBroker:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}

    @staticmethod
    def _key(conversation_id: str, call_id: str) -> str:
        return f"{conversation_id}:{call_id}"

    async def wait(
        self, conversation_id: str, call_id: str, *, timeout: float
    ) -> bool:
        """Block until allow/deny, or time out as deny."""
        key = self._key(conversation_id, call_id)
        existing = self._pending.get(key)
        if existing is not None and not existing.done():
            future = existing
        else:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending[key] = future

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except TimeoutError:
            if not future.done():
                future.set_result(False)
            return False
        finally:
            if self._pending.get(key) is future:
                self._pending.pop(key, None)

    def resolve(self, conversation_id: str, call_id: str, allowed: bool) -> bool:
        """Return True if a waiter was notified."""
        future = self._pending.get(self._key(conversation_id, call_id))
        if future is None or future.done():
            return False
        future.set_result(allowed)
        return True

    def cancel_conversation(self, conversation_id: str) -> None:
        """Deny every open gate for this chat (client abort / navigate away)."""
        prefix = f"{conversation_id}:"
        for key, future in list(self._pending.items()):
            if key.startswith(prefix) and not future.done():
                future.set_result(False)
