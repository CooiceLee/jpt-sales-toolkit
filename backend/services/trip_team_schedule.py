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

from math import ceil
from dataclasses import dataclass, field
from datetime import date

from .trip_leg_engine import build_leg
from .trip_team_rules import (
    double_booked_stop_ids,
    invalid_assignment_events,
    next_slot,
    ordered_events,
    previous_slot,
    resolve_participants,
    staffing_risks,
    unassigned_parallel_events,
)


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
    # What the customer agreed to. A fact: the plan is built around it.
    booked_slot: tuple | None = None
    # What we decided, and have not asked the customer about. A plan: it holds
    # its place, but travel can push it later without anything being wrong.
    planned_slot: tuple | None = None
    preferred_period: str = "auto"
    # Marked as agreed with the customer. Kept on the stop so that saving the
    # route does not forget what the user just recorded.
    schedule_locked: bool = False
    label: str = ""
    # Whether the customer has agreed to this time. Carried onto the itinerary
    # so that a printed day says which visits are settled and which are not -
    # the one thing a reader checks before sending the plan to anybody.
    confirmation_status: str | None = None


@dataclass
class TeamPlanResult:
    legs: list = field(default_factory=list)
    schedule_items: list = field(default_factory=list)
    stop_updates: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    member_totals: dict = field(default_factory=dict)

@dataclass
class TeamScheduleContext:
    """Everything one scheduling run carries as it walks the events.

    The fixed facts about the trip are worked out once when the run starts, so
    the scheduling below asks this rather than recomputing or passing a dozen
    arguments down.
    """

    team: tuple
    result: TeamPlanResult
    states: dict
    previous_stop: dict
    lane_sequence: dict
    lane_order: dict
    totals: dict
    invalid: set
    unassigned: set
    clashing: dict
    # Customer visits need working hours; travel, hotels and rests do not.
    avoid_weekends: bool = True
    holidays: tuple = ()


def build_member_leg(core, member_id, from_point, to_point, leg_key,
                     priority, leg_settings, sequence_no: int = 1) -> tuple:
    """One member's journey between two places, with everything v0.12 learned.

    Reuses the stored transport choice and the airports recorded for this
    member's own leg, and expands a flown connection into its ground transfers,
    so team planning does not quietly lose the airport handling that single-path
    planning already has.
    """
    override = (leg_settings or {}).get((member_id, leg_key))
    # The sequence is the member's own lane order: legs are read back sorted by
    # it, so leaving every leg at 1 would lose each person's route order.
    leg = build_leg(core, sequence_no, from_point, to_point, priority, override)
    leg["member_id"] = member_id
    leg["leg_key"] = leg_key
    segments = core._expand_flight_leg(leg, from_point, to_point, priority)
    if segments:
        leg["segments"] = segments
        leg["distance_km"] = round(
            sum(item["distance_km"] for item in segments), 1
        )
        leg["time_hours"] = round(sum(item["time_hours"] for item in segments), 1)
        elapsed = sum(
            int(item["travel_half_days"]) + int(item["stay_half_days"] or 0)
            for item in segments
        )
        leg["travel_half_days"] = min(60, elapsed)
    return leg, int(leg["travel_half_days"])



def _next_order(ctx: "TeamScheduleContext", user) -> int | None:
    """The next position in this member's own run of items.

    Within one half-day a journey and the visit it leads to both appear, and the
    journey has to come first. Recording order is that order, so a counter per
    member is enough; an event nobody on the trip attends has no lane to sit in.
    """
    if user is None:
        return None
    ctx.lane_order[user] += 1
    return ctx.lane_order[user]


def _spread_slots(start: tuple, half_days) -> list:
    """The half-days one event occupies, starting where it was placed."""
    slots = [start]
    for _ in range(max(1, int(half_days or 1)) - 1):
        slots.append(next_slot(slots[-1]))
    return slots


