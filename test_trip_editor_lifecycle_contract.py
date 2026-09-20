"""Ending a local edit gives the shared route actions back, and points at the
card that is actually holding them up.

Three defects this covers, all of them in the path *after* an edit rather than
during it:

The shared bar listened for typing. Cancelling a personal stop is not typing:
the draft was discarded, the editor was hidden, and preview and save stayed
greyed out until the reader changed something else or switched zones. A
disabled button cannot re-check itself - clicking it runs nothing.

"Go to it" for an unsaved visit record looked for `trip-visit-editor`. Visit
execution has no such element: it renders one `visit-card-<stop id>` per stop.
The reader was told which kind of thing was in the way and taken to nothing.

Opening another plan remembered the position of the zone being *left* under the
new plan's id, because the plan on screen has already changed by the time the
zones are told. The first visit to the new plan's route zone started at the
depth of the old one.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"


DOM = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// A DOM only as far as these modules reach into one: elements appear when they
// are asked for, and remember what was set on them.
function makeDom() {
  const nodes = new Map();
  const make = id => ({
    id, value: '', textContent: '', innerHTML: '', hidden: true, disabled: false,
    className: '', title: '', dataset: {}, scrollTop: 0, focused: false,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(name, value) { this.dataset[name] = value; },
    getAttribute(name) { return this.dataset[name]; },
    removeAttribute(name) { delete this.dataset[name]; },
    focus() { this.focused = true; },
    scrollIntoView() { this.scrolled = true; },
    appendChild() {},
    getBoundingClientRect: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
    querySelector(selector) { return this.children?.[selector] || null; },
    querySelectorAll() { return []; },
  });
  const el = id => { if (!nodes.has(id)) nodes.set(id, make(id)); return nodes.get(id); };
  const selectors = new Map();
  return {
    el, selectors,
    document: {
      getElementById: id => (nodes.has(id) ? nodes.get(id) : null),
      querySelector: selector => selectors.get(selector) || null,
      querySelectorAll: () => [],
      createElement: tag => make(tag),
      addEventListener() {},
      createTextNode: () => ({}),
      body: null, documentElement: {},
    },
  };
}

function context(dom, extra = {}) {
  const ctx = {
    console,
    document: dom.document,
    requestAnimationFrame: callback => callback(),
    setTimeout: (callback) => callback(),
    notify() {}, alert() {}, confirm: () => true,
    escapeHtml: value => String(value ?? ''),
    I18n: { t: (text, params = {}) => Object.entries(params)
      .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
    ...extra,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  return ctx;
}

function load(ctx, name) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + name, 'utf8'),
                  ctx, { filename: name });
}
"""


