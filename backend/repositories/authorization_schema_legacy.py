"""Default-organization and legacy credential migration helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from .authorization_schema_definitions import DEFAULT_ORGANIZATION_ID


def ensure_default_organization(conn: sqlite3.Connection) -> None:
    timestamp = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO organizations (
            id, name, slug, authorization_provider,
            authorization_duration_days, is_active, created_at, updated_at
        ) VALUES (?, 'JPT Local Organization', 'jpt-local', 'offline', 90, 1, ?, ?)
        """,
        (DEFAULT_ORGANIZATION_ID, timestamp, timestamp),
    )
    exists = conn.execute(
        "SELECT 1 FROM organizations WHERE id = ?", (DEFAULT_ORGANIZATION_ID,)
    ).fetchone()
    if not exists:
        raise RuntimeError("Unable to create the default authorization organization")


def backfill_legacy_credentials(conn: sqlite3.Connection) -> None:
    users_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    if not users_table:
        return
    users = conn.execute(
        "SELECT id, password_hash, is_active, created_at FROM users "
        "WHERE password_hash IS NOT NULL"
    ).fetchall()
    timestamp = datetime.utcnow().isoformat()
    for user_id, password_hash, is_active, created_at in users:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_credentials (
                id, organization_id, user_id, password_hash, password_scheme,
                must_change_password, is_active, created_at, updated_at,
                password_changed_at, deactivated_at
            ) VALUES (?, ?, ?, ?, 'legacy_sha256', 1, ?, ?, ?, NULL, ?)
            """,
            (
                str(uuid4()),
                DEFAULT_ORGANIZATION_ID,
                user_id,
                password_hash,
                int(bool(is_active)),
                created_at or timestamp,
                timestamp,
                None if is_active else timestamp,
            ),
        )
