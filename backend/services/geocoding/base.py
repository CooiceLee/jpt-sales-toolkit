"""Geocoding provider protocol."""

from __future__ import annotations

from typing import Protocol

from .models import GeocodeCandidate, GeocodeQuery


class GeocodeProvider(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    def search(self, query: GeocodeQuery, limit: int) -> list[GeocodeCandidate]: ...