CANCEL = DOM + r"""
// Open a personal stop, type into it, cancel it. The production modules do all
// three; nothing here pokes at the bar's buttons directly.
const dom = makeDom();
const ctx = context(dom, {
  State: { currentTripPlan: { id: 'p1',
    itinerary_generated_at: '2026-09-15T00:00:00Z',
    itinerary_summary: { valid: true, stale: false },
    stops: [{ id: 's1', customer_name: 'Beijing Optics' },
            { id: 's2', customer_name: 'Wuhan Laser' }] } },
  TripPlanningDraft: { get: () => ({ dirty: false, previewReady: false }) },
  TripDuration: { toDisplayDays: () => '1', parseDisplayDays: () => 2,
                  readStopDuration: () => 2 },
  TripExportActions: { refresh() {} },
});
['trip-route-status', 'trip-route-next', 'trip-route-preview', 'trip-route-save',
 'trip-free-stop-editor', 'trip-free-stop-name', 'trip-free-stop-geocode-status',
 'trip-free-stop-geocode-candidates', 'trip-free-stop-draft-status',
 'trip-add-free-stop', 'trip-briefing-draft-status'].forEach(dom.el);

load(ctx, 'trip-open-editors.js');
load(ctx, 'trip-route-state.js');
load(ctx, 'trip-route-bar.js');
load(ctx, 'trip-free-stop-draft.js');
load(ctx, 'trip-free-stop-form.js');
load(ctx, 'trip-briefing-draft.js');
load(ctx, 'trip-visit-draft.js');

const save = dom.el('trip-route-save');
const preview = dom.el('trip-route-preview');
const status = dom.el('trip-route-status');
const readings = {};

ctx.TripRouteBar.render();
readings.start = save.disabled;
assert.equal(save.disabled, false, 'a saved plan with nothing open refused to save');

// 1. The personal stop editor, through its own open/close.
ctx.TripFreeStopForm.open();
readings.freeStopOpened = save.disabled;
assert.equal(save.disabled, true, 'an open personal stop editor did not hold the route');
ctx.TripFreeStopDraft.mark();
assert.equal(save.disabled, true);
assert.equal(ctx.TripFreeStopForm.close({ force: true }), true);
readings.freeStopCancelled = save.disabled;
assert.equal(save.disabled, false,
  'cancelling the personal stop left preview and save disabled');
assert.equal(preview.disabled, false);
assert.match(status.textContent, /Route saved/,
  'the headline still described an editor that is closed');

// 2. The visit preparation editor: loaded, typed into, cancelled.
ctx.TripBriefingDraft.load('s1', { row_version: 1, participants: [] });
ctx.TripBriefingDraft.markDirty();
readings.briefingDirty = save.disabled;
assert.equal(save.disabled, true, 'an unsaved preparation did not hold the route');
ctx.TripBriefingDraft.reset();
readings.briefingCancelled = save.disabled;
assert.equal(save.disabled, false, 'cancelling the preparation left the route blocked');

// 3. A visit execution card, discarded from the card itself.
ctx.TripVisitDraft.mark('s2');
readings.visitDirty = save.disabled;
assert.equal(save.disabled, true, 'an unsaved visit card did not hold the route');
ctx.TripVisitDraft.discard('s2');
readings.visitDiscarded = save.disabled;
assert.equal(save.disabled, false, 'discarding the visit card left the route blocked');

// 4. Two unsaved cards at once. Discarding the first leaves the route blocked
// by the second - and the bar has to say the second, because that is where its
// own "go to it" now leads.
const next = dom.el('trip-route-next');
ctx.TripVisitDraft.mark('s1');
ctx.TripVisitDraft.mark('s2');
readings.twoDirty = next.textContent;
assert.match(next.textContent, /Beijing Optics/, 'the first unsaved card was not named');
ctx.TripVisitDraft.discard('s1');
readings.firstDiscarded = next.textContent;
assert.equal(save.disabled, true,
  'the second unsaved card stopped holding the route when the first was discarded');
assert.match(next.textContent, /Wuhan Laser/,
  'the bar went on naming the card that was discarded, while "go to it" goes to '
  + 'the one that is still unsaved');
assert.equal(ctx.TripRouteState.derive().nextStep.editor.stopId, 's2',
  'the blocked action still carries the discarded card\'s id');
ctx.TripVisitDraft.discard('s2');
readings.bothDiscarded = save.disabled;
assert.equal(save.disabled, false, 'discarding the last card left the route blocked');

// 5. And a save that failed still blocks: the editor is still open and unsaved,
// so giving the actions back on any close would be the opposite mistake.
ctx.TripFreeStopForm.open();
ctx.TripFreeStopDraft.mark();
assert.equal(save.disabled, true, 'a still-open unsaved editor released the route');
readings.stillOpen = save.disabled;
console.log(JSON.stringify(readings));
"""


TARGET = DOM + r"""
// The blocked action names the visit and goes to its card.
const dom = makeDom();
const ctx = context(dom, {
  State: { currentTripPlan: { id: 'p1', stops: [
    { id: 's1', customer_name: 'Beijing Optics' },
    { id: 's2', customer_name: 'Wuhan Laser' }] } },
  TripPlanningDraft: { get: () => ({ dirty: false }) },
});
load(ctx, 'trip-open-editors.js');
load(ctx, 'trip-route-state.js');
load(ctx, 'trip-visit-draft.js');
load(ctx, 'trip-route-focus.js');

ctx.TripVisitDraft.mark('s2');
const blocked = ctx.TripRouteState.derive().nextStep;
assert.equal(blocked.kind, 'editor');
assert.equal(blocked.editor.stopId, 's2',
  'the blocked action does not carry the id of the card holding it up');
assert.match(blocked.editor.label, /Wuhan Laser/,
  'the reader is told the kind of thing in the way but not which one');

// Nothing to go to before the card exists: no pretending it worked.
assert.equal(ctx.TripRouteFocus.focusEditor('visit', 's2'), false);

const card = dom.el('visit-card-s2');
const field = { disabled: false, focused: false, focus() { this.focused = true; } };
card.children = { 'textarea, input.form-input, select': field };
const other = dom.el('visit-card-s1');
other.children = { 'textarea, input.form-input, select':
  { disabled: false, focused: false, focus() { this.focused = true; } } };

assert.equal(ctx.TripRouteFocus.focusEditor('visit', blocked.editor.stopId), true);
assert.ok(card.scrolled, 'the card holding the route up was never brought on screen');
assert.equal(field.focused, true, 'the reader arrived at a card with no caret in it');
assert.equal(other.children['textarea, input.form-input, select'].focused, false,
  'focus landed on a different visit than the one that is unsaved');
assert.equal(ctx.TripRouteFocus.focusEditor('visit', null), false,
  'without an id it claimed to have gone somewhere');
console.log(JSON.stringify({ stopId: blocked.editor.stopId, label: blocked.editor.label }));
"""


