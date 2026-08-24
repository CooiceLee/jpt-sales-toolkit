"""Translate an authorized itinerary preview into coordinate-only requests."""

from __future__ import annotations

from .models import LegRequest


def requests_from_preview(core, plan: dict, data: dict, preview: dict) -> list[LegRequest]:
    stops = preview.get("stops") or []
    points = {}
    for stop in stops:
        point = core._route_point_from_stop(stop)
        if point:
            points[stop["id"]] = point
    if not points:
        raise ValueError("Add at least one located stop before requesting suggestions")

    origin = core._route_endpoint("origin", data, plan) or points[stops[0]["id"]]
    destination = core._route_endpoint("destination", data, plan) or points[stops[-1]["id"]]
    requests = []
    for leg in preview.get("legs") or []:
        start = points.get(leg.get("from_stop_id")) if leg.get("from_stop_id") else origin
        end = points.get(leg.get("to_stop_id")) if leg.get("to_stop_id") else destination
        if not start or not end:
            raise ValueError(f"Missing server-side route coordinates for leg {leg.get('leg_key')}")
        requests.append(
            LegRequest.create(
                leg_key=leg.get("leg_key"),
                mode=leg.get("selected_mode"),
                from_lat=start["lat"],
                from_lng=start["lng"],
                to_lat=end["lat"],
                to_lng=end["lng"],
            )
        )
    return requests
