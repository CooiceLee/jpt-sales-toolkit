"""A real team plan survives Preview, Generate and a reload from the database.

Two colleagues leave from different cities, each visits their own customer on
the same booked morning, they meet at a shared stop, and each goes home to their
own place. What the calculation worked out has to still be there after a save.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_team_roundtrip_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from backend.repositories.base import generate_uuid, get_db, now_iso  # noqa: E402
from backend.services.review_service import ReviewService  # noqa: E402
from backend.services.trip_visit_briefing_repository import (  # noqa: E402
    normalize_payload,
)
from backend.startup_upgrade import initialize_database_safely  # noqa: E402

SHANGHAI = ("Shanghai", 31.2304, 121.4737)
SHENZHEN = ("Shenzhen", 22.5431, 114.0579)
FRANKFURT = ("Frankfurt Customer", 50.1109, 8.6821)
PARIS = ("Paris Customer", 48.8566, 2.3522)
MUNICH = ("Munich Expo", 48.1351, 11.5820)


def _seed(service: ReviewService) -> dict:
    conn = get_db()
    stamp = now_iso()
    people = {}
    for key, name in (("zhang", "Zhang"), ("li", "Li")):
        people[key] = generate_uuid()
        conn.execute(
            "INSERT INTO users (id,username,display_name,role,password_hash,"
            "is_active,created_at) VALUES (?,?,?,'sales','h',1,?)",
            (people[key], name.lower(), name, stamp),
        )
    actor = people["zhang"]
    plan_id = generate_uuid()
    conn.execute(
        """INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,
           travel_mode,route_order_mode,transport_mode_priority,
           origin_name,origin_lat,origin_lng,
           destination_name,destination_lat,destination_lng,
           avoid_weekends,status,planning_mode,
           created_at,created_by,updated_at,updated_by,row_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Draft','team',?,?,?,?,1)""",
        (plan_id, "Team Europe", actor, "2026-09-14", "2026-09-30", "flight",
         "manual", '["flight","drive","ground_public"]',
         *SHANGHAI[0:1], SHANGHAI[1], SHANGHAI[2],
         *SHANGHAI[0:1], SHANGHAI[1], SHANGHAI[2],
         1, stamp, actor, stamp, actor),
    )
    stops = {}
    for key, (name, lat, lng), attendee in (
        ("frankfurt", FRANKFURT, "zhang"),
        ("paris", PARIS, "li"),
    ):
        customer_id = generate_uuid()
        conn.execute(
            "INSERT INTO customers (id,display_name,normalized_name,lat,lng,"
            "created_at,updated_at,row_version) VALUES (?,?,?,?,?,?,?,1)",
            (customer_id, name, name.lower(), lat, lng, stamp, stamp),
        )
        stop_id = generate_uuid()
        conn.execute(
            """INSERT INTO trip_plan_stops (id,plan_id,customer_id,sequence_no,
               duration_half_days,stay_days,preferred_period,schedule_locked,
               planned_date,planned_start_period,confirmation_status,
               created_at,created_by,updated_at,updated_by,row_version)
               VALUES (?,?,?,1,1,1,'auto',1,'2026-09-16','AM','confirmed',
               ?,?,?,?,1)""",
            (stop_id, plan_id, customer_id, stamp, actor, stamp, actor),
        )
        service.trip_plan_service.briefing_repo.replace(
            stop_id,
            normalize_payload({"participants": [{"user_id": people[attendee]}]}),
            actor, stamp, None,
        )
        stops[key] = stop_id
    conn.commit()

    # A shared stop both of them attend, once each has arrived.
    plan = service.add_trip_free_stop(
        plan_id,
        {"category": "other", "location_name": MUNICH[0],
         "lat": MUNICH[1], "lng": MUNICH[2], "duration_half_days": 2,
         "participant_user_ids": [people["zhang"], people["li"]]},
        actor, "leader",
    )
    stops["munich"] = [
        item["id"] for item in plan["stops"]
        if item.get("location_name") == MUNICH[0]
    ][0]

    for key, origin in (("zhang", SHANGHAI), ("li", SHENZHEN)):
        service.set_trip_member(
            plan_id,
            {
                "user_id": people[key],
                "origin_name_override": origin[0],
                "origin_lat_override": origin[1],
                "origin_lng_override": origin[2],
                "destination_name_override": origin[0],
                "destination_lat_override": origin[1],
                "destination_lng_override": origin[2],
            },
            actor, "leader",
        )
    return {"plan_id": plan_id, "actor": actor, "people": people, "stops": stops}


