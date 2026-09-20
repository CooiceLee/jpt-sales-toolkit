"""Taking one person off one visit, from the line that visit is listed on.

Doing it before meant leaving the team card, opening the other card, finding
the customer down a long list, opening their preparation, finding the attendee
rows and deleting one - to say a thing the reader was already looking at.

Two things this must not do. It must not guess: a visit that names nobody is
attended by whoever is travelling, and a visit naming one person cannot lose
that person without quietly becoming everybody's. And it must not invent a
second way to write a preparation: it sends exactly the shape that editor
sends, so the route still goes out of date when the attendees change and the
other cards still get the same plan read back.
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

const put = [];
const alerts = [];
const opened = [];
let briefing;

const ctx = {
  console,
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  alert: message => alerts.push(message),
  confirm: () => true,
  notify() {},
  setTripBusy() {},
  handleTripError: async () => {},
  document: { getElementById: () => null, addEventListener() {} },
  ApiClient: {
    getTripBriefing: async () => briefing,
    putTripBriefing: async (planId, stopId, payload) => {
      put.push({ planId, stopId, payload });
      return payload;
    },
  },
  // The token is taken when the reader acts and checked before anything is
  // said to them: they may have opened another plan while the write was out.
  TripPlanIdentity: { intend: () => 1, isCurrent: token => token === 1 },
  TripPlanRefresh: { reread: async () => true },
  TripBriefingActions: { open: stopId => opened.push(stopId) },
};
ctx.window = ctx;
ctx.State = {
  tripBusy: false,
  currentTripPlan: {
    id: 'p1',
    members: [{ user_id: 'u1', display_name: 'Anna Berg' },
              { user_id: 'u2', display_name: 'Chen Wei' }],
    stops: [{ id: 's1', customer_name: 'Berlin Optics 1' }],
  },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-team-visit-drop.js', 'utf8'),
                ctx, { filename: 'trip-team-visit-drop.js' });
const { TripTeamVisitDrop } = ctx;

const saved = () => ({
  row_version: 3, stop_row_version: 7, confirmation_status: 'confirmed',
  timezone: 'Europe/Berlin',
  // The saved location comes back with worked-out extras beside it; the write
  // takes the model's own fields and nothing else.
  location: { name: 'Works', city: 'Berlin', use_customer_default: false,
              lat: 52.52, lng: 13.405, resolved_from: 'customer' },
  // What the server sends back carries worked-out values the write never takes.
  effective_location: { name: 'Works', city: 'Berlin' },
  customer_team: [{ name: 'Herr Schmidt', title: 'Head of production', extra: 'x' }],
  contacts: [{ name: 'Frau Klein', email: 'k@example.com' }],
  participants: [
    { user_id: 'u1', display_name: 'Anna Berg', role: 'Sales', sequence_no: 1 },
    { user_id: 'u2', display_name: 'Chen Wei', role: 'Tech', sequence_no: 2 },
  ],
  channel_partner_companions: [],
  equipment: [{ kind: 'demo', model: 'M1' }],
  agenda_items: [{ topic: 'Delivery' }],
});

(async () => {
  // Nobody named: everybody travelling attends, so there is nothing to take
  // away here - say so, and open the place where people are named.
  briefing = { ...saved(), participants: [] };
  assert.equal(await TripTeamVisitDrop.drop('u1', 's1'), false);
  assert.equal(put.length, 0, 'a visit that names nobody was written to');
  assert.equal(opened.pop(), 's1', 'the reader was not taken anywhere');
  assert.match(alerts.at(-1), /names nobody/,
    `a visit attended by everybody was explained as one this person is not on: ${alerts.at(-1)}`);

  // The only person named: taking them off would leave the visit attended by
  // everybody, which is the opposite of what was asked for.
  briefing = { ...saved(), participants: [saved().participants[0]] };
  assert.equal(await TripTeamVisitDrop.drop('u1', 's1'), false);
  assert.equal(put.length, 0, 'the last named attendee was removed');
  assert.match(alerts.at(-1), /only person named/, alerts.at(-1));

  // Named alongside somebody else: this is the case that goes through.
  briefing = saved();
  assert.equal(await TripTeamVisitDrop.drop('u1', 's1'), true);
  assert.equal(put.length, 1);
  const sent = put[0].payload;
  assert.equal(put[0].stopId, 's1');
  assert.deepEqual(sent.participants.map(row => row.user_id), ['u2']);

  // The write carries the versions both sides check, and nothing the model
  // would refuse.
  assert.equal(sent.row_version, 3);
  assert.equal(sent.stop_row_version, 7);
  const ALLOWED = ['row_version', 'stop_row_version', 'confirmation_status',
    'timezone', 'location', 'customer_team', 'contacts', 'participants',
    'channel_partner_companions', 'equipment', 'agenda_items'];
  assert.deepEqual(Object.keys(sent).filter(key => !ALLOWED.includes(key)), [],
    `the write carries fields the briefing refuses: ${Object.keys(sent)}`);
  assert.ok(!('effective_location' in sent), 'a worked-out value was written back');
  assert.ok(!('extra' in sent.customer_team[0]),
    'a row was echoed back with a field the model forbids');
  assert.ok(!('resolved_from' in sent.location),
    `the location was echoed back whole: ${JSON.stringify(sent.location)}`);

  // And everything else on that preparation survives untouched.
  assert.equal(sent.confirmation_status, 'confirmed');
  assert.equal(sent.location.name, 'Works');
  assert.equal(sent.location.use_customer_default, false);
  assert.equal(sent.customer_team[0].name, 'Herr Schmidt');
  assert.equal(sent.equipment[0].model, 'M1');
  assert.equal(sent.agenda_items[0].topic, 'Delivery');

  // An open preparation draft still stops this, like every other route action.
  ctx.TripBriefingDraft = { guard: () => true };
  assert.equal(await TripTeamVisitDrop.drop('u2', 's1'), false);
  assert.equal(put.length, 1, 'an unsaved preparation was written over');
  console.log(JSON.stringify({ writes: put.length }));
})().catch(error => { console.error(error); process.exit(1); });
"""


def check_one_person_comes_off_one_visit() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["writes"] == 1


def check_the_line_offers_it_and_the_plan_is_read_back() -> None:
    itinerary = (MODULES / "trip-team-itinerary.js").read_text(encoding="utf-8")
    assert "TripTeamVisitDrop.drop(" in itinerary, (
        "the visit is listed with no way to act on it from there"
    )
    assert "TripFreeStopForm.open(" in itinerary, (
        "a personal stop is not somebody's attendance; that line must open its "
        "own editor rather than pretend the same action fits"
    )
    drop = (MODULES / "trip-team-visit-drop.js").read_text(encoding="utf-8")
    assert "TripPlanRefresh?.reread?.(planId" in drop, (
        "the plan is not read back, so the other cards keep showing the old one"
    )
    for guard in ("TripBriefingDraft?.guard?.()", "TripVisitDraft?.guard?.()"):
        assert guard in drop, f"{guard} is not asked before writing"
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "trip-team-visit-drop.js" in index, "the module is never loaded"


def main() -> None:
    check_one_person_comes_off_one_visit()
    check_the_line_offers_it_and_the_plan_is_read_back()
    print("PASS: one person comes off one visit from the line it is listed on, "
          "and the two cases that would change the meaning are refused")


if __name__ == "__main__":
    main()