POSITION = DOM + r"""
// Reading position belongs to the plan it was read in.
const dom = makeDom();
const main = dom.el('main-content');
dom.selectors.set('.main-content', main);
const host = dom.el('module-trip-planner');
const ctx = context(dom, {
  State: { currentTripPlan: { id: 'A' } },
  TripRouteBar: { render() {} },
});
load(ctx, 'trip-route-focus.js');
load(ctx, 'trip-zones.js');

const readings = {};
ctx.TripZones.show('route');
main.scrollTop = 800;                       // deep in plan A's route

// What TripPlanIdentity.accept does, in its order: the plan on screen changes
// first, and the zones are told afterwards.
ctx.State.currentTripPlan = { id: 'B' };
ctx.TripZones.planChanged({ id: 'B' }, 'A');
readings.afterSwitch = main.scrollTop;
assert.equal(ctx.TripZones.current(), 'settings');

ctx.TripZones.show('route');
readings.firstVisitToB = main.scrollTop;
assert.equal(main.scrollTop, 0,
  "the first visit to the new plan's route inherited the old plan's depth");

// B keeps its own position between its own zones.
main.scrollTop = 300;
ctx.TripZones.show('settings');
ctx.TripZones.show('route');
readings.backInsideB = main.scrollTop;
assert.equal(main.scrollTop, 300, 'moving between zones lost the reading position');

// And going back to A restores where A was being read.
ctx.State.currentTripPlan = { id: 'A' };
ctx.TripZones.planChanged({ id: 'A' }, 'B');
ctx.TripZones.show('route');
readings.backInA = main.scrollTop;
assert.equal(main.scrollTop, 800, 'returning to the first plan lost its position');

// A background re-read of the same plan is not a plan change.
main.scrollTop = 555;
ctx.TripZones.planChanged({ id: 'A' }, 'A');
readings.samePlanReread = main.scrollTop;
assert.equal(main.scrollTop, 555, 're-reading the same plan moved the reader');
assert.equal(ctx.TripZones.current(), 'route');
console.log(JSON.stringify(readings));
"""


def _run(script: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    result = subprocess.run(["node", path], capture_output=True, text=True, cwd=ROOT)
    Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout.strip().splitlines()[-1])


def check_cancelling_an_editor_gives_the_route_actions_back() -> None:
    readings = _run(CANCEL)
    assert readings["freeStopCancelled"] is False
    assert readings["briefingCancelled"] is False
    assert readings["visitDiscarded"] is False
    assert "Beijing Optics" in readings["twoDirty"]
    assert "Wuhan Laser" in readings["firstDiscarded"]
    assert readings["bothDiscarded"] is False
    assert readings["stillOpen"] is True


def check_the_blocked_action_goes_to_the_card_that_is_unsaved() -> None:
    _run(TARGET)
    focus = (MODULES / "trip-route-focus.js").read_text(encoding="utf-8")
    assert "trip-visit-editor" not in focus, (
        "the focus helper still looks for an element visit execution never "
        "renders"
    )
    planner = (MODULES / "trip-planner.js").read_text(encoding="utf-8")
    assert 'id="visit-card-${h(stop.id)}"' in planner, (
        "visit execution no longer renders visit-card-<id>, so the id the "
        "blocked action carries goes nowhere"
    )
    bar = (MODULES / "trip-route-bar.js").read_text(encoding="utf-8")
    assert bar.count(
        "focusEditor?.(editor.kind, editor.stopId || editor.userId)") == 2, (
        "the bar takes the reader to a kind of editor without saying which one: "
        "execution has a card per stop and the team card a row per member"
    )


def check_a_new_plan_does_not_inherit_the_last_ones_position() -> None:
    readings = _run(POSITION)
    assert readings["firstVisitToB"] == 0
    assert readings["backInsideB"] == 300
    assert readings["backInA"] == 800
    assert readings["samePlanReread"] == 555


def check_the_lifecycle_is_wired_at_the_editors_not_polled() -> None:
    for name in ("trip-free-stop-draft.js", "trip-briefing-draft.js",
                 "trip-visit-draft.js"):
        source = (MODULES / name).read_text(encoding="utf-8")
        assert "TripRouteBar?.render?.()" in source, (
            f"{name} changes what the shared bar may do without telling it"
        )
        assert "MutationObserver" not in source and "setInterval" not in source, (
            f"{name} watches the page instead of saying when its own state "
            "changed"
        )


def main() -> None:
    check_cancelling_an_editor_gives_the_route_actions_back()
    check_the_blocked_action_goes_to_the_card_that_is_unsaved()
    check_a_new_plan_does_not_inherit_the_last_ones_position()
    check_the_lifecycle_is_wired_at_the_editors_not_polled()
    print("PASS: cancelling an edit releases the route actions, a blocked "
          "action names and reaches its card, and a new plan starts at its own "
          "beginning")


if __name__ == "__main__":
    main()
