"""Four things a reader does, each finished rather than started.

The timeline was the right shape and the operations around it were not closed:

  * The map painted over the pinned bar - the plan's name, all four zone tabs -
    and an SVG route line took clicks inside the bar's rectangle. Leaflet paints
    its panes at 200-700 and its controls at 1000; the map element created no
    stacking context of its own, so those numbers competed with the page.
  * Thirty-one date buttons filled three rows and then scrolled away, so the
    only way back to a day was to scroll looking for it.
  * Agreeing a time with a customer - the most frequent thing done to a trip -
    had no entry point left but finding the visit by eye among fifty-three
    entries, and two visits to one customer look identical there.
  * "Map" moved the map's centre while the map was a thousand pixels above the
    reader: nothing revealed, nothing opened, no customer named. The stop
    markers had their names replaced by permanent date labels, so the one thing
    that told two dots apart was gone.
  * And a reordered stop snapped back: the list read the stored order while the
    move lived in the draft, so the next move was measured against a list the
    reader was not looking at.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from test_trip_route_board_contract import DOM

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def source(name: str) -> str:
    return (MODULES / name).read_text(encoding="utf-8")


def check_the_map_keeps_its_own_layers_to_itself() -> None:
    assert ".leaflet-container { isolation: isolate; }" in CSS, (
        "the map's panes and controls compete with the page again, so the map "
        "paints over the pinned bar and takes its clicks"
    )
    zone = CSS[CSS.index(".trip-map-zone {"):][:200]
    assert "position: relative" in zone and "z-index: 1" in zone, zone
    bar = CSS[CSS.index(".trip-zone-bar {"):][:400]
    assert "z-index: 7" in bar, "the bar's layer moved; the scale has to stay ordered"
    # Raising everything to out-bid Leaflet is the failure this replaces.
    assert "999999" not in CSS and "z-index: 9999" not in CSS


def check_the_day_navigation_stays_and_stays_small() -> None:
    toolbar = CSS[CSS.index(".trip-timeline-toolbar {"):][:300]
    assert "position: sticky" in toolbar, "the route navigation scrolls away again"
    assert "var(--trip-bar-height" in toolbar, (
        "the navigation is pinned to a number rather than to the bar's height"
    )
    nav = source("trip-day-nav.js")
    assert "readingDay" in nav and "addEventListener('scroll'" in nav, (
        "the navigation no longer follows what is being read"
    )
    assert "pending" in nav, (
        "a jump scrolls through every day on the way; each frame would be read "
        "as the day the reader is on"
    )
    toolbar_source = source("trip-timeline-toolbar.js")
    assert "trip-day-nav" in toolbar_source
    assert "trip-timeline-day" not in toolbar_source, (
        "every date is a button again - three rows of them"
    )
    # Jumping to a day has to clear both pinned lines.
    assert "#module-trip-planner .trip-day {" in CSS
    day = CSS[CSS.index("#module-trip-planner .trip-day {"):][:200]
    assert "scroll-margin-top" in day and "var(--trip-bar-height" in day
    # One scrollport for the timeline: an inner one gave two answers to "which
    # day am I on" and the pinned navigation could not see the inner one.
    listing = CSS[CSS.index(".trip-schedule-list {"):][:200]
    assert "overflow: auto" not in listing, (
        "the timeline has its own scrollport again"
    )


def check_arranging_a_visit_has_a_door() -> None:
    finder = source("trip-visit-finder.js")
    for needle in ("lead_display_id", "TripSelection?.select?.('stop'", "intent: 'agree'"):
        assert needle in finder, f"the finder no longer does: {needle}"
    assert "State.currentTripPlan?.stops" in finder, (
        "the finder reads something other than this plan's own stops"
    )
    # A hotel has no customer to agree anything with; it keeps the editor it
    # already has on the timeline.
    assert "stop.stop_kind !== 'free'" in finder, (
        "personal stops are offered as visits to agree a time for"
    )
    # The input is written once: rebuilding it on every keystroke takes the
    # caret - and any half-typed Chinese still in the input method - with it.
    assert "if (document.getElementById('trip-finder-query')) return results();" in finder, (
        "the search box is replaced while somebody is typing in it"
    )
    view = source("trip-visit-finder-view.js")
    assert "function results(" in view and "trip-finder-results" in view
    # The caret goes to the field they came for, in view.
    selection = source("trip-selection.js")
    assert "stop-agree-fields-" in selection and "stop-agreed-date-" in selection, (
        "choosing a visit no longer opens the agreed-time block"
    )
    assert "scrollIntoView" in selection and "preventScroll: true" in selection, (
        "the caret can land in a box that is off screen"
    )
    assert 'id="trip-visit-finder"' in INDEX and "trip-visit-finder.js" in INDEX
    toolbar = source("trip-timeline-toolbar.js")
    assert "TripVisitFinder.${finding ? 'close' : 'open'}()" in toolbar, (
        "there is no way to open it"
    )
    # Open is a state, not a flash: the button says so and keeps saying so.
    assert 'aria-expanded="${!!finding}"' in toolbar and 'aria-controls="trip-visit-finder"' in toolbar
    assert "is-open" in toolbar, "the button does not stay marked while the panel is open"
    assert "Set agreed visit time" in toolbar, (
        "the entry is named for something the app does not do"
    )
    candidates = source("trip-candidates-list.js")
    assert "TripVisitFinder.open(" in candidates, (
        "an already-added customer offers nothing but a disabled button again"
    )
    # Three different times, and the third is never borrowed from the first.
    times = source("trip-stop-times.js")
    assert "actual_visit_date" in times and "Not recorded yet" in times
    detail = source("trip-detail-panel.js")
    for label in ("Planned slot", "Agreed with customer", "Actually visited"):
        assert label in detail, f"the detail panel stopped separating {label}"


def check_showing_something_on_the_map_finishes() -> None:
    focus = source("trip-map-focus.js")
    for needle in ("scrollIntoView", "invalidateSize", "openPopup", "setPopupContent"):
        assert needle in focus, f"a map request no longer does: {needle}"
    assert "objects at this position" in focus, (
        "several customers on one coordinate are one dot again, with no way to "
        "say which one was asked for"
    )
    assert "city-level position" in focus, "a city centre is presented as the address"
    assert "filtered out of the map" in focus, (
        "a target hidden by the member filter is shown as an empty map"
    )
    assert "mine !== request" in focus, "clicking A then B can end on A"
    markers = source("trip-plan-markers.js")
    assert "State.tripMapMarkers.set(`stop:" in markers, (
        "the markers are not registered against the stops they stand for"
    )
    assert "permanent: true" not in markers, (
        "every customer carries a permanent date label again, overlapping the "
        "names that tell them apart"
    )
    assert "bindTooltip" in markers and "label" in markers
    candidates = source("trip-candidates-map.js")
    assert "TripMapFocus?.show?.('candidate'" in candidates, (
        "the candidate Map button only moves the centre again"
    )
    assert "TripMapFocus?.restore?.()" in candidates, (
        "a redraw fits the whole trip back into view over what was just asked for"
    )
    # The map is the same choice seen from above, not a second selection.
    selection = source("trip-selection.js")
    assert "TripMapFocus" not in selection, (
        "choosing a row on the timeline drags the reader up to the map"
    )


def check_the_customer_list_is_a_phase() -> None:
    assert 'data-candidates="closed"' in INDEX, (
        "the candidate list holds a quarter of the window again by default"
    )
    assert '#module-trip-planner[data-candidates="closed"] .trip-side' in CSS
    assert '#module-trip-planner[data-candidates="closed"] .trip-layout' in CSS, (
        "closing the list does not give its width back to the timeline"
    )
    panel = source("trip-candidate-panel.js")
    assert "renderTripCandidates" in panel and "TripSideHeight?.sync?.()" in panel


def check_the_basemap_needs_no_key() -> None:
    """A watermark across the map is not a map anybody can read.

    CARTO's basemaps need an account; without one every tile says API KEY
    REQUIRED. OpenStreetMap's own tiles need no key and the attribution they
    ask for is the one already shown.
    """
    support = source("map-support.js")
    assert "cartocdn" not in support, "the map is back on a service with no key"
    assert "tile.openstreetmap.org" in support
    assert "OpenStreetMap contributors" in support, "the required attribution is gone"


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

__DOM__

const ctx = {
  console, assert,
  escapeHtml: value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;'),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: makeDocument(['trip-visit-finder', 'trip-current-plan', 'trip-stop-order-list',
                          'trip-stop-board', 'trip-schedule-list']),
  setTimeout, addEventListener() {},
  TripStopBoard: { timing: stop => (stop.schedule_locked ? 'agreed'
    : (stop.planned_date ? 'flexible' : 'unscheduled')) },
  TripSelection: { chosen: null, select(kind, id) { this.chosen = { kind, id }; },
    is(kind, id) { return this.chosen?.kind === kind && this.chosen?.id === String(id); } },
};
ctx.window = ctx;
ctx.State = { currentTripPlan: null };
vm.createContext(ctx);
for (const file of ['trip-duration.js', 'trip-leg-overrides.js', 'trip-planning-draft.js',
                    'trip-stop-order.js', 'trip-stop-times.js',
                    'trip-visit-finder-view.js', 'trip-visit-finder.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), ctx, { filename: file });
}
const doc = ctx.document;

// Two visits to the same customer, one with an agreed time and one without.
const stops = [
  { id: 's1', stop_kind: 'customer', sequence_no: 1, customer_name: 'Berlin Optics',
    lead_display_id: 'JPT-2609-0001', city: 'Berlin', country: 'DE',
    planned_date: '2026-09-20', schedule_locked: true },
  { id: 's2', stop_kind: 'customer', sequence_no: 2, customer_name: 'Berlin Optics',
    lead_display_id: 'JPT-2609-0001', city: 'Berlin', country: 'DE',
    planned_date: '2026-09-27', planned_time_accepted: true },
  { id: 's3', stop_kind: 'customer', sequence_no: 3, customer_name: 'Lyon Lasers',
    lead_display_id: 'JPT-2609-0009', city: 'Lyon', country: 'FR' },
  { id: 'f1', stop_kind: 'free', sequence_no: 4, location_name: 'Hamburg overnight',
    category: 'hotel', planned_date: '2026-09-21' },
];
ctx.State.currentTripPlan = { id: 'p1', stops };
ctx.TripVisitFinder.open();
const rows = () => doc.querySelectorAll('#trip-visit-finder .trip-finder-row');
assert.equal(rows().length, 3, 'the finder does not list this plan\'s customer visits');
assert.ok(!doc.getElementById('trip-visit-finder').innerHTML.includes('Hamburg overnight'),
  'a hotel is offered as a visit to agree a time for');

// The same customer twice is two entries, each carrying its own stop.
ctx.TripVisitFinder.search('Berlin Optics');
assert.equal(rows().length, 2, 'two visits to one customer collapsed into one row');
const ids = rows().map(row => String(row.attrs.onclick).match(/'([^']+)'\)/)[1]);
assert.deepEqual(ids, ['s1', 's2'], ids.join(','));

// Searching by lead number and by city finds them too.
ctx.TripVisitFinder.search('JPT-2609-0009');
assert.equal(rows().length, 1);
ctx.TripVisitFinder.search('lyon');
assert.equal(rows().length, 1, 'the city is not searchable');

// "Time not agreed" is the filter somebody arranging visits actually wants.
ctx.TripVisitFinder.search('');
ctx.TripVisitFinder.setFilter('pending');
assert.equal(rows().length, 2, 'the pending filter does not exclude agreed times');
ctx.TripVisitFinder.setFilter('agreed');
assert.equal(rows().length, 1);
ctx.TripVisitFinder.setFilter('all');

// Choosing writes to the stop that was picked, not to the first of the pair.
ctx.TripVisitFinder.choose('s2');
assert.equal(ctx.TripSelection.chosen.kind, 'stop');
assert.equal(ctx.TripSelection.chosen.id, 's2', 'the second visit opened the first one');

// The order in force: a manual move is what the list and the next move use.
const plan = { id: 'p-order', stops: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] };
ctx.TripPlanningDraft.hydrate(plan);
assert.equal(ctx.TripStopOrder.stops(plan.stops).map(s => s.id).join(','), 'a,b,c');
assert.equal(ctx.TripStopOrder.pending(plan.stops), false);
ctx.TripPlanningDraft.change(draft => {
  draft.routeOrderMode = 'manual';
  draft.stopOrder = ['b', 'a', 'c'];
});
assert.equal(ctx.TripStopOrder.stops(plan.stops).map(s => s.id).join(','), 'b,a,c',
  'the list reads the stored order while the move lives in the draft');
assert.equal(ctx.TripStopOrder.pending(plan.stops), true,
  'nothing says the order on screen is not written yet');
// A stale draft order - one that no longer matches the plan - is not used.
ctx.TripPlanningDraft.change(draft => { draft.stopOrder = ['b', 'gone']; });
assert.equal(ctx.TripStopOrder.stops(plan.stops).map(s => s.id).join(','), 'a,b,c',
  'a deleted stop came back through the draft order');

// A journey is the connection *and* whose journey it is: the same leg_key
// travelled by two colleagues on different days is two journeys.
const legPlan = { id: 'p-legs', legs: [
  { leg_key: 'c1>c2', member_id: 'u-a' },
  { leg_key: 'c1>c2', member_id: 'u-b' },
] };
ctx.State.currentTripPlan = legPlan;
ctx.TripSelection.select = undefined;   // use the real one from here on
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-selection.js', 'utf8'), ctx,
  { filename: 'trip-selection.js' });
const Selection = ctx.TripSelection;
Selection.select('leg', 'c1>c2', { members: ['u-a'] });
assert.equal(Selection.is('leg', 'c1>c2', ['u-a']), true);
assert.equal(Selection.is('leg', 'c1>c2', ['u-b']), false,
  "another traveller's journey on the same connection is highlighted as this one");
// Genuinely shared travel is one row naming everybody, matched by that set.
Selection.select('leg', 'c1>c2', { members: ['u-b', 'u-a'] });
assert.equal(Selection.is('leg', 'c1>c2', ['u-a', 'u-b']), true, 'order of the names must not matter');
assert.equal(Selection.is('leg', 'c1>c2', ['u-a']), false);
// A member who leaves takes their journey with them, even where a colleague
// still travels the same connection.
Selection.select('leg', 'c1>c2', { members: ['u-b'] });
assert.ok(Selection.reconcile(legPlan));
assert.equal(Selection.reconcile({ id: 'p-legs', legs: [{ leg_key: 'c1>c2', member_id: 'u-a' }] }), null,
  'the selection survived on a connection this member no longer travels');
// A stop is still its own id.
Selection.select('stop', 's1');
assert.equal(Selection.is('stop', 's1'), true);

// The four states a visit's time can be in come from the fields that hold
// them - a calculated date is not an appointment (backend schedule_state).
const Times = ctx.TripStopTimes;
assert.equal(Times.agreement({ planned_date: '2026-09-20', schedule_locked: true }), 'confirmed');
assert.equal(Times.agreement({ planned_date: '2026-09-20', planned_time_accepted: true }), 'accepted');
assert.equal(Times.agreement({ planned_date: '2026-09-20' }), 'calculated');
assert.equal(Times.agreement({}), 'none');
assert.match(Times.agreementLabel({ planned_date: '2026-09-20' }), /for reference/,
  'a date the calculation produced is offered as an agreed time');
assert.match(Times.agreementLabel({}), /No agreed time/);

console.log(JSON.stringify({ rows: 3 }));
"""


