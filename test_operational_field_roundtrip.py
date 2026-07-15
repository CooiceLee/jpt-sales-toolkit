"""Roundtrip and authorization regressions for imported operational fields."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import close_db
from test_authorization_role_boundary import expect, login, seed_accounts


def create_customer(client: TestClient, headers: dict, name: str) -> dict:
    return expect(client.post("/api/customers", headers=headers, json={
        "display_name": name,
        "country": "Germany",
    }), 200, f"create customer {name}").json()


def create_contact(client: TestClient, headers: dict, customer_id: str, name: str) -> dict:
    return expect(client.post(
        f"/api/customers/{customer_id}/contacts",
        headers=headers,
        json={"name": name, "email": f"{name.lower()}@example.com"},
    ), 200, f"create contact {name}").json()


def assert_lead_fields(client: TestClient, ids: dict, headers: dict) -> dict:
    customer = create_customer(client, headers["leader.boundary"], "Primary Customer")
    other = create_customer(client, headers["leader.boundary"], "Other Customer")
    first = create_contact(client, headers["leader.boundary"], customer["id"], "First")
    second = create_contact(client, headers["leader.boundary"], customer["id"], "Second")
    foreign = create_contact(client, headers["leader.boundary"], other["id"], "Foreign")

    base = {
        "customer_id": customer["id"],
        "owner_id": ids["sales.a"],
        "title": "Operational field lead",
        "quantity_text": "2 demo units",
    }
    expect(client.post("/api/leads", headers=headers["leader.boundary"], json={
        **base, "primary_contact_id": foreign["id"],
    }), 400, "reject cross-customer contact on create")

    lead = expect(client.post("/api/leads", headers=headers["leader.boundary"], json={
        **base, "primary_contact_id": first["id"],
    }), 200, "create lead with operational fields").json()
    assert lead["primary_contact_id"] == first["id"]
    assert lead["quantity_text"] == "2 demo units"

    expect(client.patch(
        f"/api/leads/{lead['id']}", headers=headers["leader.boundary"],
        json={"primary_contact_id": foreign["id"], "row_version": lead["row_version"]},
    ), 400, "reject cross-customer contact on update")
    updated = expect(client.patch(
        f"/api/leads/{lead['id']}", headers=headers["leader.boundary"],
        json={
            "primary_contact_id": second["id"],
            "quantity_text": "4 production units",
            "row_version": lead["row_version"],
        },
    ), 200, "update lead operational fields").json()
    assert updated["primary_contact_id"] == second["id"]
    assert updated["quantity_text"] == "4 production units"

    expect(client.post(
        f"/api/customers/{customer['id']}/contacts/{first['id']}/archive",
        headers=headers["leader.boundary"],
    ), 200, "archive old contact")
    expect(client.patch(
        f"/api/leads/{lead['id']}", headers=headers["leader.boundary"],
        json={"primary_contact_id": first["id"], "row_version": updated["row_version"]},
    ), 400, "reject archived contact")
    return updated


def assert_after_sales_fields(client: TestClient, ids: dict, headers: dict, lead: dict) -> None:
    task = expect(client.post(
        f"/api/leads/{lead['id']}/after-sales-tasks",
        headers=headers["leader.boundary"],
        json={
            "assignee_id": ids["tech.a"],
            "issue_type": "Technical",
            "issue_description": "Cooling instability",
            "solution": "Inspect coolant flow",
            "customer_satisfaction": "Pending confirmation",
            "lessons_learned": "Record inlet temperature",
            "remarks": "Follow up Friday",
        },
    ), 200, "create after-sales result fields").json()
    assert task["customer_satisfaction"] == "Pending confirmation"
    assert task["lessons_learned"] == "Record inlet temperature"
    assert task["remarks"] == "Follow up Friday"

    updated = expect(client.patch(
        f"/api/after-sales-tasks/{task['id']}", headers=headers["tech.a"],
        json={
            "status": "Resolved",
            "customer_satisfaction": "Satisfied",
            "lessons_learned": "Add a coolant checklist",
            "remarks": "Customer confirmed stability",
            "row_version": task["row_version"],
        },
    ), 200, "Tech updates assigned result fields").json()
    assert updated["customer_satisfaction"] == "Satisfied"
    expect(client.patch(
        f"/api/after-sales-tasks/{task['id']}", headers=headers["tech.a"],
        json={"issue_type": "Quality", "row_version": updated["row_version"]},
    ), 403, "Tech cannot change request fields")
    expect(client.patch(
        f"/api/after-sales-tasks/{task['id']}", headers=headers["sales.b"],
        json={"remarks": "Out of scope", "row_version": updated["row_version"]},
    ), 403, "unrelated Sales access remains denied")

    rows = expect(client.get(
        "/api/after-sales-tasks", headers=headers["leader.boundary"],
        params={"lead_id": lead["id"]},
    ), 200, "read after-sales result fields").json()
    stored = next(row for row in rows if row["id"] == task["id"])
    assert stored["lessons_learned"] == "Add a coolant checklist"
    assert stored["remarks"] == "Customer confirmed stability"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_operational_fields_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {name: login(client, name) for name in ids}
                    lead = assert_lead_fields(client, ids, headers)
                    assert_after_sales_fields(client, ids, headers, lead)
            finally:
                close_db()
    print("PASS: operational fields roundtrip with contact and role boundaries")


if __name__ == "__main__":
    main()
