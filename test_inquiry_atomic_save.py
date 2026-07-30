"""Regression tests for all-or-nothing inquiry panel saves."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import close_db
from test_authorization_role_boundary import expect, login, seed_accounts


def seed_inquiry(client: TestClient, ids: dict, headers: dict) -> tuple[dict, dict, dict]:
    customer = expect(client.post("/api/customers", headers=headers["leader.boundary"], json={
        "display_name": "Atomic Customer",
        "country": "Germany",
        "city": "Berlin",
    }), 200, "create atomic customer").json()
    contact = expect(client.post(
        f"/api/customers/{customer['id']}/contacts",
        headers=headers["leader.boundary"],
        json={"name": "Before Contact", "email": "before@example.com", "is_primary": True},
    ), 200, "create atomic contact").json()
    lead = expect(client.post("/api/leads", headers=headers["leader.boundary"], json={
        "customer_id": customer["id"],
        "primary_contact_id": contact["id"],
        "owner_id": ids["sales.a"],
        "title": "Before Lead",
        "sales_stage": "Following",
        "product_category": "Before Product",
    }), 200, "create atomic lead").json()
    expect(client.post(
        f"/api/leads/{lead['id']}/pre-sales-tasks",
        headers=headers["leader.boundary"],
        json={"assignee_id": ids["tech.a"], "request_json": '{"sample":"atomic"}'},
    ), 200, "assign tech for aggregate permission check")
    expect(client.post(
        f"/api/leads/{lead['id']}/assignments",
        headers=headers["leader.boundary"],
        json={"user_id": ids["sales.b"], "assignment_type": "watcher"},
    ), 200, "assign watcher for aggregate permission check")
    return customer, contact, lead


def snapshot(client: TestClient, headers: dict, customer_id: str, lead_id: str) -> dict:
    customer = expect(
        client.get(f"/api/customers/{customer_id}", headers=headers),
        200,
        "read atomic customer",
    ).json()
    lead = expect(
        client.get(f"/api/leads/{lead_id}", headers=headers),
        200,
        "read atomic lead",
    ).json()
    return {"customer": customer, "contact": customer["contacts"][0], "lead": lead}


def write_counts(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        audits = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        activities = conn.execute("SELECT COUNT(*) FROM lead_activities").fetchone()[0]
        return audits, activities
    finally:
        conn.close()


def payload(state: dict, *, suffix: str = "After") -> dict:
    return {
        "customer": {
            "display_name": f"{suffix} Customer",
            "city": "Hamburg",
            "row_version": state["customer"]["row_version"],
        },
        "contact": {
            "contact_id": state["contact"]["id"],
            "updated_at": state["contact"]["updated_at"],
            "name": f"{suffix} Contact",
            "email": f"{suffix.lower()}@example.com",
        },
        "lead": {
            "title": f"{suffix} Lead",
            "product_category": f"{suffix} Product",
            "row_version": state["lead"]["row_version"],
        },
    }


def assert_unchanged(before: dict, after: dict) -> None:
    for entity, fields in {
        "customer": ("display_name", "city", "row_version"),
        "contact": ("name", "email", "updated_at"),
        "lead": ("title", "product_category", "row_version"),
    }.items():
        assert {key: before[entity].get(key) for key in fields} == {
            key: after[entity].get(key) for key in fields
        }, f"{entity} changed despite aggregate rollback"


def run_atomic_save_regression(client: TestClient, ids: dict, headers: dict, db_path: Path) -> None:
    customer, _, lead = seed_inquiry(client, ids, headers)
    leader = headers["leader.boundary"]
    initial = snapshot(client, leader, customer["id"], lead["id"])

    contact_conflict = payload(initial, suffix="ContactConflict")
    contact_conflict["contact"]["updated_at"] = "stale-contact-version"
    before_counts = write_counts(db_path)
    expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=leader,
        json=contact_conflict,
    ), 409, "contact conflict rolls back customer")
    assert_unchanged(initial, snapshot(client, leader, customer["id"], lead["id"]))
    assert write_counts(db_path) == before_counts, "contact conflict leaked audit/activity rows"

    lead_conflict = payload(initial, suffix="LeadConflict")
    lead_conflict["lead"]["row_version"] += 100
    expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=leader,
        json=lead_conflict,
    ), 409, "lead conflict rolls back customer and contact")
    assert_unchanged(initial, snapshot(client, leader, customer["id"], lead["id"]))
    assert write_counts(db_path) == before_counts, "lead conflict leaked audit/activity rows"

    watcher_payload = payload(initial, suffix="WatcherForbidden")
    watcher_payload.pop("lead")
    expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=headers["sales.b"],
        json=watcher_payload,
    ), 403, "watcher cannot save customer and contact only")
    assert_unchanged(initial, snapshot(client, leader, customer["id"], lead["id"]))
    expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=headers["tech.a"],
        json=payload(initial, suffix="TechForbidden"),
    ), 403, "task-assigned tech cannot edit aggregate")
    assert_unchanged(initial, snapshot(client, leader, customer["id"], lead["id"]))

    updated = expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=headers["sales.a"],
        json=payload(initial),
    ), 200, "owner atomically saves customer contact and lead").json()
    saved = snapshot(client, leader, customer["id"], lead["id"])
    assert saved["customer"]["display_name"] == "After Customer"
    assert saved["customer"]["row_version"] == initial["customer"]["row_version"] + 1
    assert saved["contact"]["name"] == "After Contact"
    assert saved["contact"]["email"] == "after@example.com"
    assert saved["lead"]["title"] == "After Lead"
    assert saved["lead"]["row_version"] == initial["lead"]["row_version"] + 1
    assert updated["customer"]["display_name"] == "After Customer"

    after_success_counts = write_counts(db_path)
    expect(client.patch(
        f"/api/leads/{lead['id']}/aggregate",
        headers=leader,
        json=payload(initial, suffix="StaleRetry"),
    ), 409, "stale aggregate retry is rejected")
    assert_unchanged(saved, snapshot(client, leader, customer["id"], lead["id"]))
    assert write_counts(db_path) == after_success_counts, "stale retry leaked write records"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_atomic_inquiry_") as directory:
        close_db()
        data_dir = Path(directory)
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(data_dir)}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {name: login(client, name) for name in ids}
                    run_atomic_save_regression(
                        client,
                        ids,
                        headers,
                        data_dir / "database.sqlite",
                    )
            finally:
                close_db()
    print("PASS: inquiry aggregate save is atomic, optimistic and permission-safe")


if __name__ == "__main__":
    main()
