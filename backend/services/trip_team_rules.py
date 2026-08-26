"""What the team's appointments say about who can go where.

These rules read the events and answer questions about them - who attends, which
appointments overlap, what nobody has been assigned to - without moving anybody.
The scheduling in `trip_team_schedule` uses the answers to walk each member
through their trip.

Two visits in the same half-day are an ordinary team arrangement, not an error,
so everything here reports rather than refuses.
"""

from __future__ import annotations

from datetime import timedelta

def next_slot(slot: tuple) -> tuple:
    day, period = slot
    if period == "AM":
        return day, "PM"
    return day + timedelta(days=1), "AM"


def previous_slot(slot: tuple) -> tuple:
    day, period = slot
    if period == "PM":
        return day, "AM"
    return day - timedelta(days=1), "PM"


def occupied_slots(event) -> tuple:
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
        slot = next_slot(slot)
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


def invalid_assignment_events(events: list, team: tuple) -> set:
    """Events naming only people who are not on this trip.

    Nobody travels to them, but that says nothing about where the actual team
    members are, so their journeys carry on unaffected.
    """
    return {
        event.stop_id
        for event in events
        if event.participants
        and not resolve_participants(event.participants, team)
    }


def unassigned_parallel_events(events: list, team: tuple) -> set:
    """Simultaneous visits nobody has been assigned to.

    They cannot all be attended by the whole team, and until somebody is named
    there is no way to say which member ended up where.
    """
    unresolved = set()
    for group in group_by_slot(events).values():
        if len(group) < 2:
            continue
        for event in group:
            if not event.participants:
                unresolved.add(event.stop_id)
    return unresolved


def unresolved_events(events: list, team: tuple) -> set:
    """Every event that cannot be routed, whatever the reason."""
    return invalid_assignment_events(events, team) | unassigned_parallel_events(
        events, team
    )


def group_by_slot(events: list) -> dict:
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

    unassigned_slots = {
        (risk["date"], risk["period"])
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
        if (first[0].isoformat(), first[1]) in unassigned_slots:
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


def ordered_events(events: list) -> list:
    """Booked events in the order they happen, then the rest as given."""
    booked = sorted(
        (event for event in events if event.booked_slot),
        key=lambda item: (
            item.booked_slot[0].isoformat(),
            0 if item.booked_slot[1] == "AM" else 1,
        ),
    )
    return [*booked, *(event for event in events if not event.booked_slot)]
