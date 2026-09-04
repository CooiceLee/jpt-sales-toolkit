"""
Regression tests for v0.7 data review and trip planning.

Run:
    python test_v07_review_trip.py
"""

from __future__ import annotations

import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_v07_review_trip_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


def auth_headers(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def seed_account_data(client: TestClient) -> dict:
    upsert_account("leader01", "LeaderJPT2026", "Leader 01", "leader", None)
    upsert_account("sales01", "Sales01JPT2026", "Sales 01", "sales", None)
    upsert_account("sales02", "Sales02JPT2026", "Sales 02", "sales", None)

    leader_headers = auth_headers(client, "leader01", "LeaderJPT2026")
    sales1_headers = auth_headers(client, "sales01", "Sales01JPT2026")
    sales2_headers = auth_headers(client, "sales02", "Sales02JPT2026")
    users = client.get("/api/auth/users", headers=leader_headers).json()
    user_ids = {user["username"]: user["id"] for user in users}

    lead_ids = []
    customer_ids = []
    for idx, owner_username in enumerate(["sales01", "sales01", "sales02"], start=1):
        customer_response = client.post(
            "/api/customers",
            headers=leader_headers,
            json={
                "display_name": f"=V07 Candidate {idx}" if idx == 1 else f"V07 Candidate {idx}",
                "country": "Germany",
                "city": f"City {idx}",
                "region": "EU",
                "lat": 52.0 + idx,
                "lng": 13.0 + idx,
                "geocode_source": "manual",
                "geocode_confidence": "high",
                "geocode_locked": True,
            },
        )
        assert customer_response.status_code == 200, customer_response.text
        customer_id = customer_response.json()["id"]
        customer_ids.append(customer_id)
        customer = client.get(f"/api/customers/{customer_id}", headers=leader_headers).json()
        geocode_response = client.patch(
            f"/api/customers/{customer_id}",
            headers=leader_headers,
            json={
                "lat": 52.0 + idx,
                "lng": 13.0 + idx,
                "geocode_source": "manual",
                "geocode_confidence": "high",
                "geocode_locked": True,
                "row_version": customer["row_version"],
            },
        )
        assert geocode_response.status_code == 200, geocode_response.text

        lead_response = client.post(
            "/api/leads",
            headers=leader_headers,
            json={
                "customer_id": customer_id,
                "owner_id": user_ids[owner_username],
                "title": f"V07 Quoted Lead {idx}",
                "source_channel": "Email",
                "sales_stage": "New",
                "product_category": "Fiber Laser",
                "application": "Welding",
            },
        )
        assert lead_response.status_code == 200, lead_response.text
        lead = client.get(f"/api/leads/{lead_response.json()['id']}", headers=leader_headers).json()
        update_response = client.patch(
            f"/api/leads/{lead['id']}",
            headers=leader_headers,
            json={
                "sales_stage": "Quoted",
                "estimated_value": 10000 * idx,
                "quotation_id": f"Q-V07-{idx}",
                "row_version": lead["row_version"],
            },
        )
        assert update_response.status_code == 200, update_response.text
        lead_ids.append(lead["id"])

    return {
        "leader_headers": leader_headers,
        "sales1_headers": sales1_headers,
        "sales2_headers": sales2_headers,
        "lead_ids": lead_ids,
        "customer_ids": customer_ids,
    }


def check_analysis_permission_and_candidate_pagination(client: TestClient, ctx: dict) -> None:
    leader = client.get("/api/review/analysis", headers=ctx["leader_headers"])
    sales1 = client.get("/api/review/analysis", headers=ctx["sales1_headers"])
    assert leader.status_code == 200, leader.text
    assert sales1.status_code == 200, sales1.text
    assert leader.json()["summary"]["total_leads"] == 3
    assert sales1.json()["summary"]["total_leads"] == 2

    page = client.get(
        "/api/review/trip-candidates?region=EU&limit=2&offset=1",
        headers=ctx["leader_headers"],
    )
    assert page.status_code == 200, page.text
    data = page.json()
    assert data["pagination"]["total"] == 3
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 1
    assert len(data["candidates"]) == 2

    invalid_filter = client.get(
        "/api/review/trip-candidates?sales_stage=Invalid",
        headers=ctx["leader_headers"],
    )
    assert invalid_filter.status_code == 422, invalid_filter.text


def check_trip_plan_activity_sync_and_csv_formula_escape(client: TestClient, ctx: dict) -> None:
    plan_response = client.post(
        "/api/review/trip-plans",
        headers=ctx["leader_headers"],
        json={"title": "V07 Audit Trip", "region": "EU"},
    )
    assert plan_response.status_code == 200, plan_response.text
    plan_id = plan_response.json()["id"]

    stop_response = client.post(
        f"/api/review/trip-plans/{plan_id}/stops",
        headers=ctx["leader_headers"],
        json={
            "customer_id": ctx["customer_ids"][0],
            "lead_id": ctx["lead_ids"][0],
            "visit_purpose": "=Discuss formula-safe export",
        },
    )
    assert stop_response.status_code == 200, stop_response.text
    stop_id = stop_response.json()["stops"][0]["id"]

    second_stop_response = client.post(
        f"/api/review/trip-plans/{plan_id}/stops",
        headers=ctx["leader_headers"],
        json={
            "customer_id": ctx["customer_ids"][1],
            "lead_id": ctx["lead_ids"][1],
            "stay_days": 2,
            "visit_purpose": "Second customer visit",
        },
    )
    assert second_stop_response.status_code == 200, second_stop_response.text
    second_stop_id = second_stop_response.json()["stops"][1]["id"]

    bad_reorder = client.post(
        f"/api/review/trip-plans/{plan_id}/stops/reorder",
        headers=ctx["leader_headers"],
        json={"stop_ids": [second_stop_id]},
    )
    assert bad_reorder.status_code == 400, bad_reorder.text

    reorder_response = client.post(
        f"/api/review/trip-plans/{plan_id}/stops/reorder",
        headers=ctx["leader_headers"],
        json={"stop_ids": [second_stop_id, stop_id]},
    )
    assert reorder_response.status_code == 200, reorder_response.text
    reordered_stops = reorder_response.json()["stops"]
    assert [stop["id"] for stop in reordered_stops] == [second_stop_id, stop_id]
    assert [stop["sequence_no"] for stop in reordered_stops] == [1, 2]
    stale_plan_version = reorder_response.json()["row_version"]

    versioned_plan_update = client.patch(
        f"/api/review/trip-plans/{plan_id}",
        headers=ctx["leader_headers"],
        json={"title": "V07 Audit Trip Updated", "row_version": stale_plan_version},
    )
    assert versioned_plan_update.status_code == 200, versioned_plan_update.text
    assert versioned_plan_update.json()["row_version"] == stale_plan_version + 1
    stale_plan_update = client.patch(
        f"/api/review/trip-plans/{plan_id}",
        headers=ctx["leader_headers"],
        json={"title": "V07 Stale Trip Update", "row_version": stale_plan_version},
    )
    assert stale_plan_update.status_code == 409, stale_plan_update.text
    stale_plan_archive = client.post(
        f"/api/review/trip-plans/{plan_id}/archive",
        headers=ctx["leader_headers"],
        json={"row_version": stale_plan_version},
    )
    assert stale_plan_archive.status_code == 409, stale_plan_archive.text

    invalid_lat_response = client.post(
        f"/api/review/trip-plans/{plan_id}/preview-itinerary",
        headers=ctx["leader_headers"],
        json={
            "start_date": "2026-05-11",
            "origin_lat": 91,
            "origin_lng": 13.405,
        },
    )
    assert invalid_lat_response.status_code == 422, invalid_lat_response.text

    preview_response = client.post(
        f"/api/review/trip-plans/{plan_id}/preview-itinerary",
        headers=ctx["leader_headers"],
        json={
            "row_version": stale_plan_version,
            "start_date": "2026-05-11",
            "origin_name": "Berlin",
            "origin_lat": 52.52,
            "origin_lng": 13.405,
            "destination_name": "Munich",
            "destination_lat": 48.1351,
            "destination_lng": 11.582,
            "travel_mode": "drive",
            "avoid_weekends": True,
            "holiday_dates": ["2026-05-12", "not-a-date"],
            "stop_stays": {second_stop_id: 999, stop_id: -10},
        },
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["itinerary_preview"] is True
    assert preview["itinerary_summary"]["total_stay_days"] == 31
    assert "not-a-date" in preview["itinerary_summary"]["warnings"][0]
    persisted_before_generate = client.get(
        f"/api/review/trip-plans/{plan_id}",
        headers=ctx["leader_headers"],
    )
    assert persisted_before_generate.status_code == 200, persisted_before_generate.text
    persisted = persisted_before_generate.json()
    assert persisted["itinerary_summary"] is None
    assert persisted["end_date"] is None
    assert all(stop["planned_date"] is None for stop in persisted["stops"])

    itinerary_response = client.post(
        f"/api/review/trip-plans/{plan_id}/generate-itinerary",
        headers=ctx["leader_headers"],
        json={
            "start_date": "2026-05-11",
            "origin_name": "Berlin",
            "origin_lat": 52.52,
            "origin_lng": 13.405,
            "destination_name": "Munich",
            "destination_lat": 48.1351,
            "destination_lng": 11.582,
            "travel_mode": "drive",
            "avoid_weekends": True,
            "holiday_dates": ["2026-05-12"],
        },
    )
    assert itinerary_response.status_code == 200, itinerary_response.text
    itinerary = itinerary_response.json()
    assert itinerary["travel_mode"] == "drive"
    assert itinerary["holiday_dates"] == ["2026-05-12"]
    assert itinerary["itinerary_summary"]["total_stay_days"] == 3
    assert itinerary["itinerary_summary"]["calculated_end_date"] >= "2026-05-13"
    # The date that was asked for stays as it was asked for. What the route
    # works out to is reported beside it, and running past it is a risk to be
    # seen - overwriting the request would erase the very thing the risk is
    # measured against.
    summary = itinerary["itinerary_summary"]
    assert summary["calculated_end_date"], "the route does not say when it ends"
    assert summary["requested_end_date"] == itinerary["end_date"], (
        "generating a route rewrote the end date the reader asked for"
    )
    assert [stop["sequence_no"] for stop in itinerary["stops"]] == [1, 2]
    assert all(stop["planned_date"] and stop["planned_end_date"] for stop in itinerary["stops"])
    # A stop no longer carries one inbound journey: several colleagues reach the
    # same visit separately, so how each of them gets there is on their own leg.
    # The itinerary card reads it from there, and shows nothing rather than one
    # traveller's distance presented as everybody's.
    assert all(
        stop.get("travel_distance_km") is None for stop in itinerary["stops"]
    ), "a single inbound journey was written onto a visit the whole team reaches"
    assert itinerary["legs"], "the route was saved without any journeys"
    assert all(
        leg["distance_km"] is not None and leg["member_id"]
        for leg in itinerary["legs"]
    ), "a saved journey does not say how far it is or who travels it"

    stop_after_itinerary = next(stop for stop in itinerary["stops"] if stop["id"] == stop_id)
    second_stop_after_itinerary = next(stop for stop in itinerary["stops"] if stop["id"] == second_stop_id)
    stale_stop_version = stop_after_itinerary["row_version"]
    stale_archive_version = second_stop_after_itinerary["row_version"]
    versioned_stop_update = client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{stop_id}",
        headers=ctx["leader_headers"],
        json={"notes": "Versioned stop save", "row_version": stale_stop_version},
    )
    assert versioned_stop_update.status_code == 200, versioned_stop_update.text
    stale_stop_update = client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{stop_id}",
        headers=ctx["leader_headers"],
        json={"notes": "Stale stop save", "row_version": stale_stop_version},
    )
    assert stale_stop_update.status_code == 409, stale_stop_update.text

    archive_target_update = client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{second_stop_id}",
        headers=ctx["leader_headers"],
        json={"notes": "Archive conflict setup", "row_version": stale_archive_version},
    )
    assert archive_target_update.status_code == 200, archive_target_update.text
    stale_archive = client.post(
        f"/api/review/trip-plans/{plan_id}/stops/{second_stop_id}/archive",
        headers=ctx["leader_headers"],
        json={"row_version": stale_archive_version},
    )
    assert stale_archive.status_code == 409, stale_archive.text

    update_response = client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{stop_id}",
        headers=ctx["leader_headers"],
        json={
            "result_status": "Visited",
            "result_notes": "=Customer confirmed next action",
            "actual_visit_date": "2026-05-12",
            "actual_visit_period": "AM",
        },
    )
    assert update_response.status_code == 200, update_response.text

    activities = client.get(
        f"/api/leads/{ctx['lead_ids'][0]}/activities",
        headers=ctx["leader_headers"],
    )
    assert activities.status_code == 200, activities.text
    assert any("Trip visit: Visited" in row["summary"] for row in activities.json())

    followup_response = client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{stop_id}",
        headers=ctx["leader_headers"],
        json={
            "result_status": "Follow-up Needed",
            "result_notes": "=Customer confirmed next action",
            "actual_visit_date": "2026-05-12",
            "actual_visit_period": "AM",
            "visit_customer_needs": "Needs a higher power demo",
            "visit_competitor": "Competitor X",
            "visit_budget": "50000",
            "visit_decision_maker": "CTO",
            "visit_next_action": "Send quotation and sample schedule",
            "visit_followup_due_date": "2026-05-20",
            "visit_sample_needed": True,
            "visit_quote_needed": True,
        },
    )
    assert followup_response.status_code == 200, followup_response.text
    followup_stop = next(stop for stop in followup_response.json()["stops"] if stop["id"] == stop_id)
    assert followup_stop["visit_customer_needs"] == "Needs a higher power demo"
    assert followup_stop["followup_activity_id"]

    followup_activities = client.get(
        f"/api/leads/{ctx['lead_ids'][0]}/activities",
        headers=ctx["leader_headers"],
    )
    assert followup_activities.status_code == 200, followup_activities.text
    assert any("Trip follow-up: Send quotation" in row["summary"] for row in followup_activities.json())

    lead_after_followup = client.get(
        f"/api/leads/{ctx['lead_ids'][0]}",
        headers=ctx["leader_headers"],
    )
    assert lead_after_followup.status_code == 200, lead_after_followup.text
    assert lead_after_followup.json()["next_followup_date"] == "2026-05-20"

    execution_response = client.get(
        f"/api/review/trip-plans/{plan_id}/execution?date={followup_stop['planned_date']}",
        headers=ctx["leader_headers"],
    )
    assert execution_response.status_code == 200, execution_response.text
    execution = execution_response.json()
    assert execution["selected_date"] == followup_stop["planned_date"]
    assert any(stop["id"] == stop_id for stop in execution["stops"])

    execution_export = client.get(
        f"/api/review/trip-plans/{plan_id}/execution.md?date={followup_stop['planned_date']}",
        headers=ctx["leader_headers"],
    )
    assert execution_export.status_code == 200, execution_export.text
    assert "Visit Reports" in execution_export.text
    assert "Needs a higher power demo" in execution_export.text

    csv_response = client.get(
        f"/api/review/trip-plans/{plan_id}/export.csv",
        headers=ctx["leader_headers"],
    )
    assert csv_response.status_code == 200, csv_response.text
    csv_text = csv_response.text
    assert "'=V07 Candidate 1" in csv_text
    assert "'=Discuss formula-safe export" in csv_text
    assert "'=Customer confirmed next action" in csv_text