def _record_travel(ctx: TeamScheduleContext, user, leg, from_slot, elapsed):
    """Put a journey on the timeline, and on the leg itself.

    Travel has to be visible or the customers look teleported. A flown leg has
    already been expanded into its ground transfers, and each of those is its
    own line on the timeline.
    """
    slots = _spread_slots(from_slot, elapsed)
    leg["planned_start_date"] = slots[0][0].isoformat() if elapsed else None
    leg["planned_start_period"] = slots[0][1] if elapsed else None
    leg["planned_end_date"] = slots[-1][0].isoformat() if elapsed else None
    leg["planned_end_period"] = slots[-1][1] if elapsed else None
    if not elapsed:
        return
    _record_journey_parts(ctx, user, leg, from_slot, elapsed)


def _travel_items(ctx, user, leg, part, slots, role=None):
    """One movement, on every half-day it occupies.

    A journey that runs from Sunday afternoon to Tuesday morning appears on all
    four of those half-days, the way a visit of the same length does. Recording
    only the first leaves the days in between looking free, and a two-day drive
    reading as half a day.
    """
    order = _next_order(ctx, user)
    return [
        {
            "member_id": user,
            "lane_order": order,
            "source_id": leg["leg_key"] if role is None
            else f"{leg['leg_key']}#{role}",
            "date": slot[0].isoformat(),
            "period": slot[1],
            "item_type": "leg",
            "title": (
                f"{part.get('from_label') or '-'} → "
                f"{part.get('to_label') or '-'}"
            ),
            "selected_mode": part.get("selected_mode"),
            "half_day_index": index,
            "half_day_count": len(slots),
            "inbound_travel_resolved": True,
        }
        for index, slot in enumerate(slots, start=1)
    ]


def _record_journey_parts(ctx: TeamScheduleContext, user, leg, from_slot,
                          elapsed):
    """Each movement at its own hour, and each airport wait between them.

    A flown connection is a drive to the airport, the flight, and a drive at the
    other end. Recording them all at the departure half-day says the whole of
    Shenzhen to Germany happened before lunch, and leaves the days it really
    takes looking free for something else to be booked into.
    """
    segments = leg.get("segments")
    if not segments:
        ctx.result.schedule_items.extend(
            _travel_items(ctx, user, leg, leg, _spread_slots(from_slot, elapsed))
        )
        return
    cursor = from_slot
    for segment in segments:
        # A part somebody said takes no scheduled time is still a movement and
        # is still shown, but it must not push the rest of the trip along.
        span = int(segment.get("travel_half_days") or 0)
        slots = _spread_slots(cursor, span) if span else [cursor]
        ctx.result.schedule_items.extend(
            _travel_items(ctx, user, leg, segment, slots, segment["role"])
        )
        for _ in range(span):
            cursor = next_slot(cursor)
        waiting = int(segment.get("stay_half_days") or 0)
        if not waiting:
            continue
        waits = _spread_slots(cursor, waiting)
        order = _next_order(ctx, user)
        ctx.result.schedule_items.extend(
            {
                "member_id": user,
                "lane_order": order,
                "source_id": f"{leg['leg_key']}#{segment['role']}-stay",
                "date": slot[0].isoformat(),
                "period": slot[1],
                "item_type": "airport",
                "title": segment.get("stay_label") or segment.get("to_label"),
                "half_day_index": index,
                "half_day_count": len(waits),
                "inbound_travel_resolved": True,
            }
            for index, slot in enumerate(waits, start=1)
        )
        for _ in range(waiting):
            cursor = next_slot(cursor)


