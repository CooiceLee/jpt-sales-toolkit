"""Global WGS84 geocoder backed by the public Nominatim endpoint."""

from __future__ import annotations

from .errors import GeocodingError
from .models import GeocodeCandidate, GeocodeQuery
from .rate_limit import SharedRateLimiter
from .transport import JsonTransport


class NominatimProvider:
    name = "nominatim"
    url = "https://nominatim.openstreetmap.org/search"

    def __init__(self, user_agent: str, transport=None, limiter=None) -> None:
        self.user_agent = user_agent
        self.transport = transport or JsonTransport()
        self.limiter = limiter or SharedRateLimiter(1.0)

    @property
    def enabled(self) -> bool:
        return True

    def search(self, query: GeocodeQuery, limit: int) -> list[GeocodeCandidate]:
        self.limiter.wait()
        rows = self.transport.get(
            self.url,
            {
                "q": query.text,
                "format": "jsonv2",
                "limit": limit,
                "addressdetails": 1,
                # Chinese first: this team reads Chinese, and asking for it also
                # lets a Chinese query match places outside China by their
                # Chinese name instead of ranking same-spelling domestic ones.
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.6",
            },
            {"User-Agent": self.user_agent, "Accept": "application/json"},
            self.name,
        )
        if not isinstance(rows, list):
            raise GeocodingError(
                "invalid_response", "Map service returned an invalid response.",
                status_code=502, provider=self.name,
            )
        return [self._candidate(row) for row in rows if self._valid(row)][:limit]

    @staticmethod
    def _valid(row: dict) -> bool:
        try:
            lat, lng = float(row["lat"]), float(row["lon"])
            return -90 <= lat <= 90 and -180 <= lng <= 180
        except (KeyError, TypeError, ValueError):
            return False

    def _candidate(self, row: dict) -> GeocodeCandidate:
        place_type = str(row.get("type") or row.get("category") or "location")
        # Nominatim's ``importance`` measures ranking/prominence, not address
        # precision. A famous city or country can have a very high importance
        # score while still being unsuitable as an exact customer location.
        if place_type in {"building", "house", "office", "industrial"}:
            confidence = "high"
        elif place_type in {"street", "road", "neighbourhood", "suburb"}:
            confidence = "medium"
        else:
            confidence = "low"
        return GeocodeCandidate(
            lat=float(row["lat"]),
            lng=float(row["lon"]),
            normalized_address=str(row.get("display_name") or ""),
            confidence=confidence,
            place_type=place_type,
            provider=self.name,
            provider_reference=str(row.get("place_id")) if row.get("place_id") else None,
        )
