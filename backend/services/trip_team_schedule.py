"""Schedule a trip that several team members travel.

The single-path planner walks one route order and advances one cursor, which
assumes the trip has exactly one traveller. A team splits up: two colleagues can
be with two customers at the same hour in two cities, and that is an ordinary
arrangement rather than an error.

So each member carries their own position and clock. Who attends an event
decides everything else: the next event having different attendees is a split,
one event having several attendees is a merge. Neither needs to be modelled.

Nothing here computes distances or slots. It arranges the events; the existing
leg, airport and slot helpers still do the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .trip_leg_engine import build_leg


@dataclass
class MemberState:
    """Where a member is, when they are free again, and whether we know.

    ``route_known`` goes false the moment the plan stops being able to say where
    somebody is - two visits booked over each other, or a parallel pair nobody
    has been assigned to. While it is false no travel is invented for them; a
    booked appointment later says where they are and puts it back to true.
    """

    user_id: str
    location: dict
    slot: tuple
    route_known: bool = True


@dataclass
class TeamEvent:
    """Something that has to happen, and who has to be there."""

    stop_id: str
    kind: str
    point: dict
    duration_half_days: int
    participants: tuple
    booked_slot: tuple | None = None
    preferred_period: str = "auto"
    label: str = ""


@dataclass
class TeamPlanResult:
    legs: list = field(default_factory=list)
    schedule_items: list = field(default_factory=list)
    stop_updates: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    member_totals: dict = field(default_factory=dict)


def _next_slot(slot: tuple) -> tuple:
    day, period = slot
    if period == "AM":
        return day, "PM"
    return day + timedelta(days=1), "AM"


def occupied_slots(event: "TeamEvent") -> tuple:
    """The half-days a booked event actually takes up.

    A visit that starts in the morning and lasts a day still occupies the
    afternoon, so comparing start times alone would miss a real clash.
    """
    if not event.booked_slot:
        return ()
    slots = []
    slot = event.booked_slot
    for _ in range(max(1, int(event.duration_half_days or 1))):
        slots.append(slot)
        slot = _next_slot(slot)
    return tuple(slots)


def resolve_participants(event_participants, team: tuple) -> tuple:
    """Who travels to an event.

    Nobody named means the whole team: a plan in team mode has already said who
    is travelling, so silence means everyone rather than nobody.

    Naming somebody who is not on the trip is a different thing entirely, and
    must not quietly become "everyone goes" - that is the opposite of what was
    asked for. It resolves to nobody, and the caller reports it.
    """
    if not event_participants:
        return team
    return tuple(user for user in event_participants if user in team)


def double_booked_stop_ids(events: list, team: tuple) -> dict:
    """Per member, the visits that overlap another visit of theirs.

    Overlap is measured across the half-days each visit occupies, not just the
    one it starts in: a day-long visit booked for the morning still runs into
    the afternoon appointment that follows it.
    """
    booked: dict = {}
    for event in events:
        if not event.booked_slot:
            continue
        for user in resolve_participants(event.participants, team):
            for slot in occupied_slots(event):
                booked.setdefault(user, {}).setdefault(slot, set()).add(
                    event.stop_id
                )
    clashing: dict = {}
    for user, slots in booked.items():
        for stop_ids in slots.values():
            if len(stop_ids) > 1:
                clashing.setdefault(user, set()).update(stop_ids)
    return clashing


def unresolved_events(events: list, team: tuple) -> set:
    """Events whose traveller is not yet known, so no route can be drawn.

    Two visits in the same half-day with nobody named cannot both be attended by
    the whole team, and an event naming only outsiders has no traveller at all.
    Routing either of them would invent a journey nobody makes.
    """
    unresolved = set()
    for event in events:
        if event.participants and not resolve_participants(
            event.participants, team
        ):
            unresolved.add(event.stop_id)
    for group in group_by_slot(events).values():
        if len(group) < 2:
            continue
        for event in group:
            if not event.participants:
                unresolved.add(event.stop_id)
    return unresolved


def group_by_slot(events: list[TeamEvent]) -> dict:
    """Booked events that share a half-day, keyed by that half-day."""
    groups: dict = {}
    for event in events:
        if event.booked_slot:
            groups.setdefault(event.booked_slot, []).append(event)
    return groups


def staffing_risks(events: list, team: tuple) -> list[dict]:
    """Report who cannot be in two places at once, and what is unstaffed.

    Two visits in the same half-day are legitimate when different colleagues
    cover them, so this reports rather than refuses.
    """
    risks: list[dict] = []

    for event in events:
        if event.participants and not resolve_participants(
            event.participants, team
        ):
            risks.append(
                {
                    "kind": "participant_not_in_trip_team",
                    "stop_id": event.stop_id,
                    "user_ids": sorted(str(user) for user in event.participants),
                }
            )

    for slot, group in sorted(group_by_slot(events).items()):
        if len(group) < 2:
            continue
        unstaffed = [
            event.stop_id for event in group if not (event.participants or ())
        ]
        if unstaffed:
            # Nobody has been named yet, so reporting that the whole team is
            # double-booked as well would only be noise: the one thing to do is
            # decide who goes where.
            risks.append(
                {
                    "kind": "parallel_visits_unassigned",
                    "date": slot[0].isoformat(),
                    "period": slot[1],
                    "visit_count": len(group),
                    "stop_ids": sorted(unstaffed),
                }
            )

    unassigned_dates = {
        risk["date"]
        for risk in risks
        if risk["kind"] == "parallel_visits_unassigned"
    }
    for user, stop_ids in sorted(double_booked_stop_ids(events, team).items()):
        clashing = sorted(
            (event for event in events if event.stop_id in stop_ids),
            key=lambda item: (
                item.booked_slot[0].isoformat(), item.booked_slot[1]
            ),
        )
        first = clashing[0].booked_slot
        if first[0].isoformat() in unassigned_dates:
            continue
        risks.append(
            {
                "kind": "member_double_booked",
                "user_id": user,
                "date": first[0].isoformat(),
                "period": first[1],
                "stop_ids": sorted(stop_ids),
            }
        )
    return risks


def member_lanes(events: list, team: tuple) -> dict:
    """The events each member attends, ordered by when they happen.

    Events whose traveller is still unknown are left out: a lane is a sequence
    of places one person actually goes to, and guessing here would produce a
    route nobody travels.
    """
    skip = unresolved_events(events, team)
    lanes: dict = {user: [] for user in team}
    for event in events:
        if event.stop_id in skip:
            continue
        for user in resolve_participants(event.participants, team):
            lanes.setdefault(user, []).append(event)
    for user, lane in lanes.items():
        lane.sort(key=lambda item: (
            item.booked_slot is None,
            item.booked_slot[0].isoformat() if item.booked_slot else "",
            0 if (item.booked_slot or ("", "AM"))[1] == "AM" else 1,
        ))
    return lanes


def _ordered_events(events: list) -> list:
    """Booked events in the order they happen, then the rest as given."""
    booked = sorted(
        (event for event in events if event.booked_slot),
        key=lambda item: (
            item.booked_slot[0].isoformat(),
            0 if item.booked_slot[1] == "AM" else 1,
        ),
    )
    return [*booked, *(event for event in events if not event.booked_slot)]


def plan_team_itinerary(core, team: tuple, events: list, origins: dict,
                        start_slot: tuple, priority: list) -> TeamPlanResult:
    """Walk every member through the events they attend.

    A booked appointment is a fact: it says where somebody is at a given hour
    whatever the travel estimate says, and it puts a member whose position had
    become unknown back on the map. An estimate that cannot make it in time
    produces a risk, never a refusal and never a delayed appointment.
    """
    result = TeamPlanResult()
    result.risks.extend(staffing_risks(events, team))
    skip = unresolved_events(events, team)
    clashing = double_booked_stop_ids(events, team)

    states = {
        user: MemberState(user, origins.get(user) or origins.get("__default__"),
                          start_slot, True)
        for user in team
    }
    previous_stop: dict = {user: None for user in team}
    totals = {
        user: {"distance_km": 0.0, "travel_hours": 0.0, "route_complete": True}
        for user in team
    }

    for event in _ordered_events(events):
        attendees = resolve_participants(event.participants, team)
        if event.stop_id in skip:
            # Nobody knows who went, so nobody's position can be trusted after it.
            for user in team:
                states[user].route_known = False
                totals[user]["route_complete"] = False
            continue
        if not attendees:
            continue

        for user in attendees:
            state = states[user]
            if event.stop_id in clashing.get(user, set()):
                # They cannot be at both, and picking one would invent the rest
                # of their trip from a place they may never have been.
                state.route_known = False
                totals[user]["route_complete"] = False
                continue

            inbound_resolved = state.route_known and state.location is not None
            if inbound_resolved:
                leg = build_leg(
                    core, len(result.legs) + 1, state.location, event.point,
                    priority, None,
                )
                leg["member_id"] = user
                leg["leg_key"] = (
                    f"{previous_stop[user] or 'origin'}>{event.stop_id}"
                )
                result.legs.append(leg)
                totals[user]["distance_km"] += float(leg["distance_km"])
                totals[user]["travel_hours"] += float(leg["time_hours"])
            else:
                totals[user]["route_complete"] = False

            if event.booked_slot:
                start = event.booked_slot
                if inbound_resolved:
                    arrival = core._after_slots(
                        state.slot, int(leg["travel_half_days"])
                    )
                    if core._slot_key(arrival) > core._slot_key(start):
                        result.risks.append(
                            {
                                "kind": "cannot_reach_booked_visit",
                                "user_id": user,
                                "stop_id": event.stop_id,
                                "date": start[0].isoformat(),
                                "period": start[1],
                            }
                        )
            elif state.route_known:
                start = state.slot
            else:
                continue

            slots = [start]
            for _ in range(max(1, int(event.duration_half_days or 1)) - 1):
                slots.append(_next_slot(slots[-1]))
            result.schedule_items.append(
                {
                    "member_id": user,
                    "source_id": event.stop_id,
                    "date": slots[0][0].isoformat(),
                    "period": slots[0][1],
                    "item_type": event.kind,
                    "title": event.label or event.stop_id,
                    "inbound_travel_resolved": inbound_resolved,
                }
            )
            result.stop_updates.append(
                {
                    "member_id": user,
                    "id": event.stop_id,
                    "planned_date": slots[0][0].isoformat(),
                    "planned_start_period": slots[0][1],
                    "planned_end_date": slots[-1][0].isoformat(),
                    "planned_end_period": slots[-1][1],
                }
            )
            # The visit itself re-anchors the member, whether or not the journey
            # to it could be worked out.
            state.location = event.point
            state.slot = _next_slot(slots[-1])
            state.route_known = True
            previous_stop[user] = event.stop_id

    result.member_totals = totals
    return result
