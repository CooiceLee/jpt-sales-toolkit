"""Atomic customer merge orchestration."""

from __future__ import annotations

from typing import Optional

from ..coordinate_validation import validated_coordinate_payload
from ..repositories.base import ConflictError, now_iso
from ..repositories.customer_repository import CustomerRepository
from .customer_merge_contacts import merge_contacts
from .customer_merge_labels import merge_aliases, merge_domains
from .customer_merge_preview import CustomerMergePreview
from .customer_merge_verification import (
    assert_postconditions,
    build_result,
    guard_source_identity,
    write_audit,
)


class CustomerMergeService:
    def __init__(self, customer_repo: Optional[CustomerRepository] = None):
        self.customer_repo = customer_repo or CustomerRepository()
        self.conn = self.customer_repo.conn
        self.previewer = CustomerMergePreview(self.conn)

    def preview(
        self, source_id: str, target_id: str,
        source_version: Optional[int], target_version: Optional[int],
    ) -> dict:
        return self.previewer.build(source_id, target_id, source_version, target_version)

    def merge(
        self, source_id: str, target_id: str, actor_id: str,
        source_version: Optional[int], target_version: Optional[int],
    ) -> dict:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            preview = self.previewer.build(source_id, target_id, source_version, target_version)
            guard_source_identity(self.conn, preview)
            now = now_iso()
            leads = self._move_leads(source_id, target_id, actor_id, now)
            stops = self._move_stops(source_id, target_id, actor_id, now)
            contacts = merge_contacts(self.conn, source_id, target_id, now)
            domains = merge_domains(self.conn, source_id, target_id, now, actor_id)
            aliases = merge_aliases(
                self.conn, preview["source_customer"], preview["target_customer"], now, actor_id,
            )
            self._update_customers(preview, actor_id, now, source_version, target_version)
            assert_postconditions(self.conn, source_id, target_id, preview)
            result = build_result(preview, leads, stops, contacts, domains, aliases)
            audit_id = write_audit(self.conn, target_id, actor_id, preview, result, now)
            result["audit_id"] = audit_id
            self.conn.commit()
            return result
        except Exception:
            self.conn.rollback()
            raise

    def _move_leads(self, source_id: str, target_id: str, actor_id: str, now: str) -> int:
        cursor = self.conn.execute(
            """UPDATE leads SET customer_id = ?, updated_at = ?, updated_by = ?,
               row_version = row_version + 1 WHERE customer_id = ?""",
            (target_id, now, actor_id, source_id),
        )
        return cursor.rowcount

    def _move_stops(self, source_id: str, target_id: str, actor_id: str, now: str) -> int:
        cursor = self.conn.execute(
            """UPDATE trip_plan_stops SET customer_id = ?, updated_at = ?, updated_by = ?,
               row_version = row_version + 1 WHERE customer_id = ?""",
            (target_id, now, actor_id, source_id),
        )
        return cursor.rowcount

    def _update_customers(
        self, preview: dict, actor_id: str, now: str,
        source_version: int, target_version: int,
    ) -> None:
        updates = validated_coordinate_payload(preview["field_updates"])
        assignments = ["updated_at = ?", "updated_by = ?", "row_version = row_version + 1"]
        params = [now, actor_id]
        for field, value in updates.items():
            assignments.append(f"{field} = ?")
            params.append(value)
        params.extend([preview["target_customer"]["id"], target_version])
        target = self.conn.execute(
            f"UPDATE customers SET {', '.join(assignments)} WHERE id = ? AND row_version = ?",
            params,
        )
        source = self.conn.execute(
            """UPDATE customers SET archived_at = ?, updated_at = ?, updated_by = ?,
               row_version = row_version + 1 WHERE id = ? AND row_version = ?""",
            (now, now, actor_id, preview["source_customer"]["id"], source_version),
        )
        if target.rowcount != 1 or source.rowcount != 1:
            raise ConflictError(0, 0, {"message": "Customer changed during merge"})
