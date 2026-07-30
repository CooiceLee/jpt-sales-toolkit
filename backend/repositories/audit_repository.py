"""
Audit repository - database operations for audit_logs table.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class AuditRepository(BaseRepository):
    """Repository for audit_logs table."""

    table_name = "audit_logs"

    def log(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_id: Optional[str] = None,
        before_json: Optional[str] = None,
        after_json: Optional[str] = None,
        *,
        commit: bool = True,
    ) -> str:
        """Create audit log entry. Returns log ID."""
        log_id = generate_uuid()

        self.conn.execute(
            """
            INSERT INTO audit_logs (
                id, entity_type, entity_id, actor_id, event_type,
                before_json, after_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                entity_type,
                entity_id,
                actor_id,
                event_type,
                before_json,
                after_json,
                now_iso(),
            ),
        )
        if commit:
            self.conn.commit()
        return log_id

    def list_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List audit logs for an entity."""
        cursor = self.conn.execute(
            """
            SELECT a.*, u.display_name as actor_name
            FROM audit_logs a
            LEFT JOIN users u ON a.actor_id = u.id
            WHERE a.entity_type = ? AND a.entity_id = ?
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (entity_type, entity_id, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_by_actor(
        self,
        actor_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List audit logs by actor."""
        cursor = self.conn.execute(
            """
            SELECT * FROM audit_logs
            WHERE actor_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (actor_id, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_recent(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """List recent audit logs."""
        sql = """
            SELECT a.*, u.display_name as actor_name
            FROM audit_logs a
            LEFT JOIN users u ON a.actor_id = u.id
        """
        params: list = []

        if entity_type:
            sql += " WHERE a.entity_type = ?"
            params.append(entity_type)

        sql += " ORDER BY a.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
