"""Suggestion coordinator with safe local fallback and no persistence hooks."""

from __future__ import annotations

from datetime import datetime, timezone

from .cache import MemorySuggestionCache
from .heuristic import local_estimate
from .network import TransportProviderError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TransportSuggestionService:
    def __init__(self, *, drive_provider=None, cache=None, now=_utc_now) -> None:
        self.drive_provider = drive_provider
        self.cache = cache or MemorySuggestionCache()
        self.now = now

    def suggest(self, request, *, force_refresh: bool = False):
        cache_key = f"v1:{request.cache_key}"
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached.from_cache()
        fetched_at = self.now()
        suggestion = self._uncached(request, fetched_at)
        self.cache.set(cache_key, suggestion)
        return suggestion

    def _uncached(self, request, fetched_at: str):
        if request.mode == "drive" and self.drive_provider is not None:
            try:
                return self.drive_provider.suggest(request, fetched_at)
            except TransportProviderError:
                pass
        return local_estimate(request, fetched_at)
