"""What the trip map shows when one traveller is picked out of the team.

Picking a member means "show me this person's journey". Two things used to
contradict that.

The customers merely being *considered* for the trip are drawn by a separate
layer, in the same green as the stops, and that layer was never filtered. Pick
somebody with no visits and the map still showed a cluster of green dots with
no line between them: dots that were not theirs, and no way to tell.

And a member with no journey at all got silence. The only sentence the map had
was for a member whose position could not be worked out; somebody who is simply
not on any of the trip's visits has nothing to work out, so an empty map was
left to speak for itself - which reads as a drawing that broke.
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

const notice = { textContent: '', hidden: true };
let journeys = [];
let stranded = [];
let stops = [];

const ctx = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: {
    getElementById: id => (id === 'trip-map-notice' ? notice : null),
    addEventListener() {},
  },
  L: { polyline: () => ({ bindTooltip: () => ({ addTo() {} }) }) },
  State: { tripTeamMapView: 'u-idle',
    currentTripPlan: { planning_mode: 'team', members: [
      { user_id: 'u-idle', display_name: 'QA Leader' },
      { user_id: 'u-anna', display_name: 'Anna Berg' }] } },
  TripTeamColors: { colorOf: () => '#000', bandsFor: () => [{}] },
  TripTeamJourneys: {
    journeys: () => journeys,
    incompleteMembers: () => stranded,
    memberName: (plan, id) => (plan.members.find(m => m.user_id === id) || {}).display_name || id,
  },
  TripScheduleView: { transportModeLabel: value => value },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-team-map.js', 'utf8'),
                ctx, { filename: 'trip-team-map.js' });
const { TripTeamMap } = ctx;
// The stop filter is the module's own; the schedule decides what it returns.
const plan = ctx.State.currentTripPlan;
plan.schedule_items = [];
plan.stops = [{ id: 's1' }, { id: 's2' }];
plan.legs = [];

// Nobody has given this member a visit: say so, rather than show an empty map.
journeys = []; stranded = [];
TripTeamMap.draw(plan, { addLayer() {} }, []);
assert.equal(notice.hidden, false, 'an empty map was left to explain itself');
assert.match(notice.textContent, /QA Leader/);
assert.match(notice.textContent, /not on any of its visits/, notice.textContent);

// A member whose position cannot be worked out is a different sentence.
stranded = ['Anna Berg'];
TripTeamMap.draw(plan, { addLayer() {} }, []);
assert.match(notice.textContent, /cannot say where they are/, notice.textContent);

// And a member with a journey is not told anything at all.
stranded = [];
journeys = [{ points: [[1, 2], [3, 4]], members: ['QA Leader'], memberIds: ['u-idle'],
              label: 'a → b', mode: 'drive' }];
TripTeamMap.draw(plan, { addLayer() {} }, []);
assert.equal(notice.hidden, true, notice.textContent);

// Somebody who does have visits, but whose lines did not come out, must not be
// told they have no visits: that sentence would be false, and it would send
// them looking at the wrong thing.
ctx.State.tripTeamMapView = 'u-idle';
journeys = []; stranded = [];
plan.schedule_items = [{ member_id: 'u-idle', item_type: 'visit', source_id: 's1' }];
TripTeamMap.draw(plan, { addLayer() {} }, []);
assert.ok(!/not on any of its visits/.test(notice.textContent),
  `a member with a visit was told they have none: ${notice.textContent}`);
plan.schedule_items = [];

// Looking at the whole team, one member without visits is not singled out.
ctx.State.tripTeamMapView = 'all';
journeys = [];
TripTeamMap.draw(plan, { addLayer() {} }, []);
assert.equal(notice.hidden, true, notice.textContent);

// The stops shown belong to the member picked, never to the plan.
ctx.State.tripTeamMapView = 'u-anna';
plan.schedule_items = [{ member_id: 'u-anna', item_type: 'visit', source_id: 's2' }];
assert.deepEqual(TripTeamMap.visibleStops(plan).map(s => s.id), ['s2']);
ctx.State.tripTeamMapView = 'u-idle';
assert.deepEqual(TripTeamMap.visibleStops(plan), []);
console.log(JSON.stringify({ ok: true }));
"""


def check_an_empty_members_map_says_why() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]


def check_the_candidate_layer_belongs_to_the_whole_team() -> None:
    """Candidates are customers not yet on the trip, so they are nobody's."""
    source = (MODULES / "trip-candidates-map.js").read_text(encoding="utf-8")
    loop = source[source.index("(State.tripCandidates || []).forEach"):]
    assert "if (soloMember) return;" in loop[:200], (
        "the candidate customers are drawn even when one member's journey is "
        "being looked at, in the same green as the stops"
    )
    assert "TripTeamMap?.view?.()" in source and "planning_mode === 'team'" in source, (
        "the guard no longer asks which member is being looked at"
    )
    # The plan's own markers moved into their own module when renderTripMap
    # outgrew its boundary; they still ask the same question.
    markers = (MODULES / "trip-plan-markers.js").read_text(encoding="utf-8")
    assert "TripTeamMap.visibleStops(plan)" in markers, (
        "the stop markers stopped following the member filter"
    )


def main() -> None:
    check_an_empty_members_map_says_why()
    check_the_candidate_layer_belongs_to_the_whole_team()
    print("PASS: one member's map shows that member's journey, and says so when "
          "there is none")


if __name__ == "__main__":
    main()
