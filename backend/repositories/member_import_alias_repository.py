"""Persistence for Leader-approved legacy member aliases."""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class MemberImportAliasRepository(BaseRepository):
    table_name = "member_import_aliases"
    _updatable = {"source_system", "source_name", "normalized_alias", "user_id", "is_active"}

    def create(
        self,
        organization_id: str,
        source_system: str,
        source_name: str,
        normalized_alias: str,
        user_id: str,
        actor_id: str,
    ) -> dict:
        timestamp = now_iso()
        data = {
            "id": generate_uuid(),
            "organization_id": organization_id,
            "source_system": source_system,
            "source_name": source_name,
            "normalized_alias": normalized_alias,
            "user_id": user_id,
            "is_active": 1,
            "created_at": timestamp,
            "created_by": actor_id,
            "updated_at": timestamp,
            "updated_by": actor_id,
        }
        sql, params = self._build_insert(data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return self.get_by_id(data["id"])

    def list_for_organization(
        self,
        organization_id: str,
        source_system: Optional[str] = None,
        include_inactive: bool = False,
    ) -> list[dict]:
        sql = """
            SELECT a.*, u.username, u.display_name, u.role,
                   u.is_active AS member_is_active
            FROM member_import_aliases a
            JOIN users u ON u.id = a.user_id
            WHERE a.organization_id = ?
        """
        params: list = [organization_id]
        if source_system:
            sql += " AND a.source_system = ?"
            params.append(source_system)
        if not include_inactive:
            sql += " AND a.is_active = 1"
        rows = self.conn.execute(sql + " ORDER BY a.source_system, a.source_name", params)
        return [dict(row) for row in rows.fetchall()]

    def find_active(
        self,
        organization_id: str,
        source_system: str,
        normalized_alias: str,
    ) -> Optional[dict]:
        row = self.conn.execute(
            """
            SELECT * FROM member_import_aliases
            WHERE organization_id = ? AND source_system = ?
              AND normalized_alias = ? AND is_active = 1
            """,
            (organization_id, source_system, normalized_alias),
        ).fetchone()
        return dict(row) if row else None

    def update(self, alias_id: str, changes: dict, actor_id: str) -> dict:
        unknown = set(changes) - self._updatable
        if unknown:
            raise ValueError(f"Unsupported alias fields: {sorted(unknown)}")
        if not self.get_by_id(alias_id):
            raise ValueError("Member alias not found")
        update_data = {**changes, "updated_at": now_iso(), "updated_by": actor_id}
        sql, params = self._build_update(alias_id, update_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return self.get_by_id(alias_id)

    def delete(self, alias_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM member_import_aliases WHERE id = ?", (alias_id,))
        self.conn.commit()
        return cursor.rowcount > 0
