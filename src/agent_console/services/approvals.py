"""Pause the agent loop until a human approves a tool.

Keyed by conversation + tool-call id. Optional Redis args match app wiring;
payloads are plain JSON only so a later Redis backend is a storage swap.
At apply time, re-parse the tip and revalidate — never trust objects from the
payload beyond the declared ops/ids/hashes/diff text.

Payloads are single-use: `take_payload` is an atomic get-and-delete (dict pop
locally; Redis GETDEL when available). Pending payloads also expire by TTL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis

__all__ = ["ApprovalBroker"]

logger = logging.getLogger(__name__)

# Default wall-clock TTL when wait() does not pass a tighter timeout.
_DEFAULT_PAYLOAD_TTL_SECONDS = 600.0


def _as_json_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip through JSON so only plain data is retained."""
    try:
        return json.loads(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "approval payload must be JSON-serializable "
            f"(ops, file id, generation, hashes, diff text): {exc}"
        ) from exc


class ApprovalBroker:
    def __init__(
        self, redis: Redis | None = None, prefix: str = "agentconsole:"
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._pending: dict[str, asyncio.Future[bool]] = {}
        # key -> (payload, expires_at monotonic)
        self._payloads: dict[str, tuple[dict[str, Any], float]] = {}
        self._payload_lock = asyncio.Lock()

    @staticmethod
    def _key(conversation_id: str, call_id: str) -> str:
        return f"{conversation_id}:{call_id}"

    def _payload_redis_key(self, conversation_id: str, call_id: str) -> str:
        return f"{self._prefix}approval:payload:{conversation_id}:{call_id}"

    def put_payload(
        self,
        conversation_id: str,
        call_id: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Store a JSON-safe approval payload with a TTL."""
        clean = _as_json_dict(payload)
        ttl = (
            _DEFAULT_PAYLOAD_TTL_SECONDS
            if ttl_seconds is None
            else max(0.001, float(ttl_seconds))
        )
        expires = time.monotonic() + ttl
        self._payloads[self._key(conversation_id, call_id)] = (clean, expires)
        return clean

    def get_payload(
        self, conversation_id: str, call_id: str
    ) -> dict[str, Any] | None:
        """Peek without consuming. Expired entries are dropped."""
        key = self._key(conversation_id, call_id)
        item = self._payloads.get(key)
        if item is None:
            return None
        payload, expires = item
        if time.monotonic() >= expires:
            self._payloads.pop(key, None)
            return None
        return payload

    def take_payload(
        self, conversation_id: str, call_id: str
    ) -> dict[str, Any] | None:
        """Atomic get-and-delete. Second call returns None (single-use)."""
        key = self._key(conversation_id, call_id)
        item = self._payloads.pop(key, None)
        if item is None:
            return None
        payload, expires = item
        if time.monotonic() >= expires:
            return None
        return payload

    async def take_payload_async(
        self, conversation_id: str, call_id: str
    ) -> dict[str, Any] | None:
        """Async take: Redis GETDEL when configured, else locked in-memory pop."""
        if self._redis is not None:
            rkey = self._payload_redis_key(conversation_id, call_id)
            try:
                raw = await self._redis.getdel(rkey)
            except Exception as exc:  # noqa: BLE001
                logger.warning("approval payload redis GETDEL failed: %s", exc)
                raw = None
            # Always drop the local mirror so a retry cannot re-apply.
            self.take_payload(conversation_id, call_id)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) else None

        async with self._payload_lock:
            return self.take_payload(conversation_id, call_id)

    async def wait(
        self,
        conversation_id: str,
        call_id: str,
        *,
        timeout: float,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Block until allow/deny, or time out as deny.

        When `payload` is provided it must already be JSON-serializable
        (operations, source_file_id, generation, hashes, diff_text).
        """
        key = self._key(conversation_id, call_id)
        if payload is not None:
            ttl = max(60.0, float(timeout) + 60.0)
            clean = self.put_payload(
                conversation_id, call_id, payload, ttl_seconds=ttl
            )
            if self._redis is not None:
                try:
                    await self._redis.setex(
                        self._payload_redis_key(conversation_id, call_id),
                        int(ttl),
                        json.dumps(clean),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("approval payload redis set failed: %s", exc)

        existing = self._pending.get(key)
        if existing is not None and not existing.done():
            future = existing
        else:
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending[key] = future

        try:
            allowed = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except TimeoutError:
            if not future.done():
                future.set_result(False)
            await self.take_payload_async(conversation_id, call_id)
            return False
        finally:
            if self._pending.get(key) is future:
                self._pending.pop(key, None)

        if not allowed:
            await self.take_payload_async(conversation_id, call_id)
        return allowed

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
