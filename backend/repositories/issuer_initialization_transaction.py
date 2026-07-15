"""Atomic database commit for initial Leader and issuer trust."""

from __future__ import annotations

from typing import Optional

from .authorization_event_store import insert_authorization_event as _insert_event
from .base import now_iso
from .issuer_bootstrap_store import (
    insert_bootstrap_member as _insert_bootstrap_member,
    replace_self_authorization as _replace_self_authorization,
)


def persist_initialized_issuer(
    conn,
    package: dict,
    key_info: dict,
    actor_id: str,
    bootstrap_member: Optional[dict] = None,
    password_hash: Optional[str] = None,
) -> str:
    """Persist the issuer and its initial Leader authorization atomically."""
    payload = package["payload"]
    organization_id = payload["organization"]["id"]
    timestamp = now_iso()
    savepoint = "persist_initialized_issuer"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        current = conn.execute(
            "SELECT signing_public_key FROM organizations WHERE id = ?", (organization_id,)
        ).fetchone()
        if not current or current[0]:
            raise ValueError("Authorization issuer is already initialized")
        if bootstrap_member:
            _insert_bootstrap_member(
                conn, organization_id, bootstrap_member, password_hash or "", timestamp
            )
        _replace_self_authorization(conn, package, actor_id, timestamp)
        conn.execute(
            """
            UPDATE organizations
            SET signing_key_id = ?, signing_public_key = ?, updated_at = ?
            WHERE id = ?
            """,
            (key_info["key_id"], key_info["public_key"], timestamp, organization_id),
        )
        if bootstrap_member:
            _insert_event(
                conn, organization_id, actor_id, None, actor_id,
                "member_created", {"role": "leader"}, timestamp,
            )
        _insert_event(
            conn, organization_id, actor_id, payload["package_id"], actor_id,
            "issuer_initialized", {"key_id": key_info["key_id"]}, timestamp,
        )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.rollback()
        raise
    return payload["package_id"]
