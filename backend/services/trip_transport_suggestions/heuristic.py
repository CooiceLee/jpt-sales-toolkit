"""Deterministic fallback metrics for planning, never ticketing advice."""

from __future__ import annotations

import hashlib
import math

from .links import flight_search_url, maps_directions_url
from .models import TransportSuggestion


def haversine_km(request) -> float:
    lat1, lat2 = math.radians(request.from_lat), math.radians(request.to_lat)
    dlat = lat2 - lat1
    dlng = math.radians(request.to_lng - request.from_lng)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def local_estimate(request, fetched_at: str) -> TransportSuggestion:
    straight = haversine_km(request)
    if straight <= 5 and request.mode != "other":
        distance, hours, days, confidence = straight, 0.25, 0, "medium"
        search_url = maps_directions_url(request) if request.mode != "flight" else flight_search_url()
    elif request.mode == "drive":
        distance, hours, confidence = straight * 1.18, straight * 1.18 / 75 + 0.5, "medium"
        days = 0 if hours <= 3.5 else max(1, math.ceil(hours / 7))
        search_url = maps_directions_url(request)
    elif request.mode == "ground_public":
        distance, confidence = straight * 1.15, "low"
        hours = 1.25 + distance / 95
        days = 0 if hours <= 4 else max(1, math.ceil(hours / 7))
        search_url = maps_directions_url(request)
    elif request.mode == "flight":
        distance, hours, confidence = straight, 3.0 + straight / 780, "low"
        if straight > 6000:
            hours += 2.0
        days = 1 if hours <= 10 else 2
        search_url = flight_search_url()
    else:
        distance, hours, days, confidence, search_url = straight, None, None, "low", None
    rounded_distance = round(distance, 1)
    rounded_hours = round(hours, 1) if hours is not None else None
    identity = f"{request.cache_key}|Local estimate|{rounded_distance}|{rounded_hours}"
    return TransportSuggestion(
        suggestion_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
        leg_key=request.leg_key,
        mode=request.mode,
        distance_km=rounded_distance,
        time_hours=rounded_hours,
        travel_days=days,
        provider="Local estimate",
        online=False,
        status="manual_required" if request.mode == "other" else "estimated",
        fetched_at=fetched_at,
        approximate=True,
        confidence=confidence,
        cached=False,
        search_url=search_url,
        warning="Open the search page and confirm route, schedule and price manually.",
        attribution=None,
    )