def _node(script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    result = subprocess.run(["node", path], capture_output=True, text=True, cwd=ROOT)
    Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def check_the_finder_and_the_order_behave() -> None:
    output = _node(HARNESS.replace("__DOM__", DOM))
    assert json.loads(output.strip().splitlines()[-1])["rows"] == 3


def check_a_map_request_belongs_to_the_plan_it_was_made_on() -> None:
    """The wait before a map can be pointed at is long enough to change plans.

    Bringing the map into view takes a moment, and in that moment the reader can
    open another plan or the markers can be drawn again. A request that captured
    a marker then moved a different plan's map to a layer that had been cleared.
    """
    focus = source("trip-map-focus.js")
    assert "const planId = planNow();" in focus, (
        "a map request no longer remembers which plan it was made on"
    )
    assert "planNow() !== planId" in focus, (
        "a request arriving after a plan switch still moves the new plan's map"
    )
    assert "const found = entry(kind, id);      // looked up again, never reused" in focus, (
        "the delayed step reuses the marker it captured, which may belong to a "
        "layer that has since been cleared"
    )
    restore = focus[focus.index("function restore()"):]
    assert "planNow() !== active.planId" in restore, (
        "a redraw restores another plan's focus"
    )
    clear = focus[focus.index("function clear()"):]
    assert "request += 1;" in clear, (
        "clearing leaves a request in flight, which then arrives anyway"
    )
    zones = source("trip-zones.js")
    assert "TripMapFocus?.clear?.()" in zones and "TripSelection?.clear?.()" in zones, (
        "switching plans keeps the old plan's map request and selection"
    )


def check_the_day_line_keeps_focus_while_it_follows() -> None:
    """It updates while somebody scrolls, and a select lives in it.

    Rebuilding the markup on every scroll would close an open dropdown in the
    middle of a choice and take the keyboard focus with it.
    """
    nav = source("trip-day-nav.js")
    assert "function update(" in nav, (
        "the navigation rebuilds itself while the reader is using it"
    )
    # The whole ordered list, not its length: the same number of days on other
    # dates - a date changed, another plan opened - has to redraw the options.
    assert "Array.from(pick.options, option => option.value).join(',')" in nav
    assert "shown !== list.join(',')" in nav, (
        "the options are compared by how many there are"
    )
    body = nav[nav.index("    function render() {"):]
    assert "if (update(list, at))" in body, (
        "render() rebuilds the line instead of updating it in place first"
    )
    assert body.index("if (update(list, at))") < body.index("root.innerHTML = `<button"), (
        "the rebuild happens before the in-place update it was meant to avoid"
    )


def check_the_agreed_time_says_what_really_happened() -> None:
    """The field writes to the server on change, so it has to say so.

    trip-stop-appointment-actions saves immediately - the calculation reads a
    confirmed time from the stop, so holding it in a draft would mean the
    preview ignored what was typed. A field that saves itself has to say when
    it is saving and when the save failed, and it must not claim the route was
    recalculated: that is still the last calculation's result.
    """
    status = source("trip-agree-status.js")
    for state in ("Saving…", "Agreed time saved", "Not saved. Try again."):
        assert state in status, f"the agreed time never says: {state}"
    # A date nobody confirmed is written and then moved by the next
    # calculation - which looks exactly like a save that did not work.
    assert "not confirmed: the next route calculation can move this day" in status, (
        "an unconfirmed date is presented as if it would hold its place"
    )
    assert "schedule_locked" in status, (
        "what the date will do is decided without looking at whether it is confirmed"
    )
    assert "Calculate and save the route" in status, (
        "saving a time is presented as if the route had been worked out again"
    )
    assert "TripRouteState?.derive?.()" in status, (
        "the route's state is decided here instead of by the one place that knows"
    )
    actions = source("trip-stop-appointment-actions.js")
    for call in ("'saving'", "'saved'", "'failed'"):
        assert f"TripAgreeStatus?.set?.(stopId, {call})" in actions, (
            f"the save does not report {call}"
        )
    # Recalculating straight after an unconfirmed date was typed put the
    # calculation's own day back in the field - and whoever then ticked
    # "customer confirmed" pinned that day instead of the one they agreed.
    assert "if (payload.schedule_locked || wasLocked) {" in actions, (
        "an unconfirmed date still asks for a recalculation that discards it"
    )
    assert "const wasLocked = Boolean(stop.schedule_locked);" in actions, (
        "unpinning a confirmed time no longer recalculates the route"
    )
    # No decorative button pretending to be responsible for a save that has
    # already happened, and no cancel that cannot undo it.
    detail = source("trip-detail-panel.js")
    assert "Save agreed time" not in detail and "Cancel agreed time" not in detail
    controls = source("trip-stop-schedule-controls.js")
    assert "trip-agree-fields" in controls and "stop-agree-save-" in controls, (
        "the three fields of an agreed time are not kept together"
    )
    assert controls.count("stop-schedule-lock-") == 2, (
        "the confirmation box is duplicated or gone"
    )
    # This entry never touches what actually happened on the trip.
    finder = source("trip-visit-finder.js")
    assert "actual_visit" not in finder and "result_status" not in finder


def main() -> None:
    check_the_agreed_time_says_what_really_happened()
    check_a_map_request_belongs_to_the_plan_it_was_made_on()
    check_the_day_line_keeps_focus_while_it_follows()
    check_the_map_keeps_its_own_layers_to_itself()
    check_the_day_navigation_stays_and_stays_small()
    check_arranging_a_visit_has_a_door()
    check_showing_something_on_the_map_finishes()
    check_the_customer_list_is_a_phase()
    check_the_basemap_needs_no_key()
    check_the_finder_and_the_order_behave()
    print("PASS: the map stays under the bar, the day navigation stays put, a "
          "visit can be found and arranged, a map request finishes, and a "
          "reordered stop stays where it was put")


if __name__ == "__main__":
    main()
