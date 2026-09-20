"""Which part was saved, which part was not, and where to finish the rest.

One card carries three different saving boundaries - the agreed time writes
itself to the server, the stay duration lives in the route draft until the route
is calculated and saved, and the visit's own details are saved by a button - and
a fourth kind of unsaved work, a visit preparation in another zone, can stop
every route action. Each of them said "saved" or "blocked" on its own, and the
reader was left to work out which was which:

  * Typing 2 days left a two-day stay over a one-day schedule with nothing to
    say the dates were the last calculation's, and "Visit details saved" did not
    mention that the duration was not part of that save.
  * With a preparation unsaved elsewhere, the shared bar refused and explained -
    while the out-of-date notice below it still offered a "Preview route" button
    that could only produce the same refusal.
  * The agreed time saves itself and the card is rebuilt from the answer, so a
    visit purpose typed a moment earlier was replaced by the stored value.
  * The planning card offered "Visited", which the server refuses without the
    actual date and half-day that only the execution card has.
  * And switching the stop order to automatic cleared the flag that tells the
    calculation a visit is an appointment - on the very setting where an agreed
    time most needs to be planned around.
"""

from __future__ import annotations

import json
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


def check_a_typed_duration_says_it_is_waiting() -> None:
    card = source("trip-stop-card.js")
    pending = source("trip-stop-pending.js")
    assert "TripStopPending?.half?.(stop)" in card and "function half(stop)" in pending, (
        "a duration typed into the route draft is shown beside dates from the "
        "last calculation with nothing to tell them apart"
    )
    assert "Last calculated result. Waiting to be updated: {count} days." in pending
    # Typing redraws nothing, so the note has to be written when the number
    # changes rather than at the next redraw.
    transport = source("trip-transport-actions.js")
    assert "tripStopMarkPending?.(stopId)" in transport, (
        "the note waits for an unrelated redraw before it appears"
    )
    assert "Calculate and save the route to apply a new duration." in card, (
        "nothing says what makes a new duration take effect"
    )
    # The save button's own scope, said out loud and derived from real state.
    actions = source("trip-itinerary-actions.js")
    assert "TripSaveScope?.note?.(stopId)" in actions, (
        "'Visit details saved' no longer says what it did not save"
    )
    scope = source("trip-save-scope.js")
    assert "is still in the route draft" in scope and "Still unsaved: {what}" in scope
    assert "TripOpenEditors?.list?.()" in scope, (
        "the sentence about other unsaved work is not derived from the drafts"
    )
    # And the redraws that follow a save carry what is being typed across them:
    # the card is rebuilt from the server's answer, which holds the stored
    # value, not the half-written one.
    typing = source("trip-stop-typing.js")
    assert "baselines" in typing and "baselines.set(id, String(value ?? \'\'));" in typing, (
        "nothing remembers what the field was drawn with, so a response that "
        "updates the plan turns an untouched field into a draft"
    )
    assert "if (text !== stored(stopId)) { drafts.set(id, text); return; }" in typing, (
        "whether there is anything left to save is not asked of what is stored, "
        "so the value the field happens to show can go back over a newer one"
    )
    assert "const key = stopId => `${planId()}:${stopId}`;" in typing, (
        "the draft is not kept against the plan and visit it was typed for"
    )
    assert "function guard(" in typing, "leaving a visit no longer protects what was typed"
    assert "if (drafts.has(id)) return;        // being edited: the baseline is the edit's" in typing, (
        "a redraw moves the baseline of a field being edited, so saving would "
        "carry the draft over a newer value with nothing said about it"
    )
    clash = source("trip-purpose-conflict.js")
    assert "function of(" in clash and "function blockSave(" in clash, (
        "nothing checks whether the stored purpose moved while it was typed"
    )
    assert "theirs === base ? null" in clash, (
        "a response about other fields is reported as a purpose conflict"
    )
    save_actions = source("trip-itinerary-actions.js")
    assert "TripStopTyping?.blockSave?.(stopId)" in save_actions, (
        "the save writes the draft over somebody else's change without asking"
    )
    assert "if (window.TripStopTyping?.isDirty?.(stopId)) {" in save_actions, (
        "every save submits the purpose the field happens to show, so saving "
        "the agreed time puts an old purpose back over a newer one"
    )
    assert "visit_purpose: document.getElementById" not in save_actions, (
        "the purpose is read straight out of the box the save is not about"
    )
    card_conflict = source("trip-stop-card.js")
    assert "${tripStopPurposeConflict(stop)}" in card_conflict and "Keep mine and overwrite" in card_conflict, (
        "the reader is given no way to choose between the two versions"
    )
    selection = source("trip-selection.js")
    assert "TripStopTyping?.guard?.(" in selection, (
        "choosing another object throws away an unsaved purpose"
    )
    editors = source("trip-open-editors.js")
    assert "Unsaved visit purpose for {name}" in editors, (
        "an unsaved purpose is not named among the things holding the route up"
    )
    card_source = source("trip-stop-card.js")
    assert "TripStopTyping?.valueFor?.(stop.id, stop.visit_purpose || '')" in card_source, (
        "the card draws the stored purpose over the one being typed"
    )
    assert "TripStopTyping.note(" in card_source, (
        "typing into the purpose is not recorded anywhere it can outlive the card"
    )

    # The duration is not smuggled into the visit-details request either.
    save = actions[actions.index("window.saveTripStopResult"):]
    for field in ("duration_half_days", "stay_days"):
        assert field not in save[:1200], (
            f"the visit-details save now writes {field} without saying so"
        )


