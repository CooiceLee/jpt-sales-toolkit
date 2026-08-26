"""Keep airport and transit stops attached to the leg they serve.

A manually added airport is an ordinary stop, so automatic ordering would
otherwise scatter it away from the flight it belongs to, and a ground
connection would end up routed through it.
"""

from __future__ import annotations

from .trip_leg_engine import select_mode

WAYPOINT_CATEGORIES = ("airport", "transit")


def is_waypoint(stop: dict) -> bool:
    return (
        stop.get("stop_kind") == "free"
        and stop.get("category") in WAYPOINT_CATEGORIES
    )


def split_waypoints(ordered_stops: list) -> tuple[list, dict]:
    """Separate real stops from the waypoints stored in front of each of them.

    The returned mapping is keyed by the index of the leg a waypoint group
    belongs to, where leg ``k`` connects route point ``k`` to route point
    ``k + 1`` of ``[origin, *base, destination]``.
    """
    base: list = []
    groups: dict = {}
    pending: list = []
    for item in ordered_stops:
        if is_waypoint(item[0]):
            pending.append(item)
            continue
        if pending:
            groups[len(base)] = pending
        base.append(item)
        pending = []
    if pending:
        groups[len(base)] = pending
    return base, groups


def flight_leg_indices(
    route_points: list[dict], priority: list[str], overrides: dict, distance_km
) -> set:
    """Which legs of an airport-free route are flown."""
    flights = set()
    for index in range(len(route_points) - 1):
        start, end = route_points[index], route_points[index + 1]
        override = overrides.get(leg_key(start, end)) or {}
        mode = override.get("selected_mode") or select_mode(
            distance_km(start, end), priority
        )
        if mode == "flight":
            flights.add(index)
    return flights


def apply_flight_waypoints(base: list, groups: dict, flights: set) -> list:
    """Rebuild the stop order, keeping waypoints only around flown legs.

    A ground connection must never route through an airport, so its stored
    waypoints stay out of the itinerary until that leg is flown again.
    """
    ordered: list = []
    for index, item in enumerate(base):
        if index in flights:
            ordered.extend(groups.get(index, []))
        ordered.append(item)
    if len(base) in flights:
        ordered.extend(groups.get(len(base), []))
    return ordered


def anchor_waypoints(stops: list) -> list[list]:
    """Group each stop with the waypoints stored immediately before it.

    Automatic ordering rearranges business visits. An airport belongs to the
    visit it serves, so it has to travel with it instead of being scattered.
    """
    chains: list[list] = []
    pending: list = []
    for item in stops:
        if is_waypoint(item[0]):
            pending.append(item)
            continue
        chains.append([*pending, item])
        pending = []
    if pending:
        chains.append(pending)
    return chains
