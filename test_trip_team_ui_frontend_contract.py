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


def run_js(body: str) -> dict:
    sources = "\n".join(
        (MODULES / name).read_text(encoding="utf-8")
        for name in ("trip-schedule-view.js", "trip-team-risks.js",
                     "trip-team-timeline.js")
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
    assert "Drive" in data["html"], (
        f"the travel line never says how they travel: {data['html']}"
    )
    assert "drive" not in data["html"].replace("Drive", ""), (
        "the raw mode leaked into the page instead of its label"
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
    risks = re.findall(r'"kind": "(\w+)"', core + adapter + scheduler)
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


def check_module_wiring() -> None:
    """The modules load, and the schedule view sends team plans to the timeline."""
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for name in ("trip-team-risks.js", "trip-team-timeline.js",
                 "trip-team-view.js", "trip-team-actions.js"):
        assert name in index, f"module never loaded: {name}"
    for element in ("trip-risk-bar", "trip-team-panel", "trip-team-body",
                    "trip-planning-mode"):
        assert f'id="{element}"' in index, f"missing element: {element}"
    schedule = (MODULES / "trip-schedule-view.js").read_text(encoding="utf-8")
    assert "planning_mode === 'team'" in schedule, (
        "the schedule view must send team plans to the team timeline"
    )
    assert "TripTeamView?.render?.(plan)" in schedule
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    assert "setTripMember" in api and "removeTripMember" in api


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
    check_module_wiring()
    print("PASS: team risk bar, travel team card and team timeline contracts")


if __name__ == "__main__":
    main()
