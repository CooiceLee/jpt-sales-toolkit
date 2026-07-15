"""Organization, directory and credential writes during offline activation."""

from __future__ import annotations

from uuid import uuid4

from .base import now_iso


def write_trust(conn, organization: dict, verified: dict, timestamp: str) -> None:
    current = conn.execute(
        "SELECT signing_public_key FROM organizations WHERE id = ?",
        (organization["id"],),
    ).fetchone()
    if not current:
        raise ValueError("Authorization organization is not installed")
    if current[0] and current[0] != verified["public_key"]:
        raise ValueError("Authorization issuer does not match the trusted organization")
    conn.execute(
        """
        UPDATE organizations
        SET name = ?, slug = ?, signing_key_id = ?, signing_public_key = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            organization["name"], organization["slug"], verified["key_id"],
            verified["public_key"], timestamp, organization["id"],
        ),
    )


def write_directory(conn, directory: list, member_id: str, password_hash: str) -> None:
    timestamp = now_iso()
    for entry in directory:
        initial_hash = password_hash if entry["id"] == member_id else "!directory-only"
        conn.execute(
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
                entry["id"], entry["username"], initial_hash, entry["display_name"],
                entry["role"], entry.get("region"), int(entry["is_active"]), timestamp,
            ),
        )
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, member_id))


def write_credential(
    conn,
    organization_id: str,
    user_id: str,
    password_hash: str,
    timestamp: str,
) -> None:
    conn.execute(
        """
        INSERT INTO user_credentials (
            id, organization_id, user_id, password_hash, password_scheme,
            must_change_password, is_active, created_at, updated_at, password_changed_at
        ) VALUES (?, ?, ?, ?, 'pbkdf2_sha256', 0, 1, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            password_hash = excluded.password_hash,
            password_scheme = 'pbkdf2_sha256',
            must_change_password = 0,
            is_active = 1,
            updated_at = excluded.updated_at,
            password_changed_at = excluded.password_changed_at,
            deactivated_at = NULL
        """,
        (
            str(uuid4()), organization_id, user_id, password_hash,
            timestamp, timestamp, timestamp,
        ),
    )
