"""Four pieces of work on one plan, and a zone change is not a plan change.

Everything on the trip page used to be stacked in the order it was written -
map, schedule, visit-execution forms, export panel, workbook return - with the
plan's own name and dates last. Three customer stops made a 9,317px page at
1024px, and the plan name sat about 6,200px down it.

The zones only hide and show. Nothing is re-rendered and nothing is unmounted,
so a half-typed briefing survives a look at the schedule; that is what makes a
zone change different from opening another plan.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
TRIP = INDEX[INDEX.index('id="module-trip-planner"'):INDEX.index('id="module-coordinate-review"')]
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")

ZONES = ("settings", "route", "briefing", "execution")


def check_every_zone_exists_and_has_content() -> None:
    for zone in ZONES:
        assert f'data-trip-zone-tab="{zone}"' in TRIP, f"no tab for the {zone} zone"
        assert f'data-trip-zone="{zone}"' in TRIP, f"nothing belongs to the {zone} zone"
    # The whole working area is accounted for: a panel with no zone would be
    # visible in all four, or in none.
    panels = re.findall(r'class="review-panel[^"]*"', TRIP)
    zoned = re.findall(r'data-trip-zone="', TRIP)
    assert len(zoned) >= len(panels), (
        f"{len(panels)} panels but only {len(zoned)} zone assignments"
    )


def check_the_plan_is_named_above_the_zones() -> None:
    bar = TRIP[TRIP.index('class="trip-zone-bar"'):TRIP.index('data-trip-zone="settings"')]
    assert 'id="trip-zone-plan-name"' in bar, "the strip does not name the plan"
    assert 'id="trip-zone-plan-dates"' in bar, "the strip does not show the dates"
    for zone in ZONES:
        assert f'data-trip-zone-tab="{zone}"' in bar, (
            f"the {zone} tab is not in the strip above the zones"
        )
    assert 'role="tablist"' in bar and 'role="tab"' in bar, (
        "the zone switch is not announced as one"
    )


def check_only_the_open_zone_is_shown() -> None:
    for zone in ZONES:
        rule = f'#module-trip-planner[data-active-zone="{zone}"] [data-trip-zone="{zone}"]'
        assert rule in CSS, f"nothing shows the {zone} zone"
    assert "#module-trip-planner[data-active-zone] [data-trip-zone] { display: none; }" in CSS, (
        "the zones are never hidden, so all four show at once"
    )
    # With no script, the page must show everything rather than nothing.
    assert "[data-active-zone]" in CSS and "#module-trip-planner [data-trip-zone] { display: none" not in CSS, (
        "the zones are hidden even before one has been chosen"
    )


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function build() {
  const tabs = ['settings', 'route', 'briefing', 'execution'].map(zone => ({
    dataset: { tripZoneTab: zone },
    classes: new Set(),
    attributes: {},
    classList: {
      toggle(name, on) { on ? this.owner.classes.add(name) : this.owner.classes.delete(name); },
    },
    setAttribute(name, value) { this.attributes[name] = value; },
  }));
  tabs.forEach(tab => { tab.classList.owner = tab; });
  const host = { dataset: {}, querySelectorAll: () => tabs };
  const name = { textContent: '' };
  const dates = { textContent: '' };
  const context = {
    console,
    I18n: { t: text => text },
    document: {
      getElementById: id => (
        id === 'module-trip-planner' ? host
        : id === 'trip-zone-plan-name' ? name
        : id === 'trip-zone-plan-dates' ? dates
        : null),
    },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/modules/trip-zones.js', 'utf8'), context);
  return { context, host, tabs, name, dates };
}

const app = build();
const { TripZones } = app.context;

// The plan setup is where a reader lands, because it is what they set up first.
assert.strictEqual(TripZones.DEFAULT_ZONE, 'settings');

for (const zone of TripZones.ZONES) {
  TripZones.show(zone);
  assert.strictEqual(app.host.dataset.activeZone, zone, `${zone} did not open`);
  const selected = app.tabs.filter(tab => tab.classes.has('active'));
  assert.strictEqual(selected.length, 1, `${zone}: ${selected.length} tabs look active`);
  assert.strictEqual(selected[0].dataset.tripZoneTab, zone);
  assert.strictEqual(selected[0].attributes['aria-selected'], 'true');
  const others = app.tabs.filter(tab => tab !== selected[0]);
  assert.ok(others.every(tab => tab.attributes['aria-selected'] === 'false'),
    `${zone}: another tab still says it is selected`);
}

// An unknown zone falls back rather than showing nothing at all.
TripZones.show('nonsense');
assert.strictEqual(app.host.dataset.activeZone, 'settings');

// The strip names the plan and its dates, whichever zone is open.
TripZones.show('execution');
TripZones.renderHeader({ id: 'p1', title: 'Europe September', start_date: '2026-09-14', end_date: '2026-09-30' });
assert.strictEqual(app.name.textContent, 'Europe September');
assert.ok(app.dates.textContent.includes('2026-09-14')
  && app.dates.textContent.includes('2026-09-30'), app.dates.textContent);
assert.strictEqual(app.host.dataset.activeZone, 'execution',
  'naming the plan moved the reader out of the zone they were in');

// Re-reading the same plan leaves the reader where they were working.
TripZones.planChanged({ id: 'p1', title: 'Europe September' }, 'p1');
assert.strictEqual(app.host.dataset.activeZone, 'execution',
  'a plan being re-read threw the reader back to the settings');

// Opening a different plan starts at that plan's settings.
TripZones.planChanged({ id: 'p2', title: 'Asia October' }, 'p1');
assert.strictEqual(app.host.dataset.activeZone, 'settings');
assert.strictEqual(app.name.textContent, 'Asia October');

// No plan says so, rather than showing the last one's name.
TripZones.renderHeader(null);
assert.ok(app.name.textContent.toLowerCase().includes('no plan'), app.name.textContent);
assert.strictEqual(app.dates.textContent, '');

// A plan with no dates yet says that too, instead of an empty gap.
TripZones.renderHeader({ id: 'p3', title: 'Draft' });
assert.ok(app.dates.textContent.length > 0, 'a plan with no dates showed nothing');
"""


