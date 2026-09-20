"""Each traveller's own departure and return points, settable and clearable.

A member's own points win over the plan's - that is what lets a colleague
already in Berlin join a trip that starts in Shenzhen. The card printed those
points and nothing could change them: the plan's departure field silently did
not apply to that person, and the only way out was to take them off the trip
and add them back, which threw away the route already worked out for them.

The part that is easy to get wrong is clearing. "Follows the plan" has to send
the fields as nulls: a field the payload leaves out is a field the server
leaves unchanged, so an omitted key would look like a save and change nothing.
And it must clear rather than copy today's plan value, or the member would stop
following the plan the next time the plan's own departure point moved.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const nodes = {};
function node(id) {
  const self = {
    id, value: '', innerHTML: '', hidden: false, textContent: '', disabled: false,
    attributes: {},
    setAttribute(name, value) { self.attributes[name] = value; },
    querySelector: () => null,
    // The editor freezes its own fields while its save is in the air, so the
    // fake has to hand back the ones it was asked about.
    querySelectorAll: () => Object.values(nodes).filter(
      other => typeof other.id === 'string' && other.id.includes(id.replace(
        'trip-team-endpoints-', ''))),
  };
  return self;
}
const sent = [];
const alerts = [];
const member = {
  user_id: 'u1', display_name: 'Anna Berg', row_version: 4,
  origin_name_override: 'Berlin', origin_lat_override: 52.52, origin_lng_override: 13.405,
  destination_name_override: 'Berlin',
  destination_lat_override: 52.52, destination_lng_override: 13.405,
};

const ctx = {
  console,
  escapeHtml: value => String(value ?? ''),
  alert: message => alerts.push(message),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: {
    getElementById: id => {
      if (!nodes[id]) nodes[id] = node(id);
      return nodes[id];
    },
    addEventListener() {},
  },
  TripTeamActions: {
    memberOf: () => member,
    saveEndpoints: (userId, fields) => {
      sent.push({ userId, fields });
      return Promise.resolve(false);   // refused, so the editor stays open
    },
  },
};
ctx.window = ctx;
vm.createContext(ctx);
for (const name of ['trip-china-hubs.js', 'trip-team-endpoint-form.js',
                   'trip-team-endpoints.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + name, 'utf8'), ctx,
                  { filename: name });
}
const { TripTeamEndpoints } = ctx;
const field = id => ctx.document.getElementById(id);

(async () => {

// Which of the three shapes a member's points are in.
assert.equal(TripTeamEndpoints.modeOf(member, 'origin'), 'custom');
assert.equal(TripTeamEndpoints.modeOf({}, 'origin'), 'plan');
assert.equal(TripTeamEndpoints.modeOf({
  origin_lat_override: 22.6393, origin_lng_override: 113.8107 }, 'origin'), 'SZX');

// Opened on somebody who has their own place: the place is there to edit, not
// blanked for them to type again.
TripTeamEndpoints.open('u1');
const editor = field('trip-team-endpoints-u1');
assert.equal(editor.hidden, false);
assert.ok(editor.innerHTML.includes('Berlin'), editor.innerHTML.slice(0, 300));

// Follows the plan: nulls, not missing keys.
field('trip-team-origin-preset-u1').value = 'plan';
field('trip-team-destination-preset-u1').value = 'plan';
await TripTeamEndpoints.save('u1');
assert.equal(sent.length, 1, 'nothing was sent');
const cleared = sent[0];
for (const key of ['origin_name_override', 'origin_lat_override', 'origin_lng_override',
                   'destination_name_override', 'destination_lat_override',
                   'destination_lng_override']) {
  assert.ok(key in cleared.fields, `${key} was left out, so the server keeps the old value`);
  assert.equal(cleared.fields[key], null, `${key} was sent as ${cleared.fields[key]}`);
}

// A known airport: its own coordinates, not the plan's.
field('trip-team-origin-preset-u1').value = 'PEK';
field('trip-team-destination-preset-u1').value = 'PVG';
await TripTeamEndpoints.save('u1');
const hub = sent[1].fields;
assert.match(hub.origin_name_override, /Beijing Capital/);
assert.equal(Math.round(hub.origin_lat_override * 10000), 400799);
assert.match(hub.destination_name_override, /Shanghai Pudong/);

// Somewhere typed in, and refused until it is a place: half a location saved
// is a member sent from nowhere.
//
// `Number('')` is 0, so a name with the coordinate boxes left empty passed as
// a place at 0,0 - a real point in the Gulf of Guinea, and a route worked out
// to it. The text is checked before the number, and a latitude that really is
// 0 still has to be accepted.
field('trip-team-origin-preset-u1').value = 'custom';
const refusals = [
  ['', '', '', 'nothing filled in'],
  ['Chengdu Shuangliu (CTU)', '', '', 'a name with no coordinates at all'],
  ['Chengdu Shuangliu (CTU)', '30.5785', '', 'a latitude with no longitude'],
  ['Chengdu Shuangliu (CTU)', '', '103.9471', 'a longitude with no latitude'],
  ['Chengdu Shuangliu (CTU)', '  ', '  ', 'two boxes of spaces'],
  ['   ', '30.5785', '103.9471', 'coordinates with no name'],
];
for (const [name, lat, lng, what] of refusals) {
  const before = sent.length;
  field('trip-team-origin-name-u1').value = name;
  field('trip-team-origin-lat-u1').value = lat;
  field('trip-team-origin-lng-u1').value = lng;
  await TripTeamEndpoints.save('u1');
  assert.equal(sent.length, before, `${what} was saved as a place`);
}
assert.equal(sent.length, 2, 'an incomplete location was saved');
assert.equal(alerts.length, refusals.length, 'nothing was said about a refusal');
assert.equal(field('trip-team-endpoints-u1').hidden, false,
  'the refused save closed the editor and took what was typed with it');

field('trip-team-origin-name-u1').value = 'Chengdu Shuangliu (CTU)';
field('trip-team-origin-lat-u1').value = '30.5785';
field('trip-team-origin-lng-u1').value = '103.9471';
field('trip-team-destination-preset-u1').value = 'plan';
await TripTeamEndpoints.save('u1');
const mixed = sent[2].fields;
assert.equal(mixed.origin_name_override, 'Chengdu Shuangliu (CTU)');
assert.equal(mixed.origin_lat_override, 30.5785);
assert.equal(mixed.destination_name_override, null,
  'one end can follow the plan while the other does not');

// Out-of-range coordinates are not a place either.
field('trip-team-origin-lat-u1').value = '999';
field('trip-team-origin-lng-u1').value = '103.9471';
await TripTeamEndpoints.save('u1');
assert.equal(sent.length, 3, 'a latitude of 999 was accepted');

// And a coordinate that really is zero is a place on the equator, not a gap.
field('trip-team-origin-name-u1').value = 'Null Island buoy';
field('trip-team-origin-lat-u1').value = '0';
field('trip-team-origin-lng-u1').value = '9.4';
await TripTeamEndpoints.save('u1');
assert.equal(sent.length, 4, 'a latitude of exactly 0 was refused');
assert.equal(sent[3].fields.origin_lat_override, 0);

// The editor keeps what was typed when the save is refused by the server.
assert.equal(field('trip-team-endpoints-u1').hidden, false,
  'a refused save closed the editor and took what was typed with it');
assert.equal(TripTeamEndpoints.isDirty !== undefined, true);

// What a redraw must not do: take an open editor away with what is in it.
field('trip-team-origin-name-u1').value = 'Half typed';
TripTeamEndpoints.touched();
const held = TripTeamEndpoints.capture();
assert.equal(held.userId, 'u1');
assert.equal(held.dirty, true, 'the editor did not report unsaved input');
TripTeamEndpoints.close('u1');
TripTeamEndpoints.restore(held);
assert.equal(field('trip-team-origin-name-u1').value, 'Half typed',
  'a redraw of the team card threw away what was being typed');
assert.equal(TripTeamEndpoints.openEditor().dirty, true);

// And while a save is in flight the fields it is being sent from are frozen.
TripTeamEndpoints.setBusy('u1', true);
assert.equal(field('trip-team-origin-name-u1').disabled, true,
  'the editor could be typed into while its own save was in the air');
TripTeamEndpoints.setBusy('u1', false);
assert.equal(field('trip-team-origin-name-u1').disabled, false);
console.log(JSON.stringify({ sent: sent.length, alerts: alerts.length }));
})().catch(error => { console.error(error); process.exit(1); });
"""


