"""Security regressions for global Tech boundaries and member identities."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import (
    LeadRepository,
    PreSalesTaskRepository,
    close_db,
)
from test_authorization_role_boundary import (
    TECH_SENSITIVE_FIELDS,
    create_lead,
    expect,
    login,
    seed_accounts,
    seed_business_data,
)


def assert_global_tech_precedence(client: TestClient, ids: dict, headers: dict, data: dict) -> None:
    """Legacy bad assignments must never elevate a global Tech role."""
    repo = LeadRepository()
    repo.conn.execute(
        """
        INSERT INTO lead_assignments (
            id, lead_id, user_id, assignment_type, created_at, created_by
        ) VALUES (?, ?, ?, 'collaborator', datetime('now'), ?)
        """,
        (str(uuid4()), data["leads"]["pre"]["id"], ids["tech.a"], ids["leader.boundary"]),
    )
    repo.conn.execute(
        "UPDATE leads SET owner_id = ? WHERE id = ?",
        (ids["tech.a"], data["leads"]["other"]["id"]),
    )
    repo.conn.commit()

    assigned = expect(client.get(
        f"/api/leads/{data['leads']['pre']['id']}", headers=headers["tech.a"],
    ), 200, "Tech collaborator with task remains task-scoped").json()
    assert not TECH_SENSITIVE_FIELDS.intersection(assigned)
    expect(client.get(
        f"/api/leads/{data['leads']['other']['id']}", headers=headers["tech.a"],
    ), 403, "Tech owner without a task gets no lead access")


def assert_tech_assignment_rejected(client: TestClient, ids: dict, headers: dict, data: dict) -> None:
    """Tech members cannot become commercial owners or collaborators."""
    expect(client.post("/api/leads", headers=headers["leader.boundary"], json={
        "customer_id": data["customers"]["PreSales"]["id"],
        "owner_id": ids["tech.a"],
        "title": "Forbidden Tech-owned lead",
    }), 400, "Leader creates Tech-owned lead")

    current = data["leads"]["after"]
    expect(client.patch(
        f"/api/leads/{current['id']}", headers=headers["leader.boundary"],
        json={"owner_id": ids["tech.a"], "row_version": current["row_version"]},
    ), 400, "Leader changes owner to Tech")
    expect(client.post(
        f"/api/leads/{current['id']}/assignments", headers=headers["leader.boundary"],
        json={"user_id": ids["tech.a"], "assignment_type": "collaborator"},
    ), 400, "Leader adds Tech collaborator")


def assert_activity_values_hidden(client: TestClient, headers: dict, data: dict) -> None:
    activities = expect(client.get(
        f"/api/leads/{data['leads']['pre']['id']}/activities",
        headers=headers["tech.a"],
    ), 200, "Tech lists assigned lead activities").json()
    leaked = [
        item for item in activities
        if item.get("changed_field") in TECH_SENSITIVE_FIELDS
    ]
    assert not leaked, f"Tech activity feed leaked commercial changes: {leaked}"


def _upload(client: TestClient, lead_id: str, headers: dict, category: str, name: str) -> dict:
    return expect(client.post(
        f"/api/leads/{lead_id}/attachments",
        headers=headers,
        data={"category": category},
        files={"file": (name, f"%PDF-1.4\n{name}\n".encode(), "application/pdf")},
    ), 200, f"upload {category} attachment").json()


def assert_quotation_attachment_hidden(client: TestClient, headers: dict, data: dict) -> None:
    lead_id = data["leads"]["pre"]["id"]
    quotation = _upload(
        client, lead_id, headers["leader.boundary"], "quotation", "private-quote.pdf",
    )
    report = _upload(
        client, lead_id, headers["leader.boundary"], "report", "technical-report.pdf",
    )

    visible = expect(client.get(
        f"/api/leads/{lead_id}/attachments", headers=headers["tech.a"],
    ), 200, "Tech lists attachments").json()
    assert visible == []
    expect(client.get(
        f"/api/leads/{lead_id}/attachments/{quotation['id']}/download",
        headers=headers["tech.a"],
    ), 403, "Tech downloads quotation")
    expect(client.post(
        f"/api/leads/{lead_id}/attachments", headers=headers["tech.a"],
        data={"category": "quotation"},
        files={"file": ("forbidden.pdf", b"%PDF-1.4\n", "application/pdf")},
    ), 403, "Tech uploads quotation")
    expect(client.post(
        f"/api/leads/{lead_id}/attachments", headers=headers["tech.a"],
        data={"category": "report"},
        files={"file": (
            "duplicate-as-report.pdf", b"%PDF-1.4\nprivate-quote.pdf\n", "application/pdf",
        )},
    ), 403, "Tech relabels duplicate quotation upload")
    expect(client.patch(
        f"/api/leads/{lead_id}/attachments/{report['id']}", headers=headers["tech.a"],
        json={"original_name": "forbidden-update.pdf"},
    ), 403, "Tech updates technical attachment")
    expect(client.post(
        f"/api/leads/{lead_id}/attachments/{quotation['id']}/archive",
        headers=headers["tech.a"],
    ), 403, "Tech archives quotation")
    expect(client.post(
        f"/api/leads/{lead_id}/attachments/{report['id']}/archive",
        headers=headers["tech.a"],
    ), 403, "Tech archives technical attachment")


def assert_tech_task_whitelist(client: TestClient, headers: dict, data: dict) -> None:
    expect(client.patch(
        f"/api/pre-sales-tasks/{data['pre']['id']}", headers=headers["tech.a"],
        json={"request_json": '{"commercial":"changed"}', "row_version": data["pre"]["row_version"]},
    ), 403, "Tech changes pre-sales request")
    expect(client.patch(
        f"/api/after-sales-tasks/{data['after']['id']}", headers=headers["tech.a"],
        json={"issue_description": "changed scope", "row_version": data["after"]["row_version"]},
    ), 403, "Tech changes after-sales request")

    expect(client.post(
        f"/api/pre-sales-tasks/{data['pre']['id']}/archive",
        headers=headers["leader.boundary"],
    ), 200, "Leader archives assigned task")
    archived = PreSalesTaskRepository().get_by_id(data["pre"]["id"])
    expect(client.patch(
        f"/api/pre-sales-tasks/{data['pre']['id']}", headers=headers["tech.a"],
        json={"status": "Completed", "row_version": archived["row_version"]},
    ), 403, "Tech changes archived task")


def assert_tech_formal_follow_up_rejected(client: TestClient, headers: dict, data: dict) -> None:
    lead_id = data["leads"]["after"]["id"]
    expect(client.post(f"/api/leads/{lead_id}/activities", headers=headers["tech.a"], json={
        "action_type": "follow_up", "content": "Forbidden formal follow-up",
    }), 403, "Tech creates formal follow-up")
    follow_up = expect(client.post(
        f"/api/leads/{lead_id}/activities", headers=headers["leader.boundary"],
        json={"action_type": "follow_up", "content": "Leader formal follow-up"},
    ), 200, "Leader creates formal follow-up").json()
    activity_url = f"/api/leads/{lead_id}/activities/{follow_up['activity_id']}"
    expect(client.patch(activity_url, headers=headers["tech.a"], json={
        "content": "Forbidden edit",
    }), 403, "Tech edits formal follow-up")
    expect(client.post(f"{activity_url}/archive", headers=headers["tech.a"]), 403,
           "Tech archives formal follow-up")

    expect(client.post(f"/api/leads/{lead_id}/activities", headers=headers["tech.a"], json={
        "action_type": "comment", "content": "Allowed task comment",
    }), 403, "Tech adds lead comment outside task update")


def assert_username_case_unique(client: TestClient, headers: dict) -> None:
    first = expect(client.post(
        "/api/authorization/members", headers=headers["leader.boundary"],
        json={"username": "Case.Member", "display_name": "Case Member", "role": "sales"},
    ), 201, "create mixed-case member").json()
    expect(client.post(
        "/api/authorization/members", headers=headers["leader.boundary"],
        json={"username": "case.member", "display_name": "Duplicate Case", "role": "tech"},
    ), 400, "create case-colliding member")
    expect(client.patch(
        f"/api/authorization/members/{first['id']}", headers=headers["leader.boundary"],
        json={"username": "LEADER.BOUNDARY"},
    ), 400, "rename member to case-colliding username")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_security_regressions_") as directory:
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(Path(directory))}):
            try:
                with TestClient(create_app()) as client:
                    ids = seed_accounts()
                    headers = {name: login(client, name) for name in ids}
                    data = seed_business_data(client, ids, headers)
                    assert_global_tech_precedence(client, ids, headers, data)
                    assert_tech_assignment_rejected(client, ids, headers, data)
                    assert_activity_values_hidden(client, headers, data)
                    assert_quotation_attachment_hidden(client, headers, data)
                    assert_tech_formal_follow_up_rejected(client, headers, data)
                    assert_tech_task_whitelist(client, headers, data)
                    assert_username_case_unique(client, headers)
            finally:
                close_db()
    print("PASS: global Tech security boundaries and case-insensitive member identity")


if __name__ == "__main__":
    main()
