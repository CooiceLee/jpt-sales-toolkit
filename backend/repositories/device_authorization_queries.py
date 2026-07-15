"""Read operations for device authorization repositories."""

from __future__ import annotations

from typing import Optional

from .base import DEFAULT_ORGANIZATION_ID


class DeviceAuthorizationQueries:
    """Queries shared by the device authorization repository."""

    def get_active_for_user(
        self,
        user_id: str,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ) -> Optional[dict]:
        row = self.conn.execute(
            """
            SELECT * FROM device_authorizations
            WHERE organization_id = ? AND user_id = ? AND is_active = 1
            """,
            (organization_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def get_active_for_device(
        self,
        device_fingerprint_hash: str,
        organization_id: str = DEFAULT_ORGANIZATION_ID,
    ) -> Optional[dict]:
        """Return only a package activated on the queried local device."""
        row = self.conn.execute(
            """
            SELECT * FROM device_authorizations
            WHERE organization_id = ? AND device_fingerprint_hash = ?
              AND is_active = 1 AND activation_state = 'activated'
            """,
            (organization_id, device_fingerprint_hash),
        ).fetchone()
        return dict(row) if row else None

    def _get_reserved_device(
        self,
        device_fingerprint_hash: str,
        organization_id: str,
    ) -> Optional[dict]:
        """Return an active issued or activated row used by the unique-device guard."""
        row = self.conn.execute(
            """
            SELECT * FROM device_authorizations
            WHERE organization_id = ? AND device_fingerprint_hash = ?
              AND is_active = 1
            """,
            (organization_id, device_fingerprint_hash),
        ).fetchone()
        return dict(row) if row else None

    def list_for_user(self, user_id: str, include_inactive: bool = True) -> list[dict]:
        sql = "SELECT * FROM device_authorizations WHERE user_id = ?"
        if not include_inactive:
            sql += " AND is_active = 1"
        rows = self.conn.execute(sql + " ORDER BY issued_at DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]
