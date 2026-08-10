"""Persistence helpers for offline Tech task packages."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from .base import generate_uuid, now_iso


class TechTaskExchangeRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_batch(self, package_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM tech_task_exchange_batches WHERE package_id = ?",
            (package_id,),
        ).fetchone()
        return dict(row) if row else None

    def latest_imported_assignment(
        self, organization_id: str, tech_user_id: str
    ) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT * FROM tech_task_exchange_batches
               WHERE organization_id = ? AND recipient_user_id = ?
                 AND package_type = 'tech_task_assignment'
                 AND direction = 'leader_to_tech' AND status = 'imported'
               ORDER BY created_at DESC, imported_at DESC, package_id DESC
               LIMIT 1""",
            (organization_id, tech_user_id),
        ).fetchone()
        return dict(row) if row else None

    def latest_imported_result(
        self, organization_id: str, tech_user_id: str
    ) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT * FROM tech_task_exchange_batches
               WHERE organization_id = ? AND source_user_id = ?
                 AND package_type = 'tech_task_results'
                 AND direction = 'tech_to_leader' AND status = 'imported'
               ORDER BY created_at DESC, imported_at DESC, package_id DESC
               LIMIT 1""",
            (organization_id, tech_user_id),
        ).fetchone()
        return dict(row) if row else None

    def imported_result_batches(
        self, organization_id: str, tech_user_id: str, leader_user_id: str
    ) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM tech_task_exchange_batches
               WHERE organization_id = ? AND source_user_id = ?
                 AND recipient_user_id = ?
                 AND package_type = 'tech_task_results'
                 AND direction = 'tech_to_leader' AND status = 'imported'
               ORDER BY created_at, imported_at, package_id""",
            (organization_id, tech_user_id, leader_user_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_batch(
        self,
        package: dict,
        status: str,
        *,
        imported_by: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO tech_task_exchange_batches (
                package_id, package_type, direction, organization_id,
                source_user_id, recipient_user_id, parent_package_id,
                payload_sha256, manifest_json, status, created_at,
                imported_at, imported_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package["package_id"], package["package_type"], package["direction"],
                package["organization_id"], package["source_user_id"],
                package["recipient_user_id"], package.get("parent_package_id"),
                package["payload_sha256"],
                json.dumps(package, ensure_ascii=False, separators=(",", ":")),
                status, package["created_at"], now_iso() if imported_by else None,
                imported_by,
            ),
        )

    def get_binding(self, organization_id: str, task_type: str, source_task_id: str, tech_id: str) -> Optional[dict]:
        row = self.conn.execute(
            """
            SELECT * FROM tech_task_exchange_bindings
            WHERE organization_id = ? AND task_type = ?
              AND source_task_id = ? AND tech_user_id = ?
            """,
            (organization_id, task_type, source_task_id, tech_id),
        ).fetchone()
        return dict(row) if row else None

    def find_context_binding(
        self,
        organization_id: str,
        tech_id: str,
        *,
        source_lead_id: Optional[str] = None,
        source_customer_id: Optional[str] = None,
    ) -> Optional[dict]:
        if source_lead_id:
            clause, value = "source_lead_id", source_lead_id
        elif source_customer_id:
            clause, value = "source_customer_id", source_customer_id
        else:
            return None
        row = self.conn.execute(
            f"""
            SELECT * FROM tech_task_exchange_bindings
            WHERE organization_id = ? AND tech_user_id = ? AND {clause} = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (organization_id, tech_id, value),
        ).fetchone()
        return dict(row) if row else None

    def list_bindings_for_tech(self, organization_id: str, tech_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM tech_task_exchange_bindings
            WHERE organization_id = ? AND tech_user_id = ? AND is_active = 1
            ORDER BY updated_at, id
            """,
            (organization_id, tech_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def upsert_binding(self, data: dict) -> str:
        existing = self.get_binding(
            data["organization_id"], data["task_type"],
            data["source_task_id"], data["tech_user_id"],
        )
        timestamp = now_iso()
        if existing:
            self.conn.execute(
                """
                UPDATE tech_task_exchange_bindings SET
                    local_task_id = ?, source_lead_id = ?, local_lead_id = ?,
                    source_customer_id = ?, local_customer_id = ?, leader_user_id = ?,
                    source_row_version = ?, source_snapshot_json = ?,
                    source_package_id = ?, local_row_version_at_sync = ?,
                    last_exported_local_row_version = ?,
                    last_exported_result_snapshot_json = ?,
                    is_active = 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    data["local_task_id"], data["source_lead_id"], data["local_lead_id"],
                    data["source_customer_id"], data["local_customer_id"],
                    data["leader_user_id"], data["source_row_version"],
                    data["source_snapshot_json"], data["source_package_id"],
                    data["local_row_version_at_sync"],
                    existing["last_exported_local_row_version"]
                    if existing["local_task_id"] == data["local_task_id"] else None,
                    existing.get("last_exported_result_snapshot_json")
                    if existing["local_task_id"] == data["local_task_id"] else None,
                    timestamp, existing["id"],
                ),
            )
            return existing["id"]
        binding_id = generate_uuid()
        self.conn.execute(
            """
            INSERT INTO tech_task_exchange_bindings (
                id, organization_id, task_type, source_task_id, local_task_id,
                source_lead_id, local_lead_id, source_customer_id, local_customer_id,
                leader_user_id, tech_user_id, source_row_version, source_snapshot_json,
                source_package_id, local_row_version_at_sync,
                last_exported_local_row_version,
                last_exported_result_snapshot_json,
                is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1, ?, ?)
            """,
            (
                binding_id, data["organization_id"], data["task_type"],
                data["source_task_id"], data["local_task_id"], data["source_lead_id"],
                data["local_lead_id"], data["source_customer_id"],
                data["local_customer_id"], data["leader_user_id"], data["tech_user_id"],
                data["source_row_version"], data["source_snapshot_json"],
                data["source_package_id"], data["local_row_version_at_sync"],
                timestamp, timestamp,
            ),
        )
        return binding_id

    def mark_exported(
        self, binding_id: str, local_row_version: int, result_snapshot: dict
    ) -> None:
        self.conn.execute(
            """
            UPDATE tech_task_exchange_bindings
            SET last_exported_local_row_version = ?,
                last_exported_result_snapshot_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                local_row_version,
                json.dumps(result_snapshot, ensure_ascii=False, separators=(",", ":")),
                now_iso(),
                binding_id,
            ),
        )