def _record_event(ctx: TeamScheduleContext, event, user, slots,
                  inbound_resolved):
    """Put an event on the timeline, and on the stop it belongs to.

    A visit that lasts more than one half-day occupies every one of them, so it
    appears in each. Recording only the first would leave the afternoon of a
    day-long visit looking free, which is how a second thing gets booked into
    it. The stop itself is still one row, from its start to its end.
    """
    order = _next_order(ctx, user)
    for index, slot in enumerate(slots, start=1):
        ctx.result.schedule_items.append(
            {
                "member_id": user,
                "lane_order": order,
                "source_id": event.stop_id,
                "date": slot[0].isoformat(),
                "period": slot[1],
                "item_type": event.kind,
                "title": event.label or event.stop_id,
                "half_day_index": index,
                "half_day_count": len(slots),
                "confirmation_status": event.confirmation_status,
                "inbound_travel_resolved": inbound_resolved,
            }
        )
    ctx.result.stop_updates.append(
        {
            "member_id": user,
            "id": event.stop_id,
            "stop_kind": event.kind,
            "planned_date": slots[0][0].isoformat(),
            "planned_start_period": slots[0][1],
            "planned_end_date": slots[-1][0].isoformat(),
            "planned_end_period": slots[-1][1],
            # The route was worked out from how long the visit takes and which
            # half of the day it should be in. Saving the route without them
            # leaves the stop stating a length the schedule beside it denies.
            "duration_half_days": int(event.duration_half_days or 0),
            "stay_days": max(1, ceil(int(event.duration_half_days or 0) / 2)),
            "preferred_period": event.preferred_period,
            "schedule_locked": 1 if event.schedule_locked else 0,
        }
    )


def _lose_position(ctx: TeamScheduleContext, user):
    """Stop claiming to know where somebody is.

    While a position is unknown no travel is invented from it; a later booked
    appointment says where they are and puts it back.
    """
    ctx.states[user].route_known = False
    ctx.totals[user]["route_complete"] = False


def _initialize_team_context(team: tuple, events: list, origins: dict,
                             start_slot: tuple,
                             departures: dict | None = None,
                             avoid_weekends: bool = True,
                             holidays: tuple = ()) -> TeamScheduleContext:
    """Everybody at their departure point, and what the appointments imply.

    A member with a departure day of their own starts there instead of on the
    team's. Somebody joining the trip a week in has not been travelling for
    that week, and showing them as having left with everybody else puts a
    flight on a day they were still at their desk.
    """
    result = TeamPlanResult()
    result.risks.extend(staffing_risks(events, team))
    return TeamScheduleContext(
        team=team,
        result=result,
        states={
            user: MemberState(
                user, origins.get(user) or origins.get("__default__"),
                (departures or {}).get(user) or start_slot, True,
            )
            for user in team
        },
        previous_stop={user: None for user in team},
        lane_sequence={user: 0 for user in team},
        lane_order={user: 0 for user in team},
        totals={
            user: {
                "distance_km": 0.0, "travel_hours": 0.0, "route_complete": True,
                "calculated_end_date": None, "calculated_end_period": None,
            }
            for user in team
        },
        invalid=invalid_assignment_events(events, team),
        unassigned=unassigned_parallel_events(events, team),
        clashing=double_booked_stop_ids(events, team),
        avoid_weekends=avoid_weekends,
        holidays=tuple(holidays),
    )


def _build_inbound_legs(core, ctx: TeamScheduleContext, event, travelling,
                        priority, leg_settings) -> dict:
    """The journey each member still on the map takes to reach this event."""
    inbound: dict = {}
    for user in travelling:
        state = ctx.states[user]
        if not (state.route_known and state.location is not None):
            continue
        leg_key = f"{ctx.previous_stop[user] or 'origin'}>{event.stop_id}"
        inbound[user] = build_member_leg(
            core, user, state.location, event.point, leg_key, priority,
            leg_settings, ctx.lane_sequence[user] + 1,
        )
    return inbound


