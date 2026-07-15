"""Append-only authorization lifecycle event repository."""

from __future__ import annotations

from .authorization_common import json_text
from .base import BaseRepository, DEFAULT_ORGANIZATION_ID, generate_uuid, now_iso


class AuthorizationEventRepository(BaseRepository):
    """Record and query immutable authorization lifecycle events."""

    table_name = "authorization_events"

    def delete_by_id(self, entity_id: str) -> bool:
        raise NotImplementedError("Authorization events are append-only")

    def create(self, data: dict) -> str:
        if not data.get("event_type"):
            raise ValueError("Authorization event type is required")
        event_id = data.get("id") or generate_uuid()
        insert_data = {
            "id": event_id,
            "organization_id": data.get("organization_id", DEFAULT_ORGANIZATION_ID),
            "user_id": data.get("user_id"),
            "device_authorization_id": data.get("device_authorization_id"),
            "actor_user_id": data.get("actor_user_id"),
            "event_type": data["event_type"],
            "event_data_json": json_text(data.get("event_data_json")),
            "created_at": data.get("created_at") or now_iso(),
        }
        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return event_id

    def list_for_user(self, user_id: str, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM authorization_events
            WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_for_authorization(self, authorization_id: str, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM authorization_events
            WHERE device_authorization_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (authorization_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_recent(
        self,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
        limit: int = 100,
    ) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM authorization_events
            WHERE organization_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (organization_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
