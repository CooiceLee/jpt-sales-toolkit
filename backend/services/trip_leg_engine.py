"""Pure route-leg selection and metric calculation."""

from __future__ import annotations

import math


def select_mode(distance_km: float, priority: list[str]) -> str:
    """Choose the first preferred mode suitable for the segment distance."""
    for mode in priority:
        if mode == "flight" and distance_km >= 250:
            return mode
        if mode == "drive" and distance_km <= 1200:
            return mode
        if mode == "ground_public" and distance_km <= 1800:
            return mode
    for mode in priority:
        if mode != "other":
            return mode
    return "other"


def build_leg(
    core,
    sequence_no: int,
    start: dict,
    end: dict,
    priority: list[str],
    override: dict | None = None,
) -> dict:
    override = override or {}
    straight_km = core._haversine_km(start["lat"], start["lng"], end["lat"], end["lng"])
    selected_mode = override.get("selected_mode") or select_mode(straight_km, priority)
    if selected_mode == "other" and not (
        (override.get("manual_time_hours") or 0) > 0
        or override.get("manual_travel_half_days") is not None
        or (override.get("manual_travel_days") or 0) > 0
    ):
        key = f"{start.get('stop_id') or 'origin'}>{end.get('stop_id') or 'destination'}"
        raise ValueError(f"Leg {key} using other requires manual time hours or travel days")
    estimate_mode = selected_mode if selected_mode != "other" else "drive"
    estimate = core._estimate_travel_leg(start, end, estimate_mode)

    distance_km = override.get("manual_distance_km")
    if distance_km is None:
        distance_km = estimate["distance_km"]
    time_hours = override.get("manual_time_hours")
    if time_hours is None:
        time_hours = estimate["time_hours"]
    travel_half_days = override.get("manual_travel_half_days")
    if travel_half_days is None and override.get("manual_travel_days") is not None:
        travel_half_days = int(override["manual_travel_days"]) * 2
    if travel_half_days is None:
        travel_half_days = 0 if time_hours <= 1 else max(1, math.ceil(time_hours / 4))
    travel_half_days = min(60, int(travel_half_days))
    travel_days = math.ceil(travel_half_days / 2)
    manual_travel_days = override.get("manual_travel_days")
    if manual_travel_days is None and override.get("manual_travel_half_days") is not None:
        manual_travel_days = math.ceil(
            int(override["manual_travel_half_days"]) / 2
        )

    return {
        "id": None,
        "leg_key": f"{start.get('stop_id') or 'origin'}>{end.get('stop_id') or 'destination'}",
        "sequence_no": sequence_no,
        "from_kind": start["kind"],
        "from_stop_id": start.get("stop_id"),
        "from_stop_kind": start.get("stop_kind"),
        "from_label": start.get("label"),
        "to_kind": end["kind"],
        "to_stop_id": end.get("stop_id"),
        "to_stop_kind": end.get("stop_kind"),
        "to_label": end.get("label"),
        "selected_mode": selected_mode,
        "mode": selected_mode,
        "mode_locked": bool(override.get("mode_locked", False)),
        "distance_km": round(float(distance_km), 1),
        "time_hours": round(float(time_hours), 1),
        "travel_days": int(travel_days),
        "travel_half_days": travel_half_days,
        "manual_distance_km": override.get("manual_distance_km"),
        "manual_time_hours": override.get("manual_time_hours"),
        "manual_travel_days": manual_travel_days,
        "manual_travel_half_days": override.get("manual_travel_half_days"),
        "notes": override.get("notes"),
        "from": start.get("label"),
        "to": end.get("label"),
    }