def check_a_blocked_route_offers_what_is_possible() -> None:
    schedule = source("trip-schedule-view.js")
    assert "TripRouteState?.derive?.(plan)?.editors" in schedule, (
        "the out-of-date notice decides for itself whether a route action is "
        "possible, instead of asking the one place that knows"
    )
    assert "TripRouteBar.goToBlocker()" in schedule, (
        "the notice offers a button that can only be refused"
    )
    assert "Save or cancel first: {what}" in schedule, (
        "the notice does not say whose unsaved work is in the way"
    )
    editors = source("trip-open-editors.js")
    assert "Unsaved visit preparation for {name}" in editors, (
        "an unsaved preparation is not attributed to a customer, so nobody can "
        "find it among twenty-seven visits"
    )
    assert "State?.currentTripPlan?.stops" in editors


def check_the_planning_card_does_not_promise_a_visit_record() -> None:
    card = source("trip-stop-card.js")
    assert 'id="stop-result-' not in card, (
        "the planning card offers a result the server will refuse for want of "
        "an actual date and half-day"
    )
    assert "TripRouteFocus.goToVisitRecord(" in card, (
        "there is no way from the plan to the card that records the visit"
    )
    assert "Actually visited" in card, "the card no longer shows what happened"
    focus = source("trip-route-focus.js")
    assert "function goToVisitRecord(" in focus and "TripZones?.show?.('execution')" in focus
    actions = source("trip-itinerary-actions.js")
    save = actions[actions.index("window.saveTripStopResult"):]
    body = save[save.index("ApiClient.updateTripStop"):save.index("TripPlanIdentity.accept")]
    for field in ("result_status", "result_notes"):
        assert field not in body, (
            f"the planning save still writes {field}, which it cannot complete"
        )


