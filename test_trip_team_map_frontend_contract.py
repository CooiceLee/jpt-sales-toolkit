"""Team routes on the map are the journeys the plan contains, and nothing else.

The dangerous failures here are inventing a route the calculation never made,
and claiming two colleagues travelled together when they did not. Both are
checked against the same business cases the timeline uses, so the two views
cannot drift apart.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"

HARNESS = """
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: (key, params = {}) =>
    String(key).replace(/\\{(\\w+)\\}/g, (_, name) => params[name] ?? `{${name}}`) };
globalThis.window = globalThis;
globalThis.document = { getElementById: () => null };
globalThis.TripDuration = { label: value => `${value}` };
globalThis.MapSupport = { coordinatePair: (lat, lng) =>
    (Number.isFinite(lat) && Number.isFinite(lng)) ? [lat, lng] : null };
globalThis.State = {};
"""

MODULE_FILES = (
    "trip-schedule-view.js", "trip-team-risks.js",
    "trip-team-timeline-view.js", "trip-team-timeline.js",
    "trip-team-journeys.js",
)


def run_js(body: str) -> dict:
    sources = "\n".join(
        (MODULES / name).read_text(encoding="utf-8") for name in MODULE_FILES
    )
    result = subprocess.run(
        ["node", "-e", f"{HARNESS}\n{sources}\n{body}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip())
    return json.loads(result.stdout.strip().splitlines()[-1])


PLAN = """
const plan = {
    planning_mode: 'team',
    origin_name: 'Shanghai', origin_lat: 31.23, origin_lng: 121.47,
    destination_name: 'Shanghai', destination_lat: 31.23, destination_lng: 121.47,
    members: [
        { user_id: 'z', display_name: 'Zhang' },
        { user_id: 'l', display_name: 'Li' }],
    stops: [
        { id: 'fra', customer_name: 'Frankfurt', lat: 50.11, lng: 8.68 },
        { id: 'stu', customer_name: 'Stuttgart', lat: 48.78, lng: 9.18 }],
};
const leg = (member, mode) => ({
    member_id: member, leg_key: 'fra>stu', selected_mode: mode,
    from_kind: 'stop', from_stop_id: 'fra', from_label: 'Frankfurt',
    to_kind: 'stop', to_stop_id: 'stu', to_label: 'Stuttgart',
});
"""


def check_different_modes_are_two_routes() -> None:
    """One driving and one on a train between the same cities is two routes."""
    data = run_js(PLAN + """
    const apart = TripTeamJourneys.journeys(
        { ...plan, legs: [leg('z', 'drive'), leg('l', 'ground_public')] }, 'all');
    const zhang = TripTeamJourneys.journeys(
        { ...plan, legs: [leg('z', 'drive'), leg('l', 'ground_public')] }, 'z');
    const li = TripTeamJourneys.journeys(
        { ...plan, legs: [leg('z', 'drive'), leg('l', 'ground_public')] }, 'l');
    console.log(JSON.stringify({
        all: apart.length,
        allModes: apart.map(item => item.mode).sort(),
        zhang: zhang.map(item => item.mode),
        li: li.map(item => item.mode),
    }));
    """)
    assert data["all"] == 2, "two ways of travelling is two routes on the map"
    assert data["allModes"] == ["drive", "ground_public"], data["allModes"]
    assert data["zhang"] == ["drive"], data["zhang"]
    assert data["li"] == ["ground_public"], data["li"]


def check_same_journey_is_one_route() -> None:
    """Actually travelling together is drawn once, naming both."""
    data = run_js(PLAN + """
    const together = TripTeamJourneys.journeys({
        ...plan,
        legs: [leg('z', 'ground_public'), leg('l', 'ground_public')],
    }, 'all');
    console.log(JSON.stringify({
        routes: together.length,
        members: together[0].members,
        points: together[0].points,
    }));
    """)
    assert data["routes"] == 1, "travelling together must not draw two lines"
    assert data["members"] == ["Zhang", "Li"], data["members"]
    assert data["points"] == [[50.11, 8.68], [48.78, 9.18]], data["points"]


def check_no_leg_means_no_line() -> None:
    """Travel the plan could not work out is not drawn, not even as a guess."""
    data = run_js(PLAN + """
    // Zhang is double-booked, so the calculation produced no leg for him and
    // reported his route as incomplete. Only Li's journey exists.
    const partial = {
        ...plan,
        legs: [leg('l', 'drive')],
        itinerary_summary: { member_totals: {
            z: { route_complete: false }, l: { route_complete: true } } },
    };
    console.log(JSON.stringify({
        all: TripTeamJourneys.journeys(partial, 'all').length,
        zhang: TripTeamJourneys.journeys(partial, 'z').length,
        stranded: TripTeamJourneys.incompleteMembers(partial, 'all'),
        strandedForZhang: TripTeamJourneys.incompleteMembers(partial, 'z'),
        strandedForLi: TripTeamJourneys.incompleteMembers(partial, 'l'),
    }));
    """)
    assert data["all"] == 1, "only the journey that exists is drawn"
    assert data["zhang"] == 0, (
        "a member with no workable route gets no line, dashed or otherwise"
    )
    assert data["stranded"] == ["Zhang"], data["stranded"]
    assert data["strandedForZhang"] == ["Zhang"]
    assert data["strandedForLi"] == [], data["strandedForLi"]


def check_endpoints_come_from_the_leg_not_the_stop_order() -> None:
    """Each member leaves from their own place, looked up from the leg itself."""
    data = run_js(PLAN + """
    const home = {
        ...plan,
        members: [
            { user_id: 'z', display_name: 'Zhang' },
            { user_id: 'l', display_name: 'Li',
              origin_lat_override: 22.54, origin_lng_override: 114.06,
              origin_name_override: 'Shenzhen' }],
        legs: [
            { member_id: 'z', leg_key: 'origin>fra', selected_mode: 'flight',
              from_kind: 'origin', from_label: 'Shanghai',
              to_kind: 'stop', to_stop_id: 'fra', to_label: 'Frankfurt' },
            { member_id: 'l', leg_key: 'origin>stu', selected_mode: 'flight',
              from_kind: 'origin', from_label: 'Shenzhen',
              to_kind: 'stop', to_stop_id: 'stu', to_label: 'Stuttgart' }],
    };
    const drawn = TripTeamJourneys.journeys(home, 'all');
    console.log(JSON.stringify({
        starts: drawn.map(item => item.points[0]),
        // A journey the plan does not contain must be impossible to draw.
        invented: TripTeamJourneys.journeys(
            { ...home, legs: [] }, 'all').length,
    }));
    """)
    assert [50.0 > point[0] for point in data["starts"]]
    assert sorted(data["starts"]) == [[22.54, 114.06], [31.23, 121.47]], (
        f"members must start from their own place: {data['starts']}"
    )
    assert data["invented"] == 0, (
        "with no legs there is nothing to draw, whatever the stops say"
    )


def check_flights_through_different_airports_are_two_routes() -> None:
    """Same customer, same flight leg, different airports is not one journey.

    The timeline sees a flight as its ground transfers, whose titles name the
    airports, so it already tells these apart. The map draws the whole leg as
    one line, so without the airports in its identity the two merge and one
    member is shown leaving from an airport they never went to.
    """
    data = run_js(PLAN + """
    const flight = (member, depLat, depLng, depName) => ({
        member_id: member, leg_key: 'origin>fra', selected_mode: 'flight',
        from_kind: 'origin', from_label: 'Shanghai',
        to_kind: 'stop', to_stop_id: 'fra', to_label: 'Frankfurt',
        departure_airport_lat: depLat, departure_airport_lng: depLng,
        departure_airport_name: depName,
        arrival_airport_lat: 50.04, arrival_airport_lng: 8.56,
    });
    const home = { ...plan, origin_lat: 31.23, origin_lng: 121.47 };
    const apart = TripTeamJourneys.journeys({ ...home, legs: [
        flight('z', 31.14, 121.81, 'PVG'),
        flight('l', 31.20, 121.34, 'SHA')] }, 'all');
    const together = TripTeamJourneys.journeys({ ...home, legs: [
        flight('z', 31.14, 121.81, 'PVG'),
        flight('l', 31.14, 121.81, 'PVG')] }, 'all');
    console.log(JSON.stringify({
        apartRoutes: apart.length,
        apartAirports: apart.map(item => item.points[1]).sort(),
        apartWho: apart.map(item => item.members.join('')).sort(),
        togetherRoutes: together.length,
        togetherWho: together[0].members,
        memberIds: apart.map(item => item.memberIds.join('')).sort(),
    }));
    """)
    assert data["apartRoutes"] == 2, (
        "flying from different airports is not travelling together"
    )
    assert data["apartAirports"] == [[31.14, 121.81], [31.2, 121.34]], (
        f"each member must be drawn through their own airport: "
        f"{data['apartAirports']}"
    )
    assert data["apartWho"] == ["Li", "Zhang"], data["apartWho"]
    assert data["togetherRoutes"] == 1, (
        "the same flight through the same airports is still one journey"
    )
    assert data["togetherWho"] == ["Zhang", "Li"], data["togetherWho"]
    # Choosing a line has to be able to say which of the two it was.
    assert data["memberIds"] == ["l", "z"], data["memberIds"]


def check_focus_picks_the_chosen_members_journey() -> None:
    """Two journeys sharing a leg key and mode are told apart by whose it is."""
    module = (MODULES / "trip-team-map.js").read_text(encoding="utf-8")
    assert "item.memberIds.includes(memberId)" in module, (
        "focusing a leg must disambiguate by member, not leg key and mode alone"
    )
    timeline = (MODULES / "trip-team-timeline.js").read_text(encoding="utf-8")
    assert "entry.memberIds" in timeline, (
        "the timeline has to pass on whose line was chosen"
    )


def check_flown_legs_pass_through_their_airports() -> None:
    """A flight goes via its airports, because that is where it goes."""
    data = run_js(PLAN + """
    const flown = TripTeamJourneys.journeys({
        ...plan,
        legs: [{ ...leg('z', 'flight'),
            departure_airport_lat: 50.03, departure_airport_lng: 8.56,
            arrival_airport_lat: 48.69, arrival_airport_lng: 9.22 }],
    }, 'all');
    console.log(JSON.stringify({ points: flown[0].points }));
    """)
    assert data["points"] == [
        [50.11, 8.68], [50.03, 8.56], [48.69, 9.22], [48.78, 9.18]
    ], data["points"]


def check_one_rule_for_both_views() -> None:
    """The map must not carry its own idea of what counts as one journey."""
    journeys = (MODULES / "trip-team-journeys.js").read_text(encoding="utf-8")
    assert "TripTeamTimeline.identityOf" in journeys, (
        "the map has to reuse the timeline's rule or the two views will drift"
    )
    for invented in ("sameJourney", "selected_mode ===", "from_label ==="):
        assert invented not in journeys, (
            f"the map is deciding journey identity for itself: {invented}"
        )
    # The legacy single-path line must not be drawn for a team plan.
    candidates = (MODULES / "trip-candidates-map.js").read_text(encoding="utf-8")
    assert "} else if (routePoints.length >= 2) {" in candidates, (
        "a team plan must not get one line through the stops in order"
    )
    assert "TripTeamMap.draw(plan" in candidates
    team_map = (MODULES / "trip-team-map.js").read_text(encoding="utf-8")
    assert "dashArray" not in team_map, (
        "an unknown route must be absent, not a dashed guess"
    )
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for element in ("trip-map-lanes", "trip-map-notice"):
        assert f'id="{element}"' in index, f"missing element: {element}"
    for name in ("trip-team-journeys.js", "trip-team-map.js"):
        assert name in index, f"module never loaded: {name}"
    timeline = "".join(
        (MODULES / name).read_text(encoding="utf-8")
        for name in ("trip-team-timeline.js", "trip-team-timeline-view.js")
    )
    assert "TripTeamMap.focusStop" in timeline and "TripTeamMap.focusLeg" in timeline, (
        "choosing a timeline line must show it on the map"
    )


def main() -> None:
    check_different_modes_are_two_routes()
    check_same_journey_is_one_route()
    check_no_leg_means_no_line()
    check_endpoints_come_from_the_leg_not_the_stop_order()
    check_flights_through_different_airports_are_two_routes()
    check_focus_picks_the_chosen_members_journey()
    check_flown_legs_pass_through_their_airports()
    check_one_rule_for_both_views()
    print("PASS: team map lanes, shared journeys and unresolved routes")


if __name__ == "__main__":
    main()
