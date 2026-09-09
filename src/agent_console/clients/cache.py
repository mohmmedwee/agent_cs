"""Redis-backed cache for expensive outbound calls.

This Redis instance is shared with other applications, so every key is
prefixed and the cache never enumerates or clears the keyspace. A cache miss
is always survivable: if Redis is down, callers fall through to the real call
rather than failing.
"""

import hashlib
import logging

from redis.asyncio import Redis

__all__ = ["ResponseCache"]

logger = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, redis: Redis | None, prefix: str) -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, namespace: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        return f"{self._prefix}{namespace}:{digest}"

    async def get(self, namespace: str, value: str) -> str | None:
        if self._redis is None:
            return None
        try:
            cached = await self._redis.get(self._key(namespace, value))
        except Exception as exc:  # noqa: BLE001 - cache must never break a request
            logger.warning("cache read failed: %s", exc)
            return None
        return cached.decode("utf-8") if isinstance(cached, bytes) else cached

    async def set(self, namespace: str, value: str, payload: str, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(self._key(namespace, value), payload, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache write failed: %s", exc)
