"""Pause the agent loop until a human approves a tool.

Keyed by conversation + tool-call id. Uses Redis when available so Allow/Deny
works across pods; falls back to in-process futures for single-node / no-Redis.
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

__all__ = ["ApprovalBroker"]

logger = logging.getLogger(__name__)


class ApprovalBroker:
    def __init__(
        self, redis: Redis | None = None, prefix: str = "agentconsole:"
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._pending: dict[str, asyncio.Future[bool]] = {}

    @staticmethod
    def _key(conversation_id: str, call_id: str) -> str:
        return f"{conversation_id}:{call_id}"

    def _queue_key(self, conversation_id: str, call_id: str) -> str:
        return f"{self._prefix}approval:q:{conversation_id}:{call_id}"

    def _index_key(self, conversation_id: str) -> str:
        return f"{self._prefix}approval:index:{conversation_id}"

    async def wait(
        self, conversation_id: str, call_id: str, *, timeout: float
    ) -> bool:
        """Block until allow/deny, or time out as deny."""
        if self._redis is None:
            return await self._wait_local(conversation_id, call_id, timeout=timeout)
        return await self._wait_redis(conversation_id, call_id, timeout=timeout)

    async def _wait_local(
        self, conversation_id: str, call_id: str, *, timeout: float
    ) -> bool:
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

    async def _wait_redis(
        self, conversation_id: str, call_id: str, *, timeout: float
    ) -> bool:
        assert self._redis is not None
        queue = self._queue_key(conversation_id, call_id)
        index = self._index_key(conversation_id)
        ttl = max(60, int(timeout) + 60)
        try:
            await self._redis.sadd(index, call_id)
            await self._redis.expire(index, ttl)
            # blpop timeout is integer seconds; clamp to at least 1.
            item = await self._redis.blpop(queue, timeout=max(1, int(timeout)))
            if item is None:
                return False
            _, value = item
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return value == "1"
        except Exception as exc:  # noqa: BLE001
            logger.warning("approval wait redis failed: %s; denying", exc)
            return False
        finally:
            try:
                await self._redis.srem(index, call_id)
                await self._redis.delete(queue)
            except Exception as exc:  # noqa: BLE001
                logger.warning("approval cleanup failed: %s", exc)

    async def resolve(
        self, conversation_id: str, call_id: str, allowed: bool
    ) -> bool:
        """Return True if a waiter was notified (or was registered to wait)."""
        if self._redis is None:
            return self._resolve_local(conversation_id, call_id, allowed)
        return await self._resolve_redis(conversation_id, call_id, allowed)

    def _resolve_local(
        self, conversation_id: str, call_id: str, allowed: bool
    ) -> bool:
        future = self._pending.get(self._key(conversation_id, call_id))
        if future is None or future.done():
            return False
        future.set_result(allowed)
        return True

    async def _resolve_redis(
        self, conversation_id: str, call_id: str, allowed: bool
    ) -> bool:
        assert self._redis is not None
        queue = self._queue_key(conversation_id, call_id)
        index = self._index_key(conversation_id)
        try:
            waiting = await self._redis.sismember(index, call_id)
            await self._redis.lpush(queue, "1" if allowed else "0")
            await self._redis.expire(queue, 60)
            return bool(waiting)
        except Exception as exc:  # noqa: BLE001
            logger.warning("approval resolve redis failed: %s", exc)
            return False

    async def cancel_conversation(self, conversation_id: str) -> None:
        """Deny every open gate for this chat (client abort / navigate away)."""
        if self._redis is None:
            self._cancel_local(conversation_id)
            return
        await self._cancel_redis(conversation_id)

    def _cancel_local(self, conversation_id: str) -> None:
        prefix = f"{conversation_id}:"
        for key, future in list(self._pending.items()):
            if key.startswith(prefix) and not future.done():
                future.set_result(False)

    async def _cancel_redis(self, conversation_id: str) -> None:
        assert self._redis is not None
        index = self._index_key(conversation_id)
        try:
            members = await self._redis.smembers(index)
        except Exception as exc:  # noqa: BLE001
            logger.warning("approval cancel list failed: %s", exc)
            return
        for raw in members:
            call_id = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            await self._resolve_redis(conversation_id, call_id, False)
