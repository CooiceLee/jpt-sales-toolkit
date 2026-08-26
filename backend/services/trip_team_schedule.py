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
from datetime import date


@dataclass
class MemberState:
    """Where a member is, and when they are free again."""

    user_id: str
    location: dict
    slot: tuple


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


def resolve_participants(event_participants, team: tuple) -> tuple:
    """Who travels to an event.

    An event with nobody named is attended by the whole team: a plan in team
    mode has already said who is travelling, so silence means everyone rather
    than nobody.
    """
    named = tuple(user for user in event_participants or () if user in team)
    return named or team


def group_by_slot(events: list[TeamEvent]) -> dict:
    """Booked events that share a half-day, keyed by that half-day."""
    groups: dict = {}
    for event in events:
        if event.booked_slot:
            groups.setdefault(event.booked_slot, []).append(event)
    return groups


def staffing_risks(events: list[TeamEvent], team: tuple) -> list[dict]:
    """Report who cannot be in two places at once, and what is unstaffed.

    Two visits in the same half-day are legitimate when different colleagues
    cover them, so this reports rather than refuses.
    """
    risks: list[dict] = []
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
            continue
        seen: dict = {}
        for event in group:
            for user in resolve_participants(event.participants, team):
                seen.setdefault(user, []).append(event.stop_id)
        for user, stop_ids in sorted(seen.items()):
            if len(stop_ids) > 1:
                risks.append(
                    {
                        "kind": "member_double_booked",
                        "user_id": user,
                        "date": slot[0].isoformat(),
                        "period": slot[1],
                        "stop_ids": sorted(stop_ids),
                    }
                )
    return risks


def member_lanes(events: list[TeamEvent], team: tuple) -> dict:
    """The events each member has to attend, in the order they were given."""
    lanes: dict = {user: [] for user in team}
    for event in events:
        for user in resolve_participants(event.participants, team):
            lanes.setdefault(user, []).append(event)
    return lanes