def check_v09_data_governance(client: TestClient, ctx: dict) -> None:
    customer = client.get(
        f"/api/customers/{ctx['customer_ids'][0]}",
        headers=ctx["leader_headers"],
    ).json()
    coordinate_update = client.patch(
        f"/api/customers/{ctx['customer_ids'][0]}",
        headers=ctx["leader_headers"],
        json={
            "lat": 54.123456,
            "lng": 14.123456,
            "country": "DE",
            "row_version": customer["row_version"],
        },
    )
    assert coordinate_update.status_code == 200, coordinate_update.text
    assert coordinate_update.json()["country"] == "Germany"

    audit_response = client.get(
        "/api/data/governance/coordinate-audit",
        headers=ctx["leader_headers"],
    )
    assert audit_response.status_code == 200, audit_response.text
    assert audit_response.json()["items"]

    export_response = client.post(
        "/api/data/export",
        headers=ctx["leader_headers"],
        json={"lead_ids": None},
    )
    assert export_response.status_code == 200, export_response.text
    preflight_response = client.post(
        "/api/data/preflight",
        headers=ctx["leader_headers"],
        files={"file": ("export.json", BytesIO(export_response.content), "application/json")},
    )
    assert preflight_response.status_code == 200, preflight_response.text
    preflight = preflight_response.json()
    assert preflight["source_snapshot"]["leads"] == 3
    assert "snapshot_before" in preflight
    assert "predicted" in preflight


def run() -> None:
    try:
        with TestClient(app) as client:
            ctx = seed_account_data(client)
            check_analysis_permission_and_candidate_pagination(client, ctx)
            check_trip_plan_activity_sync_and_csv_formula_escape(client, ctx)
            check_v09_data_governance(client, ctx)
        print("v0.7 review/trip regression passed")
    finally:
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
