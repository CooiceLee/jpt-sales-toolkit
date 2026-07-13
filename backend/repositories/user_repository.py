"""
User repository - database operations for users table.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class UserRepository(BaseRepository):
    """Repository for users table."""

    table_name = "users"

    def get_by_username(self, username: str) -> Optional[dict]:
        """Get user by username."""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

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

    def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update user password hash."""
        cursor = self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0
