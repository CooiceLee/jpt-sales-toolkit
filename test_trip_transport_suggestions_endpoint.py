"""Route-level anonymous transport suggestion endpoint regressions."""

from __future__ import annotations

import json
import shutil
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from test_trip_planner_free_stops import TEST_DIR, _require, _seed, _snapshot, app, close_db
from backend.services.trip_transport_suggestions import reset_transport_suggestion_service


def _payload(plan: dict, customer_stop_id: str, free_stop_id: str) -> dict:
    return {
        "row_version": plan["row_version"],
        "origin_name": "Draft Private Origin",
        "origin_lat": 48.7758,
        "origin_lng": 9.1829,
        "destination_name": "Draft Private Destination",
        "destination_lat": 50.1109,
        "destination_lng": 8.6821,
        "route_order_mode": "manual",
        "stop_order": [customer_stop_id, free_stop_id],
        "stop_stays": {customer_stop_id: 1, free_stop_id: 2},
        "leg_overrides": {
            f"{customer_stop_id}>{free_stop_id}": {
                "selected_mode": "other",
                "manual_time_hours": 2.5,
                "notes": "Manually confirmed transfer",
            }
        },
    }


def check_route_level_contract(client: TestClient, ctx: dict) -> None:
    plan_id = ctx["plan"]["id"]
    plan = _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/free-stops",
            headers=ctx["owner_headers"],
            json={
                "category": "hotel",
                "location_name": "Suggestion Private Rest Stop",
                "city": "Nuremberg",
                "country": "Germany",
                "lat": 49.4521,
                "lng": 11.0767,
                "stay_days": 2,
                "visit_purpose": "Rest only",
            },
        ),
        200,
    )
    customer_stop = next(item for item in plan["stops"] if item["stop_kind"] == "customer")
    free_stop = next(item for item in plan["stops"] if item["stop_kind"] == "free")
    payload = _payload(plan, customer_stop["id"], free_stop["id"])

    preview = _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/preview-itinerary",
            headers=ctx["owner_headers"],
            json=payload,
        ),
        200,
    )
    before = _snapshot()
    result = _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/transport-suggestions",
            headers=ctx["owner_headers"],
            json=payload,
        ),
        200,
    )
    assert _snapshot() == before, "transport suggestions must be zero-write"
    assert set(result) == {"generated_at", "privacy_notice", "warnings", "suggestions"}
    assert [item["leg_key"] for item in result["suggestions"]] == [
        item["leg_key"] for item in preview["legs"]
    ]
    assert [item["mode"] for item in result["suggestions"]] == [
        item["selected_mode"] for item in preview["legs"]
    ]
    assert any(free_stop["id"] in item["leg_key"] for item in result["suggestions"])
    manual = next(item for item in result["suggestions"] if item["mode"] == "other")
    assert manual["status"] == "manual_required"
    assert manual["time_hours"] is None and manual["travel_days"] is None
    assert all(item["requires_manual_confirmation"] for item in result["suggestions"])

    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in (
        "Suggestion Private Rest Stop",
        "Free Stop Munich Customer",
        "Frankfurt Airport",
        "Draft Private Origin",
        "Draft Private Destination",
        '"from_lat"',
        '"from_lng"',
        '"to_lat"',
        '"to_lng"',
    ):
        assert forbidden not in serialized
    for item in result["suggestions"]:
        if item["search_url"]:
            assert item["search_url"].startswith("https://www.google.com/")
    first_url = result["suggestions"][0]["search_url"]
    assert parse_qs(urlsplit(first_url).query)["origin"] == ["48.775800,9.182900"]

    cached = _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/transport-suggestions",
            headers=ctx["owner_headers"],
            json=payload,
        ),
        200,
    )
    assert all(item["cached"] for item in cached["suggestions"])
    refreshed = _require(
        client.post(
            f"/api/review/trip-plans/{plan_id}/transport-suggestions",
            headers=ctx["owner_headers"],
            json={**payload, "force_refresh": True},
        ),
        200,
    )
    assert all(item["cached"] is False for item in refreshed["suggestions"])
    assert _snapshot() == before


def check_permissions_and_input_boundary(client: TestClient, ctx: dict) -> None:
    plan_id = ctx["plan"]["id"]
    fresh = _require(
        client.get(f"/api/review/trip-plans/{plan_id}", headers=ctx["owner_headers"]),
        200,
    )
    stop_ids = [item["id"] for item in fresh["stops"]]
    payload = {
        "row_version": fresh["row_version"],
        "route_order_mode": "manual",
        "stop_order": stop_ids,
    }
    before = _snapshot()
    unauthorized = client.post(
        f"/api/review/trip-plans/{plan_id}/transport-suggestions",
        headers=ctx["other_headers"],
        json=payload,
    )
    assert unauthorized.status_code == 404
    for injected in (
        {"search_url": "https://127.0.0.1/private"},
        {"legs": [{"from_lat": 0, "from_lng": 0, "to_lat": 1, "to_lng": 1}]},
    ):
        response = client.post(
            f"/api/review/trip-plans/{plan_id}/transport-suggestions",
            headers=ctx["owner_headers"],
            json={**payload, **injected},
        )
        assert response.status_code == 422, response.text
    assert _snapshot() == before


def run() -> None:
    try:
        reset_transport_suggestion_service()
        close_db()
        with TestClient(app) as client:
            ctx = _seed(client)
            check_route_level_contract(client, ctx)
            check_permissions_and_input_boundary(client, ctx)
        print("PASS: route suggestions preserve preview order, privacy, permissions and zero-write")
    finally:
        reset_transport_suggestion_service()
        close_db()
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
