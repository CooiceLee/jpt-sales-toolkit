"""Optional Amap Web Service provider, disabled safely without a local key."""

from __future__ import annotations

import math

from .coordinates import gcj02_to_wgs84
from .errors import GeocodingError
from .models import GeocodeCandidate, GeocodeQuery
from .rate_limit import SharedRateLimiter
from .transport import JsonTransport


class AmapProvider:
    name = "amap"
    url = "https://restapi.amap.com/v3/geocode/geo"
    quota_codes = {"10003", "10004", "10010", "10014", "10015", "10019", "10045"}
    auth_codes = {
        "10001", "10002", "10005", "10006", "10007", "10008", "10009",
        "10011", "10012", "10013",
    }

    def __init__(self, api_key: str | None, transport=None, limiter=None) -> None:
        self.api_key = str(api_key or "").strip()
        self.transport = transport or JsonTransport()
        self.limiter = limiter or SharedRateLimiter(0.2)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: GeocodeQuery, limit: int) -> list[GeocodeCandidate]:
        if not self.enabled:
            raise GeocodingError(
                "provider_disabled", "Amap is not configured on this device.",
                status_code=503, retryable=False, provider=self.name,
            )
        self.limiter.wait()
        data = self.transport.get(
            self.url,
            {"key": self.api_key, "address": query.text, "city": query.city},
            {"Accept": "application/json"},
            self.name,
        )
        if not isinstance(data, dict):
            raise GeocodingError(
                "invalid_response", "Map service returned an invalid response.",
                status_code=502, provider=self.name,
            )
        if str(data.get("status")) != "1":
            code = str(data.get("infocode") or "")
            if code in self.quota_codes:
                raise GeocodingError(
                    "provider_quota", "Map service request limit reached. Try again later.",
                    status_code=429, provider=self.name,
                )
            auth_error = code in self.auth_codes
            raise GeocodingError(
                "provider_auth" if auth_error else "provider_error",
                "Map service authorization failed." if auth_error else "Map service rejected the address request.",
                status_code=502, retryable=not auth_error, provider=self.name,
            )
        rows = data.get("geocodes", [])
        if not isinstance(rows, list):
            raise self._invalid_response()
        if not rows:
            return []
        candidates = []
        for row in rows[:limit]:
            candidates.append(self._candidate(row))
        return candidates

    def _candidate(self, row: dict) -> GeocodeCandidate:
        try:
            lng, lat = (float(part) for part in row["location"].split(",", 1))
            if not math.isfinite(lat) or not math.isfinite(lng):
                raise ValueError("non-finite coordinate")
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("coordinate out of range")
            lat, lng = gcj02_to_wgs84(lat, lng)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise self._invalid_response() from exc
        return GeocodeCandidate(
            lat=lat, lng=lng,
            normalized_address=str(row.get("formatted_address") or ""),
            confidence="medium",
            place_type=str(row.get("level") or "location"),
            provider=self.name,
        )

    def _invalid_response(self) -> GeocodingError:
        return GeocodingError(
            "invalid_response", "Map service returned an invalid response.",
            status_code=502, provider=self.name,
        )
