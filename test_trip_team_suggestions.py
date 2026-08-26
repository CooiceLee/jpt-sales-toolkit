"""Suggesting a time for the visits nobody has agreed one for.

The suggestions come from running the real team calculation with a candidate
time, so what is checked here is the search around it: that appointments are
never moved, that a shared visit only lands where everybody can be, that
weekends are respected, that "nowhere works" is an answer, and that nothing is
written until somebody says so.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_suggest_")

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from backend.services.review_service import ReviewService  # noqa: E402
from backend.services.trip_team_schedule import TeamEvent  # noqa: E402
from backend.services.trip_team_suggestions import (  # noqa: E402
    candidate_slots,
    suggest_flexible_visits,
)
from backend.startup_upgrade import initialize_database_safely  # noqa: E402

SHANGHAI = {"lat": 31.2304, "lng": 121.4737, "label": "Shanghai",
            "kind": "origin", "stop_id": None}


def place(lat, lng, label, stop_id):
    return {"lat": lat, "lng": lng, "label": label, "kind": "stop",
            "stop_id": stop_id}


FRANKFURT = place(50.1109, 8.6821, "Frankfurt", "fra")
STUTTGART = place(48.7758, 9.1829, "Stuttgart", "stu")
MUNICH = place(48.1351, 11.5820, "Munich", "muc")
PARIS = place(48.8566, 2.3522, "Paris", "par")
OSLO = place(59.9139, 10.7522, "Oslo", "osl")


def visit(stop_id, point, attendees, slot=None, half_days=1):
    return TeamEvent(stop_id, "customer", point, half_days, tuple(attendees),
                     slot, label=stop_id)


def settings(team, **overrides):
    base = {
        "origins": {"__default__": SHANGHAI},
        "destinations": {"__default__": SHANGHAI},
        "initial_slot": (date(2026, 9, 14), "AM"),
        "priority": ["flight", "drive", "ground_public"],
        "leg_settings": {},
        "end": date(2026, 9, 30),
        "avoid_weekends": True,
        "holidays": (),
    }
    base.update(overrides)
    return base


def check_single_member_flexible(service) -> None:
    """A flexible visit between two appointments gets a workable time."""
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
        visit("muc", MUNICH, ["zhang"], (date(2026, 9, 23), "PM")),
    ]
    found = suggest_flexible_visits(service, team, events, settings(team))
    assert len(found) == 1, found
    suggestion = found[0]
    assert suggestion.stop_id == "stu"
    assert suggestion.date, f"no time was found for a visit that fits: {found}"
    assert suggestion.period in ("AM", "PM")
    assert suggestion.reason == "suggested"
    # It has to sit between the two appointments it is squeezed between.
    assert "2026-09-16" <= suggestion.date <= "2026-09-23", suggestion


def check_shared_flexible_needs_everybody(service) -> None:
    """A visit two people attend only lands where both of them can be."""
    team = ("zhang", "li")
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("par", PARIS, ["li"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang", "li"]),
    ]
    found = suggest_flexible_visits(service, team, events, settings(team))
    shared = [item for item in found if item.stop_id == "stu"][0]
    assert shared.date, f"a shared visit must still be placeable: {found}"
    assert set(shared.participants) == {"zhang", "li"}

    # The real test is not which half-day it picked - visiting Stuttgart before
    # the two appointments is perfectly good - but that both of them can
    # actually be there, and that both are recorded as attending.
    from backend.services.trip_team_schedule import plan_team_itinerary
    suggested = date.fromisoformat(shared.date), shared.period
    trial = [*events[:2], visit("stu", STUTTGART, ["zhang", "li"], suggested)]
    result = plan_team_itinerary(
        service, team, trial, {"__default__": SHANGHAI},
        (date(2026, 9, 14), "AM"), ["flight", "drive", "ground_public"],
        destinations={"__default__": SHANGHAI}, leg_settings={},
    )
    unreachable = [
        risk for risk in result.risks
        if risk["kind"] == "cannot_reach_booked_visit"
    ]
    assert not unreachable, (
        f"suggested a time somebody cannot get to: {unreachable}"
    )
    attending = {
        item["member_id"] for item in result.schedule_items
        if item["source_id"] == "stu" and item["item_type"] != "leg"
    }
    assert attending == {"zhang", "li"}, (
        f"a shared visit must place both of them, got {attending}"
    )


def check_appointments_are_never_moved(service) -> None:
    """Fitting a flexible visit must not disturb an agreed time."""
    team = ("zhang",)
    booked = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("muc", MUNICH, ["zhang"], (date(2026, 9, 17), "AM")),
    ]
    events = [*booked, visit("stu", STUTTGART, ["zhang"])]
    before = [(item.stop_id, item.booked_slot) for item in events]
    suggest_flexible_visits(service, team, events, settings(team))
    after = [(item.stop_id, item.booked_slot) for item in events]
    assert before == after, (
        "the events handed in were rewritten; suggesting must not mutate them"
    )
    for event in booked:
        assert event.booked_slot is not None, "an appointment lost its time"


def check_weekends_are_not_suggested(service) -> None:
    """Suggestions land on working days; appointments keep whatever they hold."""
    team = ("zhang",)
    # 2026-09-19 and 09-20 are a Saturday and a Sunday.
    slots = candidate_slots((date(2026, 9, 18), "AM"), date(2026, 9, 22),
                            True, ())
    assert not any(day.isoformat() in ("2026-09-19", "2026-09-20")
                   for day, _ in slots), slots
    holiday = candidate_slots((date(2026, 9, 21), "AM"), date(2026, 9, 23),
                              True, ("2026-09-21",))
    assert not any(day.isoformat() == "2026-09-21" for day, _ in holiday)

    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 18), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
    ]
    found = suggest_flexible_visits(service, team, events, settings(team))
    assert found[0].date not in ("2026-09-19", "2026-09-20"), found[0]

    # An appointment on a Saturday is a fact and stays where the customer put it.
    weekend_booked = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 19), "AM")),
    ]
    suggest_flexible_visits(service, team, weekend_booked, settings(team))
    assert weekend_booked[0].booked_slot == (date(2026, 9, 19), "AM")


def check_no_workable_time_is_an_answer(service) -> None:
    """When nothing fits, say so instead of forcing it in or failing."""
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
    ]
    # A window with no working half-day left in it at all.
    narrow = settings(team, initial_slot=(date(2026, 9, 19), "AM"),
                      end=date(2026, 9, 20))
    found = suggest_flexible_visits(service, team, events, narrow)
    suggestion = [item for item in found if item.stop_id == "stu"][0]
    assert suggestion.date is None, suggestion
    assert suggestion.reason == "no_workable_time", suggestion


def check_the_scarce_slot_goes_to_the_visit_with_no_alternative(service) -> None:
    """The visit with fewest workable times is placed first.

    Two working half-days are left, and they cannot hold both Stuttgart and
    Oslo: whichever is visited first puts Zhang too far away for the other.
    Stuttgart fits in either half-day, Oslo in only one, so the one with no
    alternative takes it. Working through the list in order would give the
    scarce half-day to Stuttgart, which had somewhere else to go.
    """
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
        visit("osl", OSLO, ["zhang"]),
    ]
    tight = settings(team, end=date(2026, 9, 17), priority=["drive"])
    found = {item.stop_id: item for item in
             suggest_flexible_visits(service, team, events, tight)}
    assert found["osl"].date == "2026-09-17", (
        f"the visit with only one workable time must get it: {found['osl']}"
    )
    assert found["stu"].reason == "no_workable_time", (
        f"Stuttgart cannot also fit, and saying so is the answer: {found['stu']}"
    )
    assert found["stu"].date is None


def check_an_applied_suggestion_holds_its_place(service) -> None:
    """A time we decided is honoured, and is not suggested all over again.

    Applying a suggestion saves the date and period without locking the visit,
    because the customer has not agreed to anything. If the calculation only
    looked at locked visits, the button would appear to work and the next
    preview would treat the visit as unscheduled.
    """
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        TeamEvent("stu", "customer", STUTTGART, 1, ("zhang",), None,
                  (date(2026, 9, 21), "AM"), label="stu"),
    ]
    # Already arranged, so there is nothing left to suggest.
    assert suggest_flexible_visits(service, team, events, settings(team)) == []

    from backend.services.trip_team_schedule import plan_team_itinerary
    result = plan_team_itinerary(
        service, team, events, {"__default__": SHANGHAI},
        (date(2026, 9, 14), "AM"), ["flight", "drive", "ground_public"],
        destinations={"__default__": SHANGHAI}, leg_settings={},
    )
    placed = [
        item for item in result.schedule_items
        if item["source_id"] == "stu" and item["item_type"] != "leg"
    ]
    assert placed, "the visit never reached the schedule"
    assert (placed[0]["date"], placed[0]["period"]) == ("2026-09-21", "AM"), (
        f"an applied suggestion must hold its place: {placed[0]}"
    )


def check_saved_times_reach_the_calculation(service) -> None:
    """A saved time becomes an appointment or a plan, depending on the lock.

    This is the step Apply depends on: without it the date the user applied is
    read off the stop and thrown away, and the visit comes back as unscheduled.
    """
    from backend.services.trip_team_adapter import build_team_events

    def stop(stop_id, locked):
        return {
            "id": stop_id, "stop_kind": "customer", "customer_name": stop_id,
            "lat": 48.7758, "lng": 9.1829, "duration_half_days": 1,
            "planned_date": "2026-09-21", "planned_start_period": "AM",
            "schedule_locked": locked, "briefing": {"participants": []},
        }

    events = {
        event.stop_id: event for event in build_team_events(
            service,
            {"stops": [stop("locked", 1), stop("applied", 0),
                       {**stop("open", 0), "planned_date": None,
                        "planned_start_period": None}]},
            {},
        )
    }
    agreed = events["locked"]
    assert agreed.booked_slot == (date(2026, 9, 21), "AM"), agreed
    assert agreed.planned_slot is None

    applied = events["applied"]
    assert applied.booked_slot is None, (
        "an unlocked visit is not an appointment: the customer agreed nothing"
    )
    assert applied.planned_slot == (date(2026, 9, 21), "AM"), (
        f"an applied suggestion must reach the calculation: {applied}"
    )

    assert events["open"].booked_slot is None
    assert events["open"].planned_slot is None


def check_a_planned_time_gives_way_to_travel(service) -> None:
    """Our own plan moves if the team cannot be there; an appointment does not."""
    from backend.services.trip_team_schedule import plan_team_itinerary

    team = ("zhang",)
    # Frankfurt on the 16th, then Stuttgart planned for the same morning, which
    # nobody can be in two places for.
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        TeamEvent("stu", "customer", STUTTGART, 1, ("zhang",), None,
                  (date(2026, 9, 16), "AM"), label="stu"),
    ]
    result = plan_team_itinerary(
        service, team, events, {"__default__": SHANGHAI},
        (date(2026, 9, 14), "AM"), ["drive"],
        destinations={"__default__": SHANGHAI}, leg_settings={},
    )
    moved = [risk for risk in result.risks if risk["kind"] == "planned_visit_moved"]
    assert moved, f"a planned time that slipped must be reported: {result.risks}"
    assert moved[0]["stop_id"] == "stu"
    assert moved[0]["planned_date"] == "2026-09-16"
    assert (moved[0]["date"], moved[0]["period"]) > ("2026-09-16", "AM"), moved[0]
    # And it is not reported as an appointment that could not be reached: it was
    # never an appointment.
    assert not [
        risk for risk in result.risks
        if risk["kind"] == "cannot_reach_booked_visit"
        and risk.get("stop_id") == "stu"
    ]


def check_a_bigger_clash_is_not_the_old_clash(service) -> None:
    """A candidate that makes an existing clash worse is not offered.

    The plan already has two visits booked over each other. A flexible visit put
    in the same half-day makes it a three-way clash - a different risk, and one
    the candidate caused. Comparing only kind, member and half-day would read it
    as the risk that was already there and offer the candidate anyway.
    """
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("par", PARIS, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
    ]
    found = suggest_flexible_visits(service, team, events, settings(team))
    suggestion = [item for item in found if item.stop_id == "stu"][0]
    assert suggestion.date != "2026-09-16" or suggestion.period != "AM", (
        "a candidate that joins an existing clash must not be suggested: "
        f"{suggestion}"
    )


def check_a_long_visit_does_not_run_into_a_weekend(service) -> None:
    """A visit over several half-days sits inside working days for all of them."""
    # 2026-09-18 is a Friday. A whole-day visit starting Friday PM would take
    # Saturday morning, and the calculation does not step a fixed time over a
    # weekend, so that half-day must not be offered as a start at all.
    starts = candidate_slots((date(2026, 9, 18), "AM"), date(2026, 9, 22),
                             True, (), half_days=2)
    assert (date(2026, 9, 18), "AM") in starts, starts
    assert (date(2026, 9, 18), "PM") not in starts, (
        f"a whole-day visit cannot start on Friday afternoon: {starts}"
    )
    single = candidate_slots((date(2026, 9, 18), "AM"), date(2026, 9, 22),
                             True, (), half_days=1)
    assert (date(2026, 9, 18), "PM") in single, (
        "a half-day visit on Friday afternoon is fine"
    )
    # A holiday in the middle of a long visit rules its start out too.
    over_holiday = candidate_slots((date(2026, 9, 21), "AM"), date(2026, 9, 25),
                                   True, ("2026-09-22",), half_days=4)
    assert not any(day == date(2026, 9, 21) for day, _ in over_holiday), (
        f"a two-day visit cannot run through a holiday: {over_holiday}"
    )


def check_only_customer_visits_are_suggested(service) -> None:
    """Hotels and airports are not customer visits and are left alone."""
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        TeamEvent("hotel", "free", STUTTGART, 2, ("zhang",), label="hotel"),
        visit("muc", MUNICH, ["zhang"]),
    ]
    found = suggest_flexible_visits(service, team, events, settings(team))
    assert {item.stop_id for item in found} == {"muc"}, (
        f"only customer visits belong in this suggestion: {found}"
    )


def check_planned_visits_run_in_time_order(service) -> None:
    """A time we planned decides the order too, not the order stops are stored in.

    Suggestions are searched with the candidate behaving like an appointment, so
    in time order. If the real calculation then walked planned visits in
    whatever order their stops sit in, the trip that was checked and the trip
    that runs would be different ones.
    """
    from backend.services.trip_team_rules import ordered_events

    later = TeamEvent("later", "customer", MUNICH, 1, ("zhang",), None,
                      (date(2026, 9, 18), "AM"), label="later")
    earlier = TeamEvent("earlier", "customer", STUTTGART, 1, ("zhang",), None,
                        (date(2026, 9, 17), "AM"), label="earlier")
    unscheduled = visit("open", PARIS, ["zhang"])
    order = [item.stop_id for item in
             ordered_events([later, earlier, unscheduled])]
    assert order == ["earlier", "later", "open"], order

    # An appointment and a plan of ours in the same half-day: the appointment
    # goes first, because it is the one that cannot give way.
    booked = visit("booked", FRANKFURT, ["zhang"], (date(2026, 9, 17), "AM"))
    planned = TeamEvent("planned", "customer", STUTTGART, 1, ("zhang",), None,
                        (date(2026, 9, 17), "AM"), label="planned")
    assert [item.stop_id for item in ordered_events([planned, booked])] == [
        "booked", "planned"
    ]


def check_added_cost_excludes_what_is_already_planned(service) -> None:
    """A visit is charged for the travel it adds, not for travel already there.

    The added cost is checked against the difference the suggestion actually
    makes: the plan with it, less the plan as it stands. Measuring against the
    appointments alone would bill this visit for the journey an accepted one
    already caused.
    """
    from backend.services.trip_team_schedule import plan_team_itinerary

    team = ("zhang",)
    fixed = visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM"))
    accepted = TeamEvent("stu", "customer", STUTTGART, 1, ("zhang",), None,
                         (date(2026, 9, 17), "AM"), label="stu")
    events = [fixed, accepted, visit("muc", MUNICH, ["zhang"])]
    found = suggest_flexible_visits(service, team, events, settings(team))
    munich = [item for item in found if item.stop_id == "muc"][0]
    assert munich.date, found

    def travel_hours(trial):
        result = plan_team_itinerary(
            service, team, trial, {"__default__": SHANGHAI},
            (date(2026, 9, 14), "AM"), ["flight", "drive", "ground_public"],
            destinations={"__default__": SHANGHAI}, leg_settings={},
        )
        return round(sum(item["travel_hours"]
                         for item in result.member_totals.values()), 2)

    as_it_stands = travel_hours([fixed, accepted])
    with_munich = travel_hours([
        fixed, accepted,
        visit("muc", MUNICH, ["zhang"],
              (date.fromisoformat(munich.date), munich.period)),
    ])
    expected = round(with_munich - as_it_stands, 2)
    assert abs(munich.added_travel_hours - expected) < 0.05, (
        f"the added travel should be {expected} h, the difference this visit "
        f"actually makes, but was reported as {munich.added_travel_hours} h"
    )


def check_displacing_an_accepted_time_is_rejected() -> None:
    """Pushing aside a time somebody accepted disqualifies a candidate.

    This checks the decision itself rather than an end-to-end outcome. In every
    scenario tried, a candidate that displaced an accepted visit also cost more
    travel than the alternatives, so it lost on cost before this rule applied -
    which is the ordinary case, since displacing something means going further.
    The rule is what stops the exception, so it is checked where it is made.
    """
    from backend.services.trip_team_suggestions import _blocked, _risk_key

    class Result:
        def __init__(self, risks):
            self.risks = risks

    moved = {
        "kind": "planned_visit_moved", "stop_id": "stu",
        "planned_date": "2026-09-17", "planned_period": "AM",
        "date": "2026-09-18", "period": "AM",
    }
    assert _blocked(Result([moved]), set()), (
        "a candidate that moves an accepted visit must be rejected"
    )
    # Unless the plan had already moved it: that is not this candidate's doing.
    assert not _blocked(Result([moved]), {_risk_key(moved)})
    # Moving it further than the plan already did is a new problem.
    assert _blocked(Result([{**moved, "date": "2026-09-22"}]),
                    {_risk_key(moved)})


def check_an_accepted_time_survives_a_suggestion(service) -> None:
    """Whatever is suggested, an accepted time still sits where it was put."""
    from backend.services.trip_team_schedule import plan_team_itinerary

    team = ("zhang",)
    fixed = visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM"))
    accepted = TeamEvent("stu", "customer", STUTTGART, 1, ("zhang",), None,
                         (date(2026, 9, 17), "AM"), label="stu")
    events = [fixed, accepted, visit("osl", OSLO, ["zhang"])]
    drive = settings(team, priority=["drive"])
    found = suggest_flexible_visits(service, team, events, drive)
    oslo = [item for item in found if item.stop_id == "osl"][0]
    assert oslo.date, f"a workable time for Oslo should exist: {found}"

    # Whatever it chose, running it must leave Stuttgart where it was accepted.
    result = plan_team_itinerary(
        service, team,
        [fixed, accepted,
         visit("osl", OSLO, ["zhang"],
               (date.fromisoformat(oslo.date), oslo.period))],
        {"__default__": SHANGHAI}, (date(2026, 9, 14), "AM"), ["drive"],
        destinations={"__default__": SHANGHAI}, leg_settings={},
    )
    moved = [
        risk for risk in result.risks
        if risk["kind"] == "planned_visit_moved" and risk["stop_id"] == "stu"
    ]
    assert not moved, (
        f"the suggestion pushed aside a time already accepted: {moved}"
    )
    placed = [
        item for item in result.schedule_items
        if item["source_id"] == "stu" and item["item_type"] != "leg"
    ]
    assert (placed[0]["date"], placed[0]["period"]) == ("2026-09-17", "AM"), (
        f"Stuttgart no longer sits where it was accepted: {placed[0]}"
    )


def check_suggesting_writes_nothing(service) -> None:
    """A suggestion is a proposal: the database is untouched until Apply."""
    conn = service.lead_repo.conn
    before = conn.execute(
        "SELECT COUNT(*) FROM trip_plan_stops"
    ).fetchone()[0]
    team = ("zhang",)
    events = [
        visit("fra", FRANKFURT, ["zhang"], (date(2026, 9, 16), "AM")),
        visit("stu", STUTTGART, ["zhang"]),
    ]
    suggest_flexible_visits(service, team, events, settings(team))
    after = conn.execute("SELECT COUNT(*) FROM trip_plan_stops").fetchone()[0]
    assert before == after, "suggesting must not write to the database"


def main() -> None:
    initialize_database_safely(init_settings(ROOT))
    service = ReviewService()
    check_single_member_flexible(service)
    check_shared_flexible_needs_everybody(service)
    check_appointments_are_never_moved(service)
    check_weekends_are_not_suggested(service)
    check_no_workable_time_is_an_answer(service)
    check_the_scarce_slot_goes_to_the_visit_with_no_alternative(service)
    check_an_applied_suggestion_holds_its_place(service)
    check_saved_times_reach_the_calculation(service)
    check_a_planned_time_gives_way_to_travel(service)
    check_a_bigger_clash_is_not_the_old_clash(service)
    check_a_long_visit_does_not_run_into_a_weekend(service)
    check_only_customer_visits_are_suggested(service)
    check_planned_visits_run_in_time_order(service)
    check_added_cost_excludes_what_is_already_planned(service)
    check_displacing_an_accepted_time_is_rejected()
    check_an_accepted_time_survives_a_suggestion(service)
    check_suggesting_writes_nothing(service)
    close_db()
    print("PASS: flexible visit suggestions")


if __name__ == "__main__":
    main()
