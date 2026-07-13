"""
Geocode service - address to coordinates conversion.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import json
from typing import Optional

from ..config import APP_VERSION


class GeocodeService:
    """Geocoding service using Nominatim (OpenStreetMap)."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = f"JPTSalesToolkit/{APP_VERSION}"
    RATE_LIMIT_SECONDS = 1.0  # Nominatim requires max 1 request/second

    _last_request_time = 0.0

    def geocode(
        self,
        address: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Convert address to coordinates.

        Returns dict with lat, lng, confidence, normalized_address
        or None if not found.
        """
        # Build query
        parts = []
        if address:
            parts.append(address)
        if city:
            parts.append(city)
        if country:
            parts.append(country)

        if not parts:
            return None

        query = ", ".join(parts)

        # Rate limiting
        self._rate_limit()

        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            }
            url = f"{self.NOMINATIM_URL}?{urllib.parse.urlencode(params)}"

            request = urllib.request.Request(url)
            request.add_header("User-Agent", self.USER_AGENT)

            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())

            if not data:
                return None

            result = data[0]

            # Determine confidence based on result type
            confidence = self._determine_confidence(result)

            return {
                "lat": float(result["lat"]),
                "lng": float(result["lon"]),
                "confidence": confidence,
                "normalized_address": result.get("display_name"),
                "place_type": result.get("type"),
            }

        except Exception as e:
            # Log error but don't raise - geocoding is best-effort
            print(f"Geocode error: {e}")
            return None

    def _rate_limit(self) -> None:
        """Enforce rate limiting for Nominatim."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_SECONDS:
            time.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _determine_confidence(self, result: dict) -> str:
        """Determine confidence level from result."""
        place_type = result.get("type", "")
        importance = float(result.get("importance", 0))

        # High confidence for specific addresses
        if place_type in ("building", "house", "office", "industrial"):
            return "high"

        # Medium confidence for streets and neighborhoods
        if place_type in ("street", "road", "neighbourhood", "suburb"):
            return "medium"

        # Low confidence for cities and larger areas
        return "low"
