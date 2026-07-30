"""Regression: Leader packages are scoped to one Sales recipient."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import backend.repositories.base as base
from backend.repositories.base import init_db
from backend.routers.data_exchange import ExportRequest, export_data
from backend.services import CustomerService, LeadService


async def response_json(response) -> dict:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)
    return json.loads(b"".join(chunks))


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt-json-recipient-") as directory:
        db = Path(directory) / "source.sqlite"
        base._connection = None
        base._db_path = None
        init_db(db)
        conn = sqlite3.connect(db)
        for user_id, role in (
            ("leader", "leader"),
            ("sales-a", "sales"),
            ("sales-b", "sales"),
        ):
            conn.execute(
                """INSERT INTO users
                   (id, username, password_hash, display_name, role, is_active, created_at)
                   VALUES (?, ?, 'hash', ?, ?, 1, '2026-07-28T00:00:00')""",
                (user_id, user_id, user_id, role),
            )
        conn.commit()
        conn.close()

        customers = CustomerService()
        leads = LeadService()
        for suffix in ("a", "b"):
            customer = customers.create(
                {"display_name": f"Customer {suffix}"},
                "leader",
            )
            leads.create(
                {
                    "customer_id": customer["id"],
                    "title": f"Lead {suffix}",
                    "owner_id": f"sales-{suffix}",
                    "sales_stage": "Following",
                },
                "leader",
            )

        response = await export_data(
            ExportRequest(recipient_user_id="sales-a"),
            {"id": "leader", "display_name": "Leader", "role": "leader"},
        )
        payload = await response_json(response)
        assert payload["recipient_user_id"] == "sales-a"
        assert payload["export_scope"] == "owner"
        assert len(payload["leads"]) == 1
        assert payload["leads"][0]["lead"]["owner_id"] == "sales-a"
        assert len(payload["customers"]) == 1

        base.close_db()
        base._db_path = None


if __name__ == "__main__":
    asyncio.run(run())
    print("PASS: Leader JSON export is scoped to the selected Sales recipient")
