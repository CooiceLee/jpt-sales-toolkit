"""Project grouped customers into map points, missing rows and summary counts."""

from __future__ import annotations

from ..coordinate_validation import valid_coordinate_pair


def _coordinates(core, group: dict, offsets: dict) -> tuple | None:
    lat = group.pop("raw_lat")
    lng = group.pop("raw_lng")
    valid_pair = valid_coordinate_pair(lat, lng)
    group["invalid_coordinates"] = bool(
        (lat is not None or lng is not None) and not valid_pair
    )
    if valid_pair:
        verified = (
            bool(group.get("geocode_locked"))
            or group.get("geocode_source") == "manual"
            or group.get("geocode_confidence") == "high"
        )
        quality = "exact" if verified else "auto_approximate"
        return float(lat), float(lng), quality, not verified

    country_code = group["country_code"]
    fallback = core._country_center(country_code)
    if not fallback:
        return None
    offset = offsets.get(country_code, 0)
    offsets[country_code] = offset + 1
    lat = fallback["lat"] + (offset % 5) * 0.18
    lng = fallback["lng"] + (offset // 5) * 0.18
    return lat, lng, "country_fallback", True


def _point(group: dict, location: tuple) -> dict:
    lat, lng, quality, needs_geocode = location
    leads = group["leads"]
    latest = max(leads, key=lambda lead: lead.get("updated_at") or "")
    return {
        **group,
        "id": group["customer_id"],
        "name": group["customer_name"],
        "lat": lat,
        "lng": lng,
        "coordinate_quality": quality,
        "needs_geocode": needs_geocode,
        "lead_count": len(leads),
        "latest_stage": latest["sales_stage"],
        "latest_lead_id": latest["id"],
        "latest_lead_display_id": latest["display_id"],
        "owners": list(group["owners"].values()),
        "stages": sorted(group["stages"]),
        "won_count": sum(1 for lead in leads if lead["sales_stage"] == "Won"),
        "lost_count": sum(1 for lead in leads if lead["sales_stage"] == "Lost"),
        "open_count": sum(
            1 for lead in leads if lead["sales_stage"] not in {"Won", "Lost"}
        ),
    }


def _summary(grouped: dict, points: list[dict], missing: list[dict]) -> dict:
    return {
        "customers": len(grouped),
        "points": len(points),
        "exact_points": sum(p["coordinate_quality"] == "exact" for p in points),
        "approximate_points": sum(bool(p["needs_geocode"]) for p in points),
        "missing_locations": len(missing),
        "leads": sum(p["lead_count"] for p in points)
        + sum(item["lead_count"] for item in missing),
        "won_customers": sum(p["won_count"] > 0 for p in points),
        "open_customers": sum(p["open_count"] > 0 for p in points),
        "lost_customers": sum(p["lost_count"] > 0 for p in points),
    }


def project_map_response(core, grouped: dict, filters: dict) -> dict:
    points = []
    missing = []
    offsets = {}
    for group in grouped.values():
        location = _coordinates(core, group, offsets)
        if location is None:
            missing.append(core._map_missing_location(group))
        else:
            points.append(_point(group, location))
    return {
        "filters": dict(filters),
        "summary": _summary(grouped, points, missing),
        "points": points,
        "missing_locations": missing,
    }
