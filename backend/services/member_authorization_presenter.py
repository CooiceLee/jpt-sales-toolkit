"""Response presenters for authorization-member APIs."""

from __future__ import annotations

import json
from typing import Optional


def present_member(user: Optional[dict], authorizations) -> dict:
    if not user:
        raise ValueError("Member not found")
    history = authorizations.list_for_user(user["id"])
    active = next((item for item in history if item["is_active"]), None)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "region": user.get("region"),
        "is_active": bool(user["is_active"]),
        "authorization_count": len(history),
        "active_device": active["device_fingerprint_hash"][:12] if active else None,
        "expires_at": active["expires_at"] if active else None,
    }


def present_event(event: dict) -> dict:
    try:
        details = json.loads(event.get("event_data_json") or "{}")
    except json.JSONDecodeError:
        details = {}
    return {
        "id": event["id"],
        "event_type": event["event_type"],
        "user_id": event.get("user_id"),
        "device_id": event.get("device_authorization_id"),
        "actor_id": event.get("actor_user_id"),
        "details": details,
        "created_at": event["created_at"],
    }