def check_the_stop_order_is_not_a_promise_to_a_customer() -> None:
    transport = source("trip-transport-actions.js")
    start = transport.index("    function routeModeChanged")
    end = transport.index("\n    function ", start + 10)
    mode = transport[start:end]
    assert "locked = false" not in mode, (
        "choosing automatic order still clears the flag the calculation reads "
        "as 'this visit is an appointment'"
    )
    assert "control.disabled = !stop.planned_date;" in transport, (
        "the confirmation box is disabled by the ordering mode again"
    )
    assert "if (control.disabled) control.checked = false;" not in transport, (
        "the confirmation box is unticked by the ordering mode, and the next "
        "save of that visit would write it back as unconfirmed"
    )


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
  document: makeDocument(['trip-current-plan']),
  setTimeout, addEventListener() {},
  TripDuration: { readStopDuration: stop => stop.duration_half_days ?? 2,
                  toDisplayDays: value => value / 2, normalizeHalfDays: v => v },
  TripPlanningDraft: { get: () => ({ stopDurations: { s1: { half_days: 4 } } }) },
  TripOpenEditors: { list: () => [
    { kind: 'briefing', zone: 'briefing', stopId: 's9', label: 'Unsaved visit preparation for Lyon Lasers' },
  ] },
};
ctx.window = ctx;
ctx.State = { currentTripPlan: { id: 'p1', stops: [
  { id: 's1', stop_kind: 'customer', customer_name: 'Berlin Optics',
    visit_purpose: 'stored purpose', duration_half_days: 2 },
] } };
vm.createContext(ctx);
for (const file of ['trip-stop-typing.js', 'trip-purpose-conflict.js', 'trip-save-scope.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), ctx, { filename: file });
}
const doc = ctx.document;

// What a save on this card did not cover, in one sentence, from real state.
const note = ctx.TripSaveScope.note('s1');
assert.match(note, /2 days is still in the route draft/, note);
assert.match(note, /Lyon Lasers/, 'the other unsaved work is not named');

// Nothing unsaved anywhere: the sentence has to be empty, not reassuring.
ctx.TripOpenEditors.list = () => [];
ctx.TripPlanningDraft.get = () => ({ stopDurations: { s1: { half_days: 2 } } });
assert.equal(ctx.TripSaveScope.note('s1'), '',
  'a save claims other work is unsaved when none is');

// A purpose typed into one visit belongs to that visit, not to whichever card
// happens to be on screen - and "unsaved" means "different from what the field
// was drawn with", never "different from the plan as it now stands".
ctx.TripStopTyping.baseline('s1', 'stored purpose');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false);
assert.equal(ctx.TripStopTyping.valueFor('s1', 'stored purpose'), 'stored purpose');

ctx.TripStopTyping.note('s1', 'half-typed purpose');
assert.equal(ctx.TripStopTyping.isDirty('s1'), true);
assert.equal(ctx.TripStopTyping.firstDirty().id, 's1');

// Choosing another visit and coming back: the text is still there, because it
// was kept against the visit rather than against the card.
assert.equal(ctx.TripStopTyping.valueFor('s2', 'other stored'), 'other stored',
  "another visit inherited the first one's unsaved text");
assert.equal(ctx.TripStopTyping.valueFor('s1', 'stored purpose'), 'half-typed purpose',
  'the unsaved purpose was lost by looking at another visit');

// Leaving a visit with something typed into it is refused, and says which one.
let said = '';
ctx.alert = message => { said = message; };
assert.equal(ctx.TripStopTyping.guard('s2'), true, 'moving away threw the text away');
assert.match(said, /Berlin Optics/, said);
assert.equal(ctx.TripStopTyping.guard('s1'), false, 'the visit being typed into is not blocked');

// A field nobody touched takes the server's newer value - the old one must not
// be mistaken for somebody's work now that the plan in memory has moved on.
ctx.State.currentTripPlan.stops[1] = { id: 's2', customer_name: 'Lyon Lasers',
  visit_purpose: 'purpose updated elsewhere' };
assert.equal(ctx.TripStopTyping.valueFor('s2', 'purpose updated elsewhere'),
  'purpose updated elsewhere',
  'an untouched field was restored to the value it was drawn with earlier');
assert.equal(ctx.TripStopTyping.isDirty('s2'), false);

// Typing it back to what the record says is not unsaved work.
ctx.TripStopTyping.note('s1', 'stored purpose');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false);
assert.equal(ctx.TripStopTyping.isDirty(), false);

