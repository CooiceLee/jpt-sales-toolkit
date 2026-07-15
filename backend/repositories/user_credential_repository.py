"""Password credential repository separated from business user profiles."""

from __future__ import annotations

from typing import Optional

from .authorization_common import apply_update
from .base import BaseRepository, DEFAULT_ORGANIZATION_ID, generate_uuid, now_iso


class UserCredentialRepository(BaseRepository):
    """Manage password hashes without mutating the legacy users table."""

    table_name = "user_credentials"
    _updatable = {"password_hash", "password_scheme", "must_change_password"}

    def get_by_user_id(self, user_id: str, active_only: bool = False) -> Optional[dict]:
        sql = "SELECT * FROM user_credentials WHERE user_id = ?"
        if active_only:
            sql += " AND is_active = 1"
        row = self.conn.execute(sql, (user_id,)).fetchone()
        return dict(row) if row else None

    def list_by_organization(
        self,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
        include_inactive: bool = False,
    ) -> list[dict]:
        sql = """
            SELECT id, organization_id, user_id, password_scheme,
                   must_change_password, is_active, created_at, updated_at,
                   password_changed_at, deactivated_at
            FROM user_credentials WHERE organization_id = ?
        """
        if not include_inactive:
            sql += " AND is_active = 1"
        rows = self.conn.execute(sql + " ORDER BY created_at", (organization_id,)).fetchall()
        return [dict(row) for row in rows]

    def create(self, data: dict) -> str:
        required = {"user_id", "password_hash", "password_scheme"}
        missing = sorted(field for field in required if not data.get(field))
        if missing:
            raise ValueError(f"Missing credential fields: {missing}")

        timestamp = now_iso()
        credential_id = data.get("id") or generate_uuid()
        insert_data = {
            "id": credential_id,
            "organization_id": data.get("organization_id", DEFAULT_ORGANIZATION_ID),
            "user_id": data["user_id"],
            "password_hash": data["password_hash"],
            "password_scheme": data["password_scheme"],
            "must_change_password": int(bool(data.get("must_change_password", False))),
            "is_active": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
            "password_changed_at": data.get("password_changed_at"),
        }
        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return credential_id

    def update(self, credential_id: str, data: dict) -> bool:
        unknown = set(data) - self._updatable
        if unknown:
            raise ValueError(f"Unsupported credential fields: {sorted(unknown)}")
        update_data = dict(data)
        if "must_change_password" in update_data:
            update_data["must_change_password"] = int(bool(update_data["must_change_password"]))
        if "password_hash" in update_data:
            update_data["password_changed_at"] = now_iso()
        update_data["updated_at"] = now_iso()
        return apply_update(self, credential_id, update_data)

    def deactivate(self, credential_id: str) -> bool:
        timestamp = now_iso()
        return apply_update(
            self,
            credential_id,
            {"is_active": 0, "deactivated_at": timestamp, "updated_at": timestamp},
        )

    def reactivate(self, credential_id: str) -> bool:
        return apply_update(
            self,
            credential_id,
            {"is_active": 1, "deactivated_at": None, "updated_at": now_iso()},
        )
