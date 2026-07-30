"""Regression: Sales import remaps source contacts and exposes owned leads."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

from fastapi import HTTPException

import backend.repositories.base as base
from backend.repositories.base import init_db
from backend.routers.data_exchange import import_data
from backend.services import LeadService


class Upload:
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name

    async def read(self) -> bytes:
        return self.path.read_bytes()


def add_users(db: Path) -> None:
    conn = sqlite3.connect(db)
    for user_id, role in (("leader", "leader"), ("sales-a", "sales"), ("sales-b", "sales")):
        conn.execute(
            """INSERT INTO users
               (id, username, password_hash, display_name, role, is_active, created_at)
               VALUES (?, ?, 'hash', ?, ?, 1, '2026-07-28T00:00:00')""",
            (user_id, user_id, user_id, role),
        )
    conn.commit()
    conn.close()


def lead_item(lead_id: str, customer_id: str, contact_id: str, owner_id: str) -> dict:
    return {
        "lead": {
            "id": lead_id,
            "customer_id": customer_id,
            "primary_contact_id": contact_id,
            "title": f"Lead {lead_id}",
            "owner_id": owner_id,
            "sales_stage": "Following",
        },
        "activities": [],
        "pre_sales_tasks": [],
        "after_sales_tasks": [],
        "attachments": [],
    }


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt-json-distribution-") as directory:
        root = Path(directory)
        db = root / "target.sqlite"
        payload_path = root / "leader-export.json"
        base._connection = None
        base._db_path = None
        init_db(db)
        add_users(db)

        customers = {}
        leads = []
        for suffix, owner in (("a", "sales-a"), ("b", "sales-b")):
            customer_id = f"source-customer-{suffix}"
            contact_id = f"source-contact-{suffix}"
            contacts = [{
                "id": contact_id,
                "customer_id": customer_id,
                "name": f"Contact {suffix}",
                "email": None,
                "is_primary": 1,
            }]
            if suffix == "a":
                contacts.extend([
                    {
                        "id": "source-contact-a-secondary",
                        "customer_id": customer_id,
                        "name": "Secondary contact",
                        "email": None,
                        "is_primary": 0,
                    },
                    {
                        "id": "source-contact-a-email-only",
                        "customer_id": customer_id,
                        "name": None,
                        "email": "a@example.com",
                        "is_primary": 0,
                    },
                ])
            customers[customer_id] = {
                "id": customer_id,
                "display_name": f"Customer {suffix}",
                "contacts": contacts,
            }
            leads.append(lead_item(f"source-lead-{suffix}", customer_id, contact_id, owner))

        payload_path.write_text(json.dumps({
            "version": "v2.0",
            "export_time": "2026-07-28T00:00:00",
            "exported_by": "leader",
            "exporter_name": "Leader",
            "recipient_user_id": "sales-a",
            "customers": customers,
            "leads": leads,
        }), encoding="utf-8")
        sales = {"id": "sales-a", "username": "sales-a", "display_name": "Sales A", "role": "sales"}
        try:
            await import_data(
                Upload(payload_path),
                {"id": "sales-b", "display_name": "Sales B", "role": "sales"},
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("A recipient-scoped package must reject another Sales account")

        first = await import_data(Upload(payload_path), sales)
        assert first["new_leads"] == 1 and first["skipped_records"] == 1
        assert not first["errors"], first["errors"]

        visible = LeadService().list("sales-a", "sales", limit=100)
        assert len(visible) == 1 and visible[0]["owner_id"] == "sales-a"
        contact_id = visible[0]["primary_contact_id"]
        assert contact_id and contact_id != "source-contact-a"
        contacts = visible[0]["customer"]["contacts"]
        assert len(contacts) == 3
        assert any(item["id"] == contact_id for item in contacts)
        assert sum(item["email"] is None for item in contacts) == 2

        second = await import_data(Upload(payload_path), sales)
        assert second["new_leads"] == 0 and second["updated_leads"] == 1
        assert second["skipped_records"] == 1 and not second["errors"]

        base._connection.close()
        base._connection = None
        base._db_path = None


if __name__ == "__main__":
    asyncio.run(run())
    print("PASS: Sales JSON distribution remaps contacts and preserves visibility")