def _event_start_slot(core, ctx: TeamScheduleContext, event, travelling,
                      inbound):
    """When this event begins, or None if there is no way to say.

    A booked appointment is a fact and needs no arrival time. Anything else
    starts once its last attendee has got there, which cannot be worked out
    while somebody's position is unknown. A time we planned ourselves holds that
    place if the team can be there by then, and otherwise gives way to when they
    actually arrive - it was our decision, not the customer's.
    """
    if event.booked_slot:
        return event.booked_slot
    arrivals = [
        core._after_slots(ctx.states[user].slot, elapsed)
        for user, (_, elapsed) in inbound.items()
    ]
    if len(inbound) < len(travelling) or not arrivals:
        return None
    earliest = max(arrivals, key=core._slot_key)
    if not event.planned_slot:
        return _workable_start(core, ctx, event, earliest)
    if core._slot_key(event.planned_slot) >= core._slot_key(earliest):
        return event.planned_slot
    ctx.result.risks.append(
        {
            "kind": "planned_visit_moved",
            "stop_id": event.stop_id,
            "planned_date": event.planned_slot[0].isoformat(),
            "planned_period": event.planned_slot[1],
            "date": earliest[0].isoformat(),
            "period": earliest[1],
        }
    )
    return _workable_start(core, ctx, event, earliest)


def _workable_start(core, ctx: TeamScheduleContext, event, slot: tuple) -> tuple:
    """The first half-day this event can actually begin on.

    A customer visit is called on in business hours, and the salesperson may
    have said they want the morning or the afternoon. A hotel, a rest or an
    airport transfer is none of those things and sits wherever the journey
    leaves it.
    """
    if event.kind == "free":
        return slot
    return core._seek_preferred_period(
        core._next_work_slot(slot, ctx.avoid_weekends, list(ctx.holidays)),
        event.preferred_period,
        ctx.avoid_weekends,
        list(ctx.holidays),
    )


def _record_unattended_event(ctx: TeamScheduleContext, event) -> None:
    """An appointment nobody can be routed to still happened."""
    if event.booked_slot:
        _record_event(
            ctx, event, None,
            _spread_slots(event.booked_slot, event.duration_half_days), False,
        )


def _event_slots(core, ctx: TeamScheduleContext, event, start: tuple) -> list:
    """The half-days one event occupies once it has begun.

    A two-day visit that starts on a Friday finishes on the Monday: nobody is
    received on the Saturday in between. An appointment the customer agreed to
    is kept where they put it, weekend or not.
    """
    if event.kind == "free" or event.booked_slot:
        return _spread_slots(start, event.duration_half_days)
    slots, _ = core._allocate_work_slots(
        start, max(1, int(event.duration_half_days or 1)),
        ctx.avoid_weekends, list(ctx.holidays),
    )
    return slots or _spread_slots(start, event.duration_half_days)


def _schedule_team_event(core, ctx: TeamScheduleContext, event, priority,
                         leg_settings) -> None:
    """Move everybody who attends this event to it, and mark what cannot be."""
    if event.stop_id in ctx.invalid:
        # Nobody on this trip goes, but that says nothing about where the real
        # members are, so their journeys are untouched.
        _record_unattended_event(ctx, event)
        return

    if event.stop_id in ctx.unassigned:
        # Any member might have gone, so none of their positions can be trusted
        # afterwards. The appointment itself is still real.
        for user in ctx.team:
            _lose_position(ctx, user)
        _record_unattended_event(ctx, event)
        return

    attendees = resolve_participants(event.participants, ctx.team)
    if not attendees:
        return

    # Members who cannot be at this event and another at the same hour keep the
    # appointment but lose their position: choosing one of the two would invent
    # the rest of their trip from a place they may never have been.
    conflicted = [
        user for user in attendees
        if event.stop_id in ctx.clashing.get(user, set())
    ]
    travelling = [user for user in attendees if user not in conflicted]

    inbound = _build_inbound_legs(
        core, ctx, event, travelling, priority, leg_settings
    )
    start = _event_start_slot(core, ctx, event, travelling, inbound)
    if start is None:
        return
    slots = _event_slots(core, ctx, event, start)

    for user in conflicted:
        _record_event(ctx, event, user, slots, False)
        _lose_position(ctx, user)

    for user in travelling:
        _attend_event(core, ctx, event, user, slots, start, inbound)


