"""Connection-scoped authorization audit writes for larger transactions."""

from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4


def insert_authorization_event(
    conn,
    organization_id: str,
    user_id: str,
    authorization_id: Optional[str],
    actor_id: str,
    event_type: str,
    details: dict,
    timestamp: str,
) -> None:
    """Insert an audit event without committing the caller's transaction."""
    conn.execute(
        """
        INSERT INTO authorization_events (
            id, organization_id, user_id, device_authorization_id,
            actor_user_id, event_type, event_data_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()), organization_id, user_id, authorization_id,
            actor_id, event_type, json.dumps(details), timestamp,
        ),
    )
