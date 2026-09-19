"""Track in-flight chat runs so a client disconnect does not cancel the agent.

Owner pod keeps the asyncio.Task locally. Event history + live fan-out also go
to Redis when available, so /watch and /active work from any replica. Without
Redis the broker stays single-process (dev / one-pod).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis

__all__ = ["ChatJobBroker"]

logger = logging.getLogger(__name__)

_TOMBSTONE_SECONDS = 5.0
_ACTIVE_TTL_SECONDS = 3600


@dataclass
class _Job:
    task: asyncio.Task[Any]
    cancel: asyncio.Event
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue[dict[str, Any] | None]] = field(
        default_factory=list
    )
    done: bool = False
    linger: asyncio.Task[Any] | None = None
    cancel_watch: asyncio.Task[Any] | None = None


class ChatJobBroker:
    """One background producer task per conversation, with fan-out for reconnect."""

    def __init__(
        self, redis: Redis | None = None, prefix: str = "agentconsole:"
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._jobs: dict[str, _Job] = {}
        self._pumps: dict[int, asyncio.Task[Any]] = {}

    def _meta_key(self, conversation_id: str) -> str:
        return f"{self._prefix}job:{conversation_id}:meta"

    def _events_key(self, conversation_id: str) -> str:
        return f"{self._prefix}job:{conversation_id}:events"

    def _seq_key(self, conversation_id: str) -> str:
        return f"{self._prefix}job:{conversation_id}:seq"

    def _cancel_key(self, conversation_id: str) -> str:
        return f"{self._prefix}job:{conversation_id}:cancel"

    def _channel(self, conversation_id: str) -> str:
        return f"{self._prefix}job:{conversation_id}:live"

    async def is_active(self, conversation_id: str) -> bool:
        job = self._jobs.get(conversation_id)
        if job is not None and not job.done:
            return True
        if self._redis is None:
            return False
        try:
            active = await self._redis.hget(self._meta_key(conversation_id), "active")
        except Exception as exc:  # noqa: BLE001
            logger.warning("job is_active redis failed: %s", exc)
            return False
        if isinstance(active, bytes):
            active = active.decode("utf-8")
        return active == "1"

    async def has_job(self, conversation_id: str) -> bool:
        """True while a run is live or still in its short done-tombstone window."""
        if conversation_id in self._jobs:
            return True
        if self._redis is None:
            return False
        try:
            return bool(await self._redis.exists(self._meta_key(conversation_id)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("job has_job redis failed: %s", exc)
            return False

    async def publish(
        self, conversation_id: str, event: dict[str, Any] | None
    ) -> None:
        """Push one event (or None sentinel) to history and every live subscriber."""
        job = self._jobs.get(conversation_id)
        if job is not None:
            if event is not None:
                job.events.append(event)
            else:
                job.done = True
            for queue in list(job.subscribers):
                queue.put_nowait(event)

        if self._redis is None:
            return
        try:
            await self._publish_redis(conversation_id, event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("job publish redis failed: %s", exc)

    async def _publish_redis(
        self, conversation_id: str, event: dict[str, Any] | None
    ) -> None:
        assert self._redis is not None
        events_key = self._events_key(conversation_id)
        meta_key = self._meta_key(conversation_id)
        seq_key = self._seq_key(conversation_id)
        channel = self._channel(conversation_id)

        seq = await self._redis.incr(seq_key)
        envelope = json.dumps(
            {"seq": seq, "event": event}, ensure_ascii=False
        )
        pipe = self._redis.pipeline()
        pipe.rpush(events_key, envelope)
        if event is not None:
            pipe.hset(meta_key, mapping={"active": "1", "done": "0"})
            ttl = _ACTIVE_TTL_SECONDS
        else:
            pipe.hset(meta_key, mapping={"active": "0", "done": "1"})
            ttl = int(_TOMBSTONE_SECONDS) + 1
        pipe.expire(events_key, ttl)
        pipe.expire(meta_key, ttl)
        pipe.expire(seq_key, ttl)
        await pipe.execute()
        await self._redis.publish(channel, envelope)

    async def subscribe(
        self, conversation_id: str
    ) -> tuple[asyncio.Queue[dict[str, Any] | None], list[dict[str, Any]]] | None:
        """Attach a listener. Returns (live queue, replayed events) or None if idle."""
        job = self._jobs.get(conversation_id)
        if job is not None:
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            replay = list(job.events)
            if job.done:
                queue.put_nowait(None)
                return queue, replay
            job.subscribers.append(queue)
            return queue, replay

        if self._redis is None:
            return None
        if not await self.has_job(conversation_id):
            return None
        return await self._subscribe_redis(conversation_id)

    async def _subscribe_redis(
        self, conversation_id: str
    ) -> tuple[asyncio.Queue[dict[str, Any] | None], list[dict[str, Any]]] | None:
        assert self._redis is not None
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        try:
            raw_events = await self._redis.lrange(
                self._events_key(conversation_id), 0, -1
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("job subscribe lrange failed: %s", exc)
            return None

        replay: list[dict[str, Any]] = []
        last_seq = 0
        saw_done = False
        for raw in raw_events:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            envelope = json.loads(text)
            last_seq = max(last_seq, int(envelope["seq"]))
            payload = envelope.get("event")
            if payload is None:
                saw_done = True
            else:
                replay.append(payload)

        if saw_done:
            queue.put_nowait(None)
            return queue, replay

        try:
            meta = await self._redis.hgetall(self._meta_key(conversation_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("job subscribe meta failed: %s", exc)
            return queue, replay

        done = _hget(meta, "done") == "1"
        if done:
            queue.put_nowait(None)
            return queue, replay

        pump = asyncio.create_task(
            self._redis_pump(conversation_id, queue, last_seq),
            name=f"chat-job-pump:{conversation_id}",
        )
        self._pumps[id(queue)] = pump
        return queue, replay

    async def _redis_pump(
        self,
        conversation_id: str,
        queue: asyncio.Queue[dict[str, Any] | None],
        last_seq: int,
    ) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        channel = self._channel(conversation_id)
        await pubsub.subscribe(channel)
        try:
            # Catch events published between LRANGE and SUBSCRIBE.
            raw_events = await self._redis.lrange(
                self._events_key(conversation_id), 0, -1
            )
            for raw in raw_events:
                text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                envelope = json.loads(text)
                seq = int(envelope["seq"])
                if seq <= last_seq:
                    continue
                last_seq = seq
                payload = envelope.get("event")
                await queue.put(payload)
                if payload is None:
                    return

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    if not await self.has_job(conversation_id):
                        await queue.put(None)
                        return
                    meta = await self._redis.hgetall(
                        self._meta_key(conversation_id)
                    )
                    if _hget(meta, "done") == "1":
                        await queue.put(None)
                        return
                    continue
                data = message.get("data")
                if data is None:
                    continue
                text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
                envelope = json.loads(text)
                seq = int(envelope["seq"])
                if seq <= last_seq:
                    continue
                last_seq = seq
                payload = envelope.get("event")
                await queue.put(payload)
                if payload is None:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("job redis pump failed: %s", exc)
            await queue.put(None)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def unsubscribe(
        self,
        conversation_id: str,
        queue: asyncio.Queue[dict[str, Any] | None],
    ) -> None:
        pump = self._pumps.pop(id(queue), None)
        if pump is not None and not pump.done():
            pump.cancel()
        job = self._jobs.get(conversation_id)
        if job is None:
            return
        try:
            job.subscribers.remove(queue)
        except ValueError:
            pass

    async def register(
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
            if previous.linger is not None and not previous.linger.done():
                previous.linger.cancel()
            if previous.cancel_watch is not None and not previous.cancel_watch.done():
                previous.cancel_watch.cancel()
            for queue in previous.subscribers:
                queue.put_nowait(None)
            if not previous.task.done():
                previous.task.cancel()

        job = _Job(task=task, cancel=cancel)
        self._jobs[conversation_id] = job

        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.delete(self._events_key(conversation_id))
                pipe.delete(self._seq_key(conversation_id))
                pipe.delete(self._cancel_key(conversation_id))
                pipe.hset(
                    self._meta_key(conversation_id),
                    mapping={"active": "1", "done": "0"},
                )
                pipe.expire(self._meta_key(conversation_id), _ACTIVE_TTL_SECONDS)
                await pipe.execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("job register redis failed: %s", exc)
            job.cancel_watch = asyncio.create_task(
                self._watch_remote_cancel(conversation_id, cancel, task),
                name=f"chat-job-cancel-watch:{conversation_id}",
            )

        def _clear(done: asyncio.Task[Any]) -> None:
            current = self._jobs.get(conversation_id)
            if current is None or current.task is not done:
                return
            current.done = True
            if current.cancel_watch is not None and not current.cancel_watch.done():
                current.cancel_watch.cancel()
            for queue in list(current.subscribers):
                queue.put_nowait(None)

            async def _drop_later() -> None:
                try:
                    await asyncio.sleep(_TOMBSTONE_SECONDS)
                except asyncio.CancelledError:
                    return
                still = self._jobs.get(conversation_id)
                if still is current:
                    self._jobs.pop(conversation_id, None)

            current.linger = asyncio.create_task(
                _drop_later(), name=f"chat-job-tombstone:{conversation_id}"
            )

        task.add_done_callback(_clear)

    async def _watch_remote_cancel(
        self,
        conversation_id: str,
        cancel: asyncio.Event,
        task: asyncio.Task[Any],
    ) -> None:
        assert self._redis is not None
        key = self._cancel_key(conversation_id)
        try:
            while not cancel.is_set() and not task.done():
                try:
                    if await self._redis.exists(key):
                        cancel.set()
                        if not task.done():
                            task.cancel()
                            logger.info(
                                "stopped background chat job %s (remote)",
                                conversation_id,
                            )
                        return
                except Exception as exc:  # noqa: BLE001
                    logger.warning("job cancel watch failed: %s", exc)
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            return

    async def stop(self, conversation_id: str) -> bool:
        """Cancel a run. Returns True if one was active locally or remotely."""
        found = False
        job = self._jobs.get(conversation_id)
        if job is not None:
            found = True
            job.cancel.set()
            job.done = True
            if not job.task.done():
                job.task.cancel()
                logger.info("stopped background chat job %s", conversation_id)
            for queue in list(job.subscribers):
                queue.put_nowait(None)

        if self._redis is not None:
            try:
                await self._redis.set(
                    self._cancel_key(conversation_id), "1", ex=60
                )
                # Signal remote watchers even if this pod is not the owner.
                if job is None:
                    active = await self.is_active(conversation_id)
                    found = found or active
                    if active:
                        await self._publish_redis(conversation_id, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("job stop redis failed: %s", exc)
        return found

    async def start(
        self,
        conversation_id: str,
        coro: Coroutine[Any, Any, None],
        cancel: asyncio.Event,
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=f"chat-job:{conversation_id}")
        await self.register(conversation_id, task=task, cancel=cancel)
        return task

    # Back-compat alias used by older call sites / tests.
    def spawn(
        self,
        conversation_id: str,
        coro: Coroutine[Any, Any, None],
        cancel: asyncio.Event,
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=f"chat-job:{conversation_id}")
        asyncio.create_task(
            self.register(conversation_id, task=task, cancel=cancel),
            name=f"chat-job-register:{conversation_id}",
        )
        return task


def _hget(meta: dict[Any, Any], field: str) -> str | None:
    for key, value in meta.items():
        name = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        if name == field:
            return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    return None
