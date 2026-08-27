"""Batch 4 acceptance tests for half-day scheduling and visit briefings.

All API checks run against a temporary desktop profile.  The installed team
database is never opened or modified.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_trip_batch4_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.config import init_settings  # noqa: E402
from backend.repositories import APP_SCHEMA_VERSION, close_db  # noqa: E402
from backend.repositories.base import APP_SCHEMA_MIGRATIONS, get_db  # noqa: E402
from backend.startup_upgrade import initialize_database_safely  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


STOP_V6_COLUMNS = (
    "duration_half_days",
    "preferred_period",
    "planned_start_period",
    "planned_end_period",
    "schedule_locked",
    "confirmation_status",
)
LEG_V6_COLUMNS = (
    "travel_half_days",
    "manual_travel_half_days",
    "planned_start_date",
    "planned_start_period",
    "planned_end_date",
    "planned_end_period",
)
EXAMPLE_HEADERS = [
    "No.",
    "Company Name",
    "Full Address",
    "Recommended Visit Date",
    "Demo Laser",
    "PO Laser",
    "客户人员 / Customer Personnel",
    "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)",
    "Visiting topic",
]


def _require(response, status_code: int):
    assert response.status_code == status_code, response.text
    return response.json()


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    token = _require(
        client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        ),
        200,
    )["token"]
    return {"Authorization": f"Bearer {token}"}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _drop_v6_contract(conn: sqlite3.Connection) -> None:
    """Turn the current declarative schema into a faithful schema-5 fixture."""
    terms = set(STOP_V6_COLUMNS) | set(LEG_V6_COLUMNS) | {"trip_visit_briefings"}
    objects = conn.execute(
        "SELECT type,name,sql FROM sqlite_master "
        "WHERE type IN ('index','trigger') AND sql IS NOT NULL"
    ).fetchall()
    for object_type, name, sql in objects:
        if any(term in (sql or "") for term in terms):
            conn.execute(f'DROP {object_type.upper()} IF EXISTS "{name}"')
    conn.execute("DROP TABLE IF EXISTS trip_visit_briefings")
    for table in ("trip_plan_stops", "trip_plan_free_stops"):
        for column in STOP_V6_COLUMNS:
            if column in _table_columns(conn, table):
                conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
    for column in LEG_V6_COLUMNS:
        if column in _table_columns(conn, "trip_plan_legs"):
            conn.execute(f'ALTER TABLE trip_plan_legs DROP COLUMN "{column}"')


def check_schema5_to_current_upgrade() -> None:
    assert APP_SCHEMA_VERSION == 9
    with tempfile.TemporaryDirectory(prefix="jpt_trip_schema5_to_6_") as temp:
        data_dir = Path(temp) / "data"
        data_dir.mkdir()
        db_path = data_dir / "database.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
            conn.commit()
            conn.execute("PRAGMA foreign_keys=OFF")
            _drop_v6_contract(conn)
            conn.executemany(
                "INSERT INTO app_schema_migrations(version,name,app_version,applied_at) "
                "VALUES (?,?,?,?)",
                [
                    (version, name, "0.11.9-internal", "2026-08-23T00:00:00")
                    for version, name in APP_SCHEMA_MIGRATIONS
                    if version <= 5
                ],
            )
            conn.execute("PRAGMA user_version=5")
            now = "2026-08-23T00:00:00"
            conn.execute(
                "INSERT INTO users(id,username,password_hash,display_name,role,region,is_active,created_at) "
                "VALUES ('u1','upgrade','hash','Upgrade Leader','leader','GLOBAL',1,?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO customers(id,display_name,normalized_name,country,city,lat,lng,created_at,updated_at,row_version) "
                "VALUES ('c1','Upgrade Customer','upgrade customer','Germany','Berlin',52.52,13.405,?,?,4)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO trip_plans(id,title,owner_id,start_date,end_date,route_order_mode,status,created_at,updated_at,row_version) "
                "VALUES ('p1','Keep Route','u1','2026-09-15','2026-09-30','manual','Draft',?,?,9)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO trip_plan_stops(id,plan_id,customer_id,sequence_no,planned_date,planned_end_date,stay_days,created_at,updated_at,row_version) "
                "VALUES ('s1','p1','c1',1,'2026-09-15','2026-09-15',1,?,?,8)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO trip_plan_free_stops(id,plan_id,category,location_name,lat,lng,sequence_no,planned_date,planned_end_date,stay_days,created_at,updated_at,row_version) "
                "VALUES ('f1','p1','hotel','Upgrade Hotel',52.5,13.4,2,'2026-09-16','2026-09-16',1,?,?,7)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO trip_plan_legs(id,plan_id,leg_key,sequence_no,from_kind,from_label,to_kind,to_stop_id,to_label,selected_mode,distance_km,time_hours,travel_days,manual_travel_days,created_at,updated_at,row_version) "
                "VALUES ('l1','p1','origin>s1',1,'origin','Airport','stop','s1','Upgrade Customer','drive',10,1,1,1,?,?,6)",
                (now, now),
            )
            conn.commit()
        finally:
            conn.close()

        settings = init_settings(Path(temp) / "app")
        settings.data_dir = data_dir
        settings.db_path = db_path
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.upload_dir.mkdir()
        settings.backup_dir.mkdir()
        settings.runtime_config_dir.mkdir()
        result = initialize_database_safely(settings)
        assert result.migrated is True
        assert (result.source_schema_version, result.target_schema_version) == (
            5,
            APP_SCHEMA_VERSION,
        )
        assert result.backup_path and result.backup_path.is_file()
        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == APP_SCHEMA_VERSION
            assert conn.execute(
                "SELECT title,row_version FROM trip_plans WHERE id='p1'"
            ).fetchone() == ("Keep Route", 9)
            assert conn.execute(
                "SELECT stay_days,duration_half_days,planned_start_period,planned_end_period,row_version "
                "FROM trip_plan_stops WHERE id='s1'"
            ).fetchone() == (1, 2, "AM", "PM", 8)
            assert conn.execute(
                "SELECT stay_days,duration_half_days,planned_start_period,planned_end_period,row_version "
                "FROM trip_plan_free_stops WHERE id='f1'"
            ).fetchone() == (1, 2, "AM", "PM", 7)
            assert conn.execute(
                "SELECT travel_days,travel_half_days,manual_travel_days,manual_travel_half_days,row_version "
                "FROM trip_plan_legs WHERE id='l1'"
            ).fetchone() == (1, 2, 1, 2, 6)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "trip_visit_briefings" in tables
            briefing_columns = _table_columns(conn, "trip_visit_briefings")
            assert "channel_partner_companions_json" in briefing_columns
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()


def _snapshot() -> dict[str, list[tuple]]:
    conn = get_db()
    conn.commit()
    tables = (
        "trip_plans",
        "trip_plan_stops",
        "trip_plan_free_stops",
        "trip_plan_legs",
        "trip_visit_briefings",
    )
    return {
        table: [
            tuple(row)
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
        ]
        for table in tables
    }


def _create_customer(
    client: TestClient,
    headers: dict,
    owner_id: str,
    name: str,
    *,
    city: str = "Paris",
    country: str = "France",
    address: str = "1 Shared Test Road",
    postal_code: str = "75001",
    lat: float = 48.8566,
    lng: float = 2.3522,
) -> dict:
    customer = _require(
        client.post(
            "/api/customers",
            headers=headers,
            json={
                "display_name": name,
                "address": address,
                "city": city,
                "postal_code": postal_code,
                "country": country,
                "region": "EU",
                "lat": lat,
                "lng": lng,
                "geocode_source": "manual",
                "geocode_confidence": "high",
                "geocode_locked": True,
            },
        ),
        200,
    )
    lead = _require(
        client.post(
            "/api/leads",
            headers=headers,
            json={
                "customer_id": customer["id"],
                "owner_id": owner_id,
                "title": f"{name} customer visit",
                "source_channel": "Referral",
                "sales_stage": "Following",
                "application": "Battery laser welding",
                "quantity_text": "1 set",
            },
        ),
        200,
    )
    lead = _require(
        client.patch(
            f"/api/leads/{lead['id']}",
            headers=headers,
            json={
                "row_version": lead["row_version"],
                "product_series": "CW 2000W",
                "po_number": "PO-DEMO-500",
            },
        ),
        200,
    )
    return {"customer": customer, "lead": lead}


def _seed(client: TestClient) -> dict:
    accounts = {
        "leader": (
            "batch4-leader",
            "Batch4Leader2026",
            "Batch 4 Leader",
            "leader",
        ),
        "owner": (
            "batch4-sales",
            "Batch4Sales2026",
            "Batch 4 Sales",
            "sales",
        ),
        "other": (
            "batch4-other",
            "Batch4Other2026",
            "Other Sales",
            "sales",
        ),
        "tech": (
            "batch4-tech",
            "Batch4Tech2026",
            "Aydan Tech",
            "tech",
        ),
        "inactive": (
            "batch4-inactive",
            "Batch4Inactive2026",
            "Inactive Tech",
            "tech",
        ),
    }
    ids = {
        key: upsert_account(username, password, display_name, role, "EU")
        for key, (username, password, display_name, role) in accounts.items()
    }
    headers = {
        key: _login(client, spec[0], spec[1])
        for key, spec in accounts.items()
        if key != "inactive"
    }
    get_db().execute("UPDATE users SET is_active=0 WHERE id=?", (ids["inactive"],))
    get_db().commit()

    records = {
        key: _create_customer(client, headers["leader"], ids["owner"], name)
        for key, name in (
            ("rayxion", "RAYXION (레이시온)"),
            ("phile", "PHILENERGY"),
            ("inlaser", "INLASER"),
        )
    }
    foreign = _create_customer(
        client,
        headers["leader"],
        ids["owner"],
        "Foreign Contact Customer",
        city="Lyon",
        lat=45.7640,
        lng=4.8357,
    )
    contact = _require(
        client.post(
            f"/api/customers/{records['rayxion']['customer']['id']}/contacts",
            headers=headers["leader"],
            json={
                "name": "Kim Sungkyu",
                "position": "CEO",
                "email": "kim@example.test",
                "phone": "+33-1-555-0100",
                "is_primary": True,
            },
        ),
        200,
    )
    foreign_contact = _require(
        client.post(
            f"/api/customers/{foreign['customer']['id']}/contacts",
            headers=headers["leader"],
            json={
                "name": "Foreign Person",
                "email": "foreign@example.test",
                "is_primary": True,
            },
        ),
        200,
    )
    return {
        "ids": ids,
        "headers": headers,
        "records": records,
        "foreign": foreign,
        "contact": contact,
        "foreign_contact": foreign_contact,
    }


def _create_plan(
    client: TestClient,
    ctx: dict,
    title: str,
    *,
    start_date: str = "2026-09-15",
    end_date: str = "2026-09-30",
) -> dict:
    return _require(
        client.post(
            "/api/review/trip-plans",
            headers=ctx["headers"]["leader"],
            json={
                "title": title,
                "owner_id": ctx["ids"]["owner"],
                "start_date": start_date,
                "end_date": end_date,
                "region": "EU",
                "origin_name": "Shared Test Point",
                "origin_lat": 48.8566,
                "origin_lng": 2.3522,
                "destination_name": "Shared Test Point",
                "destination_lat": 48.8566,
                "destination_lng": 2.3522,
                "route_order_mode": "manual",
                "transport_mode_priority": ["drive", "ground_public", "flight"],
                "avoid_weekends": True,
            },
        ),
        200,
    )


def _add_stop(
    client: TestClient,
    ctx: dict,
    plan: dict,
    record_key: str,
    *,
    allow_duplicate: bool = False,
) -> dict:
    return _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops",
            headers=ctx["headers"]["owner"],
            json={
                "lead_id": ctx["records"][record_key]["lead"]["id"],
                "duration_half_days": 2,
                "allow_duplicate": allow_duplicate,
            },
        ),
        200,
    )


def _route_payload(plan: dict, durations: dict[str, dict], **updates) -> dict:
    payload = {
        "row_version": plan["row_version"],
        "start_date": plan["start_date"],
        "end_date": plan["end_date"],
        "route_order_mode": "manual",
        "stop_order": [stop["id"] for stop in plan["stops"]],
        "stop_durations": durations,
    }
    payload.update(updates)
    return payload


def _customer_slots(plan: dict) -> list[tuple[str, str, str]]:
    return [
        (item["source_id"], item["date"], item["period"])
        for item in plan["schedule_items"]
        if item["item_type"] == "customer"
    ]


def check_half_day_schedule_weekends_and_legacy_exclusion(
    client: TestClient, ctx: dict
) -> dict:
    plan = _create_plan(client, ctx, "Half-day slot contract")
    for key in ("rayxion", "phile", "inlaser"):
        plan = _add_stop(client, ctx, plan, key)
    ids = [stop["id"] for stop in plan["stops"]]
    durations = {
        ids[0]: {"half_days": 1, "preferred_period": "auto", "locked": False},
        ids[1]: {"half_days": 1, "preferred_period": "auto", "locked": False},
        ids[2]: {"half_days": 3, "preferred_period": "auto", "locked": False},
    }
    before = _snapshot()
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(plan, durations),
        ),
        200,
    )
    assert _snapshot() == before, "preview must remain zero-write"
    assert _customer_slots(preview) == [
        (ids[0], "2026-09-15", "AM"),
        (ids[1], "2026-09-15", "PM"),
        (ids[2], "2026-09-16", "AM"),
        (ids[2], "2026-09-16", "PM"),
        (ids[2], "2026-09-17", "AM"),
    ]
    by_id = {stop["id"]: stop for stop in preview["stops"]}
    assert by_id[ids[0]]["duration_half_days"] == 1
    assert by_id[ids[1]]["duration_half_days"] == 1
    assert by_id[ids[2]]["duration_half_days"] == 3
    assert (
        by_id[ids[0]]["planned_date"],
        by_id[ids[0]]["planned_start_period"],
        by_id[ids[0]]["planned_end_period"],
    ) == ("2026-09-15", "AM", "AM")
    assert (
        by_id[ids[1]]["planned_date"],
        by_id[ids[1]]["planned_start_period"],
    ) == ("2026-09-15", "PM")
    assert (
        by_id[ids[2]]["planned_date"],
        by_id[ids[2]]["planned_start_period"],
        by_id[ids[2]]["planned_end_date"],
        by_id[ids[2]]["planned_end_period"],
    ) == ("2026-09-16", "AM", "2026-09-17", "AM")

    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(plan, durations),
        ),
        200,
    )

    weekend = _create_plan(
        client,
        ctx,
        "Weekend slot contract",
        start_date="2026-09-18",
        end_date="2026-09-30",
    )
    weekend = _add_stop(client, ctx, weekend, "rayxion")
    weekend = _add_stop(client, ctx, weekend, "phile")
    weekend_ids = [stop["id"] for stop in weekend["stops"]]
    weekend_preview = _require(
        client.post(
            f"/api/review/trip-plans/{weekend['id']}/preview-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(
                weekend,
                {
                    weekend_ids[0]: {
                        "half_days": 1,
                        "preferred_period": "auto",
                        "locked": False,
                    },
                    weekend_ids[1]: {
                        "half_days": 3,
                        "preferred_period": "auto",
                        "locked": False,
                    },
                },
            ),
        ),
        200,
    )
    assert [(date, period) for _, date, period in _customer_slots(weekend_preview)] == [
        ("2026-09-18", "AM"),
        ("2026-09-18", "PM"),
        ("2026-09-21", "AM"),
        ("2026-09-21", "PM"),
    ]
    assert not {
        item["date"] for item in weekend_preview["schedule_items"]
    } & {"2026-09-19", "2026-09-20"}
    return {"plan": saved, "durations": durations}


def check_duration_and_lock_conflicts_are_zero_write(
    client: TestClient, ctx: dict, state: dict
) -> None:
    plan = state["plan"]
    ids = [stop["id"] for stop in plan["stops"]]
    both = _route_payload(plan, state["durations"])
    both["stop_stays"] = {stop_id: 1 for stop_id in ids}
    before = _snapshot()
    response = client.post(
        f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
        headers=ctx["headers"]["owner"],
        json=both,
    )
    assert response.status_code == 400, response.text
    assert _snapshot() == before

    locked_durations = {
        stop_id: {
            **state["durations"][stop_id],
            "preferred_period": next(
                item for item in plan["stops"] if item["id"] == stop_id
            )["planned_start_period"],
            "locked": True,
        }
        for stop_id in ids
    }
    locked = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(plan, locked_durations),
        ),
        200,
    )
    first = locked["stops"][0]
    assert bool(first["schedule_locked"]) is True

    preferred_conflict = {
        stop_id: dict(value) for stop_id, value in locked_durations.items()
    }
    preferred_conflict[first["id"]]["preferred_period"] = (
        "PM" if first["planned_start_period"] == "AM" else "AM"
    )
    # A preferred period that disagrees with the agreed one is reported, not
    # refused: the customer's time wins and the preference is what gives way.
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{locked['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(locked, preferred_conflict),
        ),
        200,
    )
    kinds = {
        risk["kind"] for risk in saved["itinerary_summary"].get("risks") or []
    }
    assert "booked_outside_preferred_period" in kinds, kinds
    kept = next(item for item in saved["stops"] if item["id"] == first["id"])
    assert kept["planned_start_period"] == first["planned_start_period"], (
        "the agreed period must survive a conflicting preference"
    )

    # Recording an agreed time no longer requires switching the route order to
    # manual first: the appointment is what decides where the visit sits, and
    # making the user change a mode before they can write down what a customer
    # told them was the wrong way round.
    automatic = _require(
        client.post(
            f"/api/review/trip-plans/{saved['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(
                saved,
                locked_durations,
                route_order_mode="auto",
                stop_order=None,
            ),
        ),
        200,
    )
    assert any(
        bool(stop["schedule_locked"]) for stop in automatic["stops"]
    ), "the agreed times must still be locked under automatic ordering"

    # A route that cannot fit inside the requested end date is still refused,
    # and still writes nothing.
    before = _snapshot()
    response = client.post(
        f"/api/review/trip-plans/{automatic['id']}/generate-itinerary",
        headers=ctx["headers"]["owner"],
        json=_route_payload(
            automatic,
            locked_durations,
            end_date="2026-09-15",
        ),
    )
    assert response.status_code == 400, response.text
    assert _snapshot() == before


def _briefing_url(plan_id: str, stop_id: str) -> str:
    return f"/api/review/trip-plans/{plan_id}/stops/{stop_id}/briefing"


def _full_briefing_payload(
    row_version,
    stop_row_version: int,
    ctx: dict,
    *,
    location: dict | None = None,
    confirmation_status: str = "confirmed",
) -> dict:
    return {
        "row_version": row_version,
        "stop_row_version": stop_row_version,
        "confirmation_status": confirmation_status,
        "timezone": "Europe/Paris",
        "location": location
        or {
            "use_customer_default": False,
            "name": "RAYXION Paris Office",
            "address": "99 Demo Avenue",
            "city": "Paris",
            "postal_code": "75001",
            "country": "France",
            "lat": 48.8566,
            "lng": 2.3522,
        },
        "customer_team": [
            {
                "name": "Frame Welding Team",
                "title": "SDI Manager",
                "phone": "+33-1-555-0200",
                "email": "sdi@example.test",
                "notes": "Prepare the frame welding sample",
                "sequence_no": 20,
            },
            {
                "name": "Yeo-hun Son",
                "title": "Engineer",
                "sequence_no": 10,
            },
        ],
        "contacts": [
            {
                "source_contact_id": ctx["contact"]["id"],
                "name": "Kim Sungkyu",
                "position": "",
                "email": "",
                "phone": "",
                "role": "Decision maker",
                "notes": "Primary meeting contact",
                "sequence_no": 20,
            },
            {
                "source_contact_id": None,
                "name": "Renshu Kim",
                "position": "Equipment Engineer",
                "email": "renshu@example.test",
                "phone": "+33-1-555-0300",
                "role": "Technical contact",
                "notes": "Temporary visit snapshot",
                "sequence_no": 10,
            },
        ],
        "participants": [
            {
                "user_id": ctx["ids"]["tech"],
                "display_name": "Client supplied text must be replaced",
                "role": "sales",
                "responsibility": "Demo and technical questions",
                "notes": "Bring the sample kit",
                "sequence_no": 1,
            }
        ],
        "channel_partner_companions": [
            {
                "company_name": "France Channel SAS",
                "name": "Claire Martin",
                "position": "Sales Director",
                "phone": "+33-1-555-0400",
                "email": "claire@channel.example.test",
                "role": "Meeting coordinator",
                "notes": "Coordinate the Paris visit",
                "sequence_no": 20,
            },
            {
                "company_name": "Euro Partner GmbH",
                "name": "Anna Becker",
                "position": "Channel Manager",
                "phone": "+49-30-555-0500",
                "email": "anna@partner.example.test",
                "role": "Local companion",
                "notes": "Join the customer meeting",
                "sequence_no": 10,
            },
        ],
        "equipment": [
            {
                "kind": "po",
                "model": "FC 500W",
                "specification": "Air cooled",
                "quantity": "1 set",
                "owner_team": "PO team",
                "notes": "Confirm PO configuration",
                "sequence_no": 20,
            },
            {
                "kind": "demo",
                "model": "CW 2000W",
                "specification": "300μm",
                "quantity": "1 set",
                "owner_team": "Demo team",
                "notes": "Bring demo laser",
                "sequence_no": 10,
            },
        ],
        "agenda_items": [
            {
                "topic": "Review application and support plan",
                "owner": "Batch 4 Sales",
                "preparation": "Collect application requirements",
                "expected_outcome": "Agree next technical action",
                "sequence_no": 20,
            },
            {
                "topic": "Introduce JPT and RAYXION",
                "owner": "Batch 4 Leader",
                "preparation": "Prepare company overview",
                "expected_outcome": "Shared understanding",
                "sequence_no": 10,
            },
        ],
    }


def _writable_briefing(record: dict) -> dict:
    return {
        key: record[key]
        for key in (
            "row_version",
            "stop_row_version",
            "confirmation_status",
            "timezone",
            "location",
            "customer_team",
            "contacts",
            "participants",
            "channel_partner_companions",
            "equipment",
            "agenda_items",
        )
    }


def _assert_sequences(record: dict) -> None:
    for key in (
        "customer_team",
        "contacts",
        "participants",
        "channel_partner_companions",
        "equipment",
        "agenda_items",
    ):
        assert [item["sequence_no"] for item in record[key]] == list(
            range(1, len(record[key]) + 1)
        )


def check_briefing_crud_permissions_cas_and_export(
    client: TestClient, ctx: dict
) -> None:
    plan = _add_stop(
        client,
        ctx,
        _create_plan(client, ctx, "Detailed customer visit export"),
        "rayxion",
    )
    stop = plan["stops"][0]
    url = _briefing_url(plan["id"], stop["id"])
    initial = _require(client.get(url, headers=ctx["headers"]["owner"]), 200)
    assert initial["row_version"] is None
    assert initial["stop_row_version"] == stop["row_version"]
    assert initial["confirmation_status"] == "unconfirmed"
    assert initial["customer_team"] == initial["contacts"] == []
    assert initial["channel_partner_companions"] == []
    assert {item["id"] for item in initial["available_contacts"]} == {
        ctx["contact"]["id"]
    }
    available_users = {
        item["user_id"] for item in initial["available_participants"]
    }
    assert ctx["ids"]["tech"] in available_users
    assert ctx["ids"]["inactive"] not in available_users
    assert initial["suggestions"], "Lead suggestions must be visible but not auto-saved"

    assert client.get(url, headers=ctx["headers"]["other"]).status_code == 404
    assert client.get(url, headers=ctx["headers"]["tech"]).status_code == 403
    assert client.get(url, headers=ctx["headers"]["leader"]).status_code == 200

    first = _require(
        client.put(
            url,
            headers=ctx["headers"]["owner"],
            json=_full_briefing_payload(None, initial["stop_row_version"], ctx),
        ),
        200,
    )
    assert first["row_version"] == 1
    assert first["confirmation_status"] == "needs_reconfirmation"
    _assert_sequences(first)
    assert first["customer_team"][0]["name"] == "Yeo-hun Son"
    assert first["contacts"][0]["name"] == "Renshu Kim"
    source_contact = next(
        item for item in first["contacts"] if item["source_contact_id"]
    )
    assert source_contact["name"] == "Kim Sungkyu"
    assert first["participants"][0]["display_name"] == "Aydan Tech"
    assert first["participants"][0]["role"] == "tech"
    assert first["channel_partner_companions"][0]["name"] == "Anna Becker"
    assert first["equipment"][0]["kind"] == "demo"
    assert first["agenda_items"][0]["topic"] == "Introduce JPT and RAYXION"

    # The location is now saved.  A second explicit confirmation does not
    # change route identity and therefore becomes the stop's single truth.
    confirm_payload = _writable_briefing(first)
    confirm_payload["confirmation_status"] = "confirmed"
    second = _require(
        client.put(url, headers=ctx["headers"]["owner"], json=confirm_payload),
        200,
    )
    assert second["confirmation_status"] == "confirmed"
    plan_after_confirmation = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    assert plan_after_confirmation["stops"][0]["confirmation_status"] == "confirmed"

    for bad_payload in (
        {
            **_writable_briefing(second),
            "contacts": [
                {
                    "source_contact_id": ctx["foreign_contact"]["id"],
                    "name": "Foreign Person",
                    "sequence_no": 1,
                }
            ],
        },
        {
            **_writable_briefing(second),
            "participants": [
                {
                    "user_id": ctx["ids"]["inactive"],
                    "responsibility": "Must be rejected",
                    "sequence_no": 1,
                }
            ],
        },
        {
            **_writable_briefing(second),
            "channel_partner_companions": [
                {"name": "   ", "sequence_no": 1}
            ],
        },
    ):
        before = _snapshot()
        response = client.put(
            url, headers=ctx["headers"]["owner"], json=bad_payload
        )
        assert response.status_code == 400, response.text
        assert _snapshot() == before

    stale_briefing = _writable_briefing(second)
    stale_briefing["row_version"] = first["row_version"]
    before = _snapshot()
    response = client.put(
        url, headers=ctx["headers"]["owner"], json=stale_briefing
    )
    assert response.status_code == 409, response.text
    assert _snapshot() == before

    stale_stop = _writable_briefing(second)
    stale_stop["stop_row_version"] = first["stop_row_version"]
    before = _snapshot()
    response = client.put(url, headers=ctx["headers"]["owner"], json=stale_stop)
    assert response.status_code == 409, response.text
    assert _snapshot() == before

    missing_briefing_cas = _writable_briefing(second)
    missing_briefing_cas["row_version"] = None
    before = _snapshot()
    response = client.put(
        url, headers=ctx["headers"]["owner"], json=missing_briefing_cas
    )
    assert response.status_code == 409, response.text
    assert _snapshot() == before

    fresh_plan = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    stop_id = fresh_plan["stops"][0]["id"]
    saved_route = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(
                fresh_plan,
                {
                    stop_id: {
                        "half_days": 1,
                        "preferred_period": "AM",
                        "locked": False,
                    }
                },
            ),
        ),
        200,
    )
    markdown = client.get(
        f"/api/review/trip-plans/{plan['id']}/export.md",
        headers=ctx["headers"]["owner"],
    )
    assert markdown.status_code == 200, markdown.text
    for value in (
        "Company Name",
        "Full Address",
        "Recommended Visit Date",
        "Demo Laser",
        "PO Laser",
        "客户人员 / Customer Personnel",
        "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)",
        "Visiting topic",
        "RAYXION (레이시온)",
        "99 Demo Avenue",
        "CW 2000W",
        "FC 500W",
        "Yeo-hun Son",
        "Kim Sungkyu",
        "Anna Becker",
        "Introduce JPT and RAYXION",
        "Travel half-days",
    ):
        assert value in markdown.text, value
    assert "Aydan Tech" not in markdown.text

    csv_response = client.get(
        f"/api/review/trip-plans/{plan['id']}/export.csv",
        headers=ctx["headers"]["owner"],
    )
    assert csv_response.status_code == 200
    reader = csv.DictReader(io.StringIO(csv_response.text))
    assert reader.fieldnames
    assert reader.fieldnames[0] == "record_type"
    assert all(header in reader.fieldnames for header in EXAMPLE_HEADERS)
    assert {
        "duration_half_days",
        "confirmation_status",
        "leg_travel_half_days",
        "plan_title",
    } <= set(reader.fieldnames)
    rows = list(reader)
    customer_row = next(row for row in rows if row["record_type"] == "customer_stop")
    assert customer_row["Company Name"] == "RAYXION (레이시온)"
    assert "99 Demo Avenue" in customer_row["Full Address"]
    assert "2026-09-15" in customer_row["Recommended Visit Date"]
    assert "AM" in customer_row["Recommended Visit Date"]
    assert "CW 2000W" in customer_row["Demo Laser"]
    assert "FC 500W" in customer_row["PO Laser"]
    customer_personnel = customer_row["客户人员 / Customer Personnel"]
    channel_companions = customer_row[
        "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)"
    ]
    assert "Yeo-hun Son" in customer_personnel
    assert "Kim Sungkyu" in customer_personnel
    assert "Anna Becker" not in customer_personnel
    assert "Anna Becker" in channel_companions
    assert "Kim Sungkyu" not in channel_companions
    assert "Aydan Tech" not in customer_personnel + channel_companions
    assert "Introduce JPT and RAYXION" in customer_row["Visiting topic"]
    leg_rows = [row for row in rows if row["record_type"] == "leg"]
    assert len(leg_rows) == len(saved_route["legs"])
    assert leg_rows[-1]["leg_key"].endswith(">destination")
    assert leg_rows[-1]["leg_to"] == saved_route["destination_name"]

    latest = _require(client.get(url, headers=ctx["headers"]["owner"]), 200)
    cleared_payload = {
        "row_version": latest["row_version"],
        "stop_row_version": latest["stop_row_version"],
        "confirmation_status": "tentative",
        "timezone": "",
        "location": {"use_customer_default": True},
        "customer_team": [],
        "contacts": [],
        "participants": [],
        "channel_partner_companions": [],
        "equipment": [],
        "agenda_items": [],
    }
    cleared = _require(
        client.put(
            url,
            headers=ctx["headers"]["owner"],
            json=cleared_payload,
        ),
        200,
    )
    assert cleared["timezone"] is None
    for key in (
        "customer_team",
        "contacts",
        "participants",
        "channel_partner_companions",
        "equipment",
        "agenda_items",
    ):
        assert cleared[key] == [], key


def _save_custom_visit_location(
    client: TestClient,
    ctx: dict,
    plan_id: str,
    stop_id: str,
    location: dict,
) -> dict:
    """Save, then explicitly confirm, one user-entered visit location."""
    url = _briefing_url(plan_id, stop_id)
    current = _require(client.get(url, headers=ctx["headers"]["owner"]), 200)
    saved = _require(
        client.put(
            url,
            headers=ctx["headers"]["owner"],
            json=_full_briefing_payload(
                current["row_version"],
                current["stop_row_version"],
                ctx,
                location=location,
            ),
        ),
        200,
    )
    confirm = _writable_briefing(saved)
    confirm["confirmation_status"] = "confirmed"
    return _require(
        client.put(url, headers=ctx["headers"]["owner"], json=confirm),
        200,
    )


def check_visit_location_route_timeline_and_invalidation(
    client: TestClient, ctx: dict
) -> None:
    """Exercise two visits to one customer through the saved user workflow."""
    plan = _create_plan(client, ctx, "Two customer locations and rest stop")
    plan = _add_stop(client, ctx, plan, "rayxion")
    plan = _add_stop(client, ctx, plan, "rayxion", allow_duplicate=True)
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/free-stops",
            headers=ctx["headers"]["owner"],
            json={
                "category": "hotel",
                "location_name": "Lyon Rest Hotel",
                "address": "10 Rest Avenue",
                "city": "Lyon",
                "country": "France",
                "lat": 45.7640,
                "lng": 4.8357,
                "duration_half_days": 1,
                "visit_purpose": "Rest and prepare for the next visit",
            },
        ),
        200,
    )
    customer_stops = [
        stop for stop in plan["stops"] if stop["stop_kind"] == "customer"
    ]
    free_stop = next(stop for stop in plan["stops"] if stop["stop_kind"] == "free")
    first_id, second_id = (stop["id"] for stop in customer_stops)

    first_briefing = _save_custom_visit_location(
        client,
        ctx,
        plan["id"],
        first_id,
        {
            "use_customer_default": False,
            "name": "RAYXION Berlin Office",
            "address": "1 Berlin Visit Road",
            "city": "Berlin",
            "postal_code": "10115",
            "country": "Germany",
            "lat": 52.5200,
            "lng": 13.4050,
        },
    )
    _save_custom_visit_location(
        client,
        ctx,
        plan["id"],
        second_id,
        {
            "use_customer_default": False,
            "name": "RAYXION Munich Lab",
            "address": "2 Munich Visit Road",
            "city": "Munich",
            "postal_code": "80331",
            "country": "Germany",
            "lat": 48.1351,
            "lng": 11.5820,
        },
    )

    fresh = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    reordered = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops/reorder",
            headers=ctx["headers"]["owner"],
            json={
                "row_version": fresh["row_version"],
                "stop_ids": [first_id, free_stop["id"], second_id],
            },
        ),
        200,
    )
    durations = {
        stop["id"]: {
            "half_days": 1,
            "preferred_period": "auto",
            "locked": False,
        }
        for stop in reordered["stops"]
    }
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"]["owner"],
            json=_route_payload(reordered, durations),
        ),
        200,
    )

    stops_by_id = {stop["id"]: stop for stop in saved["stops"]}
    assert stops_by_id[first_id]["visit_location"]["source"] == "visit_briefing"
    assert stops_by_id[second_id]["visit_location"]["source"] == "visit_briefing"
    assert (
        stops_by_id[first_id]["visit_location"]["lat"],
        stops_by_id[first_id]["visit_location"]["lng"],
    ) == (52.5200, 13.4050)
    assert (
        stops_by_id[second_id]["visit_location"]["lat"],
        stops_by_id[second_id]["visit_location"]["lng"],
    ) == (48.1351, 11.5820)
    assert any(float(leg["distance_km"]) > 0 for leg in saved["legs"])

    timeline = saved["schedule_items"]
    assert {item["item_type"] for item in timeline} == {"customer", "free", "leg"}
    assert [item["schedule_index"] for item in timeline] == list(
        range(1, len(timeline) + 1)
    )
    assert [(item["date"], item["period"]) for item in timeline] == sorted(
        ((item["date"], item["period"]) for item in timeline),
        key=lambda item: (item[0], 0 if item[1] == "AM" else 1),
    )
    for item in timeline:
        assert {
            "slot_key",
            "date",
            "period",
            "schedule_index",
            "item_type",
            "source_id",
            "sequence_no",
            "title",
            "half_day_index",
            "half_day_count",
            "confirmation_status",
        } <= set(item)
        if item["item_type"] == "leg":
            assert item["confirmation_status"] is None
        else:
            assert item["confirmation_status"] in {
                "unconfirmed",
                "tentative",
                "confirmed",
                "needs_reconfirmation",
                "cancelled",
            }

    execution_types = set()
    for visit_date in sorted({item["date"] for item in timeline}):
        execution = _require(
            client.get(
                f"/api/review/trip-plans/{plan['id']}/execution",
                headers=ctx["headers"]["owner"],
                params={"date": visit_date},
            ),
            200,
        )
        assert execution["selected_date"] == visit_date
        assert all(
            item["date"] == visit_date for item in execution["schedule_items"]
        )
        execution_types.update(
            item["item_type"] for item in execution["schedule_items"]
        )
    assert execution_types == {"customer", "free", "leg"}

    latest = _require(
        client.get(
            _briefing_url(plan["id"], first_id),
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    details_only = _writable_briefing(latest)
    details_only["timezone"] = "Europe/Berlin"
    _require(
        client.put(
            _briefing_url(plan["id"], first_id),
            headers=ctx["headers"]["owner"],
            json=details_only,
        ),
        200,
    )
    route_kept = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    assert len(route_kept["legs"]) == len(saved["legs"])
    assert route_kept["schedule_items"]

    latest = _require(
        client.get(
            _briefing_url(plan["id"], first_id),
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    invalid = _writable_briefing(latest)
    invalid["location"] = {
        "use_customer_default": False,
        "name": "Incomplete visit location",
        "address": "Missing coordinates",
        "city": "Berlin",
        "country": "Germany",
    }
    before = _snapshot()
    response = client.put(
        _briefing_url(plan["id"], first_id),
        headers=ctx["headers"]["owner"],
        json=invalid,
    )
    assert response.status_code == 400, response.text
    assert _snapshot() == before

    changed = _writable_briefing(latest)
    changed["confirmation_status"] = "confirmed"
    changed["location"] = {
        "use_customer_default": False,
        "name": "RAYXION Hamburg Office",
        "address": "3 Hamburg Visit Road",
        "city": "Hamburg",
        "postal_code": "20095",
        "country": "Germany",
        "lat": 53.5511,
        "lng": 9.9937,
    }
    changed_result = _require(
        client.put(
            _briefing_url(plan["id"], first_id),
            headers=ctx["headers"]["owner"],
            json=changed,
        ),
        200,
    )
    assert changed_result["confirmation_status"] == "needs_reconfirmation"
    stale = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    assert stale["itinerary_summary"]["stale"] is True
    assert stale["itinerary_summary"]["reason"] == "visit_location_changed"
    assert stale["legs"] == []
    assert stale["schedule_items"] == []
    assert next(stop for stop in stale["stops"] if stop["id"] == first_id)[
        "confirmation_status"
    ] == "needs_reconfirmation"


def run() -> None:
    try:
        check_schema5_to_current_upgrade()
        close_db()
        with TestClient(app) as client:
            ctx = _seed(client)
            schedule_state = check_half_day_schedule_weekends_and_legacy_exclusion(
                client, ctx
            )
            check_duration_and_lock_conflicts_are_zero_write(
                client, ctx, schedule_state
            )
            check_briefing_crud_permissions_cas_and_export(client, ctx)
            check_visit_location_route_timeline_and_invalidation(client, ctx)
        print(
            "PASS: Batch 4 schema migration, half-day schedule, visit briefing, "
            "timeline, export, and route invalidation"
        )
    finally:
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
