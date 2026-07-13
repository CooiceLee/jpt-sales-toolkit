"""Lead detail field persistence and strict contract regression."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory(prefix="jpt_lead_fields_")
os.environ["JPT_DATA_DIR"] = TEST_DIR.name

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.repositories import close_db, LeadRepository  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


def auth_headers(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def main() -> None:
    with TestClient(app) as client:
        leader_id = upsert_account("field_leader", "FieldLeader2026", "Field Leader", "leader", None)
        headers = auth_headers(client, "field_leader", "FieldLeader2026")
        customer = client.post("/api/customers", headers=headers, json={"display_name": "Field Customer"})
        assert customer.status_code == 200, customer.text
        created = client.post("/api/leads", headers=headers, json={
            "customer_id": customer.json()["id"], "owner_id": leader_id,
            "title": "Field Lead", "source_channel": "Email",
            "original_email": "Original <message>", "inquiry_date": "2026-07-01",
            "special_requirements": "Initial special", "potential_needs": "Initial need",
            "products_detail": "Initial products",
        })
        assert created.status_code == 200, created.text
        lead_id = created.json()["id"]
        lead = client.get(f"/api/leads/{lead_id}", headers=headers).json()
        assert lead["special_requirements"] == "Initial special"
        assert lead["potential_needs"] == "Initial need"
        assert lead["products_detail"] == "Initial products"

        repo = LeadRepository()
        raw = repo.get_by_id(lead_id)
        extra = json.loads(raw["extra_json"])
        extra["source_lead_id"] = "source-123"
        repo.update(lead_id, {"extra_json": json.dumps(extra)}, leader_id, raw["row_version"])
        lead = client.get(f"/api/leads/{lead_id}", headers=headers).json()
        updated = client.patch(f"/api/leads/{lead_id}", headers=headers, json={
            "source_channel": "Exhibition", "original_email": "Updated body",
            "inquiry_date": "2026-07-02", "special_requirements": "Updated special",
            "estimated_value": 2500, "row_version": lead["row_version"],
        })
        assert updated.status_code == 200, updated.text
        lead = client.get(f"/api/leads/{lead_id}", headers=headers).json()
        assert (lead["source_channel"], lead["inquiry_date"]) == ("Exhibition", "2026-07-02")
        cleared = client.patch(f"/api/leads/{lead_id}", headers=headers, json={
            "special_requirements": None, "estimated_value": None,
            "row_version": lead["row_version"],
        })
        assert cleared.status_code == 200, cleared.text
        lead = client.get(f"/api/leads/{lead_id}", headers=headers).json()
        assert lead["special_requirements"] is None and lead["estimated_value"] is None
        stored = json.loads(repo.get_by_id(lead_id)["extra_json"])
        assert stored["source_lead_id"] == "source-123"
        assert stored["potential_needs"] == "Initial need" and "special_requirements" not in stored
        rejected = client.patch(f"/api/leads/{lead_id}", headers=headers, json={
            "unsupported_field": "ignored before", "row_version": lead["row_version"],
        })
        assert rejected.status_code == 422, rejected.text

    close_db()
    TEST_DIR.cleanup()
    panel_source = Path("frontend/js/modules/inquiry-panel.js").read_text(encoding="utf-8")
    assert "{ id: 'evaluation', label: 'Evaluation' }" in panel_source
    print("PASS: lead detail fields persist, clear, preserve metadata and reject unknown keys")


if __name__ == "__main__":
    main()
