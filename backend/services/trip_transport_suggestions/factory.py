"""Process-wide suggestion service; cached values contain no business labels."""

from __future__ import annotations

from functools import lru_cache

from .service import TransportSuggestionService


@lru_cache(maxsize=1)
def get_transport_suggestion_service() -> TransportSuggestionService:
    return TransportSuggestionService()


def reset_transport_suggestion_service() -> None:
    get_transport_suggestion_service.cache_clear()
