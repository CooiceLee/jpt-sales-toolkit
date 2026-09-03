"""Trip Planner stability and data-integrity regression tests.

Run:
    python test_trip_planner_stability.py

The application is imported only after ``JPT_DATA_DIR`` points at a temporary
directory.  No production database or attachment directory is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_trip_stability_"))
DB_PATH = TEST_DIR / "database.sqlite"
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from backend.repositories.base import get_db  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


def _auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _require(response, status_code: int):
    assert response.status_code == status_code, response.text
    return response.json()


def _create_customer(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    country: str,
    city: str,
    region: str,
    lat: float | None,
    lng: float | None,
) -> str:
    payload = {
        "display_name": name,
        "country": country,
        "city": city,
        "region": region,
        "lat": lat,
        "lng": lng,
    }
    if lat is not None and lng is not None:
        payload.update(
            {
                "geocode_source": "manual",
                "geocode_confidence": "high",
                "geocode_locked": True,
            }
        )
    data = _require(client.post("/api/customers", headers=headers, json=payload), 200)
    return data["id"]


def _create_lead(
    client: TestClient,
    headers: dict[str, str],
    *,
    customer_id: str,
    owner_id: str,
    title: str,
) -> str:
    data = _require(
        client.post(
            "/api/leads",
            headers=headers,
            json={
                "customer_id": customer_id,
                "owner_id": owner_id,
                "title": title,
                "source_channel": "Referral",
                "sales_stage": "Following",
                "product_category": "Fiber Laser",
                "application": "Welding",
            },
        ),
        200,
    )
    return data["id"]


def _create_plan(
    client: TestClient,
    headers: dict[str, str],
    *,
    title: str,
    end_date: str = "2026-09-30",
    region: str = "EU",
) -> dict:
    return _require(
        client.post(
            "/api/review/trip-plans",
            headers=headers,
            json={
                "title": title,
                "start_date": "2026-09-15",
                "end_date": end_date,
                "region": region,
                "origin_name": "Berlin",
                "origin_lat": 52.52,
                "origin_lng": 13.405,
                "destination_name": "Paris",
                "destination_lat": 48.8566,
                "destination_lng": 2.3522,
                "travel_mode": "drive",
                "avoid_weekends": True,
                "description": "Stability regression plan",
            },
        ),
        200,
    )


def _add_stop(
    client: TestClient,
    headers: dict[str, str],
    plan_id: str,
    lead_id: str,
    **extra,
) -> dict:
    payload = {"lead_id": lead_id, "visit_purpose": "Customer visit", **extra}
    return _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/stops",
            headers=headers,
            json=payload,
        ),
        200,
    )


def _database_snapshot() -> dict:
    """Hash the DB and record every user-table count plus mutable row versions."""
    conn = get_db()
    conn.commit()
    tables = [
        row["name"]
        for row in conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    counts = {
        table: conn.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()["count"]
        for table in tables
    }
    versions = {}
    for table in ("trip_plans", "trip_plan_stops", "leads", "customers"):
        versions[table] = [
            tuple(row)
            for row in conn.execute(
                f'SELECT id, row_version FROM "{table}" ORDER BY id'
            ).fetchall()
        ]
    assert DB_PATH.exists(), f"temporary database missing: {DB_PATH}"
    return {
        "sha256": hashlib.sha256(DB_PATH.read_bytes()).hexdigest(),
        "counts": counts,
        "versions": versions,
    }


def _assert_no_database_write(before: dict, after: dict, context: str) -> None:
    assert after == before, (
        f"{context} changed the temporary database:\n"
        f"before={json.dumps(before, ensure_ascii=False, sort_keys=True)}\n"
        f"after={json.dumps(after, ensure_ascii=False, sort_keys=True)}"
    )


def _warning_text(summary: dict) -> str:
    return json.dumps(summary.get("warnings") or [], ensure_ascii=False).lower()


def _seed(client: TestClient) -> dict:
    leader_id = upsert_account(
        "trip-stability-leader",
        "TripStabilityLeader2026",
        "Trip Stability Leader",
        "leader",
        None,
    )
    headers = _auth_headers(client, "trip-stability-leader", "TripStabilityLeader2026")

    customer_specs = {
        "berlin": ("Stability Berlin", "Germany", "Berlin", "EU", 52.52, 13.405),
        "paris": ("Stability Paris", "France", "Paris", "EU", 48.8566, 2.3522),
        "boston": ("Stability Boston", "United States", "Boston", "AM", 42.3601, -71.0589),
        "missing": ("Stability Missing", "Italy", "Milan", "EU", None, None),
    }
    customers = {}
    leads = {}
    for key, spec in customer_specs.items():
        customers[key] = _create_customer(
            client,
            headers,
            name=spec[0],
            country=spec[1],
            city=spec[2],
            region=spec[3],
            lat=spec[4],
            lng=spec[5],
        )
        leads[key] = _create_lead(
            client,
            headers,
            customer_id=customers[key],
            owner_id=leader_id,
            title=f"{spec[0]} opportunity",
        )
    return {"headers": headers, "leader_id": leader_id, "customers": customers, "leads": leads}


def check_preview_is_byte_for_byte_read_only_and_date_window_is_atomic(
    client: TestClient,
    ctx: dict,
) -> None:
    plan = _create_plan(client, ctx["headers"], title="Preview read-only")
    plan = _add_stop(client, ctx["headers"], plan["id"], ctx["leads"]["berlin"])
    plan = _add_stop(client, ctx["headers"], plan["id"], ctx["leads"]["paris"])

    payload = {
        "row_version": plan["row_version"],
        "start_date": "2026-09-15",
        "end_date": "2026-09-30",
        "origin_name": "Berlin",
        "origin_lat": 52.52,
        "origin_lng": 13.405,
        "destination_name": "Paris",
        "destination_lat": 48.8566,
        "destination_lng": 2.3522,
        "travel_mode": "drive",
        "avoid_weekends": True,
    }
    before = _database_snapshot()
    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=payload,
        ),
        200,
    )
    assert preview["itinerary_preview"] is True
    assert preview["row_version"] == plan["row_version"]
    _assert_no_database_write(before, _database_snapshot(), "route preview")

    constrained = _create_plan(
        client,
        ctx["headers"],
        title="End-date atomicity",
        end_date="2026-09-15",
    )
    constrained = _add_stop(
        client,
        ctx["headers"],
        constrained["id"],
        ctx["leads"]["berlin"],
        stay_days=5,
    )
    constrained_payload = {
        "row_version": constrained["row_version"],
        "start_date": "2026-09-15",
        "end_date": "2026-09-15",
        "origin_name": "Berlin",
        "origin_lat": 52.52,
        "origin_lng": 13.405,
        "destination_name": "Berlin",
        "destination_lat": 52.52,
        "destination_lng": 13.405,
        "travel_mode": "drive",
        "stop_stays": {constrained["stops"][0]["id"]: 5},
    }
    before_preview = _database_snapshot()
    overrun_preview = _require(
        client.post(
            f"/api/review/trip-plans/{constrained['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=constrained_payload,
        ),
        200,
    )
    summary = overrun_preview["itinerary_summary"]
    assert summary["calculated_end_date"] > "2026-09-15"
    warning = _warning_text(summary)
    assert "end" in warning and ("exceed" in warning or "overrun" in warning or "beyond" in warning), warning
    _assert_no_database_write(before_preview, _database_snapshot(), "overrun preview")

    before_generate = _database_snapshot()
    rejected = client.post(
        f"/api/review/trip-plans/{constrained['id']}/generate-itinerary",
        headers=ctx["headers"],
        json=constrained_payload,
    )
    assert rejected.status_code == 400, rejected.text
    rejection_text = rejected.text.lower()
    assert "end" in rejection_text and ("exceed" in rejection_text or "overrun" in rejection_text or "beyond" in rejection_text)
    _assert_no_database_write(before_generate, _database_snapshot(), "rejected route generation")


def check_explicit_null_clears_optional_fields(client: TestClient, ctx: dict) -> None:
    plan = _create_plan(client, ctx["headers"], title="Explicit null")
    plan = _add_stop(
        client,
        ctx["headers"],
        plan["id"],
        ctx["leads"]["berlin"],
        notes="Remove this note",
        visit_purpose="Remove this purpose",
    )
    updated = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"],
            json={
                "row_version": plan["row_version"],
                "description": None,
                "origin_name": None,
                "origin_lat": None,
                "origin_lng": None,
            },
        ),
        200,
    )
    assert updated["description"] is None
    assert updated["origin_name"] is None
    assert updated["origin_lat"] is None and updated["origin_lng"] is None
    assert updated["destination_name"] == "Paris", "unmentioned fields must not be cleared"

    stop = updated["stops"][0]
    updated = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop['id']}",
            headers=ctx["headers"],
            json={
                "row_version": stop["row_version"],
                "visit_purpose": None,
                "notes": None,
                "result_notes": None,
            },
        ),
        200,
    )
    stop = updated["stops"][0]
    assert stop["visit_purpose"] is None
    assert stop["notes"] is None
    assert stop["result_notes"] is None


def check_generate_persists_route_header_atomically(client: TestClient, ctx: dict) -> None:
    plan = _create_plan(client, ctx["headers"], title="Old route header", region="EU")
    plan = _add_stop(client, ctx["headers"], plan["id"], ctx["leads"]["berlin"])
    preview_payload = {
        "row_version": plan["row_version"],
        "title": "September customer route",
        "region": "AM",
        "description": "Leader-approved route notes",
        "start_date": "2026-09-15",
        "end_date": "2026-09-30",
        "travel_mode": "drive",
    }
    before = _database_snapshot()
    _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/preview-itinerary",
            headers=ctx["headers"],
            json=preview_payload,
        ),
        200,
    )
    _assert_no_database_write(before, _database_snapshot(), "route header preview")

    saved = _require(
        client.post(
            f"/api/review/trip-plans/{plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json=preview_payload,
        ),
        200,
    )
    assert saved["title"] == "September customer route"
    assert saved["region"] == "AM"
    assert saved["description"] == "Leader-approved route notes"
    reloaded = _require(
        client.get(f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]),
        200,
    )
    assert (reloaded["title"], reloaded["region"], reloaded["description"]) == (
        "September customer route",
        "AM",
        "Leader-approved route notes",
    )


def check_followup_reschedule_archive_and_lead_recalculation(client: TestClient, ctx: dict) -> None:
    lead_id = ctx["leads"]["berlin"]
    ordinary = _require(
        client.post(
            f"/api/leads/{lead_id}/activities",
            headers=ctx["headers"],
            json={
                "action_type": "follow_up",
                "method": "Email",
                "content": "Independent follow-up",
                "next_action": "Independent action",
                "next_action_date": "2026-09-25",
            },
        ),
        200,
    )
    assert ordinary["activity_id"]

    plan = _create_plan(client, ctx["headers"], title="Follow-up lifecycle")
    plan = _add_stop(client, ctx["headers"], plan["id"], lead_id)
    stop = plan["stops"][0]
    plan = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop['id']}",
            headers=ctx["headers"],
            json={
                "row_version": stop["row_version"],
                "result_status": "Follow-up Needed",
                "actual_visit_date": "2026-05-12",
                "actual_visit_period": "PM",
                "visit_next_action": "Trip action",
                "visit_followup_due_date": "2026-09-20",
            },
        ),
        200,
    )
    stop = plan["stops"][0]
    activity_id = stop["followup_activity_id"]
    assert activity_id
    assert _require(client.get(f"/api/leads/{lead_id}", headers=ctx["headers"]), 200)["next_followup_date"] == "2026-09-20"

    plan = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop['id']}",
            headers=ctx["headers"],
            json={
                "row_version": stop["row_version"],
                "result_status": "Follow-up Needed",
                "actual_visit_date": "2026-05-12",
                "actual_visit_period": "PM",
                "visit_next_action": "Trip action rescheduled",
                "visit_followup_due_date": "2026-09-28",
            },
        ),
        200,
    )
    stop = plan["stops"][0]
    assert stop["followup_activity_id"] == activity_id, "reschedule must update, not duplicate, the trip follow-up"
    row = get_db().execute(
        "SELECT payload_json, archived_at FROM lead_activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    assert row and row["archived_at"] is None
    assert json.loads(row["payload_json"])["next_action_date"] == "2026-09-28"
    assert _require(client.get(f"/api/leads/{lead_id}", headers=ctx["headers"]), 200)["next_followup_date"] == "2026-09-25"

    plan = _require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop['id']}",
            headers=ctx["headers"],
            json={
                "row_version": stop["row_version"],
                "result_status": "Visited",
                "actual_visit_date": "2026-05-12",
                "actual_visit_period": "PM",
                "result_notes": "Visit complete",
            },
        ),
        200,
    )
    row = get_db().execute(
        "SELECT archived_at FROM lead_activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    assert row and row["archived_at"] is not None, "leaving Follow-up Needed must archive the generated follow-up"
    assert _require(client.get(f"/api/leads/{lead_id}", headers=ctx["headers"]), 200)["next_followup_date"] == "2026-09-25"


def check_missing_coordinates_duplicates_and_route_staleness(client: TestClient, ctx: dict) -> None:
    missing_plan = _create_plan(client, ctx["headers"], title="Missing coordinates")
    rejected = client.post(
        f"/api/review/trip-plans/{missing_plan['id']}/stops",
        headers=ctx["headers"],
        json={"lead_id": ctx["leads"]["missing"]},
    )
    assert rejected.status_code == 400, rejected.text
    assert "coordinate" in rejected.text.lower() or "latitude" in rejected.text.lower(), rejected.text
    persisted = _require(
        client.get(f"/api/review/trip-plans/{missing_plan['id']}", headers=ctx["headers"]),
        200,
    )
    assert persisted["stops"] == []

    duplicate_plan = _create_plan(client, ctx["headers"], title="Duplicate visit")
    duplicate_plan = _add_stop(
        client,
        ctx["headers"],
        duplicate_plan["id"],
        ctx["leads"]["berlin"],
    )
    rejected = client.post(
        f"/api/review/trip-plans/{duplicate_plan['id']}/stops",
        headers=ctx["headers"],
        json={"lead_id": ctx["leads"]["berlin"]},
    )
    assert rejected.status_code == 400, rejected.text
    assert "duplicate" in rejected.text.lower() or "already" in rejected.text.lower(), rejected.text
    persisted = _require(
        client.get(f"/api/review/trip-plans/{duplicate_plan['id']}", headers=ctx["headers"]),
        200,
    )
    assert len(persisted["stops"]) == 1

    duplicate_plan = _require(
        client.post(
            f"/api/review/trip-plans/{duplicate_plan['id']}/stops",
            headers=ctx["headers"],
            json={"lead_id": ctx["leads"]["berlin"], "allow_duplicate": True},
        ),
        200,
    )
    assert len(duplicate_plan["stops"]) == 2

    route_plan = _create_plan(client, ctx["headers"], title="Stale route summary")
    route_plan = _add_stop(client, ctx["headers"], route_plan["id"], ctx["leads"]["berlin"])
    route_plan = _add_stop(client, ctx["headers"], route_plan["id"], ctx["leads"]["paris"])
    route_plan = _require(
        client.post(
            f"/api/review/trip-plans/{route_plan['id']}/generate-itinerary",
            headers=ctx["headers"],
            json={
                "row_version": route_plan["row_version"],
                "start_date": "2026-09-15",
                "end_date": "2026-09-30",
                "travel_mode": "drive",
            },
        ),
        200,
    )
    assert route_plan["itinerary_generated_at"]
    assert route_plan["itinerary_summary"].get("stale") is not True

    generated_at = route_plan["itinerary_generated_at"]
    unchanged_stop = route_plan["stops"][0]
    route_plan = _require(
        client.patch(
            f"/api/review/trip-plans/{route_plan['id']}/stops/{unchanged_stop['id']}",
            headers=ctx["headers"],
            json={
                "row_version": unchanged_stop["row_version"],
                "planned_date": unchanged_stop["planned_date"],
                "stay_days": unchanged_stop["stay_days"],
                "result_notes": "Result-only edit must not invalidate the saved route",
            },
        ),
        200,
    )
    assert route_plan["itinerary_generated_at"] == generated_at
    assert route_plan["itinerary_summary"].get("stale") is not True

    route_plan = _require(
        client.patch(
            f"/api/review/trip-plans/{route_plan['id']}",
            headers=ctx["headers"],
            json={"row_version": route_plan["row_version"], "travel_mode": "ground_public"},
        ),
        200,
    )
    stale = route_plan["itinerary_summary"]
    assert stale["stale"] is True and stale["valid"] is False
    assert stale["reason"] == "route_settings_changed"
    assert stale["warnings"]
    assert route_plan["itinerary_generated_at"] is None

    for extension in ("md", "csv"):
        blocked_export = client.get(
            f"/api/review/trip-plans/{route_plan['id']}/export.{extension}",
            headers=ctx["headers"],
        )
        assert blocked_export.status_code == 400, blocked_export.text
        assert "out of date" in blocked_export.text.lower(), blocked_export.text


def check_candidate_region_filter_does_not_mutate_plan_region(client: TestClient, ctx: dict) -> None:
    plan = _create_plan(client, ctx["headers"], title="EU plan stays EU", region="EU")
    before = _database_snapshot()
    result = _require(
        client.get("/api/review/trip-candidates?region=AM&limit=200", headers=ctx["headers"]),
        200,
    )
    assert result["filters"]["region"] == "AM"
    assert result["candidates"]
    assert all(item["region"] == "AM" for item in result["candidates"])
    _assert_no_database_write(before, _database_snapshot(), "candidate region filter")
    persisted = _require(
        client.get(f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]),
        200,
    )
    assert persisted["region"] == "EU"


def run() -> None:
    try:
        with TestClient(app) as client:
            ctx = _seed(client)
            check_preview_is_byte_for_byte_read_only_and_date_window_is_atomic(client, ctx)
            check_explicit_null_clears_optional_fields(client, ctx)
            check_generate_persists_route_header_atomically(client, ctx)
            check_followup_reschedule_archive_and_lead_recalculation(client, ctx)
            check_missing_coordinates_duplicates_and_route_staleness(client, ctx)
            check_candidate_region_filter_does_not_mutate_plan_region(client, ctx)
        print("PASS: Trip Planner stability and data-integrity regressions")
    finally:
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
