"""Regressions for airports recorded on a flown leg.

An airport belongs to the connection between two stops, never to the stop list:
stored as a stop it is reordered away from the leg it serves.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
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
    assert saved[key]["arrival_airport_name"] == "法兰克福机场"
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


def check_schema() -> None:
    conn = sqlite3.connect(str(TEST_DIR / "database.sqlite"))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trip_plan_legs)")}
    conn.close()
    for side in ("departure", "arrival"):
        for suffix in ("name", "lat", "lng", "stay_half_days"):
            assert f"{side}_airport_{suffix}" in columns
    assert APP_SCHEMA_VERSION == 7


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
    close_db()
    print("PASS: flight airports stay on the leg, expand only when flown, and persist")


if __name__ == "__main__":
    main()
