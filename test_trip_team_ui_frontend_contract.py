"""The team planning surface: risk bar, travel team card and team timeline.

Three invariants matter more than the styling: colleagues travelling together
read as one line, lanes only appear when work really is parallel, and nothing
is drawn as connected when the plan cannot say where somebody is.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"
NODE = "node"

HARNESS = """
globalThis.escapeHtml = value => String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
globalThis.I18n = { t: (key, params = {}) =>
    String(key).replace(/\\{(\\w+)\\}/g, (_, name) => params[name] ?? `{${name}}`) };
globalThis.window = globalThis;
globalThis.document = { getElementById: () => null };
globalThis.TripDuration = { label: value => `${value} half-days` };
globalThis.State = {};
"""


def _node_json(script: str) -> str:
    """Run a self-contained node script and return its last line as JSON text."""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip()[:500])
    return result.stdout.strip().splitlines()[-1]


def run_js(body: str) -> dict:
    sources = "\n".join(
        (MODULES / name).read_text(encoding="utf-8")
        for name in ("trip-schedule-view.js", "trip-team-risks.js",
                     "trip-team-timeline-view.js", "trip-team-timeline.js")
    )
    script = f"{HARNESS}\n{sources}\n{body}"
    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip())
    return json.loads(result.stdout.strip().splitlines()[-1])


def check_shared_events_merge() -> None:
    """Two colleagues at one visit is one line, naming both."""
    data = run_js("""
    const plan = { members: [
        { user_id: 'z', display_name: 'Zhang' },
        { user_id: 'l', display_name: 'Li' }] };
    const items = [
        { member_id: 'z', source_id: 'munich', item_type: 'customer',
          title: 'Munich', date: '2026-09-17', period: 'AM',
          inbound_travel_resolved: true },
        { member_id: 'l', source_id: 'munich', item_type: 'customer',
          title: 'Munich', date: '2026-09-17', period: 'AM',
          inbound_travel_resolved: true },
    ];
    const grouped = TripTeamTimeline.groupSlot(items, plan);
    console.log(JSON.stringify({
        lines: grouped.length, who: grouped[0].members,
        unresolved: grouped[0].unresolved,
    }));
    """)
    assert data["lines"] == 1, "travelling together must not read as two visits"
    assert data["who"] == ["Zhang", "Li"], data["who"]
    assert data["unresolved"] is False


def check_parallel_events_stay_separate() -> None:
    """Two customers in the same half-day are two lines, one per member."""
    data = run_js("""
    const plan = { members: [
        { user_id: 'z', display_name: 'Zhang' },
        { user_id: 'l', display_name: 'Li' }] };
    const items = [
        { member_id: 'z', source_id: 'frankfurt', item_type: 'customer',
          title: 'Frankfurt', date: '2026-09-16', period: 'AM' },
        { member_id: 'l', source_id: 'paris', item_type: 'customer',
          title: 'Paris', date: '2026-09-16', period: 'AM' },
    ];
    const grouped = TripTeamTimeline.groupSlot(items, plan);
    console.log(JSON.stringify({
        lines: grouped.length,
        who: grouped.map(entry => entry.members.join('+')).sort(),
    }));
    """)
    assert data["lines"] == 2, "parallel visits must stay separate"
    assert data["who"] == ["Li", "Zhang"], data["who"]


def check_travel_merges_only_when_it_is_the_same_journey() -> None:
    """Same two places is not the same journey; the way of travelling counts.

    Two colleagues between the same cities, one driving and one on a train, are
    not travelling together. Merging them would claim they are, and the line
    would show one of the two modes as if it were both of theirs.
    """
    data = run_js("""
    const plan = { members: [
        { user_id: 'z', display_name: 'Zhang' },
        { user_id: 'l', display_name: 'Li' }] };
    const leg = (member, mode) => ({
        member_id: member, source_id: 'f>s', item_type: 'leg',
        title: 'Frankfurt \u2192 Stuttgart', selected_mode: mode,
        date: '2026-09-18', period: 'AM', lane_order: 2,
    });
    const together = TripTeamTimeline.groupSlot(
        [leg('z', 'ground_public'), leg('l', 'ground_public')], plan);
    const apart = TripTeamTimeline.groupSlot(
        [leg('z', 'drive'), leg('l', 'ground_public')], plan);
    console.log(JSON.stringify({
        togetherRows: together.length,
        togetherWho: together[0].members,
        apartRows: apart.length,
        apartModes: apart.map(entry => entry.selected_mode).sort(),
        apartWho: apart.map(entry => entry.members.join('')).sort(),
    }));
    """)
    assert data["togetherRows"] == 1, "the same journey is one line"
    assert data["togetherWho"] == ["Zhang", "Li"], data["togetherWho"]
    assert data["apartRows"] == 2, (
        "driving and taking a train between the same cities is not travelling "
        "together"
    )
    assert data["apartModes"] == ["drive", "ground_public"], data["apartModes"]
    assert data["apartWho"] == ["Li", "Zhang"], data["apartWho"]


def check_travel_shows_how_they_travel() -> None:
    """A split travel line has to say why it is split."""
    data = run_js("""
    const plan = { members: [{ user_id: 'z', display_name: 'Zhang' }] };
    const nodes = new Map([['t', { innerHTML: '' }]]);
    globalThis.document = { getElementById: id => nodes.get(id) || null };
    TripTeamTimeline.render({ ...plan, schedule_items: [{
        member_id: 'z', source_id: 'f>s', item_type: 'leg',
        title: 'Frankfurt \u2192 Stuttgart', selected_mode: 'drive',
        date: '2026-09-18', period: 'AM', lane_order: 1,
    }] }, nodes.get('t'));
    console.log(JSON.stringify({ html: nodes.get('t').innerHTML }));
    """)
    # The visible text only: the raw mode also appears inside the onclick that
    # focuses the map, which is a function argument rather than something read.
    shown = re.sub(r"<[^>]+>", " ", data["html"])
    assert "Drive" in shown, (
        f"the travel line never says how they travel: {shown}"
    )
    assert "drive" not in shown.replace("Drive", ""), (
        "the raw mode is displayed instead of its label"
    )


def check_unresolved_travel_is_marked_not_drawn() -> None:
    """An unreachable visit is flagged, and no journey is invented for it."""
    data = run_js("""
    const plan = {
        members: [{ user_id: 'z', display_name: 'Zhang' }],
        itinerary_summary: { member_totals: {
            z: { route_complete: false } } },
    };
    const grouped = TripTeamTimeline.groupSlot([
        { member_id: 'z', source_id: 'munich', item_type: 'customer',
          title: 'Munich', date: '2026-09-17', period: 'AM',
          inbound_travel_resolved: false },
    ], plan);
    console.log(JSON.stringify({
        unresolved: grouped[0].unresolved,
        notice: TripTeamTimeline.incompleteNotice(plan),
    }));
    """)
    assert data["unresolved"] is True
    assert "Zhang" in data["notice"], (
        "a member with no workable route must be named, not silently dropped"
    )


def check_risk_bar_reads_backend_risks() -> None:
    """Every risk kind the backend emits produces a sentence, with no re-judging."""
    data = run_js("""
    const plan = {
        members: [{ user_id: 'z', display_name: 'Zhang' }],
        itinerary_summary: { risks: [
            { kind: 'member_double_booked', user_id: 'z', date: '2026-09-16',
              period: 'AM', stop_ids: ['a', 'b'] },
            { kind: 'member_return_overrun', member_id: 'z',
              calculated_end_date: '2026-09-30', date: '2026-09-30',
              deadline: '2026-09-28' },
            { kind: 'parallel_visits_unassigned', date: '2026-09-16',
              period: 'PM', visit_count: 2, stop_ids: ['a', 'b'] },
            { kind: 'cannot_reach_booked_visit', user_id: 'z',
              date: '2026-09-20', period: 'AM' },
            { kind: 'participant_not_in_trip_team', stop_ids: ['a'] },
        ] },
    };
    console.log(JSON.stringify({ lines: TripTeamRisks.lines(plan) }));
    """)
    assert len(data["lines"]) == 5, data["lines"]
    assert all("Zhang" in line or "visits" in line or "visit names" in line
               for line in data["lines"]), data["lines"]
    assert not any("{" in line for line in data["lines"]), (
        f"a risk sentence left a placeholder unfilled: {data['lines']}"
    )


def check_backend_sends_kinds_not_sentences() -> None:
    """The backend must keep emitting structured risks the frontend localises."""
    core = (ROOT / "backend" / "services" / "trip_team_rules.py").read_text(
        encoding="utf-8"
    )
    adapter = (ROOT / "backend" / "services" / "trip_team_adapter.py").read_text(
        encoding="utf-8"
    )
    # The scheduler emits risks of its own, so it counts as a source too.
    scheduler = (ROOT / "backend" / "services" / "trip_team_schedule.py").read_text(
        encoding="utf-8"
    )
    for kind in ("member_double_booked", "parallel_visits_unassigned",
                 "participant_not_in_trip_team", "member_return_overrun",
                 "cannot_reach_booked_visit"):
        assert kind in core + adapter + scheduler, (
            f"risk kind no longer emitted: {kind}"
        )
    # A risk is a dict that leads with its kind. Route points carry a "kind"
    # too - origin, stop, destination - and those are places, not warnings.
    risks = re.findall(r'\{\s*"kind": "(\w+)"', core + adapter + scheduler)
    module = (MODULES / "trip-team-risks.js").read_text(encoding="utf-8")
    for kind in set(risks):
        assert kind in module, f"risk kind {kind} has no sentence in the risk bar"


def check_timeline_is_not_drag_and_drop() -> None:
    """The first timeline is for reading and opening, not for re-planning."""
    module = (MODULES / "trip-team-timeline.js").read_text(encoding="utf-8")
    for banned in ("draggable", "dragstart", "dragover", "ondrop"):
        assert banned not in module, (
            f"the team timeline must not re-introduce dragging yet: {banned}"
        )


def check_real_backend_output_renders() -> None:
    """The whole chain: a real saved team plan rendered by the real modules.

    The fixtures above pin the rules; this proves the shapes actually line up,
    because a field the timeline reads by the wrong name would pass every unit
    check and still render an empty page.
    """
    import os
    import tempfile

    os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_team_ui_")
    sys.path.insert(0, str(ROOT))
    from backend.config import init_settings
    from backend.repositories import close_db
    from backend.services.review_service import ReviewService
    from backend.startup_upgrade import initialize_database_safely
    import test_trip_team_roundtrip as roundtrip

    initialize_database_safely(init_settings(ROOT))
    service = ReviewService()
    seed = roundtrip._seed(service)
    service.generate_trip_itinerary(seed["plan_id"], {}, seed["actor"], "leader")
    plan = service.get_trip_plan(seed["plan_id"], seed["actor"], "leader")
    close_db()

    payload = json.dumps(plan, default=str)
    munich_id = json.dumps(seed["stops"]["munich"])
    data = run_js(f"""
    const plan = {payload};
    const munichId = {munich_id};
    const nodes = new Map();
    const make = id => {{ const node = {{ id, innerHTML: '', hidden: false }}; nodes.set(id, node); return node; }};
    ['trip-schedule-list', 'trip-risk-bar'].forEach(make);
    globalThis.document = {{ getElementById: id => nodes.get(id) || null }};
    TripTeamTimeline.render(plan, nodes.get('trip-schedule-list'));
    TripTeamRisks.render(plan, nodes.get('trip-risk-bar'));
    const html = nodes.get('trip-schedule-list').innerHTML;
    console.log(JSON.stringify({{
        slots: (html.match(/class="trip-team-slot"/g) || []).length,
        entries: (html.match(/class="trip-team-entry/g) || []).length,
        html,
        risksHidden: nodes.get('trip-risk-bar').hidden,
        planningMode: plan.planning_mode,
        memberCount: (plan.members || []).length,
        sharedRows: sharedRows(plan, munichId),
    }}));

    function sharedRows(plan, stopId) {{
        // Per half-day, the rows for this stop itself - travel legs that merely
        // mention it by name are a different thing and are not counted here.
        const bySlot = new Map();
        (plan.schedule_items || []).forEach(item => {{
            const key = `${{item.date}}|${{item.period}}`;
            bySlot.set(key, [...(bySlot.get(key) || []), item]);
        }});
        return [...bySlot.values()].map(items =>
            TripTeamTimeline.groupSlot(items, plan)
                .filter(entry => entry.item_type !== 'leg'
                    && entry.source_id === stopId)
                .map(entry => entry.members.slice().sort())
        ).filter(rows => rows.length);
    }}
    """)

    assert data["planningMode"] == "team" and data["memberCount"] == 2
    assert data["slots"] >= 3, f"the real plan rendered {data['slots']} half-days"
    assert data["entries"] >= 4, f"only {data['entries']} entries rendered"
    for expected in ("Frankfurt Customer", "Paris Customer", "Munich Expo",
                     "Zhang", "Li"):
        assert expected in data["html"], (
            f"the rendered timeline never mentions {expected}"
        )
    # Both colleagues attend the Munich stop, so each half-day of it is a single
    # row naming both of them, never one row per person.
    shared = data["sharedRows"]
    assert shared, "the shared stop never reached the timeline"
    for rows in shared:
        assert len(rows) == 1, f"the shared stop rendered {len(rows)} rows in one half-day"
        assert rows[0] == ["Li", "Zhang"], rows[0]
    assert data["risksHidden"] is True, (
        "this plan has no risks, so the risk bar must stay out of the way"
    )


def check_narrow_column_and_long_names() -> None:
    """The side column is 320px at its narrowest, and names can be long.

    There is no browser here to measure boxes, so this checks the rules that
    decide whether a long name is cut or pushes the row apart: no fixed name
    column, min-width zero on the flex children that hold text, and an ellipsis
    on every line that can overflow.
    """
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    team = css[css.index("/* Team planning:"):]

    assert "grid-template-columns: 120px 1fr" not in team, (
        "a fixed 120px names column cannot hold two merged Chinese names"
    )
    assert "minmax(100px, 28%) 1fr" in team, (
        "the names column must follow the width it is given"
    )
    for rule, why in (
        (".trip-team-member > div { min-width: 0; }",
         "a flex child holding text needs min-width 0 or it refuses to shrink"),
        (".trip-team-add { display: flex; flex-wrap: wrap;",
         "the add row has to wrap in a 320px column"),
        (".trip-team-remove", "the remove control has to stay narrow"),
    ):
        assert rule in team, f"{why}: missing {rule}"

    for selector in (".trip-team-member strong, .trip-team-member small",
                     ".trip-team-entry-who"):
        block = team[team.index(selector):]
        block = block[:block.index("}")]
        assert "text-overflow: ellipsis" in block and "white-space: nowrap" in block, (
            f"{selector} can overflow and has no ellipsis"
        )

    # The layout the card sits in, so the assumption above is not guesswork.
    assert "clamp(320px, 26vw, 440px)" in css, (
        "the side column width changed; recheck the team card density"
    )

    # Long merged names must still produce one row, not one per person.
    data = run_js("""
    const plan = { members: [
        { user_id: 'z', display_name: '张三丰远' },
        { user_id: 'l', display_name: '李四光明' },
        { user_id: 'w', display_name: '王五国强' }] };
    const items = ['z', 'l', 'w'].map(id => ({
        member_id: id, source_id: 'expo', item_type: 'customer',
        title: '慕尼黑激光展', date: '2026-09-17', period: 'AM',
        lane_order: 2, inbound_travel_resolved: true }));
    const grouped = TripTeamTimeline.groupSlot(items, plan);
    console.log(JSON.stringify({
        rows: grouped.length, who: grouped[0].members.join(' \u00b7 '),
    }));
    """)
    assert data["rows"] == 1, "three colleagues at one visit is still one row"
    assert data["who"] == "张三丰远 · 李四光明 · 王五国强", data["who"]


def check_slot_order_follows_the_journey() -> None:
    """Within a half-day, travel is listed before the visit it reaches."""
    data = run_js("""
    const plan = { members: [{ user_id: 'z', display_name: 'Zhang' }] };
    const items = [
        { member_id: 'z', source_id: 'a', item_type: 'customer', title: 'Alpha',
          date: '2026-09-16', period: 'PM', lane_order: 4 },
        { member_id: 'z', source_id: 'f>a', item_type: 'leg',
          title: 'Frankfurt \u2192 Alpha', date: '2026-09-16', period: 'PM',
          lane_order: 3 },
    ];
    console.log(JSON.stringify({
        order: TripTeamTimeline.groupSlot(items, plan)
            .map(entry => entry.item_type),
    }));
    """)
    assert data["order"] == ["leg", "customer"], (
        f"the timeline reads back to front: {data['order']}"
    )


def check_only_a_decision_reads_as_planned() -> None:
    """A time the calculation produced is not labelled as a plan somebody made."""
    data = run_js("""
    const stops = [
        { id: 'agreed', schedule_locked: true, planned_date: '2026-09-16',
          planned_time_accepted: 0 },
        { id: 'applied', schedule_locked: false, planned_date: '2026-09-17',
          planned_time_accepted: 1 },
        { id: 'calculated', schedule_locked: false, planned_date: '2026-09-18',
          planned_time_accepted: 0 },
    ];
    const label = id => TripTeamTimelineView.commitment({ stops },
        { item_type: 'customer', source_id: id });
    console.log(JSON.stringify({
        agreed: label('agreed'),
        applied: label('applied'),
        calculated: label('calculated'),
        leg: TripTeamTimelineView.commitment({ stops },
            { item_type: 'leg', source_id: 'agreed' }),
    }));
    """)
    assert data["agreed"] == "Confirmed", data
    assert data["applied"] == "Planned", data
    assert data["calculated"] == "", (
        "a time only the calculation produced must not read as a plan somebody "
        f"made: {data}"
    )
    assert data["leg"] == "", data


def check_actions_call_globals_that_exist() -> None:
    """The action modules must run, not merely contain the right words.

    Two modules were written against globals that do not exist - `API` instead
    of `ApiClient`, and a `showToast` that was never defined - so pressing the
    button threw, the catch reported it through the missing function, and
    nothing happened at all. Reading the source cannot catch that; calling the
    functions can.
    """
    modules = (
        "trip-stop-schedule-controls.js",
        "trip-team-journeys.js",
        "trip-team-actions.js",
        "trip-flexible-suggestions.js",
        "trip-plan-identity.js",
        "trip-stop-appointment-actions.js",
    )
    sources = "\n".join(
        (MODULES / name).read_text(encoding="utf-8") for name in modules
    )
    script = """
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: (key, params = {}) =>
    String(key).replace(/\\{(\\w+)\\}/g, (_, name) => params[name] ?? `{${name}}`) };
globalThis.window = globalThis;
const called = [];
globalThis.State = { tripBusy: false, currentTripPlan: {
    id: 'p1', row_version: 3, planning_mode: 'team',
    stops: [{ id: 's1', row_version: 2 }], members: [] } };
const select = { value: 'u1', selectedIndex: 0, options: [{ text: 'Zhang' }] };
globalThis.document = { getElementById: id =>
    id === 'trip-team-add-user' ? select
    : { value: '', innerHTML: '', hidden: false } };
globalThis.ApiClient = new Proxy({}, { get: (_, name) => async (...args) => {
    called.push(String(name));
    return State.currentTripPlan;
} });
globalThis.notify = message => called.push('notify:' + message);
globalThis.setTripBusy = () => {};
globalThis.handleTripError = async () => { called.push('handleTripError'); };
globalThis.renderTripMap = () => {};
globalThis.renderCurrentTripPlan = () => {};
globalThis.populateTripPlanForm = () => {};
globalThis.confirm = () => true;
globalThis.TripScheduleView = { renderPlan: () => {} };
globalThis.TripPlanningDraft = { get: () => ({ dirty: false }) };
globalThis.TripPlanRefresh = { redrawVisits: () => true };
globalThis.TripPlannerModule = { renderVisitExecution: () => {} };
globalThis.TripTransportActions = { schedulePreview: () => {} };
globalThis.TripBriefingActions = { open: () => {} };
globalThis.TripTeamMap = { focusStop: () => {}, focusLeg: () => {} };
globalThis.loadTripPlanner = async () => {};
globalThis.MapSupport = { coordinatePair: (a, b) => [a, b] };
""" + sources + """
(async () => {
  await TripTeamActions.add();
  await TripTeamActions.remove('u1');
  await TripFlexibleSuggestions.load();
  await TripStopScheduleActions.appointmentChanged('s1');
  // There is one way to plan a trip, so there is no mode to switch. The
  // control and its action are gone and must not come back.
  if (typeof TripPlanningModeActions !== 'undefined') {
    throw new Error('the planning-mode action is back');
  }
  console.log(JSON.stringify(called));
})().catch(error => { console.error(String(error)); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"an action threw when called: {result.stderr.strip()[:400]}"
    )
    called = json.loads(result.stdout.strip().splitlines()[-1])
    for endpoint in ("setTripMember", "removeTripMember",
                     "getTripFlexibleSuggestions", "updateTripStop"):
        assert endpoint in called, (
            f"{endpoint} was never reached; the action failed silently: {called}"
        )
    assert any(item.startswith("notify:Zhang joined") for item in called), (
        f"adding somebody must say who joined: {called}"
    )
    assert "handleTripError" not in called, (
        f"an action reported an error on a successful call: {called}"
    )


JS_LEG_LIST = r'''
const fs=require('fs');const vm=require('vm');
const nodes = new Map([['trip-leg-list', { innerHTML: '' }],
                       ['trip-leg-count', { textContent: '' }]]);
const context = { console, escapeHtml: v => String(v ?? ''),
  I18n: { t: (k, p = {}) =>
    String(k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? `{${n}}`) },
  document: { getElementById: id => nodes.get(id) || { innerHTML: '' } },
  State: {},
  TripDuration: { label: v => String(v), toDisplayTravelDays: v => String(v),
                  toDisplayDays: v => String(v) },
  TripPlanningDraft: { MODES: ['flight', 'drive', 'ground_public', 'other'] },
  TripSuggestionView: { render: () => {} },
  MapSupport: { coordinatePair: (a, b) => [a, b] },
};
context.window = context; vm.createContext(context);
for (const f of ['trip-schedule-view.js', 'trip-team-risks.js',
                 'trip-team-timeline-view.js', 'trip-team-timeline.js',
                 'trip-team-journeys.js', 'trip-transport-view.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + f, 'utf8'), context);
}
const draft = { legOverrides: {}, transportModePriority: ['flight', 'drive'] };
const members = [{ user_id: 'a', display_name: 'Ayden' },
                 { user_id: 's', display_name: 'Slluu' }];
const leg = (m, n, from, to, mode) => ({ member_id: m, sequence_no: n,
  leg_key: from + '>' + to, from_label: from, to_label: to,
  selected_mode: mode, distance_km: 100, time_hours: 2,
  travel_half_days: 2, travel_days: 1 });
const together = [];
for (const m of ['a', 's']) {
  together.push(leg(m, 1, 'SZX', 'VJT', 'flight'), leg(m, 2, 'VJT', 'SZX', 'flight'));
}
context.TripTransportView.render(
  { planning_mode: 'team', members, legs: together, stops: [] }, draft);
const teamCount = nodes.get('trip-leg-count').textContent;
const teamNames = (nodes.get('trip-leg-list').innerHTML
  .match(/trip-leg-members">([^<]*)</g) || [])
  .map(x => x.replace(/.*">/, '').replace('<', ''));

nodes.get('trip-leg-list').innerHTML = '';
const apart = [leg('a', 1, 'VJT', 'STU', 'drive'), leg('s', 1, 'VJT', 'STU', 'ground_public')];
context.TripTransportView.render(
  { planning_mode: 'team', members, legs: apart, stops: [] }, draft);
const apartCount = nodes.get('trip-leg-count').textContent;

nodes.get('trip-leg-list').innerHTML = '';
context.TripTransportView.render(
  { planning_mode: 'legacy', members: [], legs: together.slice(0, 2), stops: [] }, draft);
console.log(JSON.stringify({
  teamCount, teamNames, apartCount,
  legacyCount: nodes.get('trip-leg-count').textContent,
  legacyNames: nodes.get('trip-leg-list').innerHTML.includes('trip-leg-members'),
}));
'''


def check_team_legs_are_listed_once_per_journey() -> None:
    """Colleagues travelling together are one leg in the list, naming them all.

    Every member has their own legs, so three people on the same trip produce
    three identical rows for each hop - nine rows for two customers. Listed flat
    and unattributed that reads as legs appearing from nowhere, which is how it
    was reported.
    """
    data = json.loads(_node_json(JS_LEG_LIST))
    assert data["teamCount"] == "2 legs", (
        f"two colleagues on the same two hops is two legs: {data['teamCount']}"
    )
    assert data["teamNames"] == ["Ayden · Slluu", "Ayden · Slluu"], data["teamNames"]
    assert data["apartCount"] == "2 legs", (
        "the same two places by different means stays two legs: "
        f"{data['apartCount']}"
    )
    assert data["legacyCount"] == "2 legs"
    assert data["legacyNames"] is False, (
        "a single-traveller plan must not gain member labels"
    )


def check_module_wiring() -> None:
    """The modules load, and the schedule view sends team plans to the timeline."""
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for name in ("trip-team-risks.js", "trip-team-timeline.js",
                 "trip-team-view.js", "trip-team-actions.js"):
        assert name in index, f"module never loaded: {name}"
    for element in ("trip-risk-bar", "trip-team-panel", "trip-team-body"):
        assert f'id="{element}"' in index, f"missing element: {element}"
    assert "trip-planning-mode" not in index, (
        "every trip is planned as a team, so there is no mode to choose"
    )
    schedule = (MODULES / "trip-schedule-view.js").read_text(encoding="utf-8")
    assert "planning_mode === 'team'" in schedule, (
        "the schedule view must send team plans to the team timeline"
    )
    assert "TripTeamView?.render?.(plan)" in schedule
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    assert "setTripMember" in api and "removeTripMember" in api


JS_PERSONAL_STOP = """
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: key => key };
globalThis.window = globalThis;
globalThis.TripFreeStopDraft = { mark() {} };
const fields = {};
const people = { checked: [], list: [] };
function node(id) {
    if (id === 'trip-free-stop-people-list') {
        return {
            set innerHTML(html) {
                people.list = [...html.matchAll(/value="([^"]+)"/g)].map(m => m[1]);
            },
            querySelectorAll: () => people.checked.map(value => ({ value })),
        };
    }
    if (!(id in fields)) fields[id] = { value: '', hidden: false };
    return fields[id];
}
globalThis.document = { getElementById: node };
globalThis.State = {};
__MODULE__
const ctl = window.TripFreeStopTeamControls;

// Team mode: the stop can name a day and the people who stop there.
State.currentTripPlan = { planning_mode: 'team', members: [
    { user_id: 'a', display_name: 'Ayden' }, { user_id: 'b', display_name: 'Slluu' },
] };
ctl.render({ planned_date: '2026-09-04', planned_start_period: 'PM',
             participant_user_ids: ['a'] });
const shown = { people: node('trip-free-stop-people').hidden,
                timing: node('trip-free-stop-team-timing').hidden,
                listed: people.list,
                date: node('trip-free-stop-start-date').value,
                period: node('trip-free-stop-start-period').value };
people.checked = ['a'];
const dated = ctl.payload();
node('trip-free-stop-start-date').value = '';
const undated = ctl.payload();

// Single-traveller mode sends none of it and shows none of it.
State.currentTripPlan = { planning_mode: 'legacy', members: [] };
ctl.render({});
const legacy = { payload: ctl.payload(),
                 people: node('trip-free-stop-people').hidden,
                 timing: node('trip-free-stop-team-timing').hidden };
console.log(JSON.stringify({ shown, dated, undated, legacy }));
"""


def check_personal_stop_carries_its_people_and_day() -> None:
    """A personal stop on a team trip says who stops there, and when.

    Without either, every personal stop is attended by the whole team and is
    fitted in wherever the route has room: a member who should have flown home
    is flown to somebody else's hotel instead. The single-traveller form must
    not change, because there is nobody to choose between.
    """
    source = (MODULES / "trip-free-stop-team-controls.js").read_text(
        encoding="utf-8"
    )
    data = json.loads(_node_json(
        JS_PERSONAL_STOP.replace("__MODULE__", source)
    ))
    assert data["shown"]["people"] is False, "team mode must show who stops here"
    assert data["shown"]["timing"] is False, "team mode must show the stay day"
    assert data["shown"]["listed"] == ["a", "b"], data["shown"]["listed"]
    assert data["shown"]["date"] == "2026-09-04", data["shown"]
    assert data["shown"]["period"] == "PM", data["shown"]

    assert data["dated"]["participant_user_ids"] == ["a"], data["dated"]
    assert data["dated"]["planned_date"] == "2026-09-04", data["dated"]
    assert data["dated"]["planned_start_period"] == "PM", data["dated"]
    assert data["dated"]["schedule_locked"] is True, (
        "a stop given a day must hold that day, or the route moves it"
    )
    assert data["undated"]["planned_date"] is None, data["undated"]
    assert data["undated"]["schedule_locked"] is False, (
        "a stop with no day must stay free for the route to place"
    )

    assert data["legacy"]["payload"] == {}, (
        f"single-traveller plans send no team fields: {data['legacy']['payload']}"
    )
    assert data["legacy"]["people"] is True and data["legacy"]["timing"] is True

    form = (MODULES / "trip-free-stop-form.js").read_text(encoding="utf-8")
    assert "TripFreeStopTeamControls?.payload?.()" in form, (
        "the save payload must carry the team fields, or the controls are "
        "shown and then thrown away"
    )
    assert "TripFreeStopTeamControls?.render?.(stop)" in form, (
        "opening a saved stop must show what it already says"
    )


JS_WHOLE_TEAM = """
globalThis.window = globalThis;
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: key => key };
globalThis.State = {};
__DRAFT__
__VISIT__
const team = [
    { user_id: 'a', display_name: 'Ayden', role: 'tech' },
    { user_id: 'b', display_name: 'Slluu', role: 'leader' },
];
State.currentTripPlan = { planning_mode: 'team', members: team };

// Nobody named: the whole team goes, so the whole team is shown.
const blank = TripBriefingDraft.normalizeRecord({});
const blankLine = TripVisitState.internalParticipantsLine({});

// Somebody named: only they go, and nothing is added to them.
const chosen = TripBriefingDraft.normalizeRecord({
    participants: [{ user_id: 'a', display_name: 'Ayden' }],
});
const chosenLine = TripVisitState.internalParticipantsLine({
    briefing: { participants: [{ user_id: 'a', display_name: 'Ayden' }] },
});

// Switching back to single-traveller leaves the member rows on the plan, so
// the mode has to be what decides this, not whether a team list exists.
State.currentTripPlan = { planning_mode: 'legacy', members: team };
const legacy = TripBriefingDraft.normalizeRecord({});
const legacyLine = TripVisitState.internalParticipantsLine({});

console.log(JSON.stringify({
    blank: blank.participants.map(item => [item.user_id, item.display_name]),
    blankLine, chosen: chosen.participants.map(item => item.user_id), chosenLine,
    legacy: legacy.participants.length, legacyLine,
}));
"""


def check_whole_team_is_shown_not_left_blank() -> None:
    """"Everybody goes" is written out, not left as an empty field.

    A visit that names nobody is attended by the whole team. Shown as an empty
    list it reads as the opposite - nobody is going - and there is nothing to
    remove a person from. So the team is filled in, each on its own row the
    editor can already add to and delete from.
    """
    data = json.loads(_node_json(
        JS_WHOLE_TEAM
        .replace("__DRAFT__", (MODULES / "trip-briefing-draft.js").read_text(
            encoding="utf-8"))
        .replace("__VISIT__", (MODULES / "trip-visit-state.js").read_text(
            encoding="utf-8"))
    ))
    assert data["blank"] == [["a", "Ayden"], ["b", "Slluu"]], (
        f"a visit naming nobody must open with the whole team on it: {data['blank']}"
    )
    assert data["blankLine"] == "Ayden · Slluu", (
        f"the saved visit must read as the whole team, not a dash: {data['blankLine']}"
    )
    assert data["chosen"] == ["a"], (
        f"naming one person must not quietly add the rest: {data['chosen']}"
    )
    assert data["chosenLine"] == "Ayden", data["chosenLine"]
    assert data["legacy"] == 0, (
        "a single-traveller plan must not fill in attendees, even while the "
        f"member rows of a previous team plan are still on it: {data['legacy']}"
    )
    assert not data["legacyLine"], data["legacyLine"]

    rows = (MODULES / "trip-briefing-rows.js").read_text(encoding="utf-8")
    for action in ("'add'", "'remove'"):
        assert f"arrayAction('participants',{action}" in rows.replace(" ", "") \
            or f"arrayAction('${{kind}}',{action}" in rows.replace(" ", ""), (
            f"the filled-in team must be editable: no {action} control"
        )


JS_ROW_IDENTITY = """
globalThis.window = globalThis;
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: (key, params = {}) =>
    String(key).replace(/\\{(\\w+)\\}/g, (_, name) => params[name] ?? `{${name}}`) };
globalThis.TripDuration = {
    label: v => `${v}`, toDisplayTravelDays: v => String(v),
    parseDisplayTravelDays: v => Number(v),
};
const nodes = {};
globalThis.document = {
    getElementById: id => (nodes[id] = nodes[id]
        || { id, value: '', textContent: '', innerHTML: '', hidden: false }),
};
globalThis.State = {};
globalThis.TripPlanningDraft = { MODES: ['flight', 'drive', 'ground_public', 'other'] };
__TIMELINE__
__JOURNEYS__
__VIEW__
const plan = {
    planning_mode: 'team',
    members: [
        { user_id: 'a', display_name: 'Ayden' },
        { user_id: 'b', display_name: 'Slluu' },
    ],
    legs: [
        { leg_key: 'origin>x', member_id: 'a', selected_mode: 'flight',
          from_label: 'Shenzhen', to_label: 'VJT', from: 'Shenzhen', to: 'VJT',
          distance_km: 9039.5, time_hours: 16.6, travel_half_days: 4 },
        { leg_key: 'origin>x', member_id: 'b', selected_mode: 'flight',
          from_label: 'Shenzhen', to_label: 'VJT', from: 'Shenzhen', to: 'VJT',
          distance_km: 9039.5, time_hours: 16.6, travel_half_days: 4 },
        { leg_key: 'x>y', member_id: 'a', selected_mode: 'drive',
          from_label: 'VJT', to_label: 'PMI', from: 'VJT', to: 'PMI',
          distance_km: 306.4, time_hours: 4.1, travel_half_days: 1 },
    ],
};
TripTransportView.render(plan, { legOverrides: {}, transportModePriority: ['flight', 'drive'] });
console.log(JSON.stringify({
    rows: [0, 1, 2].map(index => {
        const leg = TripTransportView.legAt(index);
        return leg ? `${leg.leg_key}|${leg.selected_mode}` : null;
    }),
}));
"""


def check_a_row_number_finds_the_leg_that_row_shows() -> None:
    """Editing a row edits the leg that row is showing.

    Colleagues travelling together are drawn as one row, so a row number stopped
    being a position in plan.legs. Every control on a row - the transport mode,
    the airports, the search - is handed that number, and resolving it against
    the unmerged list writes onto a different journey: an airport lands on a
    connection nobody is looking at, and the row the user filled in stays empty.
    """
    data = json.loads(_node_json(
        JS_ROW_IDENTITY
        .replace("__TIMELINE__", (MODULES / "trip-team-timeline.js").read_text(
            encoding="utf-8"))
        .replace("__JOURNEYS__", (MODULES / "trip-team-journeys.js").read_text(
            encoding="utf-8"))
        .replace("__VIEW__", (MODULES / "trip-transport-view.js").read_text(
            encoding="utf-8"))
    ))
    assert data["rows"][0] == "origin>x|flight", data["rows"]
    assert data["rows"][1] == "x>y|drive", (
        "the second row shows the second journey, not the second leg of the "
        f"first one: {data['rows']}"
    )
    assert data["rows"][2] is None, (
        f"there is no third row to edit: {data['rows']}"
    )

    for name in ("trip-leg-airports.js", "trip-leg-actions.js",
                 "trip-suggestion-actions.js"):
        source = (MODULES / name).read_text(encoding="utf-8")
        assert "currentTripPlan?.legs?.[index]" not in source, (
            f"{name} still resolves a row number against the unmerged leg list"
        )


def main() -> None:
    check_shared_events_merge()
    check_parallel_events_stay_separate()
    check_travel_merges_only_when_it_is_the_same_journey()
    check_travel_shows_how_they_travel()
    check_unresolved_travel_is_marked_not_drawn()
    check_risk_bar_reads_backend_risks()
    check_backend_sends_kinds_not_sentences()
    check_timeline_is_not_drag_and_drop()
    check_narrow_column_and_long_names()
    check_slot_order_follows_the_journey()
    check_real_backend_output_renders()
    check_only_a_decision_reads_as_planned()
    check_actions_call_globals_that_exist()
    check_team_legs_are_listed_once_per_journey()
    check_personal_stop_carries_its_people_and_day()
    check_whole_team_is_shown_not_left_blank()
    check_a_row_number_finds_the_leg_that_row_shows()
    check_module_wiring()
    print("PASS: team risk bar, travel team card and team timeline contracts")


if __name__ == "__main__":
    main()
