"""Device authorization migration helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime


def _column_exists(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    return any(
        row[1] == column_name
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    )


def apply_activation_state_migration(conn: sqlite3.Connection) -> None:
    """Separate an issued package from an authorization activated on this device."""
    if not _column_exists(conn, "device_authorizations", "activation_state"):
        conn.execute(
            "ALTER TABLE device_authorizations ADD COLUMN activation_state "
            "TEXT NOT NULL DEFAULT 'issued' CHECK ("
            "activation_state IN ('issued', 'activated'))"
        )
    resolve_active_device_duplicates(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_device_auth_active_device "
        "ON device_authorizations(organization_id, device_fingerprint_hash) "
        "WHERE is_active = 1"
    )


def resolve_active_device_duplicates(conn: sqlite3.Connection) -> None:
    """Preserve v1 rows while retaining only the newest active device reservation."""
    duplicates = conn.execute(
        """
        SELECT organization_id, device_fingerprint_hash
        FROM device_authorizations
        WHERE is_active = 1
        GROUP BY organization_id, device_fingerprint_hash
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    timestamp = datetime.utcnow().isoformat()
    for organization_id, fingerprint in duplicates:
        rows = conn.execute(
            """
            SELECT id FROM device_authorizations
            WHERE organization_id = ? AND device_fingerprint_hash = ?
              AND is_active = 1
            ORDER BY issued_at DESC, id DESC
            """,
            (organization_id, fingerprint),
        ).fetchall()
        replacement_id = rows[0][0]
        for (authorization_id,) in rows[1:]:
            conn.execute(
                """
                UPDATE device_authorizations
                SET is_active = 0, deactivated_at = ?, updated_at = ?,
                    deactivation_reason = 'migration_device_conflict',
                    replaced_by_id = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, replacement_id, authorization_id),
            )