def _attend_event(core, ctx: TeamScheduleContext, event, user, slots, start,
                  inbound) -> None:
    """One member arrives, is recorded at the event, and waits there."""
    resolved = user in inbound
    if resolved:
        leg, elapsed = inbound[user]
        ctx.lane_sequence[user] += 1
        _record_travel(ctx, user, leg, ctx.states[user].slot, elapsed)
        ctx.result.legs.append(leg)
        ctx.totals[user]["distance_km"] += float(leg["distance_km"])
        ctx.totals[user]["travel_hours"] += float(leg["time_hours"])
        arrival = core._after_slots(ctx.states[user].slot, elapsed)
        if event.booked_slot and core._slot_key(arrival) > core._slot_key(start):
            # The appointment stays where the customer put it. Not making it in
            # time is something to report, never a reason to move the meeting.
            ctx.result.risks.append(
                {
                    "kind": "cannot_reach_booked_visit",
                    "user_id": user,
                    "stop_id": event.stop_id,
                    "date": start[0].isoformat(),
                    "period": start[1],
                }
            )
    else:
        ctx.totals[user]["route_complete"] = False
    _record_event(ctx, event, user, slots, resolved)
    state = ctx.states[user]
    state.location = event.point
    state.slot = next_slot(slots[-1])
    state.route_known = True
    ctx.previous_stop[user] = event.stop_id


def _schedule_member_return(core, ctx: TeamScheduleContext, user, destinations,
                            priority, leg_settings) -> None:
    """One member's journey home. A trip is not complete until they are back."""
    state = ctx.states[user]
    home = (destinations or {}).get(user) or (destinations or {}).get(
        "__default__"
    )
    if not home or not state.route_known or state.location is None:
        if home:
            ctx.totals[user]["route_complete"] = False
        return
    if ctx.previous_stop[user] is None:
        return
    leg, elapsed = build_member_leg(
        core, user, state.location, home,
        f"{ctx.previous_stop[user]}>destination", priority, leg_settings,
        ctx.lane_sequence[user] + 1,
    )
    ctx.lane_sequence[user] += 1
    _record_travel(ctx, user, leg, state.slot, elapsed)
    ctx.result.legs.append(leg)
    ctx.totals[user]["distance_km"] += float(leg["distance_km"])
    ctx.totals[user]["travel_hours"] += float(leg["time_hours"])
    state.slot = core._after_slots(state.slot, elapsed)
    state.location = home


def _finalize_member_totals(ctx: TeamScheduleContext) -> None:
    """When each member finishes, which is what a late return is measured from."""
    for user in ctx.team:
        last = previous_slot(ctx.states[user].slot)
        ctx.totals[user]["calculated_end_date"] = last[0].isoformat()
        ctx.totals[user]["calculated_end_period"] = last[1]
    ctx.result.member_totals = ctx.totals


def plan_team_itinerary(core, team: tuple, events: list, origins: dict,
                        start_slot: tuple, priority: list,
                        destinations: dict | None = None,
                        leg_settings: dict | None = None,
                        departures: dict | None = None,
                        avoid_weekends: bool = True,
                        holidays: tuple = ()) -> TeamPlanResult:
    """Walk every member through the events they attend, and home again.

    A booked appointment is a fact: it says where somebody is at a given hour
    whatever the travel estimate says, and it puts a member whose position had
    become unknown back on the map. An estimate that cannot make it in time
    produces a risk, never a refusal and never a delayed appointment.
    """
    ctx = _initialize_team_context(
        team, events, origins, start_slot, departures, avoid_weekends, holidays
    )
    for event in ordered_events(events):
        _schedule_team_event(core, ctx, event, priority, leg_settings)
    for user in team:
        _schedule_member_return(
            core, ctx, user, destinations, priority, leg_settings
        )
    _finalize_member_totals(ctx)
    return ctx.result
