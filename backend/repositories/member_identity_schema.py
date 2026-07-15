"""Runtime schema safeguards for stable member identities."""

from __future__ import annotations

import sqlite3
import unicodedata


ALIAS_DDL = """
CREATE TABLE IF NOT EXISTS member_import_aliases (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    source_system TEXT NOT NULL COLLATE NOCASE,
    source_name TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES users(id),
    UNIQUE(organization_id, source_system, normalized_alias)
)
"""


def normalize_identity(value: str) -> str:
    """Build a Unicode-aware comparison key without changing stored names."""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).casefold()


def _assert_username_uniqueness(conn) -> None:
    seen: dict[str, tuple[str, str]] = {}
    collisions: list[tuple[tuple[str, str], tuple[str, str]]] = []
    for user_id, username in conn.execute("SELECT id, username FROM users").fetchall():
        key = normalize_identity(username)
        previous = seen.get(key)
        if previous and previous[0] != user_id:
            collisions.append((previous, (user_id, username)))
        else:
            seen[key] = (user_id, username)
    if not collisions:
        return
    details = "; ".join(
        f"{left[0]} ({left[1]!r}) vs {right[0]} ({right[1]!r})"
        for left, right in collisions
    )
    raise RuntimeError(
        "Case-insensitive username collisions require explicit account repair; "
        f"no user IDs or foreign keys were changed: {details}"
    )


def apply_member_identity_schema(conn) -> None:
    """Add identity indexes/tables while preserving every existing user ID."""
    _assert_username_uniqueness(conn)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase "
            "ON users(username COLLATE NOCASE)"
        )
    except sqlite3.IntegrityError as exc:
        raise RuntimeError(
            "Unable to enforce case-insensitive usernames; no user IDs were changed"
        ) from exc
    conn.execute(ALIAS_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_member_import_alias_user "
        "ON member_import_aliases(user_id, is_active)"
    )
