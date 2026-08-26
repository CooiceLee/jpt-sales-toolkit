"""Where the visits with no agreed time could go.

There is no second scheduler here. A candidate half-day is tried by giving the
flexible visit that time and running the real team calculation, so travel,
airports, merges, weekends and each member's own clock are all accounted for by
the code that already knows how to do it. Nothing is written; the caller decides
whether to keep a suggestion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from .trip_team_rules import next_slot
from .trip_team_schedule import plan_team_itinerary

# A candidate that produces one of these is not offered: the arrangement it
# implies is one the user would have to undo.
BLOCKING_RISKS = frozenset({
    "member_double_booked",
    "cannot_reach_booked_visit",
    "participant_not_in_trip_team",
    "parallel_visits_unassigned",
})


@dataclass
class Suggestion:
    stop_id: str
    date: str | None
    period: str | None
    participants: tuple
    added_travel_hours: float
    added_distance_km: float
    reason: str = "suggested"


def candidate_slots(start: tuple, end: date | None, avoid_weekends: bool,
                    holidays, limit: int = 60) -> list:
    """Every half-day the visit could be given, in order."""
    slots = []
    slot = start
    while len(slots) < limit:
        day, period = slot
        if end and day > end:
            break
        if not avoid_weekends or day.weekday() < 5:
            if day.isoformat() not in set(holidays or ()):
                slots.append(slot)
        slot = next_slot(slot)
    return slots


def _cost(result) -> tuple:
    """What this arrangement costs the team: time first, then distance."""
    totals = result.member_totals.values()
    return (
        round(sum(item["travel_hours"] for item in totals), 2),
        round(sum(item["distance_km"] for item in totals), 1),
    )


def _blocked(result, baseline_risks: set) -> bool:
    for risk in result.risks:
        if risk["kind"] not in BLOCKING_RISKS:
            continue
        if _risk_key(risk) not in baseline_risks:
            return True
    return False


def _risk_key(risk: dict) -> tuple:
    return (
        risk["kind"], risk.get("user_id") or risk.get("member_id"),
        risk.get("stop_id"), risk.get("date"), risk.get("period"),
    )


def _simulate(core, team, events, settings, flexible_index, slot):
    """Run the real calculation with one flexible visit given a time."""
    trial = list(events)
    trial[flexible_index] = replace(trial[flexible_index], booked_slot=slot)
    return plan_team_itinerary(
        core, team, trial, settings["origins"], settings["initial_slot"],
        settings["priority"], destinations=settings["destinations"],
        leg_settings=settings["leg_settings"],
    )


def _feasible(core, team, events, settings, index, slots, baseline_risks):
    """The times this visit could take, cheapest first."""
    options = []
    for slot in slots:
        result = _simulate(core, team, events, settings, index, slot)
        if _blocked(result, baseline_risks):
            continue
        options.append((_cost(result), slot))
    options.sort()
    return options


def suggest_flexible_visits(core, team, events, settings) -> list:
    """Propose a time for every visit with no agreed one.

    The visit with the fewest workable times is placed first: settling an easy
    one early can take the only slot a hard one had. Among the times that work,
    the cheapest in travel is chosen, which is the whole of the preference - no
    solver, and no rearranging of appointments the customer already agreed to.

    Nobody is assigned to anybody: a flexible visit is planned for whoever it
    already names, and a visit naming nobody is the whole team, which is what
    the rest of team planning already means by it.
    """
    flexible = [
        index for index, event in enumerate(events) if not event.booked_slot
    ]
    if not flexible:
        return []

    baseline = plan_team_itinerary(
        core, team, [event for event in events if event.booked_slot],
        settings["origins"], settings["initial_slot"], settings["priority"],
        destinations=settings["destinations"],
        leg_settings=settings["leg_settings"],
    )
    baseline_risks = {_risk_key(risk) for risk in baseline.risks}
    baseline_cost = _cost(baseline)

    slots = candidate_slots(
        settings["initial_slot"], settings.get("end"),
        settings.get("avoid_weekends", True), settings.get("holidays") or (),
    )
    working = list(events)
    suggestions = []
    remaining = list(flexible)
    while remaining:
        options = {
            index: _feasible(
                core, team, working, settings, index, slots, baseline_risks
            )
            for index in remaining
        }
        # Fewest ways to place it goes first, so an easy visit cannot take the
        # only time a hard one had.
        index = min(remaining, key=lambda item: (len(options[item]), item))
        event = working[index]
        best = options[index][0] if options[index] else None
        if best is None:
            suggestions.append(
                Suggestion(event.stop_id, None, None, event.participants,
                           0.0, 0.0, "no_workable_time")
            )
            remaining.remove(index)
            continue
        (hours, distance), slot = best
        working[index] = replace(event, booked_slot=slot)
        suggestions.append(
            Suggestion(
                event.stop_id, slot[0].isoformat(), slot[1], event.participants,
                round(hours - baseline_cost[0], 2),
                round(distance - baseline_cost[1], 1),
            )
        )
        baseline_cost = (hours, distance)
        remaining.remove(index)
    return suggestions
