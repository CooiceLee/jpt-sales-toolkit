#!/usr/bin/env python3
"""Independent regressions for coordinate bounds, map permissions and dirty data."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import (
    CustomerRepository,
    UserCredentialRepository,
    UserRepository,
    close_db,
)


PASSWORD = "CoordinateIntegrity2026!"


def expect(response, status: int, label: str):
    assert response.status_code == status, (
        f"{label}: expected {status}, got {response.status_code}: {response.text[:500]}"
    )
    return response


def seed_accounts() -> dict[str, str]:
    users = UserRepository()
    credentials = UserCredentialRepository()
    password_hash = hashlib.sha256(PASSWORD.encode()).hexdigest()
    result = {}
    for username, role in (
        ("coord.leader", "leader"),
        ("coord.owner", "sales"),
        ("coord.collaborator", "sales"),
        ("coord.watcher", "sales"),
    ):
        user_id = users.create(username, password_hash, username, role, "EU")
        credentials.create({
            "user_id": user_id,
            "password_hash": password_hash,
            "password_scheme": "legacy_sha256",
            "must_change_password": False,
        })
        result[username] = user_id
    return result


def login(client: TestClient, username: str) -> dict[str, str]:
    response = expect(client.post("/api/auth/login", json={
        "username": username, "password": PASSWORD,
    }), 200, f"login {username}")
    return {"Authorization": f"Bearer {response.json()['token']}"}


def map_record(client: TestClient, headers: dict, customer_id: str) -> tuple[dict, dict]:
    payload = expect(client.get("/api/review/map", headers=headers), 200, "load map").json()
    records = [*payload["points"], *payload["missing_locations"]]
    record = next(item for item in records if item["customer_id"] == customer_id)
    return payload, record


def run_contract(client: TestClient) -> None:
    ids = seed_accounts()
    headers = {name: login(client, name) for name in ids}
    leader = headers["coord.leader"]

    expect(client.post("/api/customers", headers=leader, json={
        "display_name": "Invalid Latitude", "lat": 90.01, "lng": 0,
    }), 422, "create rejects latitude above 90")
    expect(client.post("/api/data/governance/batch-repair", headers=leader, json={
        "customer_ids": [], "lat": 0, "lng": -180.01,
    }), 422, "batch repair rejects longitude below -180")
    expect(client.post("/api/intake/submit", headers=leader, json={
        "is_new_customer": True,
        "customer": {"display_name": "Invalid Intake", "lat": 999, "lng": 0},
        "lead": {"title": "Invalid Intake Lead"},
        "owner_id": ids["coord.owner"],
    }), 422, "intake repository guard returns 422")

    customer = expect(client.post("/api/customers", headers=leader, json={
        "display_name": "Coordinate GmbH", "country": "Germany",
        "city": "Munich", "postal_code": "80331", "address": "Old address",
        "lat": 48.137, "lng": 11.575, "normalized_address": "Old normalized",
        "geocode_source": "manual", "geocode_confidence": "high",
        "geocode_locked": True,
    }), 200, "create valid customer").json()
    lead = expect(client.post("/api/leads", headers=leader, json={
        "customer_id": customer["id"], "owner_id": ids["coord.owner"],
        "title": "Coordinate Lead", "sales_stage": "Following",
    }), 200, "create lead").json()
    for username, assignment_type in (
        ("coord.collaborator", "collaborator"),
        ("coord.watcher", "watcher"),
    ):
        expect(client.post(f"/api/leads/{lead['id']}/assignments", headers=leader, json={
            "user_id": ids[username], "assignment_type": assignment_type,
        }), 200, f"assign {assignment_type}")

    for username, expected in (
        ("coord.leader", True),
        ("coord.owner", True),
        ("coord.collaborator", True),
        ("coord.watcher", False),
    ):
        _, record = map_record(client, headers[username], customer["id"])
        assert record["can_edit"] is expected, f"wrong can_edit for {username}"

    changed = expect(client.patch(f"/api/customers/{customer['id']}", headers=leader, json={
        "city": "Berlin", "row_version": customer["row_version"],
    }), 200, "advance customer version").json()
    expect(client.patch(f"/api/customers/{customer['id']}", headers=leader, json={
        "lat": 49, "lng": 12, "row_version": customer["row_version"],
    }), 409, "stale coordinate save conflicts")
    current = expect(client.get(
        f"/api/customers/{customer['id']}", headers=leader,
    ), 200, "reload after conflict").json()
    assert (current["lat"], current["lng"]) == (48.137, 11.575)

    expect(client.patch(f"/api/customers/{customer['id']}", headers=leader, json={
        "lat": 0, "lng": 181, "row_version": changed["row_version"],
    }), 422, "update rejects longitude above 180")
    cleared = expect(client.patch(f"/api/customers/{customer['id']}", headers=leader, json={
        "address": "", "city": "", "postal_code": "", "country": "",
        "normalized_address": "", "row_version": changed["row_version"],
    }), 200, "explicit location-field clearing").json()
    for field in ("address", "city", "postal_code", "country", "normalized_address"):
        assert cleared[field] == "", f"{field} was not cleared"

    repo = CustomerRepository()
    repo.conn.execute(
        """UPDATE customers SET country = 'Germany', lat = 999, lng = -999,
           geocode_source = 'manual', geocode_confidence = 'high', geocode_locked = 1
           WHERE id = ?""",
        (customer["id"],),
    )
    repo.conn.commit()
    payload, dirty = map_record(client, leader, customer["id"])
    assert dirty["coordinate_quality"] == "country_fallback"
    assert dirty["needs_geocode"] is True and dirty["invalid_coordinates"] is True
    assert payload["summary"]["exact_points"] == 0

    repo.conn.execute(
        "UPDATE customers SET country = NULL, lat = 999, lng = NULL WHERE id = ?",
        (customer["id"],),
    )
    repo.conn.commit()
    _, missing = map_record(client, leader, customer["id"])
    assert missing["invalid_coordinates"] is True
    assert missing["can_edit"] is True


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_coordinate_integrity_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    run_contract(client)
            finally:
                close_db()
    print("PASS: coordinate bounds, stale saves, map can_edit and dirty-coordinate fallback")


if __name__ == "__main__":
    main()
