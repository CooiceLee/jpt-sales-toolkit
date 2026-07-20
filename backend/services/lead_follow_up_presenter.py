"""Stable public shape for a lead's latest formal follow-up."""

from __future__ import annotations

import json
from typing import Optional

PAYLOAD_FIELDS = (
    "method",
    "content",
    "status",
    "response_date",
    "customer_feedback",
    "next_action",
    "next_action_date",
    "occurred_at_raw",
)


def apply_latest_follow_up(lead: dict, activity: Optional[dict]) -> None:
    """Mutate a lead with whitelisted latest-follow-up fields."""
    if not activity:
        lead["latest_follow_up_at"] = None
        lead["latest_follow_up_summary"] = None
        lead["latest_follow_up"] = None
        return

    payload = _payload(activity.get("payload_json"))
    summary = activity.get("summary")
    view = {
        "id": activity.get("id"),
        "summary": summary,
        "created_at": activity.get("created_at"),
        "actor_id": activity.get("actor_id"),
        "actor_name": activity.get("actor_name"),
        **{field: payload.get(field) for field in PAYLOAD_FIELDS},
    }
    view["content"] = view["content"] or summary
    lead["latest_follow_up_at"] = view["created_at"]
    lead["latest_follow_up_summary"] = summary
    lead["latest_follow_up"] = view


def _payload(raw_value) -> dict:
    try:
        value = json.loads(raw_value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
