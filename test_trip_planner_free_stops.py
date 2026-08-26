"""Batch 3 regressions for customer-independent Trip Planner stops."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_trip_free_stops_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.config import init_settings  # noqa: E402
from backend.repositories import APP_SCHEMA_VERSION, close_db  # noqa: E402
from backend.repositories.base import APP_SCHEMA_MIGRATIONS, get_db  # noqa: E402
from backend.services.customer_service import CustomerService  # noqa: E402
from backend.services.spreadsheet_import.write_customers import (  # noqa: E402
    _upsert_customer,
)
from backend.startup_upgrade import initialize_database_safely  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


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


def _snapshot() -> dict[str, list[tuple]]:
    conn = get_db()
    conn.commit()
    return {
        table: [
            tuple(row)
            for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
        ]
        for table in (
            "trip_plans",
            "trip_plan_stops",
            "trip_plan_free_stops",
            "trip_plan_legs",
            "customers",
            "leads",
            "lead_activities",
        )
    }


def _seed(client: TestClient) -> dict:
    leader_id = upsert_account(
        "free-stop-leader", "FreeStopLeader2026", "Free Stop Leader", "leader", None
    )
    owner_id = upsert_account(
        "free-stop-sales", "FreeStopSales2026", "Free Stop Sales", "sales", "EU"
    )
    other_id = upsert_account(
        "free-stop-other", "FreeStopOther2026", "Other Sales", "sales", "EU"
    )
    leader_headers = _login(client, "free-stop-leader", "FreeStopLeader2026")
    owner_headers = _login(client, "free-stop-sales", "FreeStopSales2026")
    other_headers = _login(client, "free-stop-other", "FreeStopOther2026")
    customer = _require(
        client.post(
            "/api/customers",
            headers=leader_headers,
            json={
                "display_name": "Free Stop Munich Customer",
                "country": "Germany",
                "city": "Munich",
                "region": "EU",
                "lat": 48.1351,
                "lng": 11.5820,
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
            headers=leader_headers,
            json={
                "customer_id": customer["id"],
                "owner_id": owner_id,
                "title": "Munich visit",
                "source_channel": "Referral",
                "sales_stage": "Following",
            },
        ),
        200,
    )
    plan = _require(
        client.post(
            "/api/review/trip-plans",
            headers=leader_headers,
            json={
                "title": "Mixed September Route",
                "owner_id": owner_id,
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "region": "EU",
                "origin_name": "Frankfurt Airport",
                "origin_lat": 50.0379,
                "origin_lng": 8.5622,
                "destination_name": "Frankfurt Airport",
                "destination_lat": 50.0379,
                "destination_lng": 8.5622,
                "route_order_mode": "manual",
                "transport_mode_priority": ["ground_public", "drive", "flight"],
                "avoid_weekends": True,
            },
        ),
        200,
    )
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops",
            headers=owner_headers,
            json={"lead_id": lead["id"], "stay_days": 1},
        ),
        200,
    )
    return {
        "leader_id": leader_id,
        "owner_id": owner_id,
        "other_id": other_id,
        "leader_headers": leader_headers,
        "owner_headers": owner_headers,
        "other_headers": other_headers,
        "customer_id": customer["id"],
        "lead_id": lead["id"],
        "plan": plan,
    }


def check_roundtrip_route_export_and_archive(client: TestClient, ctx: dict) -> None:
    plan = ctx["plan"]
    before_counts = {
        table: get_db().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("customers", "leads", "lead_activities")
    }
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/free-stops",
            headers=ctx["owner_headers"],
            json={
                "category": "hotel",
                "location_name": "Demo Rest Hotel",
                "address": "Example Strasse 8",
                "city": "Nuremberg",
                "country": "Germany",
                "lat": 49.4521,
                "lng": 11.0767,
                "stay_days": 2,
                "visit_purpose": "Rest and internal preparation",
                "notes": "No customer visit",
                "sequence_no": 1,
            },
        ),
        200,
    )
    assert [stop["stop_kind"] for stop in plan["stops"]] == ["free", "customer"]
    free_stop = plan["stops"][0]
    assert free_stop["location_name"] == "Demo Rest Hotel"
    assert free_stop["category"] == "hotel"
    assert free_stop["customer_id"] is None and free_stop["lead_id"] is None
    listed = _require(
        client.get("/api/review/trip-plans", headers=ctx["owner_headers"]), 200
    )
    assert next(item for item in listed if item["id"] == plan["id"])["stop_count"] == 2
    assert {
        table: get_db().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before_counts
    } == before_counts

    updated = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}",
            headers=ctx["owner_headers"],
            json={
                "row_version": free_stop["row_version"],
                "stay_days": 3,
                "notes": "Rest, internal preparation, and transit buffer",
            },
        ),
        200,
    )
    updated_free = next(stop for stop in updated["stops"] if stop["id"] == free_stop["id"])
    assert updated_free["stay_days"] == 3
    conflict = client.patch(
        f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}",
        headers=ctx["owner_headers"],
        json={"row_version": free_stop["row_version"], "notes": "stale"},
    )
    assert conflict.status_code == 409

    customer_stop_id = next(
        stop["id"] for stop in updated["stops"] if stop["stop_kind"] == "customer"
    )
    reordered = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops/reorder",
            headers=ctx["owner_headers"],
            json={
                "row_version": updated["row_version"],
                "stop_ids": [customer_stop_id, free_stop["id"]],
            },
        ),
        200,
    )
    assert [stop["stop_kind"] for stop in reordered["stops"]] == ["customer", "free"]
    reordered = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops/reorder",
            headers=ctx["owner_headers"],
            json={
                "row_version": reordered["row_version"],
                "stop_ids": [free_stop["id"], customer_stop_id],
            },
        ),
        200,
    )
    assert [stop["sequence_no"] for stop in reordered["stops"]] == [1, 2]

    fresh = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}", headers=ctx["owner_headers"]
        ),
        200,
    )
    order = [stop["id"] for stop in fresh["stops"]]
    before_preview = _snapshot()
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": fresh["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
                "stop_stays": {free_stop["id"]: 3},
            },
        ),
        200,
    )
    assert _snapshot() == before_preview
    preview_free = next(stop for stop in preview["stops"] if stop["id"] == free_stop["id"])
    assert preview_free["stop_kind"] == "free" and preview_free["planned_date"]
    assert len(preview["legs"]) == 3

    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": fresh["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
                "stop_stays": {free_stop["id"]: 3},
            },
        ),
        200,
    )
    conn = get_db()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    leg_rows = conn.execute(
        "SELECT from_stop_id, from_free_stop_id, to_stop_id, to_free_stop_id "
        "FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL "
        "ORDER BY sequence_no",
        (plan["id"],),
    ).fetchall()
    assert leg_rows[0][0] is None and leg_rows[0][1] is None
    assert leg_rows[0][2] is None and leg_rows[0][3] == free_stop["id"]
    assert leg_rows[1][0] is None and leg_rows[1][1] == free_stop["id"]
    assert leg_rows[1][2] == ctx["plan"]["stops"][0]["id"] and leg_rows[1][3] is None

    markdown = client.get(
        f"/api/review/trip-plans/{plan['id']}/export.md",
        headers=ctx["owner_headers"],
    )
    assert markdown.status_code == 200 and "Demo Rest Hotel" in markdown.text
    assert "Rest, internal preparation, and transit buffer" in markdown.text
    assert "## Route Legs" in markdown.text
    assert saved["legs"][-1]["to_label"] in markdown.text
    assert "Planning Notes:" in markdown.text
    csv_response = client.get(
        f"/api/review/trip-plans/{plan['id']}/export.csv",
        headers=ctx["owner_headers"],
    )
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert {
        "No.", "Company Name", "Full Address", "Recommended Visit Date",
        "Demo Laser", "PO Laser", "客户人员 / Customer Personnel",
        "渠道代理公司陪同人员（如有） / Channel Partner Companions (if any)", "Visiting topic",
    } <= set(rows[0])
    free_row = next(row for row in rows if row["record_type"] == "free_stop")
    assert free_row["category"] == "hotel" and free_row["location_name"] == "Demo Rest Hotel"
    assert free_row["address"] == "Example Strasse 8"
    assert free_row["plan_title"] == saved["title"]
    leg_rows = [row for row in rows if row["record_type"] == "leg"]
    assert len(leg_rows) == len(saved["legs"])
    assert leg_rows[-1]["leg_key"].endswith(">destination")
    assert leg_rows[-1]["leg_to"] == saved["legs"][-1]["to_label"]
    execution = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}/execution",
            headers=ctx["owner_headers"],
        ),
        200,
    )
    assert any(stop["stop_kind"] == "free" for stop in execution["stops"])
    execution_md = client.get(
        f"/api/review/trip-plans/{plan['id']}/execution.md",
        headers=ctx["owner_headers"],
    ).text
    assert "Demo Rest Hotel" in execution_md
    assert "### 1. Demo Rest Hotel" not in execution_md
    assert conn.execute("SELECT COUNT(*) FROM lead_activities").fetchone()[0] == before_counts["lead_activities"]

    archived = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}/archive",
            headers=ctx["owner_headers"],
            json={
                "row_version": next(
                    stop for stop in saved["stops"] if stop["id"] == free_stop["id"]
                )["row_version"]
            },
        ),
        200,
    )
    assert [stop["stop_kind"] for stop in archived["stops"]] == ["customer"]
    assert archived["stops"][0]["sequence_no"] == 1
    assert archived["legs"] == []
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM lead_activities").fetchone()[0] == before_counts["lead_activities"]
    assert client.get(
        f"/api/review/trip-plans/{plan['id']}/execution",
        headers=ctx["owner_headers"],
    ).status_code == 400
    assert client.get(
        f"/api/review/trip-plans/{plan['id']}/execution.md",
        headers=ctx["owner_headers"],
    ).status_code == 400


def check_free_stop_identity_invalidates_only_stale_overrides(
    client: TestClient, ctx: dict
) -> None:
    plan = _require(
        client.post(
            "/api/review/trip-plans",
            headers=ctx["leader_headers"],
            json={
                "title": "Free stop override lifecycle",
                "owner_id": ctx["owner_id"],
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "origin_name": "Frankfurt Airport",
                "origin_lat": 50.0379,
                "origin_lng": 8.5622,
                "destination_name": "Frankfurt Airport",
                "destination_lat": 50.0379,
                "destination_lng": 8.5622,
                "route_order_mode": "manual",
            },
        ),
        200,
    )
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops",
            headers=ctx["owner_headers"],
            json={"lead_id": ctx["lead_id"]},
        ),
        200,
    )
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/free-stops",
            headers=ctx["owner_headers"],
            json={
                "category": "hotel",
                "location_name": "Near Munich",
                "lat": 48.2,
                "lng": 11.6,
            },
        ),
        200,
    )
    free_stop = next(item for item in plan["stops"] if item["stop_kind"] == "free")
    order = [item["id"] for item in plan["stops"]]
    locked_key = f"{order[0]}>{order[1]}"
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": plan["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
                "leg_overrides": {
                    locked_key: {
                        "selected_mode": "other",
                        "mode_locked": True,
                        "manual_distance_km": 5,
                        "manual_time_hours": 1,
                        "manual_travel_days": 0,
                    }
                },
            },
        ),
        200,
    )
    free_stop = next(item for item in saved["stops"] if item["id"] == free_stop["id"])
    notes_only = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}",
            headers=ctx["owner_headers"],
            json={"row_version": free_stop["row_version"], "notes": "Keep the route"},
        ),
        200,
    )
    assert next(leg for leg in notes_only["legs"] if leg["leg_key"] == locked_key)[
        "mode_locked"
    ] is True

    free_stop = next(item for item in notes_only["stops"] if item["id"] == free_stop["id"])
    stay_changed = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}",
            headers=ctx["owner_headers"],
            json={"row_version": free_stop["row_version"], "stay_days": 2},
        ),
        200,
    )
    assert stay_changed["itinerary_summary"]["stale"] is True
    retained = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": stay_changed["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
            },
        ),
        200,
    )
    retained_leg = next(leg for leg in retained["legs"] if leg["leg_key"] == locked_key)
    assert retained_leg["mode_locked"] is True
    assert retained_leg["manual_distance_km"] == 5

    regenerated = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": stay_changed["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
            },
        ),
        200,
    )
    free_stop = next(item for item in regenerated["stops"] if item["id"] == free_stop["id"])
    moved = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/free-stops/{free_stop['id']}",
            headers=ctx["owner_headers"],
            json={
                "row_version": free_stop["row_version"],
                "location_name": "Rome Rest",
                "lat": 41.9028,
                "lng": 12.4964,
            },
        ),
        200,
    )
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": moved["row_version"],
                "route_order_mode": "manual",
                "stop_order": order,
            },
        ),
        200,
    )
    changed_leg = next(leg for leg in preview["legs"] if leg["leg_key"] == locked_key)
    assert changed_leg["mode_locked"] is False
    assert changed_leg["manual_distance_km"] is None
    assert changed_leg["distance_km"] != 5


def check_customer_location_invalidates_route_but_notes_do_not(
    client: TestClient, ctx: dict
) -> None:
    plan = _require(
        client.post(
            "/api/review/trip-plans",
            headers=ctx["leader_headers"],
            json={
                "title": "Customer location dependency",
                "owner_id": ctx["owner_id"],
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "origin_name": "Frankfurt Airport",
                "origin_lat": 50.0379,
                "origin_lng": 8.5622,
                "destination_name": "Frankfurt Airport",
                "destination_lat": 50.0379,
                "destination_lng": 8.5622,
                "route_order_mode": "manual",
            },
        ),
        200,
    )
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/stops",
            headers=ctx["owner_headers"],
            json={"lead_id": ctx["lead_id"]},
        ),
        200,
    )
    stop_id = plan["stops"][0]["id"]
    locked_key = f"origin>{stop_id}"
    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": plan["row_version"],
                "route_order_mode": "manual",
                "stop_order": [stop_id],
                "leg_overrides": {
                    locked_key: {
                        "selected_mode": "other",
                        "mode_locked": True,
                        "manual_distance_km": 9,
                        "manual_time_hours": 1,
                        "manual_travel_days": 0,
                    }
                },
            },
        ),
        200,
    )
    before_plan_version = saved["row_version"]
    customer = _require(
        client.get(
            f"/api/customers/{ctx['customer_id']}",
            headers=ctx["leader_headers"],
        ),
        200,
    )
    note_update = _require(
        client.patch(
            f"/api/customers/{ctx['customer_id']}",
            headers=ctx["leader_headers"],
            json={
                "row_version": customer["row_version"],
                "company_description": "Ordinary note must not invalidate a route",
            },
        ),
        200,
    )
    unchanged = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["owner_headers"],
        ),
        200,
    )
    assert unchanged["row_version"] == before_plan_version
    assert len(unchanged["legs"]) == 2

    moved_customer = _require(
        client.patch(
            f"/api/customers/{ctx['customer_id']}",
            headers=ctx["leader_headers"],
            json={
                "row_version": note_update["row_version"],
                "city": "Rome",
                "address": "Moved route address",
                "lat": 41.9028,
                "lng": 12.4964,
            },
        ),
        200,
    )
    stale = _require(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["owner_headers"],
        ),
        200,
    )
    assert stale["itinerary_summary"]["stale"] is True
    assert stale["itinerary_summary"]["reason"] == "customer_location_changed"
    assert stale["itinerary_generated_at"] is None and stale["legs"] == []
    assert client.get(
        f"/api/review/trip-plans/{plan['id']}/execution",
        headers=ctx["owner_headers"],
    ).status_code == 400
    assert client.get(
        f"/api/review/trip-plans/{plan['id']}/execution.md",
        headers=ctx["owner_headers"],
    ).status_code == 400
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": stale["row_version"],
                "route_order_mode": "manual",
                "stop_order": [stop_id],
            },
        ),
        200,
    )
    new_leg = next(leg for leg in preview["legs"] if leg["leg_key"] == locked_key)
    assert new_leg["mode_locked"] is False
    assert new_leg["manual_distance_km"] is None
    assert new_leg["distance_km"] != 9
    conn = get_db()
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND mode_locked=1",
        (plan["id"],),
    ).fetchone()[0] == 0

    regenerated = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["owner_headers"],
            json={
                "row_version": stale["row_version"],
                "route_order_mode": "manual",
                "stop_order": [stop_id],
                "leg_overrides": {
                    locked_key: {
                        "selected_mode": "other",
                        "mode_locked": True,
                        "manual_distance_km": 13,
                        "manual_time_hours": 2,
                        "manual_travel_days": 0,
                    }
                },
            },
        ),
        200,
    )
    conn.execute(
        f"""CREATE TRIGGER fail_customer_route_invalidation
            BEFORE UPDATE OF itinerary_generated_at ON trip_plans
            WHEN OLD.id = '{plan['id']}' AND NEW.itinerary_generated_at IS NULL
            BEGIN SELECT RAISE(ABORT, 'route invalidation failure'); END"""
    )
    conn.commit()
    try:
        CustomerService().update(
            ctx["customer_id"],
            {"city": "Paris", "lat": 48.8566, "lng": 2.3522},
            ctx["leader_id"],
            moved_customer["row_version"],
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("Expected route invalidation trigger to abort customer update")
    rolled_back_customer = conn.execute(
        "SELECT city, lat, lng FROM customers WHERE id = ?", (ctx["customer_id"],)
    ).fetchone()
    assert tuple(rolled_back_customer) == ("Rome", 41.9028, 12.4964)
    rolled_back_plan = conn.execute(
        "SELECT itinerary_generated_at, itinerary_summary FROM trip_plans WHERE id = ?",
        (plan["id"],),
    ).fetchone()
    assert rolled_back_plan[0] == regenerated["itinerary_generated_at"]
    assert json.loads(rolled_back_plan[1]) == regenerated["itinerary_summary"]
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND mode_locked=1",
        (plan["id"],),
    ).fetchone()[0] == 1
    conn.execute("DROP TRIGGER fail_customer_route_invalidation")
    conn.commit()

    _upsert_customer(
        conn,
        ctx["customer_id"],
        {"city": "Milan", "lat": 45.4642, "lng": 9.1900},
        ctx["leader_id"],
    )
    conn.commit()
    imported_plan = conn.execute(
        "SELECT itinerary_generated_at, itinerary_summary FROM trip_plans WHERE id = ?",
        (plan["id"],),
    ).fetchone()
    assert imported_plan[0] is None
    assert json.loads(imported_plan[1])["reason"] == "customer_location_changed"
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND archived_at IS NULL",
        (plan["id"],),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM trip_plan_legs WHERE plan_id=? AND mode_locked=1",
        (plan["id"],),
    ).fetchone()[0] == 0


def check_permissions_and_validation(client: TestClient, ctx: dict) -> None:
    plan_id = ctx["plan"]["id"]
    ungenerated_execution = _require(
        client.get(
            f"/api/review/trip-plans/{plan_id}/execution",
            headers=ctx["owner_headers"],
        ),
        200,
    )
    assert ungenerated_execution["plan"]["id"] == plan_id
    payload = {
        "category": "rest",
        "location_name": "Unauthorized Stop",
        "lat": 48.1,
        "lng": 11.5,
    }
    assert client.post(
        f"/api/review/trip-plans/{plan_id}/free-stops",
        headers=ctx["other_headers"],
        json=payload,
    ).status_code == 404
    invalid = client.post(
        f"/api/review/trip-plans/{plan_id}/free-stops",
        headers=ctx["owner_headers"],
        json={**payload, "lat": 95},
    )
    assert invalid.status_code == 422


def check_schema4_to_current_upgrade() -> None:
    assert APP_SCHEMA_VERSION == 8
    with tempfile.TemporaryDirectory(prefix="jpt_trip_schema4_to_current_") as temp:
        data_dir = Path(temp) / "data"
        data_dir.mkdir()
        db_path = data_dir / "database.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
            conn.execute("DROP TABLE trip_plan_legs")
            conn.execute("DROP TABLE trip_plan_free_stops")
            from backend.repositories.trip_planning_schema import TRIP_PLAN_LEGS_DDL

            conn.execute(TRIP_PLAN_LEGS_DDL)
            conn.executemany(
                "INSERT INTO app_schema_migrations(version,name,app_version,applied_at) "
                "VALUES (?,?,?,?)",
                [
                    (version, name, "0.11.9-internal", "2026-08-21T00:00:00")
                    for version, name in APP_SCHEMA_MIGRATIONS
                    if version <= 4
                ],
            )
            conn.execute("PRAGMA user_version=4")
            conn.execute(
                "INSERT INTO users(id,username,password_hash,display_name,role,region,is_active,created_at) "
                "VALUES ('u1','u1','hash','Upgrade User','leader','GLOBAL',1,'2026-08-21T00:00:00')"
            )
            conn.execute(
                "INSERT INTO trip_plans(id,title,owner_id,status,created_at,updated_at,row_version) "
                "VALUES ('p1','Keep Plan','u1','Draft','2026-08-21T00:00:00','2026-08-21T00:00:00',9)"
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
        assert result.source_schema_version == 4
        assert result.target_schema_version == APP_SCHEMA_VERSION
        assert result.backup_path and result.backup_path.is_file()
        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute("SELECT title,row_version FROM trip_plans WHERE id='p1'").fetchone() == ("Keep Plan", 9)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "trip_plan_free_stops" in tables
            columns = {row[1] for row in conn.execute("PRAGMA table_info(trip_plan_legs)")}
            assert {"from_free_stop_id", "to_free_stop_id"} <= columns
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()


def run() -> None:
    try:
        check_schema4_to_current_upgrade()
        close_db()
        with TestClient(app) as client:
            ctx = _seed(client)
            check_permissions_and_validation(client, ctx)
            check_roundtrip_route_export_and_archive(client, ctx)
            check_free_stop_identity_invalidates_only_stale_overrides(client, ctx)
            check_customer_location_invalidates_route_but_notes_do_not(client, ctx)
        print("PASS: independent Trip stops, unified routing, exports, permissions, and current upgrade")
    finally:
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