def check_the_editor_sets_and_clears_one_members_points() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["sent"] == 4


QUEUE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// One write at a time, and the plan each one belongs to decided when the
// reader asked for it - not when the queue gets round to sending it.
const sent = [];
let release;
const held = new Promise(resolve => { release = resolve; });

const ctx = {
  console,
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  notify() {},
  document: { getElementById: () => null, addEventListener() {} },
  ApiClient: {
    setTripMember: (planId, payload) => {
      sent.push({ planId, payload });
      return Promise.resolve({ id: planId, members: [], stops: [] });
    },
  },
  renderCurrentTripPlan() {}, renderTripMap() {},
  TripScheduleView: { renderPlan() {} },
  TripZones: { planChanged() {} },
};
ctx.window = ctx;
ctx.State = {
  currentTripPlan: { id: 'A', row_version: 1,
    members: [{ user_id: 'u1', display_name: 'Anna Berg', row_version: 1 }] },
};
vm.createContext(ctx);
for (const name of ['trip-plan-identity.js', 'trip-team-queue.js',
                    'trip-team-actions.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + name, 'utf8'), ctx,
                  { filename: name });
}

(async () => {
  // Something slow is already in the queue.
  const first = ctx.TripTeamQueue.run(() => held);
  const change = ctx.TripTeamActions.departureChanged('u1', '2026-09-20');

  // While it waits, the reader opens another plan - which is what
  // selectTripPlan does: take a number, then put the other plan on screen.
  const token = ctx.TripPlanIdentity.intend();
  ctx.State.currentTripPlan = { id: 'B', row_version: 1,
    members: [{ user_id: 'u1', display_name: 'Anna Berg', row_version: 1 }] };
  ctx.TripPlanIdentity.accept(token, ctx.State.currentTripPlan);

  release();
  await first;
  await change;

  assert.equal(sent.length, 1, `${sent.length} writes went out`);
  assert.equal(sent[0].planId, 'A',
    `a change made on plan A was written to plan ${sent[0].planId}`);
  assert.equal(sent[0].payload.departure_date, '2026-09-20');
  // The reader is on B, so B is what stays on screen.
  assert.equal(ctx.State.currentTripPlan.id, 'B',
    "an answer about the plan the reader left took over their screen");

  // The same holds for the places editor.
  sent.length = 0;
  ctx.State.currentTripPlan = { id: 'A', row_version: 1,
    members: [{ user_id: 'u1', display_name: 'Anna Berg', row_version: 1 }] };
  let release2;
  const held2 = new Promise(resolve => { release2 = resolve; });
  const slow = ctx.TripTeamQueue.run(() => held2);
  const saving = ctx.TripTeamActions.saveEndpoints('u1',
    { origin_name_override: 'Berlin', origin_lat_override: 52.52,
      origin_lng_override: 13.405, destination_name_override: null,
      destination_lat_override: null, destination_lng_override: null });
  const second = ctx.TripPlanIdentity.intend();
  ctx.State.currentTripPlan = { id: 'B', row_version: 1, members: [] };
  ctx.TripPlanIdentity.accept(second, ctx.State.currentTripPlan);
  release2();
  await slow;
  await saving;
  assert.equal(sent[0].planId, 'A',
    `places edited on plan A were written to plan ${sent[0].planId}`);
  console.log(JSON.stringify({ writes: sent.length }));
})().catch(error => { console.error(error); process.exit(1); });
"""


def check_a_queued_change_goes_to_the_plan_it_was_made_on() -> None:
    """The queue serialises writes; it must not re-address them.

    Captured at the front of the queue instead, a change made on plan A and
    queued behind something slow is sent to whichever plan the reader has
    opened by the time it runs - and the row version cannot save it, because
    the same member on the other plan can be at the same version.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(QUEUE_HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["writes"] == 1


def check_the_server_clears_on_an_explicit_null() -> None:
    """Sending null must reach the column, and the route must go out of date."""
    router = (ROOT / "backend" / "routers" / "review.py").read_text(encoding="utf-8")
    assert "request.model_dump(exclude_unset=True)" in router, (
        "the member payload no longer distinguishes a field left out from one "
        "sent as null, so 'follows the plan' cannot clear anything"
    )
    repository = (ROOT / "backend" / "services" / "trip_member_repository.py").read_text(
        encoding="utf-8")
    assert "if field in (overrides or {})" in repository, (
        "the update writes every column instead of the ones it was given, so a "
        "date change would wipe somebody's departure point"
    )
    service = (ROOT / "backend" / "services" / "trip_plan_service.py").read_text(
        encoding="utf-8")
    block = service[service.index("def set_trip_member"):]
    assert "_invalidate_trip_itinerary" in block[:1200], (
        "moving where a member starts leaves the saved route claiming to be "
        "current"
    )


def check_the_card_says_whose_points_these_are() -> None:
    view = (MODULES / "trip-team-view.js").read_text(encoding="utf-8")
    assert "own places" in view, (
        "the row prints two place names without saying whether the plan's own "
        "departure field applies to this person at all"
    )
    assert "TripTeamEndpoints.toggle" in view, "there is no way in from the row"
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "trip-team-endpoints.js" in index, "the editor is never loaded"


def main() -> None:
    check_the_editor_sets_and_clears_one_members_points()
    check_a_queued_change_goes_to_the_plan_it_was_made_on()
    check_the_server_clears_on_an_explicit_null()
    check_the_card_says_whose_points_these_are()
    print("PASS: a traveller's own departure and return points can be set, "
          "changed and cleared back to the plan's")


if __name__ == "__main__":
    main()
