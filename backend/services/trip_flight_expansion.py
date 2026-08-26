"""Expand a flown leg into its ground transfers and the flight itself.

An airport belongs to the connection between two stops, never to the stop list:
stored as a stop it would be reordered away from the leg it serves. A flown leg
therefore carries its own airports, and this module is the single place that
turns one such leg into the segments a traveller actually experiences:

    stop A -> departure airport -> arrival airport -> stop B

Preview, the schedule and every export share this function so the itinerary a
user approves is the itinerary that gets distributed.
"""

from __future__ import annotations

GROUND_MODES = ("drive", "ground_public", "other")
AIRPORT_KIND = "airport"


def airport_point(leg: dict, side: str) -> dict | None:
    """The searched airport recorded for one end of a leg, if it has one."""
    name = leg.get(f"{side}_airport_name")
    lat = leg.get(f"{side}_airport_lat")
    lng = leg.get(f"{side}_airport_lng")
    if not name or lat is None or lng is None:
        return None
    return {
        "kind": AIRPORT_KIND,
        "side": side,
        "label": name,
        "lat": float(lat),
        "lng": float(lng),
        "stay_half_days": int(leg.get(f"{side}_airport_stay_half_days") or 0),
    }


def is_expandable(leg: dict) -> bool:
    """Both ends must be known: a half-entered pair cannot be routed."""
    if leg.get("selected_mode") != "flight":
        return False
    return bool(airport_point(leg, "departure") and airport_point(leg, "arrival"))


def ground_mode(priority: list[str]) -> str:
    """Pick a ground mode for a transfer to or from an airport.

    Never a flight: a transfer that flies would need its own airports, and the
    expansion would recurse forever.
    """
    for mode in priority or ():
        if mode in GROUND_MODES:
            return mode
    return "drive"


def missing_airport_sides(leg: dict) -> list[str]:
    """Which ends of a flown leg still need an airport."""
    if leg.get("selected_mode") != "flight":
        return []
    return [side for side in ("departure", "arrival") if not airport_point(leg, side)]


def expand(leg: dict, priority: list[str]) -> list[dict]:
    """Describe one leg as the ordered segments it is actually made of.

    A leg that is not a fully described flight yields itself unchanged, so the
    caller can treat every leg the same way.
    """
    if not is_expandable(leg):
        return [{"role": "direct", "mode": leg.get("selected_mode"), "airport": None}]
    transfer = ground_mode(priority)
    departure = airport_point(leg, "departure")
    arrival = airport_point(leg, "arrival")
    return [
        {"role": "to_airport", "mode": transfer, "airport": departure},
        {"role": "flight", "mode": "flight", "airport": arrival},
        {"role": "from_airport", "mode": transfer, "airport": None},
    ]
