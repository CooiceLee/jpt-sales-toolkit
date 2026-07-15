"""Atomic SQLite schema migration for the authorization data layer."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .authorization_schema_definitions import (
    AUTHORIZATION_DDL,
    AUTHORIZATION_MIGRATIONS,
    AUTHORIZATION_SCHEMA_NAME,
    AUTHORIZATION_SCHEMA_VERSION,
    DEFAULT_ORGANIZATION_ID,
)
from .authorization_schema_device import apply_activation_state_migration
from .authorization_schema_legacy import (
    backfill_legacy_credentials,
    ensure_default_organization,
)


def _validate_migration_registry(conn: sqlite3.Connection) -> None:
    for version, name in AUTHORIZATION_MIGRATIONS:
        existing = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        if existing and existing[0] != name:
            raise RuntimeError(
                f"Schema migration version {version} already belongs to {existing[0]}"
            )


def _record_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) "
        "VALUES (?, ?, ?)",
        (version, name, datetime.utcnow().isoformat()),
    )


def apply_authorization_schema_migration(conn: sqlite3.Connection) -> None:
    """Apply authorization migrations atomically and preserve existing rows."""
    savepoint = "authorization_data_layer_v2"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        for statement in AUTHORIZATION_DDL:
            conn.execute(statement)
        _validate_migration_registry(conn)
        ensure_default_organization(conn)
        backfill_legacy_credentials(conn)
        _record_migration(conn, *AUTHORIZATION_MIGRATIONS[0])
        apply_activation_state_migration(conn)
        _record_migration(conn, *AUTHORIZATION_MIGRATIONS[1])
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise


__all__ = [
    "AUTHORIZATION_DDL",
    "AUTHORIZATION_MIGRATIONS",
    "AUTHORIZATION_SCHEMA_NAME",
    "AUTHORIZATION_SCHEMA_VERSION",
    "DEFAULT_ORGANIZATION_ID",
    "apply_authorization_schema_migration",
]
