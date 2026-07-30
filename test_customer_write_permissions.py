"""API regressions for customer read/write role separation."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserCredentialRepository, UserRepository, close_db


PASSWORD = "CustomerBoundary2026!"


def expect(response, status_code: int, label: str):
    assert response.status_code == status_code, (
        f"{label}: expected HTTP {status_code}, got {response.status_code}; "
        f"body={response.text[:500]}"
    )
    return response


def seed_accounts() -> dict[str, str]:
    users = UserRepository()
    credentials = UserCredentialRepository()
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    ids = {}
    for username, role in (
        ("customer.leader", "leader"),
        ("customer.owner", "sales"),
        ("customer.collaborator", "sales"),
        ("customer.watcher", "sales"),
        ("customer.other", "sales"),
    ):
        user_id = users.create(username, password_hash, username, role, "EU")
        credentials.create({
            "user_id": user_id,
            "password_hash": password_hash,
            "password_scheme": "legacy_sha256",
            "must_change_password": False,
        })
        ids[username] = user_id
    return ids


def login(client: TestClient, username: str) -> dict[str, str]:
    response = expect(client.post("/api/auth/login", json={
        "username": username,
        "password": PASSWORD,
    }), 200, f"login {username}")
    return {"Authorization": f"Bearer {response.json()['token']}"}


def seed_customer(client: TestClient, ids: dict, headers: dict) -> tuple[dict, dict, dict]:
    leader_headers = headers["customer.leader"]
    customer = expect(client.post("/api/customers", headers=leader_headers, json={
        "display_name": "Boundary Laser GmbH",
        "country": "Germany",
        "city": "Munich",
        "geocode_confidence": "high",
    }), 200, "create customer").json()
    contact = expect(client.post(
        f"/api/customers/{customer['id']}/contacts",
        headers=leader_headers,
        json={"name": "Boundary Contact", "email": "boundary@example.com"},
    ), 200, "create contact").json()
    lead = expect(client.post("/api/leads", headers=leader_headers, json={
        "customer_id": customer["id"],
        "owner_id": ids["customer.owner"],
        "title": "Boundary Lead",
        "sales_stage": "Following",
    }), 200, "create lead").json()
    for username, assignment_type in (
        ("customer.collaborator", "collaborator"),
        ("customer.watcher", "watcher"),
    ):
        expect(client.post(
            f"/api/leads/{lead['id']}/assignments",
            headers=leader_headers,
            json={"user_id": ids[username], "assignment_type": assignment_type},
        ), 200, f"assign {assignment_type}")
    return customer, contact, lead


def assert_unlinked_creator_is_provisional_owner(
    client: TestClient,
    ids: dict,
    headers: dict,
) -> None:
    creator_headers = headers["customer.watcher"]
    customer = expect(client.post("/api/customers", headers=creator_headers, json={
        "display_name": "Unlinked Bootstrap Customer",
        "country": "Germany",
    }), 200, "Sales creates unlinked customer").json()
    updated = expect(client.patch(
        f"/api/customers/{customer['id']}",
        headers=creator_headers,
        json={"city": "Hamburg", "row_version": customer["row_version"]},
    ), 200, "unlinked customer creator has provisional write access").json()

    lead = expect(client.post("/api/leads", headers=headers["customer.leader"], json={
        "customer_id": customer["id"],
        "owner_id": ids["customer.owner"],
        "title": "Bootstrap Permission Ends",
        "sales_stage": "Following",
    }), 200, "Leader links the provisional customer").json()
    expect(client.post(
        f"/api/leads/{lead['id']}/assignments",
        headers=headers["customer.leader"],
        json={"user_id": ids["customer.watcher"], "assignment_type": "watcher"},
    ), 200, "former creator becomes watcher")
    expect(client.patch(
        f"/api/customers/{customer['id']}",
        headers=creator_headers,
        json={"city": "Forbidden After Linking", "row_version": updated["row_version"]},
    ), 403, "active lead ends creator bootstrap permission")


def assert_read_write_boundary(
    client: TestClient,
    headers: dict,
    customer: dict,
    contact: dict,
) -> dict:
    customer_id = customer["id"]
    watcher_headers = headers["customer.watcher"]

    visible = expect(client.get(
        f"/api/customers/{customer_id}", headers=watcher_headers,
    ), 200, "watcher retains customer read access").json()
    expect(client.get(
        f"/api/customers/{customer_id}", headers=headers["customer.other"],
    ), 403, "unassigned sales cannot read customer")

    expect(client.patch(f"/api/customers/{customer_id}", headers=watcher_headers, json={
        "lat": 48.137,
        "lng": 11.575,
        "geocode_confidence": "high",
        "row_version": visible["row_version"],
    }), 403, "watcher cannot change coordinates")
    expect(client.post(
        f"/api/customers/{customer_id}/contacts",
        headers=watcher_headers,
        json={"name": "Forbidden Contact", "email": "forbidden@example.com"},
    ), 403, "watcher cannot create contact")
    expect(client.patch(
        f"/api/customers/{customer_id}/contacts/{contact['id']}",
        headers=watcher_headers,
        json={"position": "Forbidden"},
    ), 403, "watcher cannot update contact")
    expect(client.post(
        f"/api/customers/{customer_id}/contacts/{contact['id']}/archive",
        headers=watcher_headers,
    ), 403, "watcher cannot archive contact")
    expect(client.post(
        "/api/data/governance/batch-repair",
        headers=watcher_headers,
        json={"customer_ids": [customer_id], "country": "France"},
    ), 403, "watcher cannot use customer batch repair")

    owner_update = expect(client.patch(
        f"/api/customers/{customer_id}",
        headers=headers["customer.owner"],
        json={"city": "Berlin", "row_version": visible["row_version"]},
    ), 200, "owner can update customer").json()
    collaborator_update = expect(client.patch(
        f"/api/customers/{customer_id}",
        headers=headers["customer.collaborator"],
        json={"address": "Alexanderplatz", "row_version": owner_update["row_version"]},
    ), 200, "collaborator can update customer").json()
    leader_update = expect(client.patch(
        f"/api/customers/{customer_id}",
        headers=headers["customer.leader"],
        json={"region": "EU", "row_version": collaborator_update["row_version"]},
    ), 200, "Leader can update customer").json()
    return leader_update


def assert_intake_and_import_do_not_bypass(
    client: TestClient,
    ids: dict,
    headers: dict,
    customer: dict,
    lead: dict,
) -> None:
    watcher_headers = headers["customer.watcher"]
    expect(client.post("/api/intake/submit", headers=watcher_headers, json={
        "is_new_customer": False,
        "customer_id": customer["id"],
        "contact": {"name": "Injected Contact", "email": "injected@example.com"},
        "lead": {"title": "Injected Intake"},
        "owner_id": ids["customer.watcher"],
    }), 403, "watcher cannot use intake to mutate contact")

    before = client.get(
        f"/api/customers/{customer['id']}", headers=watcher_headers,
    ).json()
    payload = {
        "version": "v2.0",
        "customers": {
            customer["id"]: {
                **customer,
                "display_name": customer["display_name"],
                "city": "Injected Import City",
                "contacts": [{"name": "Injected Import Contact"}],
            },
        },
        "leads": [{
            "lead": {
                **lead,
                "owner_id": ids["customer.watcher"],
                "title": "Injected Import Lead",
            },
        }],
    }
    response = expect(client.post(
        "/api/data/import",
        headers=watcher_headers,
        files={"file": ("watcher.json", io.BytesIO(json.dumps(payload).encode()), "application/json")},
    ), 200, "watcher import is handled without mutation")
    assert response.json()["skipped_records"] >= 1
    after = client.get(
        f"/api/customers/{customer['id']}", headers=watcher_headers,
    ).json()
    assert after["city"] == before["city"]
    assert {item["name"] for item in after["contacts"]} == {
        item["name"] for item in before["contacts"]
    }


def assert_geocode_confidence_validation(
    client: TestClient,
    headers: dict,
    customer: dict,
) -> None:
    expect(client.post("/api/customers", headers=headers["customer.leader"], json={
        "display_name": "Invalid Confidence Create",
        "geocode_confidence": "certain",
    }), 422, "invalid confidence is rejected on create")
    expect(client.patch(
        f"/api/customers/{customer['id']}",
        headers=headers["customer.leader"],
        json={"geocode_confidence": "certain", "row_version": customer["row_version"]},
    ), 422, "invalid confidence is rejected on update")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_customer_write_boundary_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {username: login(client, username) for username in ids}
                    assert_unlinked_creator_is_provisional_owner(client, ids, headers)
                    customer, contact, lead = seed_customer(client, ids, headers)
                    latest = assert_read_write_boundary(client, headers, customer, contact)
                    assert_intake_and_import_do_not_bypass(
                        client, ids, headers, latest, lead,
                    )
                    assert_geocode_confidence_validation(client, headers, latest)
            finally:
                close_db()
    print("PASS: customer watcher read/write separation and confidence validation")


if __name__ == "__main__":
    main()
