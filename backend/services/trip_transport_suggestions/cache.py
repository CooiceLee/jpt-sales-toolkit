"""Bounded process-memory TTL cache; it never opens application storage."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable


class MemorySuggestionCache:
    def __init__(
        self,
        ttl_seconds: int = 6 * 60 * 60,
        max_entries: int = 512,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self.clock = clock
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        with self._lock:
            item = self._items.pop(key, None)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= self.clock():
                return None
            self._items[key] = item
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = (self.clock() + self.ttl_seconds, value)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
