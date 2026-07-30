"""Compatibility facade for provider-neutral geocoding."""

from __future__ import annotations

from typing import Optional

from .geocoding import GeocodeQuery, get_geocoding_coordinator


class GeocodeService:
    """Preserve the legacy first-result API while exposing candidate search."""

    def __init__(self, coordinator=None) -> None:
        self.coordinator = coordinator or get_geocoding_coordinator()

    def geocode(
        self,
        address: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Convert address to coordinates.

        Returns dict with lat, lng, confidence, normalized_address
        or None if not found.
        """
        result = self.search(
            address=address, city=city, postal_code=postal_code,
            country=country, limit=1,
        )
        return result["candidates"][0] if result["candidates"] else None

    def search(
        self,
        address: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: Optional[str] = None,
        limit: int = 5,
        provider: Optional[str] = None,
    ) -> dict:
        query = GeocodeQuery.create(
            address=address, city=city, postal_code=postal_code, country=country,
        )
        return self.coordinator.search(
            query, limit=limit, provider_name=provider,
        ).as_dict()
