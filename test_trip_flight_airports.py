"""Regressions for airports recorded on a flown leg.

An airport belongs to the connection between two stops, never to the stop list:
stored as a stop it is reordered away from the leg it serves.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_flight_airports_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from backend.config import init_settings  # noqa: E402
from backend.repositories import APP_SCHEMA_VERSION, close_db  # noqa: E402
from backend.repositories.base import generate_uuid, get_db, now_iso  # noqa: E402
from backend.services.review_service import ReviewService  # noqa: E402
from backend.services.trip_flight_expansion import (  # noqa: E402
    expand,
    ground_mode,
    is_expandable,
    missing_airport_sides,
)
from backend.services.trip_leg_contract import normalize_airports  # noqa: E402
from backend.startup_upgrade import initialize_database_safely  # noqa: E402

FRA = {
    "arrival_airport_name": "法兰克福机场",
    "arrival_airport_lat": 50.0379,
    "arrival_airport_lng": 8.5622,
}
SZX = {
    "departure_airport_name": "深圳宝安国际机场",
    "departure_airport_lat": 22.6393,
    "departure_airport_lng": 113.8107,
}


def check_contract() -> None:
    """A searched airport is a name and a location together, never half of one."""
    for broken, why in (
        ({"departure_airport_name": "法兰克福机场"}, "name without a location"),
        ({"departure_airport_lat": 50.0, "departure_airport_lng": 8.5}, "location without a name"),
        ({"departure_airport_stay_half_days": 2}, "a stay without an airport"),
        ({"arrival_airport_name": "X", "arrival_airport_lat": 95.0,
          "arrival_airport_lng": 8.5}, "latitude outside the valid range"),
    ):
        try:
            normalize_airports(dict(broken), "leg")
        except ValueError:
            continue
        raise AssertionError(f"accepted {why}")

    value = {**SZX, "departure_airport_stay_half_days": "2"}
    normalize_airports(value, "leg")
    assert value["departure_airport_stay_half_days"] == 2
    assert value["arrival_airport_name"] is None
    normalize_airports({}, "leg")


def check_expansion() -> None:
    """Only a fully described flight expands, and transfers never fly."""
    flown = {"selected_mode": "flight", **SZX, **FRA,
             "departure_airport_stay_half_days": 2}
    assert is_expandable(flown)
    segments = expand(flown, ["flight", "drive"])
    assert [item["role"] for item in segments] == [
        "to_airport", "flight", "from_airport"
    ]
    assert [item["mode"] for item in segments] == ["drive", "flight", "drive"]
    assert segments[0]["airport"]["stay_half_days"] == 2

    assert ground_mode(["flight"]) == "drive"
    assert not is_expandable({**flown, "selected_mode": "drive"})
    assert missing_airport_sides({**flown, "selected_mode": "drive"}) == []
    half = {"selected_mode": "flight", **SZX}
    assert not is_expandable(half)
    assert missing_airport_sides(half) == ["arrival"]
    assert expand(half, ["drive"])[0]["role"] == "direct"


def _seed(service: ReviewService) -> tuple[str, str, str]:
    conn = get_db()
    actor = generate_uuid()
    stamp = now_iso()
    conn.execute(
        "INSERT INTO users (id,username,display_name,role,password_hash,is_active,created_at)"
        " VALUES (?,'air','air','leader','h',1,?)",
        (actor, stamp),
    )
    plan_id = generate_uuid()
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,travel_mode,
           route_order_mode,transport_mode_priority,origin_name,origin_lat,origin_lng,
           destination_name,destination_lat,destination_lng,avoid_weekends,status,
           created_at,created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'Draft',?,?,?,?,1)""",
        (plan_id, "Airport trip", actor, "2026-09-14", "2026-09-30", "flight", "manual",
         '["drive","flight","ground_public"]', "Shenzhen city", 22.5431, 114.0579,
         "Shenzhen city", 22.5431, 114.0579, 1, stamp, actor, stamp, actor),
    )
    customer_id = generate_uuid()
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,lat,lng,created_at,updated_at,row_version)"
        " VALUES (?,?,?,?,?,?,?,1)",
        (customer_id, "German Customer", "german customer", 50.1109, 8.6821, stamp, stamp),
    )
    stop_id = generate_uuid()
    conn.execute(
        """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,duration_half_days,
           stay_days,preferred_period,schedule_locked,confirmation_status,
           created_at,created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,1,2,1,'auto',0,'unconfirmed',?,?,?,?,1)""",
        (stop_id, plan_id, customer_id, stamp, actor, stamp, actor),
    )
    conn.commit()
    return plan_id, stop_id, actor


