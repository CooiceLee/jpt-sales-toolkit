"""The visit being prepared is chosen beside the editor that prepares it.

The one preparation editor used to live inside the daily schedule, so choosing
a visit meant reading a timetable of travel legs and half-day boxes to find the
customer whose preparation was unfinished. It now sits in the zone named after
the work - a narrow list of visits on the left, the editor on the right - and
the schedule keeps the job it is good at: what the trip looks like.

The other thing pinned here is duller and cost more: a panel marked for one
zone was nested inside a panel marked for another. The zone that is not open is
display:none, so the workbook-return panel inside it was invisible in every
zone of the page - measured in a browser before this change, visible in none.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
PICKER = (ROOT / "frontend" / "js" / "modules"
          / "trip-briefing-picker.js").read_text(encoding="utf-8")

VOID = {"br", "img", "input", "hr", "meta", "link", "source", "track", "area",
        "base", "col", "embed", "param", "wbr"}


class Zones(HTMLParser):
    """Every element's chain of enclosing data-trip-zone panels."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.found: dict[str, list[str]] = {}
        self.nested: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        zone = data.get("data-trip-zone")
        chain = [item for _, item in self.stack if item]
        if zone and chain:
            self.nested.append((zone, chain))
        if tag not in VOID:
            self.stack.append((tag, zone))
        name = data.get("id") or (data.get("class") or "").split(" ")[0]
        if name:
            self.found.setdefault(name, []).append(chain + ([zone] if zone else []))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return


def parsed() -> Zones:
    zones = Zones()
    zones.feed(INDEX)
    return zones


def check_a_zone_panel_is_never_inside_another_zones_panel() -> None:
    tree = parsed()
    wrong = [(zone, chain) for zone, chain in tree.nested if chain[-1] != zone]
    assert not wrong, (
        "a panel marked for one zone sits inside another zone's panel, so it "
        f"is display:none whichever zone is open: {wrong}"
    )


def check_the_editor_and_its_picker_are_in_the_preparation_zone() -> None:
    tree = parsed()
    for name in ("trip-briefing-editor", "trip-briefing-picker"):
        assert tree.found.get(name) == [["briefing"]], (
            f"{name} is in {tree.found.get(name)}, not the preparation zone"
        )
    assert 'class="trip-briefing-workspace"' in INDEX
    assert "trip-briefing-picker.js" in INDEX, "the picker module is not loaded"


def check_the_preparation_zone_does_not_repeat_the_overview() -> None:
    tree = parsed()
    # The standing list of every leg is gone: journeys are read on the timeline
    # and edited one at a time in the panel beside it.
    for name in ("trip-schedule-list", "trip-map", "trip-risk-bar",
                 "trip-current-plan", "trip-stop-order-list"):
        chains = tree.found.get(name) or []
        assert chains, f"{name} is not on the page at all"
        # Every occurrence, not just the first: a second copy dropped into the
        # preparation zone is exactly the duplication this rules out.
        assert all("briefing" not in chain for chain in chains), (
            f"{name} is repeated inside the preparation zone: {chains}"
        )
    assert tree.found.get("trip-current-plan") == [["route"]], (
        "the itinerary the reader edits is no longer with the route it belongs to"
    )


def check_the_trip_files_sit_with_the_trip_they_are_for() -> None:
    """Sharing a file is not preparing a visit.

    The export panel stayed in the preparation zone while the editor moved in
    beside it, so "拜访准备" held one visit's form and every file of the whole
    trip. The files belong with the workbook that comes back from the field.
    """
    tree = parsed()
    for name in ("trip-export-panel", "trip-working-import-panel"):
        chains = tree.found.get(name) or []
        assert chains and all(chain == ["execution"] for chain in chains), (
            f"{name} is in {chains}, not with the rest of the trip's files"
        )


def check_the_picker_says_what_a_reader_picks_on() -> None:
    for marker, why in (
        ("data-briefing-pick", "the rows carry no identity to select or highlight"),
        ("TripBriefingActions?.open?.(", "selection bypasses the action that guards the draft"),
        ("internalParticipantsLine", "the picker invents its own way of saying who goes"),
        ("data-business", "business text is left for the translation walker to rewrite"),
        ("escapeHtml", "customer names are written into the page unescaped"),
    ):
        assert marker in PICKER, f"{marker}: {why}"
    for forbidden in ("TripBriefingForm", "TripBriefingDraft.load", "ApiClient."):
        assert forbidden not in PICKER, (
            f"the picker loads a visit itself through {forbidden}, so choosing "
            "one skips the unsaved-draft question"
        )
    assert "confirmation_status" in PICKER, "the row does not say whether the visit is confirmed"
    assert "planned_date" in PICKER, "the row does not say when the visit is"
    # Naming nobody means the whole team goes; a dash would read as nobody.
    assert "Whole team" in PICKER


def check_the_editor_header_names_the_plan() -> None:
    rows = (ROOT / "frontend" / "js" / "modules"
            / "trip-briefing-rows.js").read_text(encoding="utf-8")
    head = rows[rows.index("trip-briefing-head"):rows.index("trip-briefing-scroll")]
    assert "currentTripPlan" in head, (
        "the editor does not say which plan the visit belongs to, so two plans "
        "with the same customer look identical"
    )


def check_the_two_columns_give_way_on_a_narrow_screen() -> None:
    assert ".trip-briefing-workspace {" in CSS
    wide = CSS[CSS.index(".trip-briefing-workspace {"):]
    columns = re.search(r"grid-template-columns:\s*minmax\((\d+)px", wide)
    assert columns and 220 <= int(columns.group(1)) <= 360, (
        "the visit list is not a narrow selector beside a wide editor"
    )
    # Somewhere below the desktop width the two columns stack. Which pixel is
    # the page's business; that it happens before a 1024px laptop is not.
    stacked = [
        int(width) for width, body in re.findall(
            r"@media[^{]*max-width:\s*(\d+)px[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}",
            CSS, re.S)
        if re.search(r"\.trip-briefing-workspace\s*\{\s*grid-template-columns:\s*1fr", body)
    ]
    assert stacked and max(stacked) >= 1024, (
        "the visit list and the editor stay side by side on a 1024px screen, "
        f"where neither has room: breakpoints found {stacked}"
    )


def main() -> None:
    check_a_zone_panel_is_never_inside_another_zones_panel()
    check_the_editor_and_its_picker_are_in_the_preparation_zone()
    check_the_preparation_zone_does_not_repeat_the_overview()
    check_the_trip_files_sit_with_the_trip_they_are_for()
    check_the_picker_says_what_a_reader_picks_on()
    check_the_editor_header_names_the_plan()
    check_the_two_columns_give_way_on_a_narrow_screen()
    print("PASS: the preparation zone chooses a visit and prepares it, "
          "and no panel hides inside another zone")


if __name__ == "__main__":
    main()
