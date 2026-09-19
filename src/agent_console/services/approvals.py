"""Pause the agent loop until a human approves a tool.

Keyed by conversation + tool-call id. Optional Redis args match app wiring;
payloads are plain JSON only so a later Redis backend is a storage swap.
At apply time, re-parse the tip and revalidate — never trust objects from the
payload beyond the declared ops/ids/hashes/diff text.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis

__all__ = ["ApprovalBroker"]

logger = logging.getLogger(__name__)


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
        # Plain JSON dicts only — never lxml / Element / Document handles.
        self._payloads: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(conversation_id: str, call_id: str) -> str:
        return f"{conversation_id}:{call_id}"

    def _payload_redis_key(self, conversation_id: str, call_id: str) -> str:
        return f"{self._prefix}approval:payload:{conversation_id}:{call_id}"

    def put_payload(
        self, conversation_id: str, call_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Store a JSON-safe approval payload (sync; Redis write is best-effort)."""
        clean = _as_json_dict(payload)
        self._payloads[self._key(conversation_id, call_id)] = clean
        return clean

    def get_payload(
        self, conversation_id: str, call_id: str
    ) -> dict[str, Any] | None:
        return self._payloads.get(self._key(conversation_id, call_id))

    def take_payload(
        self, conversation_id: str, call_id: str
    ) -> dict[str, Any] | None:
        return self._payloads.pop(self._key(conversation_id, call_id), None)

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
            clean = self.put_payload(conversation_id, call_id, payload)
            if self._redis is not None:
                ttl = max(60, int(timeout) + 60)
                try:
                    await self._redis.setex(
                        self._payload_redis_key(conversation_id, call_id),
                        ttl,
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
            self.take_payload(conversation_id, call_id)
            if self._redis is not None:
                try:
                    await self._redis.delete(
                        self._payload_redis_key(conversation_id, call_id)
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("approval payload redis delete failed: %s", exc)
            return False
        finally:
            if self._pending.get(key) is future:
                self._pending.pop(key, None)

        if not allowed:
            self.take_payload(conversation_id, call_id)
            if self._redis is not None:
                try:
                    await self._redis.delete(
                        self._payload_redis_key(conversation_id, call_id)
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("approval payload redis delete failed: %s", exc)
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
                # Payload cleanup happens in wait() when it observes deny.
