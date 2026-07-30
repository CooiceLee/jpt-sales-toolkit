"""Process-wide maintenance gate for replacing the active database safely."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Callable


@dataclass
class _AccessToken:
    acquired: bool = False


class DatabaseAccessGate:
    """Writer-preferring gate shared by API requests and database restore."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_readers = 0
        self._writer_active = False
        self._writer_queue: deque[_AccessToken] = deque()

    def _try_shared(self, token: _AccessToken) -> None:
        with self._lock:
            if self._writer_active or self._writer_queue:
                return
            self._active_readers += 1
            token.acquired = True

    def _release_shared(self) -> None:
        with self._lock:
            self._active_readers -= 1

    def _queue_exclusive(self, token: _AccessToken) -> None:
        with self._lock:
            self._writer_queue.append(token)

    def _try_exclusive(self, token: _AccessToken) -> None:
        with self._lock:
            if (
                self._writer_active
                or self._active_readers
                or not self._writer_queue
                or self._writer_queue[0] is not token
            ):
                return
            self._writer_queue.popleft()
            self._writer_active = True
            token.acquired = True

    def _cancel_exclusive(self, token: _AccessToken) -> None:
        with self._lock:
            if not token.acquired:
                try:
                    self._writer_queue.remove(token)
                except ValueError:
                    pass

    def _release_exclusive(self) -> None:
        with self._lock:
            self._writer_active = False

    @staticmethod
    async def _call(callback: Callable[..., object], *args: object) -> None:
        """Run a short lock transition off-loop and finish it if cancelled."""
        task = asyncio.create_task(asyncio.to_thread(callback, *args))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    @asynccontextmanager
    async def shared(self) -> AsyncIterator[None]:
        token = _AccessToken()
        try:
            while not token.acquired:
                await self._call(self._try_shared, token)
                if not token.acquired:
                    await asyncio.sleep(0.01)
            yield
        finally:
            if token.acquired:
                await self._call(self._release_shared)

    @asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        token = _AccessToken()
        try:
            await self._call(self._queue_exclusive, token)
            while not token.acquired:
                await self._call(self._try_exclusive, token)
                if not token.acquired:
                    await asyncio.sleep(0.01)
            yield
        finally:
            callback = (
                self._release_exclusive
                if token.acquired
                else self._cancel_exclusive
            )
            args = () if token.acquired else (token,)
            await self._call(callback, *args)

    @property
    def waiting_writers(self) -> int:
        """Return queued writers for diagnostics and deterministic tests."""
        with self._lock:
            return len(self._writer_queue)

    @property
    def is_idle(self) -> bool:
        with self._lock:
            return not self._active_readers and not self._writer_active and not self._writer_queue


database_access_gate = DatabaseAccessGate()
