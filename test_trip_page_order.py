"""The plan being edited comes first, and every field says what it is.

The trip page was laid out in the order its parts were written, not the order
they are used: the map, the schedule, the visit-execution forms and the export
panel came first, and the plan's own name, dates and travellers came last. In
one column - a 1024px window, or a detail panel open - the audit measured the
plan name about 6,200px down a 9,317px page, with only three customer stops.

Nothing here changes how a route is worked out. It changes what the reader
reaches first, and it gives the dates and coordinates labels that stay visible
after something has been typed into them.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
TRIP = INDEX[INDEX.index('id="module-trip-planner"'):INDEX.index('id="module-coordinate-review"')]

# What the reader is trying to set up, and what they only need once it is set.
SETUP = ('id="trip-title"', 'id="trip-start-date"', 'id="trip-end-date"',
         'id="trip-team-panel"', 'id="trip-plan-list"')
LATER = ('id="trip-visit-execution"', 'class="trip-working-import-panel"',
         'class="trip-export-panel"', 'id="trip-schedule-list"')


def check_the_plan_comes_before_the_work_on_it() -> None:
    setup_end = max(TRIP.index(marker) for marker in SETUP)
    for marker in LATER:
        assert marker in TRIP, f"missing from the trip page: {marker}"
        assert setup_end < TRIP.index(marker), (
            f"{marker} comes before the plan's own fields, so a one-column "
            "window puts the plan name below it"
        )


def check_the_setup_is_near_the_top() -> None:
    """Not a pixel measurement, but the same thing in document order."""
    total = len(TRIP)
    position = TRIP.index('id="trip-title"') / total
    assert position < 0.2, (
        f"the plan title sits {position:.0%} of the way down the trip page"
    )
    assert 'class="trip-plan-setup"' in TRIP, (
        "the plan's fields are not grouped into their own area"
    )


def check_every_date_and_coordinate_has_a_label() -> None:
    """A placeholder is gone the moment somebody types, and these are numbers.

    Four unlabelled coordinate boxes cannot be told apart once they hold
    values, which is exactly what the audit found.
    """
    for field in (
        "trip-title", "trip-start-date", "trip-end-date",
        "trip-origin-name", "trip-destination-name",
        "trip-origin-lat", "trip-origin-lng",
        "trip-destination-lat", "trip-destination-lng",
    ):
        pattern = re.compile(
            r'<label[^>]*>\s*<span>([^<]+)</span>\s*'
            r'<input[^>]*id="' + re.escape(field) + r'"',
            re.S,
        )
        match = pattern.search(TRIP)
        assert match, f"{field} has no visible label of its own"
        assert match.group(1).strip(), f"{field}'s label is empty"


def check_the_coordinates_are_out_of_the_way_but_reachable() -> None:
    """Rarely needed, and the tallest thing on the form when it is open."""
    assert 'class="trip-advanced-coordinates"' in TRIP
    advanced = TRIP[TRIP.index('class="trip-advanced-coordinates"'):]
    advanced = advanced[:advanced.index("</details>")]
    for field in ("trip-origin-lat", "trip-origin-lng",
                  "trip-destination-lat", "trip-destination-lng"):
        assert field in advanced, f"{field} is not inside the advanced group"
    assert "<summary>" in advanced, (
        "the advanced group has no heading to open it by"
    )
    # Collapsed by default, and openable without a script.
    assert "<details" in TRIP and "open>" not in advanced.split(">")[0] + ">"


def check_the_route_engine_was_not_touched() -> None:
    """This batch reorganises the page; it must not change what is sent."""
    payload = (ROOT / "frontend" / "js" / "modules" / "trip-planning-draft.js").read_text(
        encoding="utf-8"
    )
    for field in ("route_order_mode", "stop_order", "stop_durations", "leg_overrides"):
        assert field in payload, f"the itinerary request lost {field}"
    form = (ROOT / "frontend" / "js" / "modules" / "trip-form.js").read_text(
        encoding="utf-8"
    )
    assert "planning_mode: 'team'" in form, "the planning mode changed"
    assert "trip-planning-mode" not in INDEX, (
        "the removed planning-mode control came back"
    )


def main() -> None:
    check_the_plan_comes_before_the_work_on_it()
    check_the_setup_is_near_the_top()
    check_every_date_and_coordinate_has_a_label()
    check_the_coordinates_are_out_of_the_way_but_reachable()
    check_the_route_engine_was_not_touched()
    print("PASS: the trip page leads with the plan, and every field is labelled")


if __name__ == "__main__":
    main()
