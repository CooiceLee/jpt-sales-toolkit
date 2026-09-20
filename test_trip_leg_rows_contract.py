"""A travel row stands for one journey, and everything about it agrees.

Two faults met on the same list.

The rows were merged by connection, mode and airports alone. Two colleagues
who drive Lyon → Porto on different days, at different distances, over a
different number of hours, produced one row: the second person's journey was
not shown at all, and the facts on screen were the first person's. The map
merges by the same rule on purpose - one line for one connection - so the list
needs its own rule rather than a change to the one the map draws with: a row
may only speak for several people when every fact it shows is the same for all
of them.

And the travel options were wired to a different list than the one on screen.
The rows are the merged journeys, numbered 0..n; the search results were
written by walking the unmerged legs, numbered 0..m. From the second merge
onwards every result landed on the wrong row, and the last row got none at all
- a result for Lyon → Porto shown under Berlin → Lyon is worse than no result.

So: one row model, used by the list, by the search results and by what a search
applies to. Plus what a reader needs to see on the row itself - when it leaves,
when it arrives, and who is on it, inside the row so a filter hides the name
with the journey it belongs to.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from test_trip_route_board_contract import DOM

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

__DOM__

const suggestions = { 'c2>c3': [{ suggestion_id: 'S-NEXT', mode: 'flight', provider: 'NEXT-SOURCE',
                                  distance_km: 900, time_hours: 2, online: true, fetched_at: '2026-09-17T10:00:00Z' }],
                      'origin>c2': [{ suggestion_id: 'S-SHARED', mode: 'drive', provider: 'SHARED-SOURCE',
                                      distance_km: 100, time_hours: 2, online: true, fetched_at: '2026-09-17T10:00:00Z' }] };
const ctx = {
  console, assert,
  escapeHtml: value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;'),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text),
    locale: () => 'en-US' },
  document: makeDocument(['trip-leg-list', 'trip-leg-board', 'trip-leg-count',
                          'trip-transport-priority', 'trip-suggest-route', 'trip-suggestion-status']),
  addEventListener() {},
  TripDuration: { label: v => String(v), toDisplayTravelDays: v => String(v), toDisplayDays: v => String(v) },
  TripPlanningDraft: { MODES: ['flight', 'drive', 'ground_public', 'other'] },
  TripSuggestionState: {
    get: () => ({ status: 'ready', suggestions: [], warnings: [], focusLegKey: null }),
    forLeg: key => suggestions[key] || [],
    stale: () => false,
  },
  MapSupport: { coordinatePair: (a, b) => [a, b] },
};
ctx.window = ctx;
ctx.State = { currentTripPlan: null };
vm.createContext(ctx);
for (const file of ['trip-team-timeline.js', 'trip-team-journeys.js', 'trip-leg-rows.js',
                    'trip-leg-card.js', 'trip-transport-view.js',
                    'trip-suggestion-view.js']) {
  const path = `frontend/js/modules/${file}`;
  if (!fs.existsSync(path)) continue;   // before the fix the row model does not exist yet
  vm.runInContext(fs.readFileSync(path, 'utf8'), ctx, { filename: file });
}
const doc = ctx.document;
const draft = { legOverrides: {}, transportModePriority: ['flight', 'drive'] };
const members = [{ user_id: 'u-a', display_name: 'Anna Berg' },
                 { user_id: 'u-b', display_name: 'Bruno Katz' }];
const cards = () => doc.querySelectorAll('#trip-leg-list .trip-leg-card[data-leg-key]');
const text = node => node.textContent;

// The same connection, the same mode - two days apart, and not the same journey.
const apartDays = [
  { member_id: 'u-a', leg_key: 'c1>c2', sequence_no: 1, from_label: 'Lyon', to_label: 'Porto',
    selected_mode: 'drive', distance_km: 1100, time_hours: 11, travel_half_days: 2,
    planned_start_date: '2026-09-14', planned_start_period: 'AM',
    planned_end_date: '2026-09-14', planned_end_period: 'PM' },
  { member_id: 'u-b', leg_key: 'c1>c2', sequence_no: 1, from_label: 'Lyon', to_label: 'Porto',
    selected_mode: 'drive', distance_km: 1290, time_hours: 13, travel_half_days: 4,
    planned_start_date: '2026-09-16', planned_start_period: 'AM',
    planned_end_date: '2026-09-17', planned_end_period: 'AM' },
];
ctx.TripTransportView.render({ planning_mode: 'team', members, stops: [], legs: apartDays }, draft);
assert.equal(cards().length, 2,
  'two journeys two days apart were merged into one row, keeping only the first');
const byMember = name => cards().find(card => text(card).includes(name));
assert.ok(byMember('Anna Berg') && byMember('Bruno Katz'), 'a traveller lost their journey');
assert.ok(text(byMember('Anna Berg')).includes('2026-09-14'), text(byMember('Anna Berg')));
assert.ok(text(byMember('Bruno Katz')).includes('2026-09-16'),
  "the second journey shows the first one's departure day");
assert.ok(text(byMember('Bruno Katz')).includes('1290'),
  "the second journey shows the first one's distance");
// A journey that runs into the next day says so, rather than "0.5 travel days".
assert.ok(text(byMember('Bruno Katz')).includes('2026-09-17'),
  'a journey that arrives the next day does not say when it arrives');
// The names belong to the row, so a filter hides them with it.
cards().forEach(card => {
  const names = card.querySelectorAll('.trip-leg-members');
  assert.equal(names.length, 1, 'the traveller names are not inside the row');
});

// Truly together: same day, same facts, one row naming both.
const together = apartDays.map(leg => ({ ...leg, distance_km: 1100, time_hours: 11,
  travel_half_days: 2, planned_start_date: '2026-09-14', planned_start_period: 'AM',
  planned_end_date: '2026-09-14', planned_end_period: 'PM' }));
ctx.TripTransportView.render({ planning_mode: 'team', members, stops: [], legs: together }, draft);
assert.equal(cards().length, 1, 'colleagues on the same journey were listed twice');
assert.ok(text(cards()[0]).includes('Anna Berg') && text(cards()[0]).includes('Bruno Katz'),
  'a shared journey does not name everybody on it');

// Travel options land on the row they belong to, not on the row after it.
const mixed = [
  { member_id: 'u-a', leg_key: 'origin>c2', sequence_no: 1, from_label: 'PVG', to_label: 'Lyon',
    selected_mode: 'drive', distance_km: 100, time_hours: 2, travel_half_days: 1,
    planned_start_date: '2026-09-12', planned_start_period: 'AM',
    planned_end_date: '2026-09-12', planned_end_period: 'AM' },
  { member_id: 'u-b', leg_key: 'origin>c2', sequence_no: 1, from_label: 'PVG', to_label: 'Lyon',
    selected_mode: 'drive', distance_km: 100, time_hours: 2, travel_half_days: 1,
    planned_start_date: '2026-09-12', planned_start_period: 'AM',
    planned_end_date: '2026-09-12', planned_end_period: 'AM' },
  { member_id: 'u-a', leg_key: 'c2>c3', sequence_no: 2, from_label: 'Lyon', to_label: 'Porto',
    selected_mode: 'flight', distance_km: 900, time_hours: 2, travel_half_days: 1,
    planned_start_date: '2026-09-15', planned_start_period: 'PM',
    planned_end_date: '2026-09-15', planned_end_period: 'PM' },
];
const plan = { planning_mode: 'team', members, stops: [], legs: mixed };
ctx.TripTransportView.render(plan, draft);
assert.equal(cards().length, 2, 'the shared first journey was not merged');
ctx.TripSuggestionView.render(plan);
const holder = card => card.querySelector('.trip-leg-suggestions');
const shared = cards()[0], next = cards()[1];
assert.ok(holder(shared).innerHTML.includes('SHARED-SOURCE'),
  'the shared journey lost its own travel options');
assert.ok(holder(next).innerHTML.includes('NEXT-SOURCE'),
  'a travel option never reached the journey it was found for');
assert.ok(!holder(next).innerHTML.includes('SHARED-SOURCE'),
  "another journey's travel options were shown on this one");

// What a search acts on is the row that was clicked, not a position in a list
// the reader cannot see.
assert.equal(ctx.TripTransportView.legAt(1).leg_key, 'c2>c3');
assert.equal(ctx.TripLegRows.legsAt(plan, draft, 1).map(leg => leg.member_id).join(','), 'u-a');
assert.equal(ctx.TripLegRows.legsAt(plan, draft, 0).map(leg => leg.member_id).join(','), 'u-a,u-b');

console.log(JSON.stringify({ rows: cards().length }));
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


def check_a_row_is_one_journey_and_owns_its_travel_options() -> None:
    output = _node(HARNESS.replace("__DOM__", DOM))
    assert json.loads(output.strip().splitlines()[-1])["rows"] == 2


def check_the_map_keeps_its_own_grouping() -> None:
    """The map draws one line per connection on purpose.

    Fixing the list by changing the identity the map groups by would split that
    line into one per person and per day - so the list gets its own rule and
    the map's stays where it is.
    """
    journeys = (MODULES / "trip-team-journeys.js").read_text(encoding="utf-8")
    rows = (MODULES / "trip-leg-rows.js").read_text(encoding="utf-8")
    assert "planned_start_date" not in journeys, (
        "the map's grouping now depends on dates, so one connection is drawn "
        "as several lines"
    )
    for fact in ("planned_start_date", "planned_start_period", "planned_end_date",
                 "distance_km", "time_hours", "selected_mode"):
        assert fact in rows, f"a row may be merged while {fact} differs"
    view = (MODULES / "trip-transport-view.js").read_text(encoding="utf-8")
    suggestion_view = (MODULES / "trip-suggestion-view.js").read_text(encoding="utf-8")
    assert "TripTeamJourneys?.identityOf" not in view and "TripTeamJourneys.identityOf" not in view, (
        "the list still groups by the map's identity"
    )
    assert "plan?.legs || []).forEach(renderLeg)" not in suggestion_view, (
        "travel options are still written by walking the unmerged legs"
    )
    assert "TripLegRows" in suggestion_view, (
        "the list and its travel options do not share one row model"
    )


def main() -> None:
    check_a_row_is_one_journey_and_owns_its_travel_options()
    check_the_map_keeps_its_own_grouping()
    print("PASS: one row is one journey, it says when it leaves and arrives, "
          "and its travel options belong to it")


if __name__ == "__main__":
    main()