// A redraw does not move the baseline of something being edited.
ctx.State.currentTripPlan = { id: 'p1', stops: [
  { id: 's1', customer_name: 'Berlin Optics', visit_purpose: 'original' },
  { id: 's2', customer_name: 'Lyon Lasers', visit_purpose: 'other stored' },
] };
ctx.TripStopTyping.reset();
assert.equal(ctx.TripStopTyping.valueFor('s1', 'original'), 'original');
ctx.TripStopTyping.note('s1', 'mine');
// the server's copy moves on, and the card is redrawn with it
ctx.State.currentTripPlan.stops[0].visit_purpose = 'theirs';
assert.equal(ctx.TripStopTyping.valueFor('s1', 'theirs'), 'mine',
  'the redraw drew over what was being typed');
assert.equal(ctx.TripStopTyping.baselineOf('s1'), 'original',
  'the redraw moved the baseline of a field being edited');
// Typing back to what it was *loaded* with, after somebody else changed it, is
// still a change to the stored purpose: it may not be called "nothing pending"
// and then written back by the next save.
ctx.TripStopTyping.note('s1', 'original');
assert.equal(ctx.TripStopTyping.isDirty('s1'), true,
  'the old text was called clean while the record holds something else');
assert.equal(ctx.TripStopTyping.baselineOf('s1'), 'original');
const reverted = ctx.TripStopTyping.conflict('s1');
assert.equal(reverted && reverted.theirs, 'theirs',
  'reverting to the loaded value hid the fact that the record had moved');
// but typing what the record actually says leaves nothing to save
ctx.TripStopTyping.note('s1', 'theirs');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false,
  'a field that says exactly what the record says is still reported as unsaved');
ctx.TripStopTyping.note('s1', 'original');       // back to the pending state

// A response that changed other fields is not a conflict about this one.
ctx.TripStopTyping.reset();
ctx.State.currentTripPlan.stops[0].visit_purpose = 'original';
ctx.TripStopTyping.valueFor('s1', 'original');
ctx.TripStopTyping.note('s1', 'mine');
ctx.State.currentTripPlan.stops[0].planned_date = '2026-10-01';   // something else changed
ctx.TripStopTyping.valueFor('s1', 'original');
assert.equal(ctx.TripStopTyping.conflict('s1'), null,
  'a response about other fields was reported as a purpose conflict');

// When the purpose itself moved, the draft may not be written over it silently.
ctx.State.currentTripPlan.stops[0].visit_purpose = 'theirs';
ctx.TripStopTyping.valueFor('s1', 'theirs');
const clash = ctx.TripStopTyping.conflict('s1');
assert.equal(clash.mine, 'mine');
assert.equal(clash.theirs, 'theirs');
let blocked = '';
ctx.alert = message => { blocked = message; };
assert.equal(ctx.TripStopTyping.blockSave('s1'), true,
  'the save carried the draft over somebody else\'s change');
assert.match(blocked, /Choose which version to keep/, blocked);
// Choosing is what releases it, either way.
ctx.TripStopTyping.keepMine('s1');
assert.equal(ctx.TripStopTyping.conflict('s1'), null);
assert.equal(ctx.TripStopTyping.blockSave('s1'), false);
assert.equal(ctx.TripStopTyping.isDirty('s1'), true, 'keeping mine discarded my text');
ctx.TripStopTyping.takeTheirs('s1');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false);

// A save makes what is stored the new baseline.
ctx.TripStopTyping.valueFor('s1', 'theirs');
ctx.TripStopTyping.note('s1', 'mine again');
ctx.State.currentTripPlan.stops[0].visit_purpose = 'mine again';
ctx.TripStopTyping.markClean('s1');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false);
ctx.TripStopTyping.note('s1', 'mine again');
assert.equal(ctx.TripStopTyping.isDirty('s1'), false, 'the baseline did not follow the save');

