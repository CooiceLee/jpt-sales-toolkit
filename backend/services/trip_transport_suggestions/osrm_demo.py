"""Optional FOSSGIS OSRM demo adapter; disabled unless explicitly enabled."""

from __future__ import annotations

import hashlib
import math

from ..geocoding.rate_limit import SharedRateLimiter
from .links import maps_directions_url, osrm_route_url
from .models import TransportSuggestion
from .network import RestrictedJsonClient, TransportProviderError


class OsrmDemoDriveProvider:
    def __init__(self, *, enabled: bool = False, transport=None, limiter=None) -> None:
        self.enabled = bool(enabled)
        self.transport = transport or RestrictedJsonClient()
        self.limiter = limiter or SharedRateLimiter(1.0)

    def suggest(self, request, fetched_at: str) -> TransportSuggestion:
        if not self.enabled:
            raise TransportProviderError("OSRM demo provider is disabled")
        if request.mode != "drive":
            raise TransportProviderError("OSRM demo supports drive only")
        self.limiter.wait()
        data = self.transport.get_osrm(
            osrm_route_url(request),
            "JPTSalesToolkit/transport-demo (https://github.com/CooiceLee/jpt-sales-toolkit)",
        )
        try:
            route = data["routes"][0]
            distance = float(route["distance"]) / 1000
            hours = float(route["duration"]) / 3600
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise TransportProviderError("OSRM demo returned invalid route metrics") from exc
        if not all(math.isfinite(value) and value >= 0 for value in (distance, hours)):
            raise TransportProviderError("OSRM demo returned invalid route metrics")
        distance, hours = round(distance, 1), round(hours, 1)
        identity = f"{request.cache_key}|FOSSGIS OSRM demo|{distance}|{hours}"
        return TransportSuggestion(
            suggestion_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
            leg_key=request.leg_key, mode="drive", distance_km=distance, time_hours=hours,
            travel_days=0 if hours <= 4 else max(1, math.ceil(hours / 8)),
            provider="FOSSGIS OSRM demo", online=True, status="estimated",
            fetched_at=fetched_at, approximate=True, confidence="medium", cached=False,
            search_url=maps_directions_url(request), requires_manual_confirmation=True,
            warning="Best-effort demo result. Confirm current traffic and route manually.",
            attribution="Route: OSRM; data © OpenStreetMap contributors (ODbL).",
        )
