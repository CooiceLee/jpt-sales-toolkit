"""Atomic replacement transaction for single-device authorizations."""

from __future__ import annotations

from typing import Callable, Optional

from .base import now_iso


def replace_active_authorization(
    conn,
    current: Optional[dict],
    prepared: dict,
    reason: str,
    insert: Callable[[dict], None],
) -> str:
    """Deactivate the old authorization and insert its replacement atomically."""
    savepoint = "replace_device_authorization"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        if current:
            timestamp = now_iso()
            conn.execute(
                """
                UPDATE device_authorizations
                SET is_active = 0, deactivated_at = ?,
                    deactivation_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, reason, timestamp, current["id"]),
            )
        insert(prepared)
        if current:
            conn.execute(
                "UPDATE device_authorizations SET replaced_by_id = ? WHERE id = ?",
                (prepared["id"], current["id"]),
            )
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.rollback()
        raise
    conn.commit()
    return prepared["id"]
