"""Each traveller's own itinerary, on their own row of the team card.

The card said who is going and how far they travel; the schedule said what
happens half-day by half-day with everybody mixed together. Neither answered
"what is this person doing on this trip", and for somebody on none of the
visits the answer arrived as a blank row and an empty map - which reads as a
fault rather than as a fact about the plan.

Built from the schedule the calculation produced, never from the plan's stop
list: a stop is on the trip, a stop on *this* member's schedule is a stop they
go to, and the two differ for every visit they are not named on. The half-days
are collapsed back into places, because a two-day visit is one visit.
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

const ctx = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: { getElementById: () => null, addEventListener() {} },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-team-itinerary.js', 'utf8'),
                ctx, { filename: 'trip-team-itinerary.js' });
const { TripTeamItinerary } = ctx;

const anna = { user_id: 'u-anna', display_name: 'Anna Berg' };
const idle = { user_id: 'u-idle', display_name: 'QA Leader' };
const plan = {
  itinerary_generated_at: '2026-09-16T00:00:00Z',
  itinerary_summary: { stale: false, member_totals: {
    'u-anna': { distance_km: 19041.5, route_complete: true,
                calculated_end_date: '2026-10-07' },
    'u-idle': { distance_km: 0, route_complete: true,
                calculated_end_date: '2026-09-15' },
  } },
  members: [anna, idle],
  // Three stops are on the plan; Anna is scheduled on two of them, one of
  // which takes a whole day and so appears twice.
  stops: [{ id: 's1' }, { id: 's2' }, { id: 's3' }],
  schedule_items: [
    { member_id: 'u-anna', item_type: 'leg', source_id: 'origin>s1',
      date: '2026-09-14', period: 'AM', lane_order: 1, title: 'SZX → Berlin' },
    { member_id: 'u-anna', item_type: 'customer', source_id: 's1',
      date: '2026-09-14', period: 'AM', lane_order: 2, title: 'Berlin Optics 1' },
    { member_id: 'u-anna', item_type: 'customer', source_id: 's1',
      date: '2026-09-14', period: 'PM', lane_order: 2, title: 'Berlin Optics 1' },
    { member_id: 'u-anna', item_type: 'free', source_id: 'f1',
      date: '2026-09-17', period: 'AM', lane_order: 1, title: 'Hamburg overnight' },
    { member_id: 'u-anna', item_type: 'customer', source_id: 's2',
      date: '2026-09-18', period: 'PM', lane_order: 3, title: 'Frankfurt Optics 1' },
    { member_id: 'u-other', item_type: 'customer', source_id: 's3',
      date: '2026-09-19', period: 'AM', lane_order: 1, title: 'Somebody else' },
  ],
};

// One entry per place, in the order they happen, and only this member's.
const rows = TripTeamItinerary.stops(plan, 'u-anna');
// Joined rather than compared as arrays: the module builds its list inside the
// sandbox, so an array from it is not the same Array as one built out here.
assert.equal(rows.map(row => row.source_id).join(','), 's1,f1,s2',
  rows.map(row => row.source_id).join(','));
assert.equal(rows[0].period, 'AM', 'a whole-day visit was listed from its afternoon');
assert.ok(!rows.some(row => row.item_type === 'leg'), 'travel was listed as a stop');
assert.equal(TripTeamItinerary.stops(plan, 'u-idle').length, 0,
  "somebody else's visits were listed as this member's");

// The summary counts visits and personal stops apart, and carries the totals.
const summary = TripTeamItinerary.summary(plan, anna, rows);
assert.match(summary, /2 visits/, summary);
assert.match(summary, /1 personal stops/, summary);
// The distance and the return day are on the member's own line directly above
// this one. Printed here as well, the card said the same fact twice in four
// lines - and for somebody with no trip it said "0 km · back 15 Sep" over a
// sentence saying they have no trip at all.
assert.ok(!/km/.test(summary), `the distance is repeated here: ${summary}`);
assert.ok(!/2026-10-07/.test(summary), `the return day is repeated: ${summary}`);

const drawn = TripTeamItinerary.render(plan, anna);
assert.match(drawn, /Berlin Optics 1/);
assert.match(drawn, /Frankfurt Optics 1/);
assert.ok(!drawn.includes('Somebody else'),
  "the row shows the plan's stops instead of this member's");
assert.ok(drawn.includes('data-business'),
  'customer names are printed without saying they are somebody else\'s words');

// A stop the calculation could not make work is marked on the line it is on,
// and the reason is printed there - a colour on its own is not something the
// reader can act on. A risk naming somebody else is not this member's to
// answer for, even when they are on the same visit.
ctx.TripTeamRisks = { describe: (p, risk) => 'cannot reach ' + risk.stop_id };
const risky = JSON.parse(JSON.stringify(plan));
risky.itinerary_summary.risks = [
  { kind: 'cannot_reach_booked_visit', stop_id: 's1', user_id: 'u-anna' },
  { kind: 'cannot_reach_booked_visit', stop_id: 's2', user_id: 'u-other' },
];
const flags = TripTeamItinerary.risksByStop(risky, 'u-anna');
assert.equal(flags.has('s1'), true, "the member's own flagged visit is not marked");
assert.equal(flags.has('s2'), false, "somebody else's risk was put on this member");

ctx.TripRouteState = { blocks: kind => kind === 'cannot_reach_booked_visit' };
const marked = TripTeamItinerary.render(risky, anna);
assert.match(marked, /is-risky/, 'the flagged stop is not marked on its line');
assert.match(marked, /cannot reach s1/, 'the reason is not printed on the line');
assert.match(marked, /1 do not work/, 'the summary does not carry the count');

// Not every risk is a trip that cannot be made. The customer agreeing to an
// afternoon when the morning was asked for is a thing to confirm, and counting
// it as impossible is how this card came to report more failures than the bar
// above it, which has always judged the two apart.
risky.itinerary_summary.risks = [
  { kind: 'booked_outside_preferred_period', stop_id: 's1', user_id: 'u-anna' },
];
const checking = TripTeamItinerary.render(risky, anna);
assert.ok(!/do not work/.test(checking),
  `a preference that was not met was called impossible: ${checking}`);
assert.match(checking, /1 to confirm/, checking);
assert.match(checking, /is-checking/, 'the softer case is marked as a blocker');
assert.ok(!/is-risky/.test(checking), checking);
const oneRow = (marked.match(/is-risky/g) || []).length;
assert.equal(oneRow, 1, `${oneRow} lines were marked for one risk`);

// A risk that names nobody belongs to the visit, so everybody on it sees it.
risky.itinerary_summary.risks = [{ kind: 'booked_on_skipped_day', stop_id: 's1' }];
assert.equal(TripTeamItinerary.risksByStop(risky, 'u-anna').has('s1'), true);
assert.equal(TripTeamItinerary.risksByStop(risky, 'u-idle').has('s1'), true);

// And with nothing flagged, nothing is coloured.
assert.ok(!/is-risky/.test(TripTeamItinerary.render(plan, anna)),
  'a clean itinerary came back marked');

// Nothing scheduled: a sentence, and the one thing that changes it.
const empty = TripTeamItinerary.render(plan, idle);
assert.match(empty, /Not on any visit/, empty);
assert.match(empty, /Visit preparation/, empty);

// Before any route exists there is nothing to report either way, and saying
// "not on any visit" then would be a guess about a calculation that never ran.
const fresh = { ...plan, itinerary_generated_at: null };
const waiting = TripTeamItinerary.render(fresh, idle);
assert.match(waiting, /No route calculated yet/, waiting);
assert.ok(!/Not on any visit/.test(waiting), waiting);

// A member the plan cannot place is a third case, and not "no visits" either.
const stranded = JSON.parse(JSON.stringify(plan));
stranded.itinerary_summary.member_totals['u-idle'].route_complete = false;
const lost = TripTeamItinerary.render(stranded, idle);
assert.match(lost, /cannot work out where this person is/, lost);
assert.ok(!/Not on any visit/.test(lost), lost);
console.log(JSON.stringify({ rows: rows.length }));
"""


def check_each_member_row_shows_that_members_trip() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["rows"] == 3


def check_the_row_is_drawn_and_the_closed_editor_is_not() -> None:
    view = (MODULES / "trip-team-view.js").read_text(encoding="utf-8")
    assert "TripTeamItinerary?.render?.(plan, member)" in view, (
        "the member's own trip is not shown on their row"
    )
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "trip-team-itinerary.js" in index, "the module is never loaded"
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".trip-team-endpoints[hidden] { display: none; }" in css, (
        "the closed endpoint editor is display:flex over its own hidden "
        "attribute, so every member row carries an empty bar"
    )
    assert "max-height" in css[css.index(".trip-team-itinerary-list"):
                               css.index(".trip-team-itinerary-list") + 400], (
        "a twenty-stop itinerary pushes the rest of the team off the card"
    )


def main() -> None:
    check_each_member_row_shows_that_members_trip()
    check_the_row_is_drawn_and_the_closed_editor_is_not()
    print("PASS: every traveller's row says what that traveller does on the "
          "trip, including when the answer is nothing")


if __name__ == "__main__":
    main()
