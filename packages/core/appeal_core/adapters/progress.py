"""ProgressBus adapters: Redis (stream per case, so reconnecting clients can resume with Last-Event-ID)
and an in-process fallback for tests / inprocess mode."""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

TERMINAL = {"READY", "FAILED", "NEEDS_HUMAN", "NEEDS_CATEGORY", "AWAITING_CONFIRMATION"}


class RedisProgressBus:
    """Each case has a Redis list of events (ids 1..n) plus a pub/sub channel for wake-ups."""

    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.url = url

    def _key(self, case_id: str) -> str:
        return f"progress:{case_id}"

    def publish(self, case_id: str, event: dict[str, Any]) -> None:
        n = self.r.rpush(self._key(case_id), "")  # reserve id
        event = {**event, "id": n}
        self.r.lset(self._key(case_id), n - 1, json.dumps(event))
        self.r.expire(self._key(case_id), 7 * 24 * 3600)
        self.r.publish(f"chan:{case_id}", str(n))

    def history(self, case_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        items = self.r.lrange(self._key(case_id), after_id, -1)
        return [json.loads(i) for i in items if i]

    async def subscribe(self, case_id: str, after_id: int = 0, heartbeat: float = 10.0) -> AsyncIterator[dict[str, Any]]:
        import redis.asyncio as aredis

        ar = aredis.Redis.from_url(self.url, decode_responses=True)
        ps = ar.pubsub()
        await ps.subscribe(f"chan:{case_id}")
        last = after_id
        try:
            while True:
                for ev in self.history(case_id, last):
                    last = ev["id"]
                    yield ev
                msg = await ps.get_message(ignore_subscribe_messages=True, timeout=heartbeat)
                if msg is None:
                    yield {"type": "heartbeat"}
        finally:
            await ps.unsubscribe()
            await ar.aclose()

    def delete(self, case_id: str) -> None:
        self.r.delete(self._key(case_id))

    def ping(self) -> bool:
        try:
            return bool(self.r.ping())
        except Exception:
            return False


class MemoryProgressBus:
    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.lock = threading.Lock()

    def publish(self, case_id: str, event: dict[str, Any]) -> None:
        with self.lock:
            ev = {**event, "id": len(self.events[case_id]) + 1}
            self.events[case_id].append(ev)

    def history(self, case_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.lock:
            return [e for e in self.events[case_id] if e["id"] > after_id]

    async def subscribe(self, case_id: str, after_id: int = 0, heartbeat: float = 10.0) -> AsyncIterator[dict[str, Any]]:
        last = after_id
        waited = 0.0
        while True:
            evs = self.history(case_id, last)
            for ev in evs:
                last = ev["id"]
                yield ev
            await asyncio.sleep(0.2)
            waited = 0.0 if evs else waited + 0.2
            if waited >= heartbeat:
                waited = 0.0
                yield {"type": "heartbeat"}

    def delete(self, case_id: str) -> None:
        with self.lock:
            self.events.pop(case_id, None)

    def ping(self) -> bool:
        return True
