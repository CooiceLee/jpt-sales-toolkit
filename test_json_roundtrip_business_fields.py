"""Regression: JSON round-trip reuses source IDs and synchronizes business fields."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import backend.repositories.base as base
from backend.repositories.base import init_db
from backend.routers.data_exchange import (
    ExportRequest,
    LEAD_JSON_SYNC_FIELDS,
    _lead_import_update_fields,
    export_data,
    import_data,
)
from backend.services import CustomerService, LeadService


class Upload:
    def __init__(self, payload: dict):
        self.filename = "exchange.json"
        self._content = json.dumps(payload).encode("utf-8")

    async def read(self) -> bytes:
        return self._content


def use_db(path: Path) -> None:
    base.close_db()
    base._db_path = None
    init_db(path)


def add_users(path: Path) -> None:
    conn = sqlite3.connect(path)
    for user_id, role in (("leader", "leader"), ("sales-a", "sales")):
        conn.execute(
            """INSERT INTO users
               (id, username, password_hash, display_name, role, is_active, created_at)
               VALUES (?, ?, 'hash', ?, ?, 1, '2026-07-28T00:00:00')""",
            (user_id, user_id, user_id, role),
        )
    conn.commit()
    conn.close()


async def response_json(response) -> dict:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)
    return json.loads(b"".join(chunks))


async def run() -> None:
    assert "owner_id" not in LEAD_JSON_SYNC_FIELDS
    assert {
        "sales_stage",
        "next_followup_date",
        "quotation_id",
        "deal_amount",
        "lost_reason_text",
        "special_requirements",
    } <= LEAD_JSON_SYNC_FIELDS
    collaborator_patch = _lead_import_update_fields(
        {
            "title": "Allowed",
            "sales_stage": "Won",
            "deal_amount": None,
            "special_requirements": None,
            "owner_id": "other",
        },
        "collaborator",
    )
    assert collaborator_patch == {
        "title": "Allowed",
        "special_requirements": None,
    }

    with tempfile.TemporaryDirectory(prefix="jpt-json-roundtrip-") as directory:
        root = Path(directory)
        leader_db = root / "leader.sqlite"
        sales_db = root / "sales.sqlite"
        leader = {"id": "leader", "display_name": "Leader", "role": "leader"}
        sales = {"id": "sales-a", "display_name": "Sales A", "role": "sales"}

        try:
            use_db(leader_db)
            add_users(leader_db)
            customer = CustomerService().create(
                {"display_name": "Round-trip Customer"},
                "leader",
            )
            original = LeadService().create(
                {
                    "customer_id": customer["id"],
                    "title": "Leader original",
                    "owner_id": "sales-a",
                    "sales_stage": "Following",
                    "fulfillment_status": "Not Started",
                    "service_status": "None",
                    "product_series": "Series A",
                    "quotation_id": "Q-OLD",
                    "quotation_date": "2026-07-01",
                    "deal_amount": 1200,
                    "currency": "EUR",
                    "next_followup_date": "2026-08-01",
                    "special_requirements": "Original requirement",
                    "products_detail": "Original products",
                },
                "leader",
            )
            original_id = original["id"]
            leader_package = await response_json(await export_data(
                ExportRequest(recipient_user_id="sales-a"),
                leader,
            ))
            exported = leader_package["leads"][0]["lead"]
            assert exported["special_requirements"] == "Original requirement"

            use_db(sales_db)
            add_users(sales_db)
            first = await import_data(Upload(leader_package), sales)
            assert first["new_leads"] == 1 and not first["errors"], first
            imported = LeadService().list("sales-a", "sales", limit=10)[0]
            assert json.loads(imported["extra_json"])["source_lead_id"] == original_id

            LeadService().update(
                imported["id"],
                {
                    "title": "Sales updated",
                    "sales_stage": "Lost",
                    "fulfillment_status": "Not Started",
                    "service_status": "Resolved",
                    "product_series": None,
                    "quotation_id": None,
                    "quotation_date": "",
                    "deal_amount": None,
                    "currency": "",
                    "next_followup_date": None,
                    "lost_reason_code": "budget",
                    "lost_reason_text": "Budget frozen",
                    "special_requirements": None,
                    "products_detail": "Updated products",
                },
                "sales-a",
                "owner",
                imported["row_version"],
            )
            sales_package = await response_json(await export_data(
                ExportRequest(),
                sales,
            ))
            returned = sales_package["leads"][0]["lead"]
            assert returned["special_requirements"] is None
            assert json.loads(returned["extra_json"])["source_lead_id"] == original_id
            # Simulate stale/incorrect package ownership metadata. Existing
            # ownership must remain local and is never part of the sync contract.
            returned["owner_id"] = "leader"

            use_db(leader_db)
            result = await import_data(Upload(sales_package), leader)
            assert result["new_leads"] == 0
            assert result["updated_leads"] == 1
            assert result["skipped_records"] == 0
            assert not result["errors"], result["errors"]

            all_leads = LeadService().list("leader", "leader", limit=10)
            assert len(all_leads) == 1
            updated = LeadService().get(original_id)
            assert updated["owner_id"] == "sales-a"
            assert updated["title"] == "Sales updated"
            assert updated["sales_stage"] == "Lost"
            assert updated["service_status"] == "Resolved"
            assert updated["product_series"] is None
            assert updated["quotation_id"] is None
            assert updated["quotation_date"] == ""
            assert updated["deal_amount"] is None
            assert updated["currency"] == ""
            assert updated["next_followup_date"] is None
            assert updated["lost_reason_code"] == "budget"
            assert updated["lost_reason_text"] == "Budget frozen"
            assert updated["special_requirements"] is None
            assert updated["products_detail"] == "Updated products"
        finally:
            base.close_db()
            base._db_path = None


if __name__ == "__main__":
    asyncio.run(run())
    print("PASS: JSON business fields round-trip, clear values, and preserve owner identity")
