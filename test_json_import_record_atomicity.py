"""Regression: one malformed JSON record cannot leave a partial entity behind."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

import backend.repositories.base as base
from backend.repositories.base import init_db
from backend.routers.data_exchange import import_data


class Upload:
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name

    async def read(self) -> bytes:
        return self.path.read_bytes()


def lead(lead_id: str, customer_id: str, contact_id: str) -> dict:
    return {
        "lead": {
            "id": lead_id,
            "customer_id": customer_id,
            "primary_contact_id": contact_id,
            "title": lead_id,
            "owner_id": "sales",
            "sales_stage": "Following",
        },
        "activities": [],
        "pre_sales_tasks": [],
        "after_sales_tasks": [],
        "attachments": [],
    }


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt-json-record-atomicity-") as directory:
        root = Path(directory)
        db = root / "target.sqlite"
        source = root / "source.json"
        base._connection = None
        base._db_path = None
        init_db(db)
        conn = sqlite3.connect(db)
        for user_id, role in (("leader", "leader"), ("sales", "sales")):
            conn.execute(
                """INSERT INTO users
                   (id, username, password_hash, display_name, role, is_active, created_at)
                   VALUES (?, ?, 'hash', ?, ?, 1, '2026-07-28T00:00:00')""",
                (user_id, user_id, user_id, role),
            )
        conn.commit()
        conn.close()

        customers = {
            "good-customer": {
                "id": "good-customer",
                "display_name": "Good customer",
                "contacts": [{
                    "id": "good-contact",
                    "name": "Good contact",
                    "email": None,
                }],
            },
            "bad-customer": {
                "id": "bad-customer",
                "display_name": "Bad customer",
                "contacts": [
                    {"id": "partial-contact", "name": "Must roll back", "email": None},
                    {"id": "invalid-contact", "name": None, "email": None},
                ],
            },
        }
        source.write_text(json.dumps({
            "version": "v2.0",
            "export_time": "2026-07-28T00:00:00",
            "exported_by": "leader",
            "customers": customers,
            "leads": [
                lead("good-lead", "good-customer", "good-contact"),
                lead("bad-lead", "bad-customer", "partial-contact"),
            ],
        }), encoding="utf-8")

        report = await import_data(
            Upload(source),
            {"id": "sales", "display_name": "Sales", "role": "sales"},
        )
        assert report["new_customers"] == 1
        assert report["new_leads"] == 1
        assert report["skipped_records"] == 1
        assert len(report["errors"]) == 2

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM customer_contacts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM customers WHERE display_name = 'Bad customer'"
        ).fetchone()[0] == 0
        conn.close()
        base.close_db()
        base._db_path = None


if __name__ == "__main__":
    asyncio.run(run())
    print("PASS: malformed JSON records roll back without partial entities")
