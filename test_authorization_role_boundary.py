"""API regression for Leader, Sales and task-scoped Tech authorization."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserCredentialRepository, UserRepository, close_db


PASSWORD = "RoleBoundary2026!"
TECH_SENSITIVE_FIELDS = {
    "estimated_value",
    "deal_amount",
    "currency",
    "quotation_id",
    "quotation_date",
    "po_number",
    "po_date",
    "lost_reason_code",
    "lost_reason_text",
}
SENSITIVE_VALUES = {
    "estimated_value": 85000,
    "deal_amount": 72500,
    "currency": "USD",
    "quotation_id": "Q-SECURITY-2026",
    "quotation_date": "2026-07-10",
    "po_number": "PO-PRIVATE-2026",
    "po_date": "2026-07-11",
    "lost_reason_code": "price",
    "lost_reason_text": "Internal commercial assessment",
}


def expect(response, status_code: int, label: str):
    """Assert an API status while preserving useful endpoint evidence."""
    assert response.status_code == status_code, (
        f"{label}: expected HTTP {status_code}, got {response.status_code}; "
        f"body={response.text[:500]}"
    )
    return response


def seed_accounts() -> dict[str, str]:
    """Create real persisted identities and compatible local credentials."""
    users = UserRepository()
    credentials = UserCredentialRepository()
    legacy_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    ids = {}
    for name, role in (
        ("leader.boundary", "leader"),
        ("sales.a", "sales"),
        ("sales.b", "sales"),
        ("tech.a", "tech"),
        ("tech.b", "tech"),
    ):
        user_id = users.create(name, legacy_hash, name.title(), role, "EU")
        if not credentials.get_by_user_id(user_id):
            credentials.create({
                "user_id": user_id,
                "password_hash": legacy_hash,
                "password_scheme": "legacy_sha256",
                "must_change_password": False,
            })
        ids[name] = user_id
    return ids


def login(client: TestClient, username: str) -> dict[str, str]:
    response = expect(
        client.post("/api/auth/login", json={"username": username, "password": PASSWORD}),
        200,
        f"login {username}",
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def create_customer(client: TestClient, headers: dict, label: str) -> dict:
    customer = expect(client.post("/api/customers", headers=headers, json={
        "display_name": f"{label} Laser Systems",
        "website": f"https://{label.lower()}.example.com",
        "industry": "Industrial Automation",
        "country": "Germany",
        "city": "Munich",
        "address": f"{label} Service Plant",
        "region": "EU",
    }), 200, f"create {label} customer").json()
    expect(client.post(f"/api/customers/{customer['id']}/contacts", headers=headers, json={
        "name": f"{label} Service Contact",
        "position": "Plant Engineer",
        "email": f"service-{label.lower()}@example.com",
        "phone": "+49-89-555-0100",
        "whatsapp": "+49-170-555-0100",
        "is_primary": True,
    }), 200, f"create {label} contact")
    return customer


def create_lead(
    client: TestClient,
    headers: dict,
    customer_id: str,
    owner_id: str,
    label: str,
) -> dict:
    lead = expect(client.post("/api/leads", headers=headers, json={
        "customer_id": customer_id,
        "owner_id": owner_id,
        "title": f"{label} Fiber Laser Project",
        "sales_stage": "Following",
        "product_category": "Fiber Laser",
        "application": "Precision welding",
        "special_requirements": "Validate pulse stability at customer site",
    }), 200, f"create {label} lead").json()
    payload = {**SENSITIVE_VALUES, "row_version": lead["row_version"]}
    return expect(
        client.patch(f"/api/leads/{lead['id']}", headers=headers, json=payload),
        200,
        f"seed {label} sensitive commercial fields",
    ).json()


def seed_business_data(client: TestClient, ids: dict, headers: dict) -> dict:
    customers = {
        name: create_customer(client, headers["leader.boundary"], name)
        for name in ("PreSales", "AfterSales", "Unrelated")
    }
    leads = {
        "pre": create_lead(
            client, headers["leader.boundary"], customers["PreSales"]["id"],
            ids["sales.a"], "PreSales",
        ),
        "after": create_lead(
            client, headers["leader.boundary"], customers["AfterSales"]["id"],
            ids["sales.a"], "AfterSales",
        ),
        "other": create_lead(
            client, headers["leader.boundary"], customers["Unrelated"]["id"],
            ids["sales.b"], "Unrelated",
        ),
    }
    pre = expect(client.post(
        f"/api/leads/{leads['pre']['id']}/pre-sales-tasks",
        headers=headers["leader.boundary"],
        json={"assignee_id": ids["tech.a"], "request_json": '{"sample":"10W blue"}'},
    ), 200, "assign Tech A pre-sales task").json()
    after = expect(client.post(
        f"/api/leads/{leads['after']['id']}/after-sales-tasks",
        headers=headers["leader.boundary"],
        json={
            "assignee_id": ids["tech.a"],
            "issue_type": "Technical",
            "issue_description": "Intermittent pulse stability at production speed",
        },
    ), 200, "assign Tech A after-sales task").json()
    other_pre = expect(client.post(
        f"/api/leads/{leads['other']['id']}/pre-sales-tasks",
        headers=headers["leader.boundary"],
        json={"assignee_id": ids["tech.b"], "request_json": '{"sample":"20W green"}'},
    ), 200, "assign unrelated pre-sales task").json()
    other_after = expect(client.post(
        f"/api/leads/{leads['other']['id']}/after-sales-tasks",
        headers=headers["leader.boundary"],
        json={
            "assignee_id": ids["tech.b"],
            "issue_type": "Quality",
            "issue_description": "Unrelated beam quality investigation",
        },
    ), 200, "assign unrelated after-sales task").json()
    return {
        "customers": customers,
        "leads": leads,
        "pre": pre,
        "after": after,
        "other_pre": other_pre,
        "other_after": other_after,
    }


def assert_role_visibility(client: TestClient, headers: dict, data: dict) -> None:
    expected = {
        "leader.boundary": {"pre", "after", "other"},
        "sales.a": {"pre", "after"},
        "sales.b": {"other"},
        "tech.a": {"pre", "after"},
        "tech.b": {"other"},
    }
    lead_names = {lead["id"]: name for name, lead in data["leads"].items()}
    for username, visible_names in expected.items():
        response = expect(
            client.get("/api/leads", headers=headers[username]),
            200,
            f"{username} lead visibility",
        )
        actual = {lead_names[item["id"]] for item in response.json()}
        assert actual == visible_names, f"{username}: expected {visible_names}, got {actual}"

    for name in ("pre", "after"):
        leader_view = expect(client.get(
            f"/api/leads/{data['leads'][name]['id']}", headers=headers["leader.boundary"],
        ), 200, f"Leader reads {name} lead").json()
        assert all(leader_view.get(field) == value for field, value in SENSITIVE_VALUES.items())

        tech_view = expect(client.get(
            f"/api/leads/{data['leads'][name]['id']}", headers=headers["tech.a"],
        ), 200, f"Tech A reads assigned {name} lead").json()
        leaked = TECH_SENSITIVE_FIELDS.intersection(tech_view)
        assert not leaked, f"Tech A assigned {name} lead leaked sensitive fields: {sorted(leaked)}"

    tech_list = client.get("/api/leads", headers=headers["tech.a"]).json()
    for lead in tech_list:
        leaked = TECH_SENSITIVE_FIELDS.intersection(lead)
        assert not leaked, f"Tech A lead list leaked sensitive fields: {sorted(leaked)}"

    expect(client.get(
        f"/api/leads/{data['leads']['other']['id']}", headers=headers["tech.a"],
    ), 403, "Tech A reads unrelated lead")


def assert_customer_boundary(client: TestClient, headers: dict, data: dict) -> None:
    customer = expect(client.get(
        f"/api/customers/{data['customers']['PreSales']['id']}", headers=headers["tech.a"],
    ), 200, "Tech A reads assigned service customer").json()
    assert customer["display_name"] == "PreSales Laser Systems"
    assert customer["contacts"][0]["email"] == "service-presales@example.com"
    assert customer["contacts"][0]["phone"] == "+49-89-555-0100"

    after_customer = expect(client.get(
        f"/api/customers/{data['customers']['AfterSales']['id']}", headers=headers["tech.a"],
    ), 200, "Tech A reads assigned after-sales customer").json()
    assert after_customer["contacts"][0]["email"] == "service-aftersales@example.com"

    expect(client.get(
        f"/api/customers/{data['customers']['Unrelated']['id']}", headers=headers["tech.a"],
    ), 403, "Tech A reads unrelated customer")
    expect(client.get("/api/customers", headers=headers["tech.a"]), 403, "Tech A lists customers")

    expect(client.post("/api/customers", headers=headers["tech.a"], json={
        "display_name": "Forbidden Tech Customer",
    }), 403, "Tech A creates customer")
    expect(client.patch(
        f"/api/customers/{customer['id']}",
        headers=headers["tech.a"],
        json={"city": "Forbidden Update", "row_version": customer["row_version"]},
    ), 403, "Tech A edits assigned customer")
    contact_id = customer["contacts"][0]["id"]
    expect(client.post(f"/api/customers/{customer['id']}/contacts", headers=headers["tech.a"], json={
        "name": "Forbidden New Contact", "email": "forbidden@example.com",
    }), 403, "Tech A creates contact for assigned customer")
    expect(client.patch(
        f"/api/customers/{customer['id']}/contacts/{contact_id}",
        headers=headers["tech.a"],
        json={"position": "Forbidden Contact Edit"},
    ), 403, "Tech A edits assigned customer contact")
    expect(client.post(
        f"/api/customers/{customer['id']}/contacts/{contact_id}/archive",
        headers=headers["tech.a"],
    ), 403, "Tech A archives assigned customer contact")


def assert_lead_mutation_boundary(client: TestClient, ids: dict, headers: dict, data: dict) -> None:
    assigned = client.get(
        f"/api/leads/{data['leads']['pre']['id']}", headers=headers["tech.a"],
    ).json()
    expect(client.post("/api/leads", headers=headers["tech.a"], json={
        "customer_id": data["customers"]["PreSales"]["id"],
        "owner_id": ids["sales.a"],
        "title": "Forbidden Tech Lead",
    }), 403, "Tech A creates lead")
    expect(client.patch(
        f"/api/leads/{assigned['id']}",
        headers=headers["tech.a"],
        json={"application": "Forbidden edit", "row_version": assigned["row_version"]},
    ), 403, "Tech A edits assigned lead")


def assert_task_boundary(client: TestClient, ids: dict, headers: dict, data: dict) -> None:
    pre_list = expect(client.get(
        "/api/pre-sales-tasks", headers=headers["tech.a"],
        params={"assignee_id": ids["tech.b"]},
    ), 200, "Tech A pre-sales task list").json()
    after_list = expect(client.get(
        "/api/after-sales-tasks", headers=headers["tech.a"],
        params={"assignee_id": ids["tech.b"]},
    ), 200, "Tech A after-sales task list").json()
    assert {item["id"] for item in pre_list} == {data["pre"]["id"]}
    assert {item["id"] for item in after_list} == {data["after"]["id"]}

    expect(client.patch(f"/api/pre-sales-tasks/{data['pre']['id']}", headers=headers["tech.a"], json={
        "assignee_id": ids["tech.b"], "row_version": data["pre"]["row_version"],
    }), 403, "Tech A reassigns own pre-sales task")
    expect(client.patch(f"/api/after-sales-tasks/{data['after']['id']}", headers=headers["tech.a"], json={
        "assignee_id": ids["tech.b"], "row_version": data["after"]["row_version"],
    }), 403, "Tech A reassigns own after-sales task")

    expect(client.patch(f"/api/pre-sales-tasks/{data['other_pre']['id']}", headers=headers["tech.a"], json={
        "status": "In Progress", "row_version": data["other_pre"]["row_version"],
    }), 403, "Tech A edits unrelated pre-sales task")
    expect(client.patch(f"/api/after-sales-tasks/{data['other_after']['id']}", headers=headers["tech.a"], json={
        "status": "In Progress", "row_version": data["other_after"]["row_version"],
    }), 403, "Tech A edits unrelated after-sales task")

    expect(client.patch(f"/api/pre-sales-tasks/{data['pre']['id']}", headers=headers["tech.a"], json={
        "status": "In Progress", "result_json": '{"finding":"stable"}',
        "row_version": data["pre"]["row_version"],
    }), 200, "Tech A updates own pre-sales result")
    expect(client.patch(f"/api/after-sales-tasks/{data['after']['id']}", headers=headers["tech.a"], json={
        "status": "In Progress", "solution": "Inspect cooling and timing signals",
        "row_version": data["after"]["row_version"],
    }), 200, "Tech A updates own after-sales result")

    expect(client.post(
        f"/api/pre-sales-tasks/{data['pre']['id']}/archive", headers=headers["tech.a"],
    ), 403, "Tech A archives own pre-sales task")
    expect(client.post(
        f"/api/after-sales-tasks/{data['after']['id']}/archive", headers=headers["tech.a"],
    ), 403, "Tech A archives own after-sales task")


def assert_feature_boundary(client: TestClient, headers: dict) -> None:
    expect(client.get("/api/review/dashboard", headers=headers["tech.a"]), 403, "Tech A Review access")
    expect(client.post("/api/intake/parse-email", headers=headers["tech.a"], json={
        "raw_email": "Technical user must not access intake",
    }), 403, "Tech A Intake access")
    expect(client.post("/api/data/export", headers=headers["tech.a"], json={
        "lead_ids": None,
    }), 403, "Tech A Data Exchange access")


def assert_task_scope_lifecycle(client: TestClient, headers: dict, data: dict) -> None:
    """An archived assignment must remove access, while restore must recover it."""
    lead_url = f"/api/leads/{data['leads']['pre']['id']}"
    customer_url = f"/api/customers/{data['customers']['PreSales']['id']}"
    task_url = f"/api/pre-sales-tasks/{data['pre']['id']}"
    expect(client.post(f"{task_url}/archive", headers=headers["leader.boundary"]), 200,
           "Leader archives Tech A pre-sales task")
    expect(client.get(lead_url, headers=headers["tech.a"]), 403,
           "Tech A reads lead after assignment archive")
    expect(client.get(customer_url, headers=headers["tech.a"]), 403,
           "Tech A reads customer after assignment archive")
    expect(client.post(f"{task_url}/restore", headers=headers["leader.boundary"]), 200,
           "Leader restores Tech A pre-sales task")
    expect(client.get(lead_url, headers=headers["tech.a"]), 200,
           "Tech A reads lead after assignment restore")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_role_boundary_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {name: login(client, name) for name in ids}
                    data = seed_business_data(client, ids, headers)
                    assert_role_visibility(client, headers, data)
                    assert_customer_boundary(client, headers, data)
                    assert_lead_mutation_boundary(client, ids, headers, data)
                    assert_task_boundary(client, ids, headers, data)
                    assert_feature_boundary(client, headers)
                    assert_task_scope_lifecycle(client, headers, data)
            finally:
                close_db()
    print("PASS: Leader/Sales/Tech API authorization boundaries and Tech masking")


if __name__ == "__main__":
    main()
