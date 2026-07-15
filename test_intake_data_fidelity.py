"""Intake parser, contact persistence and owner-boundary regression."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory(prefix="jpt_intake_fidelity_")
os.environ["JPT_DATA_DIR"] = TEST_DIR.name

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import app  # noqa: E402
from backend.repositories import close_db  # noqa: E402
from scripts.create_test_accounts import upsert_account  # noqa: E402


def auth_headers(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def main() -> None:
    with TestClient(app) as client:
        leader_id = upsert_account("intake_leader", "IntakeLeader2026", "Intake Leader", "leader", None)
        sales_id = upsert_account("intake_sales", "IntakeSales2026", "Intake Sales", "sales", None)
        sales_headers = auth_headers(client, "intake_sales", "IntakeSales2026")
        email = """GROSJEAN Gaetan<g.grosjean@staubli.com> 在 2026年3月9日 写道：
Regards
Gaëtan GROSJEAN
Global Manufacturing Engineering Coordinator
STAUBLI FAVERGES
74210 Faverges-Seythenex / FR
Mobile: +33 6 72 14 71 70
www.staubli.com"""
        parsed = client.post("/api/intake/parse-email", headers=sales_headers, json={"raw_email": email})
        assert parsed.status_code == 200, parsed.text
        data = parsed.json()
        assert data["email"] == "g.grosjean@staubli.com"
        assert data["inquiry_date"] == "2026-03-09"
        assert data["phone"] == "+33 6 72 14 71 70"

        payload = {
            "is_new_customer": True,
            "customer": {"display_name": data["company_name"], "country": data["country"]},
            "contact": {
                "name": data["contact_name"], "position": data["contact_position"],
                "email": data["email"], "phone": data["phone"], "is_primary": True,
            },
            "lead": {
                "title": "Parsed inquiry", "source_channel": "Email",
                "original_email": email, "inquiry_date": data["inquiry_date"],
                "special_requirements": "Keep surface clean",
            },
            "owner_id": sales_id,
        }
        created = client.post("/api/intake/submit", headers=sales_headers, json=payload)
        assert created.status_code == 200, created.text
        lead = client.get(f"/api/leads/{created.json()['lead_id']}", headers=sales_headers).json()
        assert lead["inquiry_date"] == "2026-03-09"
        assert lead["special_requirements"] == "Keep surface clean"
        assert lead["customer"]["contacts"][0]["email"] == data["email"]

        payload["owner_id"] = leader_id
        denied = client.post("/api/intake/submit", headers=sales_headers, json=payload)
        assert denied.status_code == 403, denied.text

    intake_source = Path("frontend/js/modules/intake-submit.js").read_text(encoding="utf-8")
    form_source = Path("frontend/js/modules/inquiry-form.js").read_text(encoding="utf-8")
    renderer_source = Path("frontend/js/modules/inquiry-field-renderer.js").read_text(encoding="utf-8")
    assert "contact: buildContact(fields)" in intake_source
    assert "inquiry_date: fields.inquiry_date" in intake_source
    assert "const safeValue = escapeHtml(value);" in renderer_source
    assert "escapeHtml(value || '-')" in form_source
    close_db()
    TEST_DIR.cleanup()
    print("PASS: intake parser, contact persistence, owner boundary and form escaping contracts")


if __name__ == "__main__":
    main()
