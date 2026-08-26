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
    # Pushing aside a time somebody already accepted is exactly what applying
    # one suggestion and asking for the next is meant to avoid.
    "planned_visit_moved",
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


def _workday(day: date, avoid_weekends: bool, holidays: set) -> bool:
    if avoid_weekends and day.weekday() >= 5:
        return False
    return day.isoformat() not in holidays


def candidate_slots(start: tuple, end: date | None, avoid_weekends: bool,
                    holidays, limit: int = 60, half_days: int = 1) -> list:
    """Every half-day the visit could start in, in order.

    A visit lasting more than one half-day has to sit inside working days for
    all of them: once it is being tried it behaves like an appointment, and the
    calculation does not step an appointment over a Saturday. Checking only the
    half-day it starts in would let a Friday afternoon visit run into one.
    """
    excluded = set(holidays or ())
    span = max(1, int(half_days or 1))
    slots = []
    slot = start
    while len(slots) < limit:
        day, _ = slot
        if end and day > end:
            break
        occupied = [slot]
        for _ in range(span - 1):
            occupied.append(next_slot(occupied[-1]))
        if all(_workday(item[0], avoid_weekends, excluded) for item in occupied):
            if not (end and occupied[-1][0] > end):
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
    """What makes two risks the same risk.

    A clash between two visits and a clash between the same two plus a third
    share their kind, member and half-day. Without the stops in the key the
    bigger one looks like the one the plan already had, and the candidate that
    caused it is offered as though it changed nothing.
    """
    return (
        risk["kind"], risk.get("user_id") or risk.get("member_id"),
        risk.get("stop_id"),
        tuple(sorted(risk.get("stop_ids") or ())),
        tuple(sorted(risk.get("user_ids") or ())),
        risk.get("date"), risk.get("period"),
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
    # Customer visits only. A hotel or an airport also has no agreed time, but
    # deciding when to sleep somewhere is a different question from deciding
    # when to see a customer, and mixing them here would answer neither well.
    flexible = [
        index for index, event in enumerate(events)
        if event.kind == "customer"
        and not event.booked_slot and not event.planned_slot
    ]
    if not flexible:
        return []

    # Everything already arranged - appointments, times somebody accepted,
    # hotels and airports - is what a candidate is measured against. Comparing
    # against the appointments alone would charge one visit for the travel
    # another one already caused, and would call risks new that were there.
    baseline = plan_team_itinerary(
        core, team,
        [event for index, event in enumerate(events) if index not in flexible],
        settings["origins"], settings["initial_slot"], settings["priority"],
        destinations=settings["destinations"],
        leg_settings=settings["leg_settings"],
    )
    baseline_risks = {_risk_key(risk) for risk in baseline.risks}
    baseline_cost = _cost(baseline)

    def slots_for(event):
        return candidate_slots(
            settings["initial_slot"], settings.get("end"),
            settings.get("avoid_weekends", True),
            settings.get("holidays") or (),
            half_days=event.duration_half_days,
        )
    working = list(events)
    suggestions = []
    remaining = list(flexible)
    while remaining:
        options = {
            index: _feasible(
                core, team, working, settings, index,
                slots_for(working[index]), baseline_risks
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
