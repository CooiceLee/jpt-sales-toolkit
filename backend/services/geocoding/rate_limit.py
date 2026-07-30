"""Process-wide provider request pacing."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class SharedRateLimiter:
    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self.clock = clock
        self.sleeper = sleeper
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            delay = (
                0.0 if self._last_request is None
                else self.interval_seconds - (now - self._last_request)
            )
            if delay > 0:
                self.sleeper(delay)
            self._last_request = self.clock()
