"""
In-process pub/sub for live alerts. Publishing is thread-safe: FastAPI runs
sync endpoints in a thread pool, while SSE subscribers live on an event loop,
so items are handed over with `call_soon_threadsafe`. A slow subscriber drops
its OLDEST items rather than blocking ingestion.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any


class AlertBus:
    def __init__(self, maxsize: int = 1000):
        self._subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subs.add((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = {s for s in self._subs if s[1] is not q}

    @property
    def subscribers(self) -> int:
        return len(self._subs)

    @staticmethod
    def _put(q: asyncio.Queue, item: Any) -> None:
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(item)

    def publish(self, item: Any) -> int:
        with self._lock:
            subs = list(self._subs)
        dead, sent = [], 0
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(self._put, q, item)
                sent += 1
            except RuntimeError:                  # loop closed
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)
        return sent