# The editor is in one zone and most of the buttons that open it are in others.
REVEAL = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function build(activeZone) {
  const scrolled = [];
  const measured = [];
  const zone = { dataset: { tripZone: 'route' } };
  const inZone = extra => ({
    ...extra,
    closest(selector) { return selector === '[data-trip-zone]' ? zone : null; },
  });
  const editor = inZone({
    id: 'trip-briefing-editor', hidden: false,
    innerHTML: '<textarea>half-typed briefing</textarea>',
    scrollIntoView: options => scrolled.push(options),
  });
  const map = inZone({ id: 'trip-map' });
  const host = { dataset: { activeZone }, querySelectorAll: () => [] };
  const context = {
    console,
    I18n: { t: text => text },
    State: { tripMap: { invalidateSize: () => measured.push('measured') } },
    requestAnimationFrame: callback => callback(),
    document: {
      getElementById: id => ({
        'module-trip-planner': host,
        'trip-briefing-editor': editor,
        'trip-map': map,
      }[id] || null),
    },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/modules/trip-zones.js', 'utf8'), context);
  vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-briefing-reveal.js', 'utf8'), context);
  return { context, host, editor, scrolled, measured };
}

// A10 - opened from the visit execution zone, the editor is in another one.
// Un-hiding it there shows nothing at all.
const fromExecution = build('execution');
fromExecution.context.TripZones.show('execution');
fromExecution.context.TripBriefingReveal.show(fromExecution.editor);
assert.strictEqual(fromExecution.host.dataset.activeZone, 'route',
  'the editor was revealed inside a zone that is not on screen');
assert.strictEqual(fromExecution.scrolled.length, 1,
  'the reader was not taken to the editor');
assert.ok(fromExecution.editor.innerHTML.includes('half-typed briefing'),
  'revealing the editor threw away what was typed in it');

// Opened from the zone it already lives in, nothing moves but the scroll.
const fromRoute = build('route');
fromRoute.context.TripZones.show('route');
fromRoute.context.TripBriefingReveal.show(fromRoute.editor);
assert.strictEqual(fromRoute.host.dataset.activeZone, 'route');
assert.strictEqual(fromRoute.scrolled.length, 1);

// A11 - the map measured itself while its zone was display:none. Opening the
// zone asks the same map to measure again.
const app = build('settings');
app.context.TripZones.show('settings');
assert.deepStrictEqual(app.measured, [],
  'the map was remeasured for a zone it is not in');
const before = app.context.State.tripMap;
app.context.TripZones.show('route');
assert.deepStrictEqual(app.measured, ['measured'],
  'the map was never remeasured, so it keeps the size it had while hidden');
assert.strictEqual(app.context.State.tripMap, before,
  'the map was rebuilt instead of remeasured, losing zoom and markers');
app.context.TripZones.show('briefing');
app.context.TripZones.show('route');
assert.deepStrictEqual(app.measured, ['measured', 'measured'],
  'coming back to the map zone left it stale');

// A page with no map yet must not throw on the way into the zone.
const empty = build('settings');
empty.context.State.tripMap = null;
empty.context.TripZones.show('route');
"""


def check_every_briefing_entry_point_reveals_it() -> None:
    """Four buttons in three zones, one way in - so none of them is missed."""
    modules = ROOT / "frontend" / "js" / "modules"
    openers = [
        path.name for path in sorted(modules.glob("*.js"))
        if "trip-briefing-editor" in path.read_text(encoding="utf-8")
        and path.name not in {"trip-briefing-actions.js", "trip-briefing-reveal.js"}
    ]
    assert not openers, (
        "these modules reach for the briefing editor themselves instead of "
        f"going through the one path that reveals it: {openers}"
    )
    # Both spellings: a module that reaches it through window uses `?.`, and
    # the point is which door they use, not how they spell it.
    callers = [
        path.name for path in sorted(modules.glob("*.js"))
        if "TripBriefingActions.open(" in path.read_text(encoding="utf-8")
        or "TripBriefingActions?.open?.(" in path.read_text(encoding="utf-8")
    ]
    assert len(callers) >= 4, (
        f"only {callers} open a briefing; the picker, the flexible-visit list, "
        "the execution card, the timeline's detail panel and the visit-drop all do"
    )
    actions = (modules / "trip-briefing-actions.js").read_text(encoding="utf-8")
    assert "TripBriefingReveal.show(root)" in actions, (
        "opening the editor no longer goes through the reveal"
    )
    rows = (modules / "trip-briefing-rows.js").read_text(encoding="utf-8")
    assert "TripBriefingReveal.open()" in rows, (
        "drawing the form makes it visible by a path of its own again"
    )
    # And the editor really is inside a zone, or there is nothing to reveal.
    editor = TRIP[TRIP.index('id="trip-briefing-editor"') - 900:
                  TRIP.index('id="trip-briefing-editor"')]
    assert 'data-trip-zone="' in editor, (
        "the briefing editor is not inside any zone"
    )


def check_a_zone_change_does_not_redraw() -> None:
    """Hiding is what keeps an unsaved briefing alive across a zone change."""
    source = (ROOT / "frontend" / "js" / "modules" / "trip-zones.js").read_text(
        encoding="utf-8"
    )
    for forbidden in ("innerHTML", "loadTripPlanner", "remove()", "replaceChildren",
                      "L.map(", "destroyTripPlannerMap"):
        assert forbidden not in source, (
            f"the zone switch calls {forbidden}, which would throw away a draft"
        )


def main() -> None:
    check_every_zone_exists_and_has_content()
    check_the_plan_is_named_above_the_zones()
    check_only_the_open_zone_is_shown()
    check_a_zone_change_does_not_redraw()
    check_every_briefing_entry_point_reveals_it()
    for script, label in ((HARNESS, "zones"), (REVEAL, "reveal and map size")):
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{label}: {result.stderr or result.stdout}"
    print("PASS: four trip zones, one plan, and a zone change keeps the draft")


if __name__ == "__main__":
    main()