def check_itinerary(service: ReviewService, plan_id: str, stop_id: str, actor: str) -> None:
    """The schedule shows the transfers and the wait, and only when flying."""
    key = f"origin>{stop_id}"
    plan = service.get_trip_plan(plan_id, actor, "leader")

    plain = service._calculate_trip_itinerary(plan, {})
    assert not (plain["legs"][0].get("segments") or []), "no airports means no expansion"

    airports = {**SZX, **FRA, "selected_mode": "flight",
                "departure_airport_stay_half_days": 2}
    flown = service._calculate_trip_itinerary(plan, {"leg_overrides": {key: airports}})
    outbound = flown["legs"][0]
    segments = outbound["segments"]
    assert [item["role"] for item in segments] == [
        "to_airport", "flight", "from_airport"
    ]
    assert segments[0]["stay_half_days"] == 2
    assert outbound["travel_half_days"] >= 4, "the wait at the airport takes time"
    items = flown["summary"]["schedule_items"]
    assert any(item["item_type"] == "airport" for item in items), "the wait is on the timeline"
    assert len(flown["legs"]) == len(plain["legs"]), "expansion adds no stored connections"

    grounded = service._calculate_trip_itinerary(
        plan, {"leg_overrides": {key: {**airports, "selected_mode": "drive"}}}
    )
    assert not (grounded["legs"][0].get("segments") or []), (
        "a ground connection must never route through an airport"
    )


def check_persistence(service: ReviewService, plan_id: str, stop_id: str, actor: str) -> None:
    """Choosing an airport survives a regeneration without locking the leg."""
    key = f"origin>{stop_id}"
    airports = {**SZX, **FRA, "selected_mode": "flight"}
    service.generate_trip_itinerary(
        plan_id, {"leg_overrides": {key: airports}}, actor, "leader"
    )
    saved = service.trip_plan_service.leg_repo.saved_airports(plan_id)
    # Keyed by (member_id, leg_key): the shared path belongs to no member, and
    # two colleagues covering the same stops must not overwrite each other.
    assert saved[(None, key)]["arrival_airport_name"] == "法兰克福机场"
    assert not any(
        leg.get("mode_locked")
        for leg in service.trip_plan_service.leg_repo.list_active(plan_id)
    ), "airports must not require the leg to be locked"

    service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    plan = service.get_trip_plan(plan_id, actor, "leader")
    outbound = plan["legs"][0]
    assert outbound["arrival_airport_name"] == "法兰克福机场", (
        "a plain regeneration must not drop the chosen airports"
    )


def check_weekend_departure(service, plan_id: str, actor: str) -> None:
    """Leaving on a Saturday is normal; only the customer visit needs a workday."""
    conn = get_db()
    conn.execute(
        "UPDATE trip_plans SET start_date='2026-09-19', end_date='2026-10-10' WHERE id=?",
        (plan_id,),
    )
    conn.commit()
    plan = service.get_trip_plan(plan_id, actor, "leader")
    calc = service._calculate_trip_itinerary(plan, {})
    first = calc["legs"][0]
    assert first["planned_start_date"] == "2026-09-19", (
        f"travel must start on the Saturday the trip starts, got {first['planned_start_date']}"
    )
    visit = calc["stop_updates"][0]
    assert visit["planned_date"] >= "2026-09-21", (
        f"the customer visit must still wait for a workday, got {visit['planned_date']}"
    )


def check_calendar_deadline(service) -> None:
    """A return that lands on a weekend is late, even though it is not a workday."""
    friday = (date(2026, 10, 2), "PM")
    for actual, label in (
        ((date(2026, 10, 3), "AM"), "Saturday"),
        ((date(2026, 10, 4), "PM"), "Sunday"),
        ((date(2026, 10, 5), "AM"), "Monday"),
    ):
        assert service._calendar_slots_after(friday, actual) > 0, (
            f"a return on {label} after a Friday deadline must count as overrun"
        )
    assert service._calendar_slots_after(friday, (date(2026, 10, 2), "AM")) == 0
    assert service._calendar_slots_after(friday, friday) == 0