def check_members_are_team_accounts(service, seed) -> None:
    """Only people the company can send are planned for."""
    try:
        service.set_trip_member(
            seed["plan_id"], {"user_id": "not-an-account"},
            seed["actor"], "leader",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("planned a trip for somebody with no account")


def check_missing_endpoints_are_rejected(service, seed) -> None:
    """Somebody with nowhere to leave from is missing data, not route-complete."""
    from backend.services.trip_team_adapter import validate_team_inputs

    try:
        validate_team_inputs(("zhang",), {}, {"__default__": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a member with no departure point")
    try:
        validate_team_inputs((), {"__default__": {}}, {"__default__": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a team trip with nobody on it")


def check_round_trip(service, seed) -> None:
    plan_id, actor, people = seed["plan_id"], seed["actor"], seed["people"]
    preview = service.preview_trip_itinerary(plan_id, {}, actor, "leader")
    summary = preview["itinerary_summary"]
    assert summary["planning_mode"] == "team"
    assert set(summary["members"]) == set(people.values())

    # Two customers at the same booked hour is what a team is for, not an error.
    assert not [
        risk for risk in summary["risks"]
        if risk["kind"] in ("member_double_booked", "unassigned_parallel_events")
    ], summary["risks"]

    # One stop is one row, however many colleagues attend it.
    munich_rows = [
        row for row in summary["stop_updates"]
        if row["id"] == seed["stops"]["munich"]
    ]
    assert len(munich_rows) == 1, f"a shared stop wrote {len(munich_rows)} rows"

    expected_legs = {
        (leg["member_id"], leg["leg_key"]): (
            leg["sequence_no"], leg["planned_start_date"],
            leg["planned_start_period"], leg["planned_end_date"],
            leg["planned_end_period"],
        )
        for leg in summary["legs"]
    }
    assert expected_legs, "a team trip has journeys in it"
    for member in people.values():
        lane = sorted(
            value[0] for key, value in expected_legs.items() if key[0] == member
        )
        assert lane == list(range(1, len(lane) + 1)), f"{member} lane: {lane}"

    saved = service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert saved is not None

    reloaded = service.get_trip_plan(plan_id, actor, "leader")
    actual_legs = {
        (leg["member_id"], leg["leg_key"]): (
            leg["sequence_no"], leg["planned_start_date"],
            leg["planned_start_period"], leg["planned_end_date"],
            leg["planned_end_period"],
        )
        for leg in reloaded["legs"]
    }
    assert actual_legs == expected_legs, (
        "the saved journeys differ from the ones that were calculated:\n"
        f"  calculated {sorted(expected_legs)}\n  reloaded   {sorted(actual_legs)}"
    )

    stored = reloaded["itinerary_summary"]
    assert stored["member_totals"] == summary["member_totals"]
    assert stored["risks"] == summary["risks"]
    assert stored["schedule_items"] == summary["schedule_items"]

    # The times the calculation gave the stops are on the stops themselves.
    by_id = {item["id"]: item for item in reloaded["stops"]}
    for row in summary["stop_updates"]:
        stop = by_id[row["id"]]
        assert stop["planned_date"] == row["planned_date"], stop
        assert stop["planned_start_period"] == row["planned_start_period"]
        assert stop["planned_end_date"] == row["planned_end_date"]
        assert stop["planned_end_period"] == row["planned_end_period"]

    # Everybody is planned all the way home, each to their own city.
    homes = {
        leg["member_id"]: leg["to_label"] for leg in reloaded["legs"]
        if leg["leg_key"].endswith(">destination")
    }
    assert set(homes.values()) == {SHANGHAI[0], SHENZHEN[0]}, homes
    for total in stored["member_totals"].values():
        assert total["route_complete"] is True
        assert total["calculated_end_date"]


def check_overrun_is_a_risk_not_a_refusal(service, seed) -> None:
    """With fixed appointments the dates are what gives, so say it and save it."""
    plan_id, actor = seed["plan_id"], seed["actor"]
    service.update_trip_plan(
        plan_id, {"end_date": "2026-09-16"}, actor, "leader"
    )
    saved = service.generate_trip_itinerary(plan_id, {}, actor, "leader")
    assert saved is not None, "a team trip that runs long must still save"
    kinds = [risk["kind"] for risk in saved["itinerary_summary"]["risks"]]
    assert "member_return_overrun" in kinds, kinds


def main() -> None:
    settings = init_settings(ROOT)
    initialize_database_safely(settings)
    service = ReviewService()
    seed = _seed(service)
    check_members_are_team_accounts(service, seed)
    check_missing_endpoints_are_rejected(service, seed)
    check_round_trip(service, seed)
    check_overrun_is_a_risk_not_a_refusal(service, seed)
    close_db()
    print("PASS: team itinerary survives preview, generate and reload")


if __name__ == "__main__":
    main()
