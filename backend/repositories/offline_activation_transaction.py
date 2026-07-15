"""Atomic persistence for a verified offline authorization package."""

from __future__ import annotations

from .authorization_event_store import insert_authorization_event
from .base import now_iso
from .offline_activation_authorization_store import (
    validate_existing as _validate_existing,
    write_authorization as _write_authorization,
)
from .offline_activation_member_store import (
    write_credential as _write_credential,
    write_directory as _write_directory,
    write_trust as _write_trust,
)


def activate_verified_package(conn, package: dict, verified: dict, password_hash: str) -> str:
    """Commit trust, directory, local credential, authorization and audit together."""
    payload = verified["payload"]
    member = payload["member"]
    organization = payload["organization"]
    authorization_id = payload["package_id"]
    timestamp = now_iso()
    savepoint = "activate_verified_authorization"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        _write_trust(conn, organization, verified, timestamp)
        _write_directory(conn, payload["team_directory"], member["id"], password_hash)
        _write_authorization(conn, package, payload, member, timestamp)
        _write_credential(conn, organization["id"], member["id"], password_hash, timestamp)
        insert_authorization_event(
            conn,
            organization["id"],
            member["id"],
            authorization_id,
            member["id"],
            "authorization_activated",
            {"package_id": authorization_id},
            timestamp,
        )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.rollback()
        raise
    return authorization_id