def check_member_isolation(service, plan_id: str, stop_id: str, actor: str) -> None:
    """Two members covering the same stops keep separate airports."""
    repo = service.trip_plan_service.leg_repo
    conn = get_db()
    others = [
        row[0]
        for row in conn.execute("SELECT id FROM users WHERE id != ?", (actor,))
    ]
    mate = others[0] if others else generate_uuid()
    if not others:
        conn.execute(
            "INSERT INTO users (id,username,display_name,role,password_hash,"
            "is_active,created_at) VALUES (?,'mate','mate','sales','h',1,?)",
            (mate, now_iso()),
        )
    for user in (actor, mate):
        conn.execute(
            "INSERT OR IGNORE INTO trip_plan_members (id,plan_id,user_id,"
            "created_at,updated_at) VALUES (?,?,?,?,?)",
            (generate_uuid(), plan_id, user, now_iso(), now_iso()),
        )
    conn.commit()

    key = f"origin>{stop_id}"
    stamp = now_iso()
    repo.replace_active(
        plan_id,
        [
            {
                "leg_key": key, "member_id": actor, "sequence_no": 1,
                "from_kind": "origin", "to_kind": "stop", "to_stop_id": stop_id,
                "selected_mode": "flight", "distance_km": 100.0,
                "time_hours": 1.0, "travel_days": 0, "travel_half_days": 0,
                "arrival_airport_name": "法兰克福机场",
                "arrival_airport_lat": 50.0379, "arrival_airport_lng": 8.5622,
            },
            {
                "leg_key": key, "member_id": mate, "sequence_no": 1,
                "from_kind": "origin", "to_kind": "stop", "to_stop_id": stop_id,
                "selected_mode": "drive", "distance_km": 100.0,
                "time_hours": 2.0, "travel_days": 0, "travel_half_days": 0,
                "arrival_airport_name": "巴黎夏尔·戴高乐机场",
                "arrival_airport_lat": 49.0097, "arrival_airport_lng": 2.5479,
            },
        ],
        actor,
        stamp,
    )
    saved = repo.saved_airports(plan_id)
    assert saved[(actor, key)]["arrival_airport_name"] == "法兰克福机场"
    assert saved[(mate, key)]["arrival_airport_name"] == "巴黎夏尔·戴高乐机场", (
        "one member's airport overwrote the other's"
    )

    try:
        repo.replace_active(
            plan_id,
            [{
                "leg_key": key, "member_id": generate_uuid(), "sequence_no": 1,
                "from_kind": "origin", "to_kind": "stop", "to_stop_id": stop_id,
                "selected_mode": "drive", "distance_km": 1.0, "time_hours": 1.0,
                "travel_days": 0, "travel_half_days": 0,
            }],
            actor,
            now_iso(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("a leg for a non-member was accepted")


def check_booked_time_beats_preferences(service, plan_id: str, actor: str) -> None:
    """A confirmed appointment outranks the weekend, holiday and AM/PM wishes."""
    conn = get_db()
    stop_id = conn.execute(
        "SELECT id FROM trip_plan_stops WHERE plan_id = ? AND archived_at IS NULL",
        (plan_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE trip_plans SET start_date='2026-09-14', end_date='2026-10-10',"
        " holiday_dates=? WHERE id=?",
        ('["2026-10-01"]', plan_id),
    )
    for booked_date, booked_period, preferred, expected_risk in (
        # 2026-09-19 is a Saturday, 2026-10-01 a Chinese holiday.
        ("2026-09-19", "AM", "auto", "booked_on_skipped_day"),
        ("2026-10-01", "AM", "auto", "booked_on_skipped_day"),
        ("2026-09-16", "PM", "AM", "booked_outside_preferred_period"),
    ):
        conn.execute(
            "UPDATE trip_plan_stops SET schedule_locked=1, planned_date=?,"
            " planned_start_period=?, preferred_period=? WHERE id=?",
            (booked_date, booked_period, preferred, stop_id),
        )
        conn.commit()
        plan = service.get_trip_plan(plan_id, actor, "leader")
        calc = service._calculate_trip_itinerary(plan, {"stop_order": [stop_id]})
        visit = calc["stop_updates"][0]
        assert visit["planned_date"] == booked_date, (
            f"booked {booked_date} was moved to {visit['planned_date']}"
        )
        assert visit["planned_start_period"] == booked_period
        kinds = [item["kind"] for item in calc["summary"]["risks"]]
        assert expected_risk in kinds, f"expected {expected_risk}, got {kinds}"
    conn.execute(
        "UPDATE trip_plan_stops SET schedule_locked=0, planned_date=NULL,"
        " planned_start_period=NULL, preferred_period='auto' WHERE id=?",
        (stop_id,),
    )
    conn.commit()


def check_team_primitives() -> None:
    """Parallel visits are legitimate; unknown travellers are never guessed."""
    from datetime import date as _date

    from backend.services.trip_team_rules import (
        member_lanes,
        occupied_slots,
        resolve_participants,
        staffing_risks,
        unresolved_events,
    )
    from backend.services.trip_team_schedule import TeamEvent

    team = ("zhang", "li")
    morning = (_date(2026, 9, 16), "AM")
    afternoon = (_date(2026, 9, 16), "PM")

    def visit(stop_id, attendees, slot=morning, half_days=1):
        return TeamEvent(
            stop_id=stop_id, kind="customer", point={"lat": 0.0, "lng": 0.0},
            duration_half_days=half_days, participants=tuple(attendees),
            booked_slot=slot,
        )

    assert resolve_participants((), team) == team, "silence means the whole team"
    assert resolve_participants(("zhang",), team) == ("zhang",)
    # Naming somebody who left the team must not silently become "everyone goes".
    assert resolve_participants(("wang",), team) == ()
    assert resolve_participants(("zhang", "wang"), team) == ("zhang",)
    outsider = [visit("frankfurt", ["wang"])]
    assert [item["kind"] for item in staffing_risks(outsider, team)] == [
        "participant_not_in_trip_team"
    ]
    assert all(not lane for lane in member_lanes(outsider, team).values()), (
        "a visit with no valid traveller must not be routed for anyone"
    )

    for attendees, expected in (
        ((["zhang"], ["li"]), []),
        ((["zhang"], ["zhang"]), ["member_double_booked"]),
        (([], []), ["parallel_visits_unassigned"]),
        ((["zhang"], []), ["parallel_visits_unassigned"]),
    ):
        events = [visit("frankfurt", attendees[0]), visit("paris", attendees[1])]
        kinds = [item["kind"] for item in staffing_risks(events, team)]
        assert kinds == expected, f"{attendees} -> {kinds}, expected {expected}"

    # Two unassigned visits at the same hour cannot both be the whole team, so
    # neither may enter a lane and become a journey nobody makes.
    unassigned = [visit("frankfurt", []), visit("paris", [])]
    assert unresolved_events(unassigned, team) == {"frankfurt", "paris"}
    assert all(not lane for lane in member_lanes(unassigned, team).values())
    alone = [visit("frankfurt", [])]
    assert unresolved_events(alone, team) == set(), "travelling together is normal"
    assert [event.stop_id for event in member_lanes(alone, team)["zhang"]] == [
        "frankfurt"
    ]

    # A day-long visit booked for the morning still runs into the afternoon.
    assert occupied_slots(visit("a", ["zhang"], morning, 2)) == (morning, afternoon)
    spanning = [
        visit("a", ["zhang"], morning, 2), visit("b", ["zhang"], afternoon, 1)
    ]
    assert "member_double_booked" in [
        item["kind"] for item in staffing_risks(spanning, team)
    ], "an overlap hidden by duration was missed"
    sequential = [
        visit("a", ["zhang"], morning, 1), visit("b", ["zhang"], afternoon, 1)
    ]
    assert staffing_risks(sequential, team) == []

    conflicting = [visit("frankfurt", ["zhang"]), visit("paris", ["zhang"])]
    assert len(member_lanes(conflicting, team)["zhang"]) == 2, (
        "a conflicting visit must not be dropped"
    )

    shared = TeamEvent(
        stop_id="stuttgart", kind="free", point={"lat": 0.0, "lng": 0.0},
        duration_half_days=1, participants=("zhang", "li"),
        booked_slot=(_date(2026, 9, 17), "AM"),
    )
    lanes = member_lanes(
        [visit("frankfurt", ["zhang"]), visit("paris", ["li"]), shared], team
    )
    assert lanes["zhang"][-1].stop_id == "stuttgart"
    assert lanes["li"][-1].stop_id == "stuttgart", "a shared event is the merge"

    ordered = member_lanes(
        [
            visit("late", ["zhang"], (_date(2026, 9, 18), "AM")),
            visit("early", ["zhang"], (_date(2026, 9, 15), "PM")),
        ],
        team,
    )
    assert [event.stop_id for event in ordered["zhang"]] == ["early", "late"], (
        "a lane follows the booked times, not the order it was handed"
    )


def check_team_itinerary(service) -> None:
    """Every member walks their own trip, and nothing is invented for them."""
    from datetime import date as _date

    from backend.services.trip_team_schedule import TeamEvent, plan_team_itinerary

    team = ("zhang", "li")
    priority = ["drive", "flight", "ground_public"]
    shanghai = {"lat": 31.14, "lng": 121.80, "label": "Shanghai",
                "kind": "origin", "stop_id": None}
    shenzhen = {"lat": 22.64, "lng": 113.81, "label": "Shenzhen",
                "kind": "origin", "stop_id": None}

    def place(lat, lng, label, stop_id):
        return {"lat": lat, "lng": lng, "label": label, "kind": "stop",
                "stop_id": stop_id}

    frankfurt = place(50.11, 8.68, "Frankfurt", "f")
    paris = place(48.85, 2.35, "Paris", "p")
    munich = place(48.13, 11.58, "Munich", "m")
    stuttgart = place(48.78, 9.18, "Stuttgart", "s")
    dusseldorf = place(51.22, 6.78, "Dusseldorf", "d")

    def event(stop_id, point, attendees, slot=None, kind="customer"):
        return TeamEvent(stop_id, kind, point, 1, tuple(attendees), slot,
                         label=stop_id)

    def plan(events, origins=None):
        return plan_team_itinerary(
            service, team, events, origins or {"__default__": shanghai},
            (_date(2026, 9, 15), "AM"), priority,
        )

    morning = (_date(2026, 9, 16), "AM")

    # Two colleagues, two cities, same hour: ordinary, and no journey between
    # the customers may appear.
    result = plan([event("f", frankfurt, ["zhang"], morning),
                   event("p", paris, ["li"], morning)])
    pairs = {(leg["member_id"], leg["leg_key"]) for leg in result.legs}
    assert pairs == {("zhang", "origin>f"), ("li", "origin>p")}, pairs
    assert result.risks == []

    # Nobody named: neither visit may be routed for anyone.
    result = plan([event("f", frankfurt, [], morning),
                   event("p", paris, [], morning)])
    assert [risk["kind"] for risk in result.risks] == [
        "parallel_visits_unassigned"
    ]
    assert result.legs == []
    assert not any(
        totals["route_complete"] for totals in result.member_totals.values()
    ), "nobody's position can be trusted after an unassigned parallel pair"

    # One person, two places, same hour: both kept, neither routed.
    result = plan([event("f", frankfurt, ["zhang"], morning),
                   event("p", paris, ["zhang"], morning)])
    assert "member_double_booked" in [risk["kind"] for risk in result.risks]
    assert not any(leg["member_id"] == "zhang" for leg in result.legs)
    assert result.member_totals["zhang"]["route_complete"] is False
    assert result.member_totals["li"]["route_complete"] is True, (
        "one member's clash must not disturb another"
    )

    # Split, regroup, then carry on together from the shared place.
    result = plan([
        event("f", frankfurt, ["zhang"], morning),
        event("p", paris, ["li"], morning),
        event("s", stuttgart, ["zhang", "li"], (_date(2026, 9, 17), "AM"), "free"),
        event("m", munich, ["zhang", "li"], (_date(2026, 9, 18), "AM")),
    ])
    pairs = {(leg["member_id"], leg["leg_key"]) for leg in result.legs}
    assert {("zhang", "f>s"), ("li", "p>s")} <= pairs, pairs
    assert {("zhang", "s>m"), ("li", "s>m")} <= pairs, "the merge is the shared event"
    assert all(
        totals["route_complete"] for totals in result.member_totals.values()
    )

    # Colleagues leaving from different Chinese cities.
    result = plan(
        [event("f", frankfurt, ["zhang"], morning),
         event("p", paris, ["li"], morning)],
        origins={"__default__": shanghai, "zhang": shanghai, "li": shenzhen},
    )
    starts = {
        leg["member_id"]: leg["from_label"]
        for leg in result.legs if leg["leg_key"].startswith("origin>")
    }
    assert starts == {"zhang": "Shanghai", "li": "Shenzhen"}, starts

    # An unknown position is restored by the next booked appointment.
    result = plan([
        event("f", frankfurt, ["zhang"], morning),
        event("p", paris, ["zhang"], morning),
        event("m", munich, ["zhang"], (_date(2026, 9, 17), "AM")),
        event("d", dusseldorf, ["zhang"], (_date(2026, 9, 17), "PM")),
    ])
    keys = [leg["leg_key"] for leg in result.legs if leg["member_id"] == "zhang"]
    assert not any(key.endswith(">m") for key in keys), (
        "travel to Munich cannot be worked out and must not be invented"
    )
    assert "origin>f" not in keys and "origin>p" not in keys, (
        "a clash must clear the position, not route on from where they started"
    )
    kept = {
        item["source_id"] for item in result.schedule_items
        if item["member_id"] == "zhang" and item["item_type"] != "leg"
    }
    assert kept == {"f", "p", "m", "d"}, (
        f"every appointment stays visible, got {kept}"
    )
    booked = [
        item for item in result.schedule_items
        if item["source_id"] == "m" and item["item_type"] != "leg"
    ]
    assert booked and booked[0]["date"] == "2026-09-17"
    assert booked[0]["inbound_travel_resolved"] is False
    assert "m>d" in keys, "the appointment says where they are, so travel resumes"
    assert result.member_totals["zhang"]["route_complete"] is False


def check_team_travel_and_return(service) -> None:
    """Travel time, real merges, outsiders and the journey home."""
    from datetime import date as _date

    from backend.services.trip_team_schedule import TeamEvent, plan_team_itinerary

    team = ("zhang", "li")
    priority = ["drive", "flight", "ground_public"]

    def place(lat, lng, label, stop_id=None, kind="stop"):
        return {"lat": lat, "lng": lng, "label": label, "kind": kind,
                "stop_id": stop_id}

    shanghai = place(31.14, 121.80, "Shanghai", None, "origin")
    shenzhen = place(22.64, 113.81, "Shenzhen", None, "origin")
    frankfurt = place(50.11, 8.68, "Frankfurt", "f")
    paris = place(48.85, 2.35, "Paris", "p")
    munich = place(48.13, 11.58, "Munich", "m")
    stuttgart = place(48.78, 9.18, "Stuttgart", "s")
    morning = (_date(2026, 9, 16), "AM")

    def event(stop_id, point, attendees, slot=None, kind="customer"):
        return TeamEvent(stop_id, kind, point, 1, tuple(attendees), slot,
                         label=stop_id)

    def plan(events, origins=None, destinations=None, leg_settings=None):
        return plan_team_itinerary(
            service, team, events, origins or {"__default__": shanghai},
            (_date(2026, 9, 15), "AM"), priority, destinations=destinations,
            leg_settings=leg_settings,
        )

    # Naming somebody who left the trip says nothing about where the real
    # members are, so their journeys must carry on.
    result = plan([event("x", frankfurt, ["wang"], morning),
                   event("m", munich, ["zhang"], (_date(2026, 9, 17), "AM"))])
    assert "participant_not_in_trip_team" in [r["kind"] for r in result.risks]
    assert result.member_totals["zhang"]["route_complete"] is True, (
        "an outsider's visit must not stop the team's own routing"
    )
    assert any(leg["leg_key"] == "origin>m" for leg in result.legs)
    assert any(
        item["source_id"] == "x" and item["member_id"] is None
        for item in result.schedule_items
    ), "the visit itself stays visible"

    # A visit with no booked time starts after the journey to it, not before.
    result = plan([event("f", frankfurt, ["zhang"], morning),
                   event("m", munich, ["zhang"])])
    first = [i for i in result.schedule_items if i["source_id"] == "f"][0]
    second = [i for i in result.schedule_items if i["source_id"] == "m"][0]
    assert (second["date"], second["period"]) > (first["date"], first["period"])

    # A shared event cannot begin before its last attendee arrives.
    result = plan([event("f", frankfurt, ["zhang"], morning),
                   event("p", paris, ["li"], morning),
                   event("s", stuttgart, ["zhang", "li"], None, "free")])
    shared = [i for i in result.schedule_items if i["source_id"] == "s"]
    assert len(shared) == 2
    assert shared[0]["date"] == shared[1]["date"]
    assert shared[0]["period"] == shared[1]["period"], (
        "one event cannot start at two different times"
    )

    # Everybody goes home, each to their own return point.
    result = plan(
        [event("f", frankfurt, ["zhang"], morning),
         event("p", paris, ["li"], morning)],
        origins={"__default__": shanghai, "li": shenzhen},
        destinations={"__default__": shanghai, "li": shenzhen},
    )
    homes = {
        leg["member_id"]: leg["to_label"]
        for leg in result.legs if leg["leg_key"].endswith(">destination")
    }
    assert homes == {"zhang": "Shanghai", "li": "Shenzhen"}, homes
    assert all(t["route_complete"] for t in result.member_totals.values())

    # Team mode keeps the airport handling that single-path planning has.
    result = plan(
        [event("f", frankfurt, ["zhang"], (_date(2026, 9, 20), "AM"))],
        leg_settings={("zhang", "origin>f"): {
            "selected_mode": "flight",
            "departure_airport_name": "PVG",
            "departure_airport_lat": 31.1443, "departure_airport_lng": 121.8083,
            "arrival_airport_name": "FRA",
            "arrival_airport_lat": 50.0379, "arrival_airport_lng": 8.5622,
        }},
    )
    flown = [leg for leg in result.legs if leg["leg_key"] == "origin>f"][0]
    assert [item["role"] for item in flown.get("segments") or []] == [
        "to_airport", "flight", "from_airport"
    ], "a flown member leg must still expand into its ground transfers"


def check_team_lanes_and_timeline(service) -> None:
    """Each lane keeps its own order, and travel shows on the timeline."""
    from datetime import date as _date

    from backend.services.trip_team_schedule import TeamEvent, plan_team_itinerary

    team = ("zhang", "li")

    def place(lat, lng, label, stop_id=None, kind="stop"):
        return {"lat": lat, "lng": lng, "label": label, "kind": kind,
                "stop_id": stop_id}

    shanghai = place(31.14, 121.80, "Shanghai", None, "origin")
    result = plan_team_itinerary(
        service, team,
        [TeamEvent("f", "customer", place(50.11, 8.68, "Frankfurt", "f"), 1,
                   ("zhang",), (_date(2026, 9, 16), "AM"), label="f"),
         TeamEvent("m", "customer", place(48.13, 11.58, "Munich", "m"), 1,
                   ("zhang",), (_date(2026, 9, 18), "AM"), label="m"),
         TeamEvent("p", "customer", place(48.85, 2.35, "Paris", "p"), 1,
                   ("li",), (_date(2026, 9, 16), "AM"), label="p")],
        {"__default__": shanghai}, (_date(2026, 9, 15), "AM"),
        ["flight", "drive"], destinations={"__default__": shanghai},
    )

    # Legs are read back ordered by sequence_no, so each member's own lane has
    # to be numbered from 1 upwards or their route order is lost on reload.
    for member in team:
        lane = [leg for leg in result.legs if leg["member_id"] == member]
        assert [leg["sequence_no"] for leg in lane] == list(
            range(1, len(lane) + 1)
        ), f"{member} lane must be numbered within its own lane, got {lane}"

    # Travel has to appear on the timeline, or customers look teleported.
    travel = [i for i in result.schedule_items if i["item_type"] == "leg"]
    assert travel, "team travel must reach the timeline"
    assert all(i["member_id"] in team for i in travel)
    assert all(i["date"] and i["period"] for i in travel)
    for leg in result.legs:
        assert leg["planned_start_date"] and leg["planned_end_date"], (
            f"a leg on the timeline needs its own planned time: {leg['leg_key']}"
        )

    # Travel and the visit it leads to can land in the same half-day, and the
    # journey has to be listed first or the timeline reads back to front.
    same_slot = plan_team_itinerary(
        service, ("zhang",),
        [TeamEvent("f", "customer", place(50.11, 8.68, "Frankfurt", "f"), 1,
                   ("zhang",), (_date(2026, 9, 16), "AM"), label="f"),
         TeamEvent("m", "customer", place(48.13, 11.58, "Munich", "m"), 1,
                   ("zhang",), (_date(2026, 9, 16), "PM"), label="m")],
        {"__default__": shanghai}, (_date(2026, 9, 15), "AM"), ["drive"],
    )
    in_slot = [
        item for item in same_slot.schedule_items
        if item["date"] == "2026-09-16" and item["period"] == "PM"
    ]
    assert len(in_slot) >= 2, f"expected travel and the visit together: {in_slot}"
    travel = [item for item in in_slot if item["item_type"] == "leg"]
    visit = [item for item in in_slot if item["source_id"] == "m"]
    assert travel and visit, in_slot
    assert max(item["lane_order"] for item in travel) < visit[0]["lane_order"], (
        "travel must be ordered before the visit it reaches, "
        f"got travel={[i['lane_order'] for i in travel]} "
        f"visit={visit[0]['lane_order']}"
    )
    assert all(item["lane_order"] is not None for item in in_slot)

    # A visit lasting more than one half-day occupies every one of them, or the
    # afternoon of a day-long visit looks free and a second thing gets booked in.
    long_visit = plan_team_itinerary(
        service, ("zhang",),
        [TeamEvent("f", "customer", place(50.11, 8.68, "Frankfurt", "f"), 4,
                   ("zhang",), (_date(2026, 9, 16), "AM"), label="f")],
        {"__default__": shanghai}, (_date(2026, 9, 15), "AM"), ["flight"],
    )
    visit_slots = [
        (item["date"], item["period"]) for item in long_visit.schedule_items
        if item["source_id"] == "f" and item["item_type"] != "leg"
    ]
    assert len(visit_slots) == 4, f"a two-day visit occupies four half-days: {visit_slots}"
    assert len(set(visit_slots)) == 4, "each half-day appears once"
    counts = {
        item["half_day_count"] for item in long_visit.schedule_items
        if item["source_id"] == "f"
    }
    assert counts == {4}, counts
    stop_rows = [
        row for row in long_visit.stop_updates if row["id"] == "f"
    ]
    assert len(stop_rows) == 1, "the stop itself is still one row"
    assert stop_rows[0]["planned_date"] == "2026-09-16"
    assert stop_rows[0]["planned_end_date"] == "2026-09-17"

    # Each member's finish is what a return overrun can later be measured from.
    for member in team:
        total = result.member_totals[member]
        assert total["calculated_end_date"] and total["calculated_end_period"]


def check_schema() -> None:
    conn = sqlite3.connect(str(TEST_DIR / "database.sqlite"))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trip_plan_legs)")}
    conn.close()
    for side in ("departure", "arrival"):
        for suffix in ("name", "lat", "lng", "stay_half_days"):
            assert f"{side}_airport_{suffix}" in columns
    assert APP_SCHEMA_VERSION == 14


def main() -> None:
    check_contract()
    check_expansion()
    settings = init_settings(ROOT)
    initialize_database_safely(settings)
    check_schema()
    service = ReviewService()
    plan_id, stop_id, actor = _seed(service)
    check_itinerary(service, plan_id, stop_id, actor)
    check_persistence(service, plan_id, stop_id, actor)
    check_member_isolation(service, plan_id, stop_id, actor)
    check_booked_time_beats_preferences(service, plan_id, actor)
    check_team_primitives()
    check_team_itinerary(service)
    check_team_travel_and_return(service)
    check_team_lanes_and_timeline(service)
    check_calendar_deadline(service)
    check_weekend_departure(service, plan_id, actor)
    close_db()
    print("PASS: flight airports, weekend departure and calendar deadline")


if __name__ == "__main__":
    main()
