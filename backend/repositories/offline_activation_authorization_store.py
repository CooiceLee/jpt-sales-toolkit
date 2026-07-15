"""Device-authorization persistence during offline activation."""

from __future__ import annotations

import json


def write_authorization(conn, package: dict, payload: dict, member: dict, timestamp: str) -> None:
    signature = package["signature"]
    existing = conn.execute(
        "SELECT * FROM device_authorizations WHERE id = ?", (payload["package_id"],)
    ).fetchone()
    if existing:
        validate_existing(dict(existing), package, payload, member)
        if not existing["is_active"]:
            raise ValueError("Authorization package has been replaced or deactivated")
        conn.execute(
            "UPDATE device_authorizations "
            "SET activation_state = 'activated', updated_at = ? WHERE id = ?",
            (timestamp, payload["package_id"]),
        )
        return

    old_rows = conn.execute(
        """
        SELECT id FROM device_authorizations
        WHERE organization_id = ? AND activation_state = 'activated' AND is_active = 1
        """,
        (payload["organization"]["id"],),
    ).fetchall()
    for old_row in old_rows:
        conn.execute(
            """
            UPDATE device_authorizations
            SET is_active = 0, deactivated_at = ?, updated_at = ?,
                deactivation_reason = 'local_authorization_replaced'
            WHERE id = ?
            """,
            (timestamp, timestamp, old_row["id"]),
        )
    conn.execute(
        """
        INSERT INTO device_authorizations (
            id, organization_id, user_id, device_fingerprint_hash, role,
            activation_state, authorization_version, payload_json, signature,
            signature_algorithm, signing_key_id, issued_at, valid_from, expires_at,
            is_active, created_by, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'activated', ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            payload["package_id"], payload["organization"]["id"], member["id"],
            payload["device"]["id"], member["role"], payload["authorization_version"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            signature["value"], signature["algorithm"], signature["key_id"],
            payload["issued_at"], payload["valid_from"], payload["expires_at"],
            member["id"], timestamp,
        ),
    )
    for old_row in old_rows:
        conn.execute(
            "UPDATE device_authorizations SET replaced_by_id = ? WHERE id = ?",
            (payload["package_id"], old_row["id"]),
        )


def validate_existing(existing: dict, package: dict, payload: dict, member: dict) -> None:
    signature = package["signature"]
    matches = (
        json.loads(existing["payload_json"]) == payload
        and existing["signature"] == signature["value"]
        and existing["signature_algorithm"] == signature["algorithm"]
        and existing["signing_key_id"] == signature["key_id"]
        and existing["user_id"] == member["id"]
        and existing["device_fingerprint_hash"] == payload["device"]["id"]
        and existing["role"] == member["role"]
    )
    if not matches:
        raise ValueError("Authorization package ID conflicts with stored data")
