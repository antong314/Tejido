"""Per-participant SSE subscriber registry.

Multiple browser tabs of the same participant subscribe to the same
participant_id; broadcasts go to every queue for that id. Single
process, in-memory.

Subscribers use the `subscribe` async-context-manager which adds a
queue, yields it to the SSE generator, and removes it on disconnect
(generator close / cancellation). Broadcasts never block — if a queue
is full or a subscriber has gone away, the event is enqueued anyway and
either drains later or is GC'd when the queue is removed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)


class SSEHub:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def _add(self, participant_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._queues.setdefault(participant_id, []).append(queue)

    async def _remove(self, participant_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._queues.get(participant_id)
            if queues is None:
                return
            try:
                queues.remove(queue)
            except ValueError:
                pass
            if not queues:
                self._queues.pop(participant_id, None)

    @asynccontextmanager
    async def subscribe(self, participant_id: str) -> AsyncIterator[asyncio.Queue]:
        """Add a queue, yield it, remove it on context exit (incl. cancellation)."""
        queue: asyncio.Queue = asyncio.Queue()
        await self._add(participant_id, queue)
        try:
            yield queue
        finally:
            await self._remove(participant_id, queue)

    async def broadcast(self, participant_id: str, event: dict[str, Any]) -> None:
        """Push an event to every subscriber queue for this participant.

        If no one is subscribed, the event is dropped silently. Frontends
        that reconnect should re-fetch /state to recover.
        """
        async with self._lock:
            queues = list(self._queues.get(participant_id, []))
        for q in queues:
            await q.put(event)

    def subscriber_count(self, participant_id: str) -> int:
        return len(self._queues.get(participant_id, ()))
