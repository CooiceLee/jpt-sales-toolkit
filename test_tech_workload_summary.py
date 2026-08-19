"""Focused API regression for the Tech navigation workload summary."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import (
    AfterSalesTaskRepository,
    CustomerRepository,
    LeadRepository,
    PreSalesTaskRepository,
    UserCredentialRepository,
    UserRepository,
    close_db,
)


PASSWORD = "WorkloadSummary2026!"
EXPECTED_KEYS = {
    "pre_sales_active_lead_count",
    "after_sales_active_lead_count",
}


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
    ids: dict[str, str] = {}
    for username, role in (
        ("leader.workload", "leader"),
        ("sales.workload", "sales"),
        ("tech.a.workload", "tech"),
        ("tech.b.workload", "tech"),
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


def create_lead(
    customers: CustomerRepository,
    leads: LeadRepository,
    leader_id: str,
    sales_id: str,
    label: str,
) -> tuple[str, str]:
    customer_id = customers.create({
        "display_name": f"{label} customer",
        "normalized_name": f"{label.lower()} customer",
        "country": "Germany",
    }, leader_id)
    lead_id = leads.create({
        "customer_id": customer_id,
        "owner_id": sales_id,
        "title": f"{label} sensitive project",
        "sales_stage": "Following",
        "estimated_value": 999999,
    }, leader_id)
    return customer_id, lead_id


def seed_workloads(ids: dict[str, str]) -> None:
    leader = ids["leader.workload"]
    sales = ids["sales.workload"]
    tech_a = ids["tech.a.workload"]
    tech_b = ids["tech.b.workload"]
    customers, leads = CustomerRepository(), LeadRepository()
    pre, after = PreSalesTaskRepository(), AfterSalesTaskRepository()

    records = {
        label: create_lead(customers, leads, leader, sales, label)
        for label in (
            "shared-active", "second-active", "terminal", "archived-task",
            "archived-lead", "archived-customer", "other-tech",
        )
    }

    # Two active tasks on one lead count once; Open and In Progress both count.
    shared = records["shared-active"][1]
    pre.create(shared, {"assignee_id": tech_a, "status": "Open",
                        "request_json": '{"secret":"must not leak"}'}, leader)
    pre.create(shared, {"assignee_id": tech_a, "status": "In Progress"}, leader)
    after.create(shared, {"assignee_id": tech_a, "status": "Open",
                          "issue_type": "Technical",
                          "issue_description": "must not leak"}, leader)
    after.create(shared, {"assignee_id": tech_a, "status": "In Progress",
                          "issue_type": "Quality",
                          "issue_description": "must not leak"}, leader)

    second = records["second-active"][1]
    pre.create(second, {"assignee_id": tech_a, "status": "In Progress"}, leader)
    after.create(second, {"assignee_id": tech_a, "status": "In Progress",
                          "issue_type": "Other", "issue_description": "active"}, leader)

    terminal = records["terminal"][1]
    for status in ("Completed", "Cancelled"):
        pre.create(terminal, {"assignee_id": tech_a, "status": status}, leader)
    for status in ("Resolved", "Closed"):
        after.create(terminal, {"assignee_id": tech_a, "status": status,
                                "issue_type": "Other", "issue_description": status}, leader)

    archived_task_lead = records["archived-task"][1]
    archived_pre = pre.create(
        archived_task_lead, {"assignee_id": tech_a, "status": "Open"}, leader,
    )
    archived_after = after.create(
        archived_task_lead,
        {"assignee_id": tech_a, "status": "Open", "issue_type": "Other",
         "issue_description": "archived"}, leader,
    )
    pre.archive(archived_pre, leader)
    after.archive(archived_after, leader)

    archived_lead = records["archived-lead"][1]
    pre.create(archived_lead, {"assignee_id": tech_a, "status": "Open"}, leader)
    after.create(archived_lead, {"assignee_id": tech_a, "status": "Open",
                                 "issue_type": "Other",
                                 "issue_description": "archived lead"}, leader)
    leads.archive(archived_lead, leader)

    archived_customer, customer_lead = records["archived-customer"]
    pre.create(customer_lead, {"assignee_id": tech_a, "status": "Open"}, leader)
    after.create(customer_lead, {"assignee_id": tech_a, "status": "Open",
                                 "issue_type": "Other",
                                 "issue_description": "archived customer"}, leader)
    customers.archive(archived_customer, leader)

    other = records["other-tech"][1]
    pre.create(other, {"assignee_id": tech_b, "status": "Open"}, leader)
    after.create(other, {"assignee_id": tech_b, "status": "Open",
                         "issue_type": "Other", "issue_description": "other"}, leader)

    # Repository-level task seeding deliberately bypasses TaskService's
    # aggregate synchronization, so set the Lead projection explicitly.
    for label, status in (
        ("shared-active", "Open"),
        ("second-active", "In Progress"),
        ("terminal", "Resolved"),
        ("archived-task", "None"),
        ("archived-lead", "Open"),
        ("archived-customer", "Open"),
        ("other-tech", "Open"),
    ):
        leads.conn.execute(
            "UPDATE leads SET service_status = ? WHERE id = ?",
            (status, records[label][1]),
        )
    leads.conn.commit()


def assert_contract(client: TestClient, headers: dict[str, dict[str, str]]) -> None:
    endpoint = "/api/tasks/workload-summary"
    expect(client.get(endpoint), 401, "anonymous workload summary")
    expect(client.get(endpoint, headers=headers["leader.workload"]), 403,
           "Leader cannot use Tech-only summary")
    expect(client.get(endpoint, headers=headers["sales.workload"]), 403,
           "Sales cannot use Tech-only summary")

    tech_a = expect(client.get(endpoint, headers=headers["tech.a.workload"]), 200,
                    "Tech A workload summary").json()
    assert set(tech_a) == EXPECTED_KEYS, tech_a
    assert tech_a == {
        "pre_sales_active_lead_count": 2,
        "after_sales_active_lead_count": 2,
    }
    assert all(type(value) is int for value in tech_a.values())

    tech_b = expect(client.get(endpoint, headers=headers["tech.b.workload"]), 200,
                    "Tech B workload summary").json()
    assert tech_b == {
        "pre_sales_active_lead_count": 1,
        "after_sales_active_lead_count": 1,
    }

    # The complete review remains commercial-role-only.
    expect(client.get("/api/review/dashboard", headers=headers["tech.a.workload"]), 403,
           "Tech review dashboard boundary")

    # Commercial navigation counts use the same active-status definition.
    # The terminal Resolved/Closed lead must not inflate the after-sales badge.
    leader_dashboard = expect(
        client.get("/api/review/dashboard", headers=headers["leader.workload"]),
        200,
        "Leader review dashboard",
    ).json()
    sales_dashboard = expect(
        client.get("/api/review/dashboard", headers=headers["sales.workload"]),
        200,
        "Sales review dashboard",
    ).json()
    assert leader_dashboard["service_open_count"] == 4, leader_dashboard
    assert sales_dashboard["service_open_count"] == 4, sales_dashboard


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_tech_workload_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {username: login(client, username) for username in ids}
                    seed_workloads(ids)
                    assert_contract(client, headers)
            finally:
                close_db()
    print("PASS: Tech workload summary scope, status and archive boundaries")


if __name__ == "__main__":
    main()
