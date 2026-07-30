"""Cache, deduplication and provider selection for geocoding searches."""

from __future__ import annotations

import threading

from .base import GeocodeProvider
from .cache import GeocodeCache
from .errors import GeocodingError
from .models import GeocodeCandidate, GeocodeQuery, GeocodeSearchResult


class GeocodingCoordinator:
    _FALLBACK_ERROR_CODES = {
        "invalid_response",
        "network_error",
        "provider_error",
        "provider_quota",
        "timeout",
        "tls_error",
    }

    def __init__(self, providers: list[GeocodeProvider], cache: GeocodeCache) -> None:
        self.providers = {provider.name: provider for provider in providers}
        self.cache = cache
        self._key_locks = tuple(threading.Lock() for _ in range(64))

    def search(
        self,
        query: GeocodeQuery,
        *,
        limit: int = 5,
        provider_name: str | None = None,
    ) -> GeocodeSearchResult:
        if not query.text:
            raise GeocodingError(
                "invalid_request", "Enter an address, city, postal code, or country.",
                status_code=400, retryable=False,
            )
        limit = max(1, min(int(limit), 5))
        providers = self._provider_chain(provider_name)
        last_result = None
        for index, provider in enumerate(providers):
            has_fallback = index + 1 < len(providers)
            try:
                result = self._search_provider(query, provider, limit)
            except GeocodingError as exc:
                if provider_name or not has_fallback or not self._can_fallback(exc):
                    raise
                continue
            if result.candidates or provider_name or not has_fallback:
                return result
            last_result = result
        if last_result is not None:
            return last_result
        raise GeocodingError(
            "provider_disabled", "No map service is configured.",
            status_code=503, retryable=False,
        )

    def _search_provider(
        self,
        query: GeocodeQuery,
        provider: GeocodeProvider,
        limit: int,
    ) -> GeocodeSearchResult:
        cache_key = f"v1:{provider.name}:{query.cache_key}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return self._restore(query, provider.name, cached, limit)

        lock = self._lock_for(cache_key)
        with lock:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return self._restore(query, provider.name, cached, limit)
            candidates = provider.search(query, 5)
            ttl = 60 * 60 * 24 if not candidates else None
            self.cache.set(
                cache_key,
                {"candidates": [candidate.as_dict() for candidate in candidates]},
                ttl_seconds=ttl,
            )
            return GeocodeSearchResult(query, candidates[:limit], provider.name)

    def _provider_chain(self, requested: str | None) -> list[GeocodeProvider]:
        if requested:
            provider = self.providers.get(requested)
            if not provider or not provider.enabled:
                raise GeocodingError(
                    "provider_disabled", "Requested map service is not configured.",
                    status_code=503, retryable=False, provider=requested,
                )
            return [provider]
        providers = [provider for provider in self.providers.values() if provider.enabled]
        if providers:
            return providers
        raise GeocodingError("provider_disabled", "No map service is configured.",
                             status_code=503, retryable=False)

    def _can_fallback(self, exc: GeocodingError) -> bool:
        return exc.retryable and exc.code in self._FALLBACK_ERROR_CODES

    def _lock_for(self, cache_key: str) -> threading.Lock:
        return self._key_locks[hash(cache_key) % len(self._key_locks)]

    @staticmethod
    def _restore(
        query: GeocodeQuery, provider: str, payload: dict, limit: int,
    ) -> GeocodeSearchResult:
        candidates = [GeocodeCandidate(**row) for row in payload.get("candidates", [])][:limit]
        return GeocodeSearchResult(query, candidates, provider, cached=True)
