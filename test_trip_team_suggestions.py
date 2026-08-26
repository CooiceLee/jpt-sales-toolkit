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
    check_suggesting_writes_nothing(service)
    close_db()
    print("PASS: flexible visit suggestions")


if __name__ == "__main__":
    main()
