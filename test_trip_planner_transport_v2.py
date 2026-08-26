"""Batch 2 regressions for Trip Planner transport policies and persisted legs.

Run with the native project Python. All application data lives in temporary
directories; the installed desktop profile is never opened.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_trip_transport_v2_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.config import init_settings  # noqa: E402
from backend.repositories import APP_SCHEMA_VERSION, close_db  # noqa: E402
from backend.repositories.base import APP_SCHEMA_MIGRATIONS, get_db  # noqa: E402
from backend.services.review_service import ReviewService  # noqa: E402
from backend.startup_upgrade import initialize_database_safely  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


NEW_PLAN_COLUMNS = (
    "route_order_mode",
    "transport_mode_priority",
    "departure_window_start",
    "departure_window_end",
    "return_window_start",
    "return_window_end",
)


def _require(response, status_code: int):
    assert response.status_code == status_code, response.text
    return response.json()


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "trip-v2-leader", "password": "TripV2Leader2026"},
    )
    token = _require(response, 200)["token"]
    return {"Authorization": f"Bearer {token}"}


def _logical_snapshot() -> dict:
    conn = get_db()
    conn.commit()
    tables = (
        "trip_plans",
        "trip_plan_stops",
        "trip_plan_free_stops",
        "trip_plan_legs",
    )
    return {
        table: [
            tuple(row)
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
        ]
        for table in tables
    }


def _create_customer(client: TestClient, headers: dict, spec: tuple) -> tuple[str, str]:
    name, country, city, lat, lng, owner_id = spec
    customer = _require(
        client.post(
            "/api/customers",
            headers=headers,
            json={
                "display_name": name,
                "country": country,
                "city": city,
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
                "title": f"{name} visit",
                "source_channel": "Referral",
                "sales_stage": "Following",
            },
        ),
        200,
    )
    return customer["id"], lead["id"]


def _seed_api(client: TestClient) -> dict:
    owner_id = upsert_account(
        "trip-v2-leader",
        "TripV2Leader2026",
        "Trip V2 Leader",
        "leader",
        None,
    )
    headers = _headers(client)
    specs = {
        "paris": ("V2 Paris", "France", "Paris", 48.8566, 2.3522, owner_id),
        "munich": ("V2 Munich", "Germany", "Munich", 48.1351, 11.5820, owner_id),
        "rome": ("V2 Rome", "Italy", "Rome", 41.9028, 12.4964, owner_id),
    }
    records = {key: _create_customer(client, headers, value) for key, value in specs.items()}
    return {"headers": headers, "owner_id": owner_id, "records": records}


def _create_plan(client: TestClient, ctx: dict, *, title: str = "Europe September") -> dict:
    return _require(
        client.post(
            "/api/review/trip-plans",
            headers=ctx["headers"],
            json={
                "title": title,
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "region": "EU",
                "origin_name": "Shanghai Pudong",
                "origin_lat": 31.1443,
                "origin_lng": 121.8083,
                "destination_name": "Shanghai Pudong",
                "destination_lat": 31.1443,
                "destination_lng": 121.8083,
                "route_order_mode": "manual",
                "transport_mode_priority": ["flight", "ground_public", "drive"],
                "departure_window_start": "2026-09-14T18:00",
                "departure_window_end": "2026-09-15T12:00",
                "return_window_start": "2026-09-29T18:00",
                "return_window_end": "2026-09-30T23:00",
                "avoid_weekends": True,
            },
        ),
        200,
    )


def _add_stops(client: TestClient, ctx: dict, plan: dict) -> dict:
    for key in ("paris", "munich", "rome"):
        plan = _require(
            client.post(
                f"/api/review/trip-plans/{plan['id']}/stops",
                headers=ctx["headers"],
                json={"lead_id": ctx["records"][key][1], "stay_days": 1},
            ),
            200,
        )
    return plan


def _base_payload(plan: dict) -> dict:
    return {
        "row_version": plan["row_version"],
        "start_date": "2026-09-15",
        "end_date": "2026-09-30",
        "origin_name": "Shanghai Pudong",
        "origin_lat": 31.1443,
        "origin_lng": 121.8083,
        "destination_name": "Shanghai Pudong",
        "destination_lat": 31.1443,
        "destination_lng": 121.8083,
        "route_order_mode": "manual",
        "transport_mode_priority": ["flight", "ground_public", "drive"],
        "departure_window_start": "2026-09-14T18:00",
        "departure_window_end": "2026-09-15T12:00",
        # Reserve enough time for the intercontinental final leg now that the
        # half-day scheduler enforces the return window rather than treating it
        # as display-only metadata.
        "return_window_start": "2026-09-28T18:00",
        "return_window_end": "2026-09-30T23:00",
        "stop_order": [item["id"] for item in plan["stops"]],
        "stop_stays": {item["id"]: 1 for item in plan["stops"]},
    }


def check_preview_manual_order_and_windows_are_read_only(client: TestClient, ctx: dict) -> dict:
    plan = _add_stops(client, ctx, _create_plan(client, ctx))
    stop_ids = [item["id"] for item in plan["stops"]]
    payload = _base_payload(plan)
    payload["stop_order"] = list(reversed(stop_ids))
    before = _logical_snapshot()
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )
    assert preview["itinerary_preview"] is True
    assert [item["id"] for item in preview["stops"]] == list(reversed(stop_ids))
    assert preview["route_order_mode"] == "manual"
    assert preview["transport_mode_priority"] == ["flight", "ground_public", "drive"]
    assert preview["departure_window_start"] == "2026-09-14T18:00"
    assert preview["return_window_end"] == "2026-09-30T23:00"
    assert len(preview["legs"]) == 4
    assert preview["legs"][0]["leg_key"] == f"origin>{stop_ids[-1]}"
    assert preview["legs"][-1]["leg_key"] == f"{stop_ids[0]}>destination"
    assert all(leg["selected_mode"] in {"flight", "drive", "ground_public"} for leg in preview["legs"])
    assert _logical_snapshot() == before, "preview must not create or update any leg/stop/plan row"
    return {"plan": plan, "payload": payload, "preview": preview}


def check_locked_other_leg_and_atomic_generation(client: TestClient, ctx: dict, state: dict) -> dict:
    plan = state["plan"]
    payload = state["payload"]
    # The half-day engine now enforces the return window. Leave enough slots
    # for the intercontinental final leg instead of relying on the legacy
    # date-only engine that ignored return_window_start.
    payload["return_window_start"] = "2026-09-28T18:00"
    target = state["preview"]["legs"][1]
    payload["leg_overrides"] = {
        target["leg_key"]: {
            "selected_mode": "other",
            "mode_locked": True,
            "manual_distance_km": 321.0,
            "manual_time_hours": 5.5,
            "manual_travel_days": 1,
            "notes": "Confirmed private transfer",
        }
    }
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )
    assert [item["id"] for item in saved["stops"]] == payload["stop_order"]
    assert len(saved["legs"]) == 4
    locked = next(item for item in saved["legs"] if item["leg_key"] == target["leg_key"])
    assert locked["selected_mode"] == "other" and locked["mode_locked"] is True
    assert locked["distance_km"] == 321.0 and locked["time_hours"] == 5.5
    assert locked["travel_days"] == 1 and locked["notes"] == "Confirmed private transfer"
    active = get_db().execute(
        "SELECT COUNT(*) AS count FROM trip_plan_legs WHERE plan_id = ? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()["count"]
    assert active == 4

    # No override in the next preview: a persisted locked same-adjacency leg must survive.
    followup_payload = _base_payload(saved)
    followup_payload["stop_order"] = [item["id"] for item in saved["stops"]]
    followup_payload["stop_stays"] = {
        item["id"]: (2 if index == 0 else 1)
        for index, item in enumerate(saved["stops"])
    }
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=followup_payload,
        ),
        200,
    )
    retained = next(item for item in preview["legs"] if item["leg_key"] == target["leg_key"])
    assert retained["selected_mode"] == "other" and retained["mode_locked"] is True
    return saved


def check_invalid_inputs_and_overrun_are_atomic(client: TestClient, ctx: dict, saved: dict) -> None:
    payload = _base_payload(saved)
    target_key = saved["legs"][0]["leg_key"]
    payload["leg_overrides"] = {
        target_key: {"selected_mode": "other", "mode_locked": True}
    }
    before = _logical_snapshot()
    rejected = client.post(
        f"/api/review/trip-plans/{saved['id']}/generate-itinerary",
        headers=ctx["headers"],
        json=payload,
    )
    assert rejected.status_code == 400, rejected.text
    assert "other" in rejected.text.lower() and ("time" in rejected.text.lower() or "day" in rejected.text.lower())
    assert _logical_snapshot() == before

    invalid_order = {**_base_payload(saved), "stop_order": [saved["stops"][0]["id"]]}
    before = _logical_snapshot()
    rejected = client.post(
        f"/api/review/trip-plans/{saved['id']}/generate-itinerary",
        headers=ctx["headers"],
        json=invalid_order,
    )
    assert rejected.status_code == 400, rejected.text
    assert _logical_snapshot() == before

    duplicate_priority = client.patch(
        f"/api/review/trip-plans/{saved['id']}",
        headers=ctx["headers"],
        json={
            "row_version": saved["row_version"],
            "transport_mode_priority": ["drive", "drive"],
        },
    )
    assert duplicate_priority.status_code in {400, 422}, duplicate_priority.text

    before = _logical_snapshot()
    mixed_timezone = client.patch(
        f"/api/review/trip-plans/{saved['id']}",
        headers=ctx["headers"],
        json={
            "row_version": saved["row_version"],
            "departure_window_start": "2026-09-14T18:00+08:00",
            "departure_window_end": "2026-09-15T12:00",
        },
    )
    assert mixed_timezone.status_code == 400, mixed_timezone.text
    assert _logical_snapshot() == before


def check_reordered_route_replaces_obsolete_legs(client: TestClient, ctx: dict, saved: dict) -> None:
    old_keys = {item["leg_key"] for item in saved["legs"]}
    payload = _base_payload(saved)
    payload["return_window_start"] = "2026-09-28T18:00"
    payload["stop_order"] = list(reversed([item["id"] for item in saved["stops"]]))
    regenerated = _require(
        client.post(
            f"/api/review/trip-plans/{saved['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )
    new_keys = {item["leg_key"] for item in regenerated["legs"]}
    assert len(new_keys) == 4
    assert new_keys != old_keys
    rows = get_db().execute(
        "SELECT leg_key, archived_at FROM trip_plan_legs WHERE plan_id = ?",
        (saved["id"],),
    ).fetchall()
    assert {row["leg_key"] for row in rows if row["archived_at"] is None} == new_keys
    assert any(row["archived_at"] is not None for row in rows if row["leg_key"] in old_keys - new_keys)


def check_stale_crud_archives_current_legs(client: TestClient, ctx: dict) -> None:
    plan = _add_stops(client, ctx, _create_plan(client, ctx, title="Stale leg lifecycle"))
    payload = _base_payload(plan)
    retained_key = f"origin>{plan['stops'][0]['id']}"
    payload["leg_overrides"] = {
        retained_key: {
            "selected_mode": "flight",
            "mode_locked": True,
            "notes": "Keep this unchanged adjacency",
        }
    }
    generated = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )
    assert len(generated["legs"]) == 4

    removed_stop = generated["stops"][1]
    removed = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops/{removed_stop['id']}/archive",
            headers=ctx["headers"],
            json={"row_version": removed_stop["row_version"]},
        ),
        200,
    )
    assert len(removed["stops"]) == 2 and removed["legs"] == []
    assert removed["itinerary_summary"]["stale"] is True
    current = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]
        ),
        200,
    )
    assert len(current["stops"]) == 2 and current["legs"] == []
    conn = get_db()
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0

    before = _logical_snapshot()
    preview_three = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=_base_payload(removed),
        ),
        200,
    )
    assert len(preview_three["legs"]) == 3
    retained = next(item for item in preview_three["legs"] if item["leg_key"] == retained_key)
    assert retained["mode_locked"] is True and retained["selected_mode"] == "flight"
    assert _logical_snapshot() == before

    regenerated_three = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=_base_payload(removed),
        ),
        200,
    )
    assert len(regenerated_three["legs"]) == 3
    added = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops",
            headers=ctx["headers"],
            json={"lead_id": removed_stop["lead_id"], "stay_days": 1},
        ),
        200,
    )
    assert len(added["stops"]) == 3 and added["legs"] == []
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0
    preview_four = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=_base_payload(added),
        ),
        200,
    )
    assert len(preview_four["legs"]) == 4

    regenerated_four = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=_base_payload(added),
        ),
        200,
    )
    reversed_ids = list(reversed([item["id"] for item in regenerated_four["stops"]]))
    reordered = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops/reorder",
            headers=ctx["headers"],
            json={"stop_ids": reversed_ids, "row_version": regenerated_four["row_version"]},
        ),
        200,
    )
    assert reordered["route_order_mode"] == "manual"
    assert [item["id"] for item in reordered["stops"]] == reversed_ids
    assert reordered["legs"] == []
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0
    before = _logical_snapshot()
    preview_reordered = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=_base_payload(reordered),
        ),
        200,
    )
    assert len(preview_reordered["legs"]) == 4
    assert _logical_snapshot() == before


def check_auto_route_priority_and_obsolete_overrides(client: TestClient, ctx: dict) -> None:
    plan = _add_stops(client, ctx, _create_plan(client, ctx, title="Auto route contract"))
    locked_key = f"origin>{plan['stops'][0]['id']}"
    payload = _base_payload(plan)
    payload["leg_overrides"] = {
        locked_key: {"selected_mode": "flight", "mode_locked": True}
    }
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )

    auto_payload = _base_payload(saved)
    auto_payload.pop("stop_order")
    auto_payload.update(
        {
            "route_order_mode": "auto",
            "transport_mode_priority": ["drive"],
            "origin_name": "Rome",
            "origin_lat": 41.9028,
            "origin_lng": 12.4964,
            "leg_overrides": {
                locked_key: {"selected_mode": "flight", "mode_locked": True}
            },
        }
    )
    calls = []
    original = ReviewService._order_route_stops

    def tracked(self, origin, destination, stops, priority):
        calls.append(tuple(priority))
        return original(self, origin, destination, stops, priority)

    before = _logical_snapshot()
    ReviewService._order_route_stops = tracked
    try:
        preview = _require(
            client.post(
                f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
                headers=ctx["headers"],
                json=auto_payload,
            ),
            200,
        )
    finally:
        ReviewService._order_route_stops = original
    assert calls == [("drive",)]
    assert preview["route_order_mode"] == "auto"
    assert locked_key not in {item["leg_key"] for item in preview["legs"]}
    assert any(
        "obsolete leg overrides" in warning.lower()
        for warning in preview["itinerary_summary"]["warnings"]
    )
    assert _logical_snapshot() == before

    strict_manual = {**auto_payload, "route_order_mode": "manual"}
    strict_manual["stop_order"] = [item["id"] for item in preview["stops"]]
    rejected = client.post(
        f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
        headers=ctx["headers"],
        json=strict_manual,
    )
    assert rejected.status_code == 400 and "unknown leg override" in rejected.text.lower()

    service = ReviewService.__new__(ReviewService)
    origin = {"lat": 0.0, "lng": 0.0, "label": "Origin"}
    destination = {"lat": -60.0, "lng": -80.0, "label": "Destination"}
    synthetic = [
        ({"id": "a"}, {"lat": -55.0, "lng": -20.0, "label": "A"}),
        ({"id": "b"}, {"lat": -35.0, "lng": 40.0, "label": "B"}),
    ]
    drive_order = [
        item[0]["id"]
        for item in service._order_route_stops(origin, destination, synthetic, ["drive"])
    ]
    flight_order = [
        item[0]["id"]
        for item in service._order_route_stops(origin, destination, synthetic, ["flight"])
    ]
    assert drive_order == ["a", "b"] and flight_order == ["b", "a"]


def check_legacy_travel_mode_compatibility(client: TestClient, ctx: dict) -> None:
    legacy = _require(
        client.post(
            "/api/review/trip-plans",
            headers=ctx["headers"],
            json={
                "title": "Legacy single-mode plan",
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "origin_name": "Paris",
                "origin_lat": 48.8566,
                "origin_lng": 2.3522,
                "destination_name": "Munich",
                "destination_lat": 48.1351,
                "destination_lng": 11.582,
                "travel_mode": "drive",
            },
        ),
        200,
    )
    legacy = _require(
        client.post(
            f"/api/review/trip-plans/{legacy['id']}/stops",
            headers=ctx["headers"],
            json={"lead_id": ctx["records"]["munich"][1]},
        ),
        200,
    )
    generated = _require(
        client.post(
            f"/api/review/trip-plans/{legacy['id']}/generate-itinerary",
            headers=ctx["headers"],
            json={"row_version": legacy["row_version"], "travel_mode": "drive"},
        ),
        200,
    )
    assert generated["travel_mode"] == "drive"
    assert generated["transport_mode_priority"] == ["drive"]
    assert generated["legs"] and all(item["selected_mode"] == "drive" for item in generated["legs"])


def check_reassigned_plan_revokes_creator_access(client: TestClient, ctx: dict) -> None:
    sales_one_id = upsert_account(
        "trip-v2-sales-one", "TripV2SalesOne2026", "Trip V2 Sales One", "sales", "EU"
    )
    sales_two_id = upsert_account(
        "trip-v2-sales-two", "TripV2SalesTwo2026", "Trip V2 Sales Two", "sales", "EU"
    )

    def login(username: str, password: str) -> dict[str, str]:
        token = _require(
            client.post("/api/auth/login", json={"username": username, "password": password}),
            200,
        )["token"]
        return {"Authorization": f"Bearer {token}"}

    sales_one_headers = login("trip-v2-sales-one", "TripV2SalesOne2026")
    sales_two_headers = login("trip-v2-sales-two", "TripV2SalesTwo2026")
    plan = _require(
        client.post(
            "/api/review/trip-plans",
            headers=sales_one_headers,
            json={"title": "Reassigned sales plan", "start_date": "2026-09-15"},
        ),
        200,
    )
    assert plan["owner_id"] == sales_one_id
    reassigned = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"],
            json={"owner_id": sales_two_id, "row_version": plan["row_version"]},
        ),
        200,
    )
    assert reassigned["owner_id"] == sales_two_id
    assert plan["id"] not in {
        item["id"] for item in _require(
            client.get("/api/review/trip-plans", headers=sales_one_headers), 200
        )
    }
    assert plan["id"] in {
        item["id"] for item in _require(
            client.get("/api/review/trip-plans", headers=sales_two_headers), 200
        )
    }
    for path in (
        f"/api/review/trip-plans/{plan['id']}",
        f"/api/review/trip-plans/{plan['id']}/export/markdown",
    ):
        assert client.get(path, headers=sales_one_headers).status_code == 404
    assert client.patch(
        f"/api/review/trip-plans/{plan['id']}",
        headers=sales_one_headers,
        json={"description": "must not be accepted", "row_version": reassigned["row_version"]},
    ).status_code == 404


def check_schema3_to_current_upgrade() -> None:
    assert APP_SCHEMA_VERSION == 8
    with tempfile.TemporaryDirectory(prefix="jpt_trip_schema3_to_current_") as temp:
        data_dir = Path(temp) / "data"
        data_dir.mkdir()
        db_path = data_dir / "database.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
            conn.execute("DROP TABLE IF EXISTS trip_visit_briefings")
            conn.execute("DROP TABLE IF EXISTS trip_plan_legs")
            conn.execute("DROP TABLE IF EXISTS trip_plan_free_stops")
            stop_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(trip_plan_stops)")
            }
            for column in (
                "duration_half_days", "preferred_period", "planned_start_period",
                "planned_end_period", "schedule_locked", "confirmation_status",
            ):
                if column in stop_columns:
                    conn.execute(f"ALTER TABLE trip_plan_stops DROP COLUMN {column}")
            existing = {row[1] for row in conn.execute("PRAGMA table_info(trip_plans)")}
            for column in NEW_PLAN_COLUMNS:
                if column in existing:
                    conn.execute(f"ALTER TABLE trip_plans DROP COLUMN {column}")
            conn.executemany(
                "INSERT INTO app_schema_migrations(version, name, app_version, applied_at) VALUES (?, ?, ?, ?)",
                [
                    (version, name, "0.11.9-internal", "2026-08-20T00:00:00")
                    for version, name in APP_SCHEMA_MIGRATIONS
                    if version <= 3
                ],
            )
            conn.execute("PRAGMA user_version = 3")
            conn.execute(
                "INSERT INTO users(id, username, password_hash, display_name, role, region, is_active, created_at) "
                "VALUES ('u1','u1','hash','Upgrade User','leader','GLOBAL',1,'2026-08-20T00:00:00')"
            )
            conn.execute(
                "INSERT INTO customers(id,display_name,normalized_name,country,city,region,lat,lng,created_at,updated_at,row_version) "
                "VALUES ('c1','Upgrade Customer','upgrade customer','Germany','Berlin','EU',52.52,13.405,"
                "'2026-08-20T00:00:00','2026-08-20T00:00:00',1)"
            )
            conn.execute(
                "INSERT INTO trip_plans(id,title,owner_id,start_date,end_date,travel_mode,avoid_weekends,status,created_at,updated_at,row_version) "
                "VALUES ('p1','Preserve Plan','u1','2026-09-15','2026-09-30','drive',1,'Draft',"
                "'2026-08-20T00:00:00','2026-08-20T00:00:00',7)"
            )
            conn.execute(
                "INSERT INTO trip_plan_stops(id,plan_id,customer_id,sequence_no,stay_days,result_status,created_at,updated_at,row_version) "
                "VALUES ('s1','p1','c1',1,2,'Planned','2026-08-20T00:00:00','2026-08-20T00:00:00',5)"
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
        first = initialize_database_safely(settings)
        assert first.migrated is True
        assert first.source_schema_version == 3
        assert first.target_schema_version == APP_SCHEMA_VERSION
        assert first.backup_path and first.backup_path.is_file()
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            plan = dict(conn.execute("SELECT * FROM trip_plans WHERE id='p1'").fetchone())
            stop = dict(conn.execute("SELECT * FROM trip_plan_stops WHERE id='s1'").fetchone())
            assert plan["title"] == "Preserve Plan" and plan["row_version"] == 7
            assert plan["route_order_mode"] == "auto"
            assert json.loads(plan["transport_mode_priority"]) == ["drive"]
            assert stop["stay_days"] == 2 and stop["duration_half_days"] == 4
            assert stop["row_version"] == 5
            assert conn.execute("SELECT COUNT(*) FROM trip_plan_legs").fetchone()[0] == 0
            assert [row[0] for row in conn.execute(
                "SELECT version FROM app_schema_migrations ORDER BY version"
            )] == list(range(1, APP_SCHEMA_VERSION + 1))
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()
        second = initialize_database_safely(settings)
        assert second.migrated is False and second.backup_path is None


def run() -> None:
    try:
        check_schema3_to_current_upgrade()
        close_db()
        with TestClient(app) as client:
            ctx = _seed_api(client)
            state = check_preview_manual_order_and_windows_are_read_only(client, ctx)
            saved = check_locked_other_leg_and_atomic_generation(client, ctx, state)
            check_invalid_inputs_and_overrun_are_atomic(client, ctx, saved)
            check_reordered_route_replaces_obsolete_legs(client, ctx, saved)
            check_stale_crud_archives_current_legs(client, ctx)
            check_auto_route_priority_and_obsolete_overrides(client, ctx)
            check_legacy_travel_mode_compatibility(client, ctx)
            check_reassigned_plan_revokes_creator_access(client, ctx)
        print("PASS: Trip Planner transport v2, leg atomicity, and current upgrade")
    finally:
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
