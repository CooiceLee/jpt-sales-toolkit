"""
User repository - database operations for users table.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class UserRepository(BaseRepository):
    """Repository for users table."""

    table_name = "users"
    _profile_fields = {"username", "display_name", "role", "region"}

    def get_by_username(self, username: str) -> Optional[dict]:
        """Get user by username."""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def _ensure_username_available(self, username: str, excluded_id: Optional[str] = None) -> None:
        """Enforce Unicode-aware case-insensitive member identity uniqueness."""
        normalized = username.casefold()
        for member in self.list_all():
            if member["id"] != excluded_id and member["username"].casefold() == normalized:
                raise ValueError("Username already exists")

    def list_all(self) -> list[dict]:
        """List all users (for bootstrap check)."""
        cursor = self.conn.execute("SELECT * FROM users")
        return [dict(row) for row in cursor.fetchall()]

    def list_active(self, role: Optional[str] = None) -> list[dict]:
        """List active users, optionally filtered by role."""
        sql = "SELECT * FROM users WHERE is_active = 1"
        params: list = []

        if role:
            sql += " AND role = ?"
            params.append(role)

        sql += " ORDER BY display_name"
        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def create(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        region: Optional[str] = None,
    ) -> str:
        """Create new user. Returns user ID."""
        self._ensure_username_available(username)
        user_id = generate_uuid()
        data = {
            "id": user_id,
            "username": username,
            "password_hash": password_hash,
            "display_name": display_name,
            "role": role,
            "region": region,
            "is_active": 1,
            "created_at": now_iso(),
        }
        sql, params = self._build_insert(data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return user_id

    def update_last_login(self, user_id: str) -> None:
        """Update last_login_at timestamp."""
        self.conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now_iso(), user_id),
        )
        self.conn.commit()

    def deactivate(self, user_id: str) -> bool:
        """Deactivate user (soft delete)."""
        cursor = self.conn.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?",
            (user_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def reactivate(self, user_id: str) -> bool:
        """Reactivate a previously deactivated user."""
        cursor = self.conn.execute(
            "UPDATE users SET is_active = 1 WHERE id = ? AND is_active = 0",
            (user_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_profile(self, user_id: str, data: dict) -> Optional[dict]:
        """Update the centrally managed member identity fields."""
        unknown = set(data) - self._profile_fields
        if unknown:
            raise ValueError(f"Unsupported user fields: {sorted(unknown)}")
        if data.get("role") and data["role"] not in {"leader", "sales", "tech"}:
            raise ValueError(f"Unsupported role: {data['role']}")
        if "username" in data:
            self._ensure_username_available(data["username"], user_id)
        if not data:
            return self.get_by_id(user_id)
        sql, params = self._build_update(user_id, data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return self.get_by_id(user_id)

    def upsert_directory_member(self, data: dict, password_hash: str) -> dict:
        """Synchronize a signed team-directory member by stable user ID."""
        if data.get("role") not in {"leader", "sales", "tech"}:
            raise ValueError(f"Unsupported role: {data.get('role')}")
        self._ensure_username_available(data["username"], data["id"])
        self.conn.execute(
            """
            INSERT INTO users (
                id, username, password_hash, display_name, role, region,
                is_active, created_at, last_login_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                role = excluded.role,
                region = excluded.region,
                is_active = excluded.is_active
            """,
            (
                data["id"], data["username"], password_hash,
                data.get("display_name") or data["username"], data["role"],
                data.get("region"), int(bool(data.get("is_active", True))), now_iso(),
            ),
        )
        self.conn.commit()
        return self.get_by_id(data["id"])

    def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update user password hash."""
        cursor = self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        scheme = "pbkdf2_sha256" if password_hash.startswith("pbkdf2_sha256$") else "legacy_sha256"
        self.conn.execute(
            """
            UPDATE user_credentials
            SET password_hash = ?, password_scheme = ?, must_change_password = 0,
                is_active = 1, updated_at = ?, password_changed_at = ?, deactivated_at = NULL
            WHERE user_id = ?
            """,
            (password_hash, scheme, now_iso(), now_iso(), user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0
