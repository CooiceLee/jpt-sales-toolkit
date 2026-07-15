"""Member and self-authorization writes for initial issuer setup."""

from __future__ import annotations

import json
from uuid import uuid4


def insert_bootstrap_member(
    conn,
    organization_id: str,
    member: dict,
    password_hash: str,
    timestamp: str,
) -> None:
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        raise ValueError("First-run setup is no longer available")
    conn.execute(
        """
        INSERT INTO users (
            id, username, password_hash, display_name, role, region, is_active, created_at
        ) VALUES (?, ?, ?, ?, 'leader', ?, 1, ?)
        """,
        (
            member["id"], member["username"], password_hash,
            member["display_name"], member.get("region"), timestamp,
        ),
    )
    conn.execute(
        """
        INSERT INTO user_credentials (
            id, organization_id, user_id, password_hash, password_scheme,
            must_change_password, is_active, created_at, updated_at, password_changed_at
        ) VALUES (?, ?, ?, ?, 'pbkdf2_sha256', 0, 1, ?, ?, ?)
        """,
        (
            str(uuid4()), organization_id, member["id"], password_hash,
            timestamp, timestamp, timestamp,
        ),
    )


def replace_self_authorization(conn, package: dict, actor_id: str, timestamp: str) -> None:
    payload = package["payload"]
    signature = package["signature"]
    previous = conn.execute(
        """
        SELECT id FROM device_authorizations
        WHERE organization_id = ? AND user_id = ? AND is_active = 1
        """,
        (payload["organization"]["id"], actor_id),
    ).fetchone()
    if previous:
        conn.execute(
            """
            UPDATE device_authorizations
            SET is_active = 0, deactivated_at = ?, updated_at = ?,
                deactivation_reason = 'issuer_initialized'
            WHERE id = ?
            """,
            (timestamp, timestamp, previous["id"]),
        )
    conn.execute(
        """
        INSERT INTO device_authorizations (
            id, organization_id, user_id, device_fingerprint_hash, role,
            activation_state, authorization_version, payload_json, signature,
            signature_algorithm, signing_key_id, issued_at, valid_from, expires_at,
            is_active, created_by, updated_at
        ) VALUES (?, ?, ?, ?, 'leader', 'activated', ?, ?, ?, 'ed25519', ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            payload["package_id"], payload["organization"]["id"], actor_id,
            payload["device"]["id"], payload["authorization_version"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            signature["value"], signature["key_id"], payload["issued_at"],
            payload["valid_from"], payload["expires_at"], actor_id, timestamp,
        ),
    )
    if previous:
        conn.execute(
            "UPDATE device_authorizations SET replaced_by_id = ? WHERE id = ?",
            (payload["package_id"], previous["id"]),
        )
