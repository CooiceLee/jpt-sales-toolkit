"""The plan's bar stays reachable, and a control group wraps on its own width.

Two things a reader lost as soon as the page got long.

The bar carries the plan's identity, its status and the only two route actions
there are - and it scrolled away with the rest of the page, so deciding to save
meant scrolling back up to find the button, and the status that says *why* a
button is off was off screen at the moment it mattered. It is pinned to the top
of the scrolling area now: the real bar, not a second copy of it with the same
ids, and everything else that pins in this module starts below it by however
tall it measures - two rows, a sentence of status, at whatever zoom.

And the two choices on a travel row sat in one no-wrap flex row. Inside a 280px
column that squeezed "Fix the transport mode" into one character per line: a
label rendered vertically, beside a checkbox nobody could read. Wrapping is
decided by the width of the card the controls are in - a viewport breakpoint
cannot see that a column inside a wide window is narrow.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
MODULES = ROOT / "frontend" / "js" / "modules"


def block(selector: str, length: int = 420) -> str:
    start = CSS.index(selector)
    return CSS[start:start + length]


def check_the_bar_is_pinned_to_the_scrolling_area() -> None:
    bar = block(".trip-zone-bar {")
    assert "position: sticky" in bar, (
        "the bar scrolls away with the page, taking the status and both route "
        "actions with it"
    )
    # The scrollport is .main-content and it carries padding: a plain top: 0
    # stops one padding below the top of what the reader sees, and rows go on
    # showing - cut in half - in the strip above it.
    assert "top: calc(-1 * var(--main-pad, 24px))" in bar, bar
    assert "z-index" in bar
    assert "background: white" in bar, "a transparent pinned bar shows the page through it"
    # One bar, not a copy: two elements with the same ids means two answers to
    # "did this save", and the second one is never wired to anything.
    assert INDEX.count('class="trip-zone-bar"') == 1
    assert INDEX.count('id="trip-route-save"') == 1
    assert INDEX.count('id="trip-route-status"') == 1
    # Two rows: the plan and its actions, then the four zones.
    tabs = block(".trip-zone-tabs {")
    assert "grid-column: 1 / -1" in tabs, (
        "the zone tabs share the first row, so a long status pushes them off it"
    )


def check_everything_else_that_pins_starts_below_it() -> None:
    assert "trip-bar-offset.js" in INDEX, "nothing measures the bar"
    offset = (MODULES / "trip-bar-offset.js").read_text(encoding="utf-8")
    assert "--trip-bar-height" in offset and "getBoundingClientRect" in offset, (
        "the bar's height is guessed rather than measured"
    )
    assert "offsetParent" in offset, (
        "measured while the module is hidden every edge is zero, and 0px is "
        "then kept until something else happens to ask again"
    )
    side = block("#module-trip-planner .trip-side {")
    assert "var(--trip-bar-height" in side, (
        "the candidate panel pins under the bar and is covered by it"
    )
    margin = CSS[CSS.index("scroll-margin-top: calc(var(--trip-bar-height"):]
    assert margin, "a jumped-to target can land behind the bar"
    focus = (MODULES / "trip-route-focus.js").read_text(encoding="utf-8")
    assert "block: 'start'" in focus, (
        "a tall editor centred in the window puts its title behind the bar"
    )
    # First entry into a zone has to reach that zone. Measuring against the bar
    # now always answers "already there", because the bar never leaves the top.
    assert 'data-trip-zone="${zone}"' in focus, (
        "the first-visit scroll still measures against the pinned bar"
    )


def check_the_travel_controls_wrap_on_the_card_they_are_in() -> None:
    assert ".trip-leg-card { container-type: inline-size; }" in CSS, (
        "the controls can only react to the window, not to the column they are "
        "in, so a narrow card renders the lock label one character per line"
    )
    assert ".trip-leg-controls {\n  display: grid" in CSS, (
        "the controls are one no-wrap flex row again"
    )
    assert re.search(r"@container \(min-width: \d+px\)", CSS), (
        "the two-column layout is chosen by viewport width again"
    )
    assert ".trip-leg-control-row .trip-check span,\n.trip-leg-control-row .btn { white-space: nowrap; }" in CSS, (
        "the label may be broken between characters"
    )
    card_source = (MODULES / "trip-leg-card.js").read_text(encoding="utf-8")
    assert "trip-leg-control-row" in card_source, "the second row is not rendered"
    assert "Fix the transport mode" in card_source, (
        "mode_locked only constrains the mode; 'lock this leg' claims it also "
        "pins the dates, the airports and the people"
    )
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    for english, chinese in (("Fix the transport mode", "固定交通方式"),
                             ("Within the same half-day", "在同一个半天内完成"),
                             ("Listed journeys", "所列交通段合计"),
                             ("Team aggregate distance", "团队累计里程（逐人相加）")):
        assert f"['{english}', '{chinese}']" in i18n, english


def check_the_distance_total_says_what_it_counts() -> None:
    """74,121 is four travellers' own distances added up, not the route's length.

    The trip is about 54,000km of route; the summary shows 74,121 because four
    colleagues on one flight count it four times. Both readings are legitimate,
    and the label is what tells them apart.
    """
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert "['Team aggregate distance', '团队累计里程（逐人相加）']" in i18n, (
        "the team distance does not say that it adds up each traveller's own"
    )


def main() -> None:
    check_the_bar_is_pinned_to_the_scrolling_area()
    check_everything_else_that_pins_starts_below_it()
    check_the_travel_controls_wrap_on_the_card_they_are_in()
    check_the_distance_total_says_what_it_counts()
    print("PASS: the plan bar stays reachable, what pins starts below it, and "
          "a travel row's controls wrap on their own width")


if __name__ == "__main__":
    main()