(async () => {
// The save itself, against a record somebody else has moved on.
//
// "Nothing pending" is not the same as "the field agrees with the record": a
// save that always submits whatever the box shows would put the old text back
// over the newer one, on the newest row version, with nothing said about it.
ctx.setTripBusy = () => {};
ctx.notify = () => {};
ctx.handleTripError = async () => {};
ctx.TripStopScheduleControls = { readPayload: () => ({ preferred_period: 'AM' }) };
ctx.TripPlanIdentity = { intend: () => 'token', accept: (token, moved) => {
  ctx.State.currentTripPlan = moved; return true;
} };
const store = { s1: { id: 's1', customer_name: 'Berlin Optics',
  visit_purpose: 'C from somebody else', row_version: 57 } };
const sent = [];
ctx.ApiClient = { updateTripStop: async (planId, stopId, payload) => {
  sent.push(payload);
  if ('visit_purpose' in payload) store[stopId].visit_purpose = payload.visit_purpose;
  store[stopId].row_version += 1;
  return { id: planId, stops: [ { ...store[stopId] } ] };
} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-actions.js', 'utf8'),
  ctx, { filename: 'trip-itinerary-actions.js' });

// baseline A -> typed B -> the record becomes C -> typed back to A -> save
ctx.TripStopTyping.reset();
ctx.State.currentTripPlan = { id: 'p1', stops: [
  { id: 's1', customer_name: 'Berlin Optics', visit_purpose: 'A as loaded', row_version: 56 },
] };
ctx.TripStopTyping.valueFor('s1', 'A as loaded');
ctx.TripStopTyping.note('s1', 'B typed by me');
ctx.State.currentTripPlan.stops[0] = { ...store.s1 };          // the record moves to C
ctx.TripStopTyping.valueFor('s1', 'C from somebody else');     // and the card is redrawn
ctx.TripStopTyping.note('s1', 'A as loaded');                  // typed back to the loaded value
let stopped = '';
ctx.alert = message => { stopped = message; };
await ctx.saveTripStopResult('s1');
assert.equal(store.s1.visit_purpose, 'C from somebody else',
  'the old text went back over a newer purpose, and nothing was said about it');
assert.equal(sent.length, 0, 'the save was sent at all');
assert.match(stopped, /Choose which version to keep/, stopped);

// Confirmed, it goes - and only then.
ctx.TripStopTyping.keepMine('s1');
await ctx.saveTripStopResult('s1');
assert.equal(store.s1.visit_purpose, 'A as loaded', 'the confirmed overwrite did not happen');
assert.equal(sent.length, 1);
assert.equal(sent[0].visit_purpose, 'A as loaded');

// And a save that is not about the purpose does not carry it at all.
sent.length = 0;
ctx.State.currentTripPlan.stops[0] = { ...store.s1 };
store.s1.visit_purpose = 'changed again elsewhere';
ctx.TripStopTyping.reset();
ctx.TripStopTyping.valueFor('s1', 'A as loaded');
await ctx.saveTripStopResult('s1');
assert.equal('visit_purpose' in sent[0], false,
  'a save about the agreed time submitted the purpose the field happened to show');
assert.equal(store.s1.visit_purpose, 'changed again elsewhere',
  "a save about the agreed time undid somebody else's purpose");

// Another plan's unsaved work never shows on this one.
ctx.TripStopTyping.note('s1', 'typed on plan one');
ctx.State.currentTripPlan = { id: 'p2', stops: [{ id: 's1', customer_name: 'Somebody else' }] };
assert.equal(ctx.TripStopTyping.isDirty(), false, "another plan's draft leaked into this one");
assert.equal(ctx.TripStopTyping.valueFor('s1', 'plan two stored'), 'plan two stored');

console.log(JSON.stringify({ ok: true }));
})().catch(error => { console.error(error); process.exit(1); });
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


def check_the_scope_and_the_typing_behave() -> None:
    output = _node(HARNESS.replace("__DOM__", DOM))
    assert json.loads(output.strip().splitlines()[-1])["ok"]


def main() -> None:
    check_a_typed_duration_says_it_is_waiting()
    check_a_blocked_route_offers_what_is_possible()
    check_the_planning_card_does_not_promise_a_visit_record()
    check_the_stop_order_is_not_a_promise_to_a_customer()
    check_the_scope_and_the_typing_behave()
    print("PASS: a save says which part it covered, a blocked route offers the "
          "thing that has to happen first, typing survives a redraw, and the "
          "stop order no longer cancels a customer's agreed time")


if __name__ == "__main__":
    main()
