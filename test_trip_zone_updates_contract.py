"""Which zone moved because of work done in another one.

The four zones share one plan, so anything done in any of them moves the
others: saving a route rewrites the daily schedule and every member's totals, a
preparation that changes where a visit happens puts the saved route out of
date, a returned workbook fills in execution results. The reader sees one zone
at a time, so all of that happened out of sight with nothing to say it had.

What has to hold: a mark stands for a real difference in that zone's own data,
the zone being read is never marked, opening a marked zone clears it, and
opening a different plan marks nothing - four marks on a plan nobody has looked
at yet would mean nothing at all.
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

const tabs = ['settings', 'route', 'briefing', 'execution'].map(zone => ({
  dataset: { tripZoneTab: zone }, title: '', children: [],
  classList: { toggle(name, on) { this[name] = on; } },
  querySelector: () => null,
  appendChild(node) { this.children.push(node); },
  removeAttribute() { this.title = ''; },
}));
let open = 'settings';
const ctx = {
  console,
  I18n: { t: text => text },
  document: {
    querySelectorAll: () => tabs,
    createElement: () => ({ className: '', setAttribute() {}, remove() {} }),
    addEventListener() {},
  },
  TripZones: { current: () => open },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-zone-updates.js', 'utf8'),
                ctx, { filename: 'trip-zone-updates.js' });
const { TripZoneUpdates } = ctx;
const marks = () => TripZoneUpdates.pending().sort().join(',');

const plan = () => ({
  id: 'p1', title: 'Trip', start_date: '2026-09-14', end_date: '2026-10-30',
  origin_name: 'SZX', destination_name: 'PVG',
  members: [{ user_id: 'u1', departure_date: '2026-09-14' }],
  itinerary_generated_at: '2026-09-16T00:00:00Z',
  itinerary_summary: { stale: false, risks: [], member_totals: { u1: { distance_km: 10 } } },
  schedule_items: [{ member_id: 'u1', item_type: 'customer', source_id: 's1',
                     date: '2026-09-14', period: 'AM' }],
  stops: [{ id: 's1', sequence_no: 1, planned_date: '2026-09-14',
            confirmation_status: 'confirmed', briefing: { participants: ['u1'] },
            result_status: 'Planned' }],
});

// Opening a plan marks nothing: none of it is news yet.
TripZoneUpdates.sync(plan());
assert.equal(marks(), '', `a freshly opened plan was marked: ${marks()}`);

// A route recalculation moves the schedule - and only that.
const recalculated = plan();
recalculated.itinerary_generated_at = '2026-09-17T00:00:00Z';
recalculated.schedule_items[0].date = '2026-09-15';
recalculated.stops[0].planned_date = '2026-09-15';
TripZoneUpdates.sync(recalculated);
assert.equal(marks(), 'route', `wrong zones marked: ${marks()}`);
assert.equal(tabs[1].classList['has-update'], true, 'the tab does not show it');
assert.ok(tabs[1].title, 'the tab does not say what the mark means');

// Opening it is what clears it.
TripZoneUpdates.seen('route');
assert.equal(marks(), '');
assert.equal(tabs[1].classList['has-update'], false);

// A preparation saved on a stop moves the preparation zone, not execution.
const prepared = JSON.parse(JSON.stringify(recalculated));
prepared.stops[0].briefing = { participants: ['u1', 'u2'] };
TripZoneUpdates.sync(prepared);
assert.equal(marks(), 'briefing', `wrong zones marked: ${marks()}`);
TripZoneUpdates.seen('briefing');

// A returned result moves execution, not preparation.
const executed = JSON.parse(JSON.stringify(prepared));
executed.stops[0].result_status = 'Visited';
TripZoneUpdates.sync(executed);
assert.equal(marks(), 'execution', `wrong zones marked: ${marks()}`);
TripZoneUpdates.seen('execution');

// Every field the execution card writes back has to count as a change to the
// execution zone. A quote asked for, a sample promised, a budget written down:
// left out of the comparison, the reader is never told the zone moved.
const ZONES = ['settings', 'route', 'briefing', 'execution'];
const baseline = () => { TripZoneUpdates.sync(plan()); ZONES.forEach(TripZoneUpdates.seen); };

for (const field of ['visit_quote_needed', 'visit_sample_needed', 'visit_budget',
                     'visit_competitor', 'visit_decision_maker',
                     'visit_next_action', 'visit_followup_due_date']) {
  baseline();
  const edited = plan();
  edited.stops[0][field] = 'written';
  TripZoneUpdates.sync(edited);
  assert.equal(marks(), 'execution', `changing ${field} marked ${marks()}`);
}

// And a member's coordinates, which the name beside them does not reveal: two
// airports can be typed under one name and be different places.
open = 'route';
baseline();
const moved = plan();
moved.members[0].origin_lat_override = 31.1443;
TripZoneUpdates.sync(moved);
assert.equal(marks(), 'settings', `moving a member's own place marked ${marks()}`);
open = 'settings';
baseline();

// The zone being read is never marked: the reader is looking straight at it.
open = 'settings';
const renamed = plan();
renamed.title = 'Trip renamed';
TripZoneUpdates.sync(renamed);
assert.equal(marks(), '', `the open zone was marked: ${marks()}`);

// Nothing changed, nothing marked - a redraw is not an update.
open = 'route';
TripZoneUpdates.sync(JSON.parse(JSON.stringify(renamed)));
assert.equal(marks(), '', `a redraw of the same plan marked ${marks()}`);

// Another plan is not an update to this one.
baseline();
const other = plan();
other.id = 'p2';
other.title = 'Another trip';
TripZoneUpdates.sync(other);
assert.equal(marks(), '', `opening another plan marked ${marks()}`);

// And no plan at all clears everything.
TripZoneUpdates.sync(null);
assert.equal(marks(), '');
console.log(JSON.stringify({ ok: true }));
"""


def check_a_mark_means_that_zone_really_changed() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]


def check_it_is_wired_where_every_change_arrives() -> None:
    zones = (MODULES / "trip-zones.js").read_text(encoding="utf-8")
    assert "TripZoneUpdates?.sync?.(plan" in zones, (
        "nothing compares the zones when a new version of the plan arrives"
    )
    assert "TripZoneUpdates?.seen?.(chosen)" in zones, (
        "opening a zone no longer clears its mark, so it stays marked for ever"
    )
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "trip-zone-updates.js" in index, "the module is never loaded"
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".trip-zone-dot" in css and ".trip-zone-tab.has-update" in css, (
        "the mark has no appearance, so it is invisible"
    )


def main() -> None:
    check_a_mark_means_that_zone_really_changed()
    check_it_is_wired_where_every_change_arrives()
    print("PASS: a zone is marked when its own content moved behind the "
          "reader's back, and only then")


if __name__ == "__main__":
    main()
